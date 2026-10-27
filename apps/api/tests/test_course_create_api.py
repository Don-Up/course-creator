"""Tests of the course creation API.

`POST /api/courses` writes real folders, so every test points the courses
root at a temporary directory.  A test that built a course in the
repository's own `courses/` folder would leave a course behind that the
next test run would see, and that nobody asked for.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app


VALID_BODY: dict[str, object] = {
    "title": "测试课程",
    "slug": "test-course",
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


def test_a_valid_request_creates_a_course(courses_root: Path) -> None:
    """A legal intake form is answered with 201 and the new course.

    Args:
        courses_root: The temporary courses root the fixture installed.

    Returns:
        Nothing. The test fails when the course is not answered with 201,
        or when the answer does not carry the slug, a run id and the
        status "preparing".
    """
    with TestClient(app) as client:
        response = client.post("/api/courses", json=VALID_BODY)

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"course", "run_id", "status"}
    assert body["course"]["slug"] == "test-course"
    assert body["course"]["title"] == "测试课程"
    assert body["course"]["chapters"] == 0
    assert body["run_id"]
    assert body["status"] == "preparing"


def test_the_new_course_lays_out_the_folder_skeleton(courses_root: Path) -> None:
    """The course lands on the disk as a folder with the known layout.

    Args:
        courses_root: The temporary courses root the fixture installed.

    Returns:
        Nothing. The test fails when the course file or one of the six
        folders is missing.
    """
    with TestClient(app) as client:
        client.post("/api/courses", json=VALID_BODY)

    course_root = courses_root / "test-course"
    assert course_root.is_dir()
    for name in ("lessons", "reference", "markdown", "assets", "quality", "workspace"):
        assert (course_root / name).is_dir()
    metadata = json.loads((course_root / "course.json").read_text(encoding="utf-8"))
    assert metadata["slug"] == "test-course"
    assert metadata["lessons"] == []
    assert metadata["status"] == "preparing"


def test_a_slug_that_is_already_taken_is_answered_with_conflict(
    courses_root: Path,
) -> None:
    """The same slug twice is a conflict, not a second course.

    Args:
        courses_root: The temporary courses root the fixture installed.

    Returns:
        Nothing. The test fails when the second request is answered with
        something else than 409.
    """
    with TestClient(app) as client:
        first = client.post("/api/courses", json=VALID_BODY)
        second = client.post("/api/courses", json=VALID_BODY)

    assert first.status_code == 201
    assert second.status_code == 409


def test_a_refused_creation_leaves_the_existing_course_alone(
    courses_root: Path,
) -> None:
    """A course that is already there is never overwritten.

    Args:
        courses_root: The temporary courses root the fixture installed.

    Returns:
        Nothing. The test fails when the course file of the first course
        changed.
    """
    with TestClient(app) as client:
        client.post("/api/courses", json=VALID_BODY)
        course_file = courses_root / "test-course" / "course.json"
        before = course_file.read_bytes()
        client.post("/api/courses", json={**VALID_BODY, "title": "另一个标题"})

    assert course_file.read_bytes() == before


@pytest.mark.parametrize("slug", ["Test-Course", "test course", "test_course"])
def test_an_illegal_slug_is_answered_with_unprocessable(
    courses_root: Path,
    slug: str,
) -> None:
    """A slug that is not a legal course name never reaches the disk.

    Args:
        courses_root: The temporary courses root the fixture installed.
        slug: The illegal slug of the request, for example "Test-Course".

    Returns:
        Nothing. The test fails when the request is answered with
        something else than 422.
    """
    with TestClient(app) as client:
        response = client.post("/api/courses", json={**VALID_BODY, "slug": slug})

    assert response.status_code == 422


def test_an_illegal_slug_leaves_nothing_on_the_disk(courses_root: Path) -> None:
    """A refused request does not leave a half written course behind.

    Args:
        courses_root: The temporary courses root the fixture installed.

    Returns:
        Nothing. The test fails when the courses root is not empty.
    """
    with TestClient(app) as client:
        client.post("/api/courses", json={**VALID_BODY, "slug": "Test-Course"})

    assert list(courses_root.iterdir()) == []


def test_a_title_of_one_character_is_answered_with_unprocessable(
    courses_root: Path,
) -> None:
    """The intake form is checked before anything is written.

    Args:
        courses_root: The temporary courses root the fixture installed.

    Returns:
        Nothing. The test fails when the request is answered with
        something else than 422.
    """
    with TestClient(app) as client:
        response = client.post("/api/courses", json={**VALID_BODY, "title": "课"})

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("audience", "短"),
        ("goals", "太短"),
        ("scope", "短"),
        ("preferred_chapter_count", 0),
        ("preferred_chapter_count", 61),
        ("effective_char_min", 999),
        ("effective_char_min", 50001),
        ("token_budget_mtokens", 0),
        ("token_budget_mtokens", 10001),
    ],
)
def test_a_field_out_of_its_range_is_answered_with_unprocessable(
    courses_root: Path,
    field: str,
    value: object,
) -> None:
    """Every bound of the intake form is checked before anything is written.

    Args:
        courses_root: The temporary courses root the fixture installed.
        field: The field that is out of its range, for example "scope".
        value: The value that is out of its range, for example "短".

    Returns:
        Nothing. The test fails when the request is answered with
        something else than 422.
    """
    with TestClient(app) as client:
        response = client.post("/api/courses", json={**VALID_BODY, field: value})

    assert response.status_code == 422


def test_two_courses_get_two_different_run_ids(courses_root: Path) -> None:
    """Every creation gets its own run id.

    Args:
        courses_root: The temporary courses root the fixture installed.

    Returns:
        Nothing. The test fails when the two run ids are the same.
    """
    with TestClient(app) as client:
        first = client.post("/api/courses", json=VALID_BODY)
        second = client.post(
            "/api/courses",
            json={**VALID_BODY, "slug": "other-course"},
        )

    assert first.json()["run_id"] != second.json()["run_id"]


def test_the_new_course_looks_the_same_in_the_course_list(
    courses_root: Path,
) -> None:
    """The course of the creation answer is the course of the list.

    Args:
        courses_root: The temporary courses root the fixture installed.

    Returns:
        Nothing. The test fails when the two courses differ.
    """
    with TestClient(app) as client:
        created = client.post("/api/courses", json=VALID_BODY)
        listed = client.get("/api/courses")

    item = next(
        entry for entry in listed.json()["items"] if entry["slug"] == "test-course"
    )
    assert created.json()["course"] == item
