"""Tests of the chapter list of a course.

`GET /api/courses/{slug}/chapters` answers with the chapters a course
has, so the browser can show a chapter picker.  The summary of a course
carries the number of chapters, but not which ones they are, and the
chapter files on the disk are not the list either: a chapter that is
planned but not written yet is still a chapter of the course.

The keys of the list are the keys the single chapter route accepts, so a
chapter taken from the list can be read back without a second guess.
That round trip is what these tests pin down.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app


LESSONS = [
    {
        "number": 1,
        "title": "第一课",
        "markdown": "lessons/01-first.md",
    },
    {
        "number": 2,
        "title": "第二课",
        "markdown": "lessons/02-second.md",
    },
]


@pytest.fixture()
def courses_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the course service at a temporary courses root.

    Args:
        tmp_path: The empty directory pytest provides for this test.
        monkeypatch: The patcher pytest provides for this test.

    Returns:
        The directory the service now reads its courses from.
    """
    root = tmp_path / "courses"
    (root / "demo" / "lessons").mkdir(parents=True)
    (root / "demo" / "course.json").write_text(
        json.dumps(
            {
                "slug": "demo",
                "title": "示例课程",
                "description": "一节用来测章节列表的课",
                "duration": "",
                "status": "preparing",
                "lessons": LESSONS,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    for lesson in LESSONS:
        (root / "demo" / lesson["markdown"]).write_text(
            f"# {lesson['title']}\n\n正文。\n", encoding="utf-8"
        )
    monkeypatch.setattr(
        "app.course_service.get_settings",
        lambda: SimpleNamespace(courses_root=root),
    )
    return root


def test_the_chapters_of_a_course_are_listed(courses_root: Path) -> None:
    """Every lesson of the course file is one item of the list.

    Args:
        courses_root: The temporary courses root the fixture installed.

    Returns:
        Nothing. The test fails when the list does not carry the two
        lessons of the course, with their numbers and their titles.
    """
    with TestClient(app) as client:
        response = client.get("/api/courses/demo/chapters")

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["key"] for item in items] == ["1", "2"]
    assert [item["number"] for item in items] == [1, 2]
    assert [item["title"] for item in items] == ["第一课", "第二课"]
    assert items[0]["path"] == "lessons/01-first.md"


def test_a_key_of_the_list_reads_the_chapter_back(courses_root: Path) -> None:
    """A chapter taken from the list can be read with its own key.

    Args:
        courses_root: The temporary courses root the fixture installed.

    Returns:
        Nothing. The test fails when the chapter cannot be read with the
        key the list handed out, or when the content is another chapter.
    """
    with TestClient(app) as client:
        listed = client.get("/api/courses/demo/chapters")
        key = listed.json()["items"][1]["key"]
        read = client.get(f"/api/courses/demo/chapters/{key}")

    assert read.status_code == 200
    body = read.json()
    assert body["key"] == "2"
    assert body["path"] == "lessons/02-second.md"
    assert "第二课" in body["content"]


def test_a_course_without_lessons_has_an_empty_list(courses_root: Path) -> None:
    """A course that has not been generated yet has no chapters.

    Args:
        courses_root: The temporary courses root the fixture installed.

    Returns:
        Nothing. The test fails when the list of an empty course is not
        empty.
    """
    (courses_root / "empty").mkdir()
    (courses_root / "empty" / "course.json").write_text(
        json.dumps(
            {"slug": "empty", "title": "空课", "lessons": []}, ensure_ascii=False
        ),
        encoding="utf-8",
    )

    with TestClient(app) as client:
        response = client.get("/api/courses/empty/chapters")

    assert response.status_code == 200
    assert response.json()["items"] == []


def test_an_unknown_course_is_answered_with_not_found(courses_root: Path) -> None:
    """A course that is not there has no chapters.

    Args:
        courses_root: The temporary courses root the fixture installed.

    Returns:
        Nothing. The test fails when the request is answered with
        something else than 404.
    """
    with TestClient(app) as client:
        response = client.get("/api/courses/nope/chapters")

    assert response.status_code == 404


def test_an_illegal_slug_is_answered_with_bad_request(courses_root: Path) -> None:
    """A slug that is not a legal course name never reaches the disk.

    Args:
        courses_root: The temporary courses root the fixture installed.

    Returns:
        Nothing. The test fails when the request is answered with
        something else than 400.
    """
    with TestClient(app) as client:
        response = client.get("/api/courses/Demo/chapters")

    assert response.status_code == 400
