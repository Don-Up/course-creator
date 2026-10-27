"""Behaviour tests of the chapter and workspace editor.

Two people can open the same chapter at the same time.  The editor
therefore hands out the fingerprint of the content it read and refuses a
save whose fingerprint is out of date: the second one to save is told to
refresh and compare instead of quietly overwriting the first one's work.

The tests therefore watch three things: the fingerprint that comes back
from a read, the status code a save is answered with, and what is on the
disk afterwards.  Every test points the courses root at a temporary
directory, so a test never writes into the repository's own `courses/`
folder.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.courses import chapters
from app.courses.common import content_hash
from app.db import initialize_database, row_to_dict
from app.main import app

COURSE_SLUG = "test-course"
ORIGINAL = "# 第一章\n\n原来的正文。\n"
UPDATED = "# 第一章\n\n改过的正文。\n"
EMPTY_HASH = content_hash("")

VALID_BODY: dict[str, object] = {
    "title": "测试课程",
    "slug": COURSE_SLUG,
    "audience": "有 Python 基础的学习者",
    "goals": "学会用 Agent 把一门课从零做出来",
    "scope": "从 intake 走到 release",
    "preferred_chapter_count": 2,
}


@pytest.fixture()
def courses_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the course service at a temporary courses root.

    Args:
        tmp_path: The empty directory pytest provides for this test.
        monkeypatch: The patcher pytest provides for this test.

    Returns:
        The directory the service now creates its courses in.
    """
    root = tmp_path / "courses"
    root.mkdir()
    monkeypatch.setattr(
        "app.course_service.get_settings",
        lambda: SimpleNamespace(courses_root=root),
    )
    return root


@pytest.fixture()
def course(courses_root: Path) -> Path:
    """Create a course that has one chapter on the disk.

    Args:
        courses_root: The temporary courses root the fixture installed.

    Returns:
        The folder of the new course, with `lessons/01.md` written into it.
    """
    with TestClient(app) as client:
        response = client.post("/api/courses", json=VALID_BODY)
    assert response.status_code == 201

    course_root = courses_root / COURSE_SLUG
    (course_root / "lessons" / "01.md").write_text(ORIGINAL, encoding="utf-8")
    return course_root


def table_rows(database_path: Path, table: str) -> list[dict[str, Any]]:
    """Read every row of one table out of the throwaway database.

    Args:
        database_path: The database file to read.
        table: The name of the table, for example "chapter_versions".

    Returns:
        One dictionary per row, with the JSON columns decoded.
    """
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(f"SELECT * FROM {table}").fetchall()
    finally:
        connection.close()
    return [row_to_dict(row) or {} for row in rows]


def test_reading_a_chapter_hands_out_its_fingerprint(course: Path) -> None:
    """A read gives back the content and the fingerprint of that content.

    Args:
        course: The course folder the fixture created.

    Returns:
        Nothing. The test fails when the chapter cannot be read or when the
        fingerprint is missing or empty.
    """
    with TestClient(app) as client:
        response = client.get(f"/api/courses/{COURSE_SLUG}/chapters/01")

    assert response.status_code == 200
    body = response.json()
    assert body["key"] == "01"
    assert body["content"] == ORIGINAL
    assert body["content_hash"] == content_hash(ORIGINAL)
    assert len(body["content_hash"]) == 64


def test_saving_with_the_fingerprint_of_the_read_is_accepted(
    course: Path, use_temp_database: Path
) -> None:
    """A save whose fingerprint still matches the file on disk is accepted.

    Args:
        course: The course folder the fixture created.
        use_temp_database: The throwaway database the save writes into.

    Returns:
        Nothing. The test fails when the save is refused or when the file
        on disk still carries the old content.
    """
    with TestClient(app) as client:
        read = client.get(f"/api/courses/{COURSE_SLUG}/chapters/01")
        response = client.put(
            f"/api/courses/{COURSE_SLUG}/chapters/01",
            json={"content": UPDATED, "expected_hash": read.json()["content_hash"]},
        )

    assert response.status_code == 200
    assert (course / "lessons" / "01.md").read_text(encoding="utf-8") == UPDATED
    assert response.json()["content_hash"] == content_hash(UPDATED)


