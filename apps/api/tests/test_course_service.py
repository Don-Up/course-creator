"""Behaviour tests for the course service facade.

`app/course_service.py` is the only door the API routes use: it takes the
courses root out of the settings and hands the work to the scanner.  The
tests therefore replace the settings with a temporary directory and check
that the facade answers from it.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.course_service import get_course, list_courses


@pytest.fixture()
def courses_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the facade at a temporary courses root.

    Args:
        tmp_path: The empty directory pytest provides for this test.
        monkeypatch: The patcher pytest provides for this test.

    Returns:
        The directory the facade now reads its courses from.
    """
    monkeypatch.setattr(
        "app.course_service.get_settings",
        lambda: SimpleNamespace(courses_root=tmp_path),
    )
    return tmp_path


def write_course(courses_root: Path, slug: str, **fields: object) -> Path:
    """Write the course.json of one course.

    Args:
        courses_root: The directory that holds every course folder,
            for example courses/.
        slug: The short name of the course, for example "python-101".
        fields: The fields of the course file, for example
            ``{"title": "Python 入门"}``.

    Returns:
        The folder of the new course, for example courses/python-101/.
    """
    metadata: dict[str, object] = {"title": "Python 入门", "lessons": []}
    metadata.update(fields)
    course_root = courses_root / slug
    course_root.mkdir(parents=True)
    (course_root / "course.json").write_text(
        json.dumps(metadata, ensure_ascii=False),
        encoding="utf-8",
    )
    return course_root


def test_the_facade_lists_the_courses_of_the_settings_root(
    courses_root: Path,
) -> None:
    """The facade takes the courses root out of the settings.

    Args:
        courses_root: The temporary courses root the fixture installed.

    Returns:
        Nothing. The test fails when the course is not listed.
    """
    write_course(courses_root, "python-101")

    items = list_courses()

    assert [item["slug"] for item in items] == ["python-101"]


def test_the_facade_answers_with_none_for_an_unknown_course(
    courses_root: Path,
) -> None:
    """A course that does not exist is nothing, not an error.

    Args:
        courses_root: The temporary courses root the fixture installed.

    Returns:
        Nothing. The test fails when the facade raises instead of
        answering with None.
    """
    assert get_course("python-101") is None


def test_the_facade_refuses_a_slug_that_could_leave_the_courses_root(
    courses_root: Path,
) -> None:
    """The path guard of the scanner still holds behind the facade.

    Args:
        courses_root: The temporary courses root the fixture installed.

    Returns:
        Nothing. The test fails when the illegal slug is accepted.
    """
    with pytest.raises(ValueError):
        get_course("../secrets")
