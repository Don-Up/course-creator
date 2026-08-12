from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.courses.common import content_hash
from app.db import database, initialize_database
from app.workflow.services import artifact_commits
from app.workflow.services.artifact_commits import (
    commit_chapter_candidate,
    get_chapter_artifact,
    reject_chapter_candidate,
    verify_chapter_candidate,
)


def _configure(monkeypatch, tmp_path):
    settings = SimpleNamespace(
        database_path=tmp_path / "agent.db",
        data_root=tmp_path / ".course-agent",
        courses_root=tmp_path / "courses",
    )
    monkeypatch.setattr("app.db.get_settings", lambda: settings)
    monkeypatch.setattr(artifact_commits, "get_settings", lambda: settings)
    monkeypatch.setattr(
        artifact_commits, "_safe_course_root",
        lambda slug: settings.courses_root / slug,
    )
    initialize_database(settings.database_path)
    return settings


def _lesson(settings, slug="artifact-commit-test"):
    path = settings.courses_root / slug / "lessons" / "01-test.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("before\n", encoding="utf-8")
    return path


def test_candidate_is_immutable_current_revision_and_can_be_verified(monkeypatch, tmp_path):
    settings = _configure(monkeypatch, tmp_path)
    path = _lesson(settings)
    candidate = commit_chapter_candidate(
        course_slug="artifact-commit-test", relative_path="lessons/01-test.md",
        content="after\n", expected_hash=content_hash("before\n"),
        reason="test", run_id=None,
    )
    assert path.read_text(encoding="utf-8") == "after\n"
    stored = get_chapter_artifact(candidate["id"])
    assert stored and stored["status"] == "CANDIDATE"
    assert (settings.data_root / stored["storage_uri"]).read_text(encoding="utf-8") == "after\n"

    verify_chapter_candidate(candidate["id"], {"gate": "test", "passed": True})
    stored = get_chapter_artifact(candidate["id"])
    assert stored and stored["status"] == "VERIFIED"
    assert stored["verification"] == {"gate": "test", "passed": True}


def test_candidate_rejects_stale_writer_and_records_supersession(monkeypatch, tmp_path):
    settings = _configure(monkeypatch, tmp_path)
    _lesson(settings, "artifact-conflict-test")
    first = commit_chapter_candidate(
        course_slug="artifact-conflict-test", relative_path="lessons/01-test.md",
        content="first\n", expected_hash=content_hash("before\n"), reason="first",
    )
    with pytest.raises(RuntimeError, match="章节已发生变化"):
        commit_chapter_candidate(
            course_slug="artifact-conflict-test", relative_path="lessons/01-test.md",
            content="stale\n", expected_hash=content_hash("before\n"), reason="stale",
        )
    second = commit_chapter_candidate(
        course_slug="artifact-conflict-test", relative_path="lessons/01-test.md",
        content="second\n", expected_hash=content_hash("first\n"), reason="second",
    )
    reject_chapter_candidate(second["id"], {"reason": "regression"})
    with database() as connection:
        edge = connection.execute(
            "SELECT relation FROM artifact_edges WHERE parent_artifact_id = ? AND child_artifact_id = ?",
            (first["id"], second["id"]),
        ).fetchone()
    assert edge and edge["relation"] == "supersedes"
    assert get_chapter_artifact(first["id"])["is_current"] == 0
    assert get_chapter_artifact(second["id"])["status"] == "REJECTED"