def test_saving_with_an_outdated_fingerprint_is_a_conflict(course: Path) -> None:
    """A save that carries a stale fingerprint changes nothing at all.

    Args:
        course: The course folder the fixture created.

    Returns:
        Nothing. The test fails when the save is accepted or when the file
        on disk was overwritten anyway.
    """
    with TestClient(app) as client:
        client.get(f"/api/courses/{COURSE_SLUG}/chapters/01")
        response = client.put(
            f"/api/courses/{COURSE_SLUG}/chapters/01",
            json={"content": UPDATED, "expected_hash": content_hash("别人改过的内容")},
        )

    assert response.status_code == 409
    assert (course / "lessons" / "01.md").read_text(encoding="utf-8") == ORIGINAL


def test_a_path_that_leaves_the_course_is_refused(
    courses_root: Path, course: Path
) -> None:
    """A path with `..` in it never reaches a file outside the course.

    Args:
        courses_root: The temporary courses root the fixture installed.
        course: The course folder the fixture created.

    Returns:
        Nothing. The test fails when a request with `..` is answered with
        anything else than 400, or when a file appeared outside the course
        folder.
    """
    before = (course / "course.json").read_bytes()

    with TestClient(app) as client:
        workspace = client.put(
            f"/api/courses/{COURSE_SLUG}/workspace/files/..%2F..%2Fcourse.json",
            json={"content": "越界写入", "expected_hash": EMPTY_HASH},
        )
        chapter = client.put(
            f"/api/courses/{COURSE_SLUG}/chapters/..%2F..%2Fcourse.json",
            json={"content": "越界写入", "expected_hash": EMPTY_HASH},
        )

    assert workspace.status_code == 400
    assert chapter.status_code == 400
    assert not (courses_root / "course.json").exists()
    assert not (courses_root.parent / "course.json").exists()
    assert (course / "course.json").read_bytes() == before


def test_overwriting_a_chapter_leaves_a_snapshot_behind(
    course: Path, use_temp_database: Path
) -> None:
    """The content that was replaced is kept under `.agent-history/`.

    Args:
        course: The course folder the fixture created.
        use_temp_database: The throwaway database the save writes into.

    Returns:
        Nothing. The test fails when no snapshot was taken or when it does
        not carry the content that was replaced.
    """
    with TestClient(app) as client:
        read = client.get(f"/api/courses/{COURSE_SLUG}/chapters/01")
        client.put(
            f"/api/courses/{COURSE_SLUG}/chapters/01",
            json={"content": UPDATED, "expected_hash": read.json()["content_hash"]},
        )

    history = course / ".agent-history"
    assert history.is_dir()
    snapshots = list(history.rglob("01.md"))
    assert len(snapshots) == 1
    assert snapshots[0].read_text(encoding="utf-8") == ORIGINAL


def test_a_saved_chapter_leaves_a_version_row(
    course: Path, use_temp_database: Path
) -> None:
    """Every accepted save is written down in `chapter_versions`.

    Args:
        course: The course folder the fixture created.
        use_temp_database: The throwaway database the save writes into.

    Returns:
        Nothing. The test fails when the row is missing or when it points
        at the wrong course, chapter or content.
    """
    with TestClient(app) as client:
        read = client.get(f"/api/courses/{COURSE_SLUG}/chapters/01")
        client.put(
            f"/api/courses/{COURSE_SLUG}/chapters/01",
            json={"content": UPDATED, "expected_hash": read.json()["content_hash"]},
        )

    rows = table_rows(use_temp_database, "chapter_versions")
    assert len(rows) == 1
    assert rows[0]["course_slug"] == COURSE_SLUG
    assert rows[0]["chapter_key"] == "01"
    assert rows[0]["source_path"] == "lessons/01.md"
    assert rows[0]["content_hash"] == content_hash(UPDATED)
    assert rows[0]["snapshot_path"].startswith(".agent-history/")
    assert rows[0]["reason"]


def test_a_workspace_file_can_be_read_and_saved(course: Path) -> None:
    """A workspace file is read and written with the same fingerprint rule.

    Args:
        course: The course folder the fixture created.

    Returns:
        Nothing. The test fails when the read or the save is refused, or
        when the file on disk does not carry the new content.
    """
    with TestClient(app) as client:
        read = client.get(f"/api/courses/{COURSE_SLUG}/workspace/files/NOTES.md")
        response = client.put(
            f"/api/courses/{COURSE_SLUG}/workspace/files/NOTES.md",
            json={"content": "新的笔记\n", "expected_hash": read.json()["content_hash"]},
        )

    assert read.status_code == 200
    assert response.status_code == 200
    assert (course / "workspace" / "NOTES.md").read_text(encoding="utf-8") == "新的笔记\n"
    assert response.json()["content_hash"] == content_hash("新的笔记\n")


def test_a_workspace_file_that_cannot_be_edited_is_refused(course: Path) -> None:
    """A file the editor cannot write is refused instead of being mangled.

    Args:
        course: The course folder the fixture created.

    Returns:
        Nothing. The test fails when the file was answered with 200.
    """
    (course / "workspace" / "diagram.png").write_bytes(b"\x89PNG\r\n")

    with TestClient(app) as client:
        response = client.put(
            f"/api/courses/{COURSE_SLUG}/workspace/files/diagram.png",
            json={"content": "不是图片", "expected_hash": EMPTY_HASH},
        )

    assert response.status_code == 400
    assert (course / "workspace" / "diagram.png").read_bytes() == b"\x89PNG\r\n"


def test_a_workspace_file_with_an_outdated_fingerprint_is_a_conflict(
    course: Path,
) -> None:
    """A stale fingerprint is refused for a workspace file as well.

    Args:
        course: The course folder the fixture created.

    Returns:
        Nothing. The test fails when the save was accepted or when the
        file on disk was overwritten anyway.
    """
    with TestClient(app) as client:
        client.get(f"/api/courses/{COURSE_SLUG}/workspace/files/NOTES.md")
        response = client.put(
            f"/api/courses/{COURSE_SLUG}/workspace/files/NOTES.md",
            json={"content": "新的笔记\n", "expected_hash": content_hash("别人改过的内容")},
        )

    assert response.status_code == 409
    assert (course / "workspace" / "NOTES.md").read_text(encoding="utf-8") != "新的笔记\n"


def test_a_save_that_cannot_be_written_down_changes_nothing(
    course: Path, use_temp_database: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A save that breaks half way leaves the chapter as it was.

    The chapter is written to the disk first and the version is written
    down afterwards.  When the second half breaks, the chapter has to go
    back to the content it had, so the course and its history never
    disagree about what was saved.

    Args:
        course: The course folder the fixture created.
        use_temp_database: The throwaway database the save writes into.
        monkeypatch: The patcher that makes the bookkeeping break.

    Returns:
        Nothing. The test fails when the chapter kept the new content or
        when a version row survived the broken save.
    """
    def break_the_bookkeeping(*args: Any, **kwargs: Any) -> None:
        """Stand in for a bookkeeping write that breaks.

        Args:
            args: The arguments the real function would have received.
            kwargs: The keyword arguments the real function would have received.

        Returns:
            Nothing. It always raises.
        Raises RuntimeError: always, because that is the point of it.
        """
        raise RuntimeError("版本写到一半炸了")

    monkeypatch.setattr(chapters, "_record_version", break_the_bookkeeping)

    with TestClient(app, raise_server_exceptions=False) as client:
        read = client.get(f"/api/courses/{COURSE_SLUG}/chapters/01")
        response = client.put(
            f"/api/courses/{COURSE_SLUG}/chapters/01",
            json={"content": UPDATED, "expected_hash": read.json()["content_hash"]},
        )

    assert response.status_code == 500
    assert (course / "lessons" / "01.md").read_text(encoding="utf-8") == ORIGINAL
    initialize_database(use_temp_database)
    assert table_rows(use_temp_database, "chapter_versions") == []
