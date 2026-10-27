"""Behaviour tests for the course directory scanner.

`app/courses/catalog.py` reads the courses root and turns every folder that
carries a `course.json` into one item of the course list.  The tests
therefore work on real directories: a folder that is not a course has to be
skipped instead of breaking the list, and a course that does not exist has
to come back as `None` instead of an exception.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.courses.catalog import get_course, list_courses

EXPECTED_ITEM_KEYS = frozenset(
    {
        "slug",
        "title",
        "description",
        "chapters",
        "status",
        "duration",
    }
)


def write_course(courses_root: Path, slug: str, **overrides: Any) -> Path:
    """Write the course.json of one course.

    Args:
        courses_root: The directory that holds every course folder,
            for example courses/.
        slug: The short name of the course, for example "python-101".
        overrides: The fields to replace, for example
            ``{"status": "published"}`` for a released course.

    Returns:
        The folder of the new course, for example courses/python-101/.
    """
    lessons = overrides.pop("lessons", [])
    metadata: dict[str, Any] = {
        "schemaVersion": 1,
        "slug": slug,
        "title": "Python 入门",
        "description": "学会构建一个可恢复的 Agent",
        "duration": "待蓝图确认",
        "status": "preparing",
        "lessons": lessons,
    }
    metadata.update(overrides)
    course_root = courses_root / slug
    course_root.mkdir(parents=True)
    (course_root / "course.json").write_text(
        json.dumps(metadata, ensure_ascii=False),
        encoding="utf-8",
    )
    return course_root


def test_list_courses_reads_every_course_folder(tmp_path: Path) -> None:
    """Both courses of the root show up in the list.

    Args:
        tmp_path: The empty directory pytest provides for this test.

    Returns:
        Nothing. The test fails when a course is missing from the list.
    """
    write_course(tmp_path, "python-101", title="Python 入门")
    write_course(tmp_path, "rust-101", title="Rust 入门")

    items = list_courses(tmp_path)

    assert [item["slug"] for item in items] == ["python-101", "rust-101"]


def test_courses_are_listed_in_slug_order(tmp_path: Path) -> None:
    """The order of the list does not depend on the order of the disk.

    Args:
        tmp_path: The empty directory pytest provides for this test.

    Returns:
        Nothing. The test fails when the list is not ordered by slug.
    """
    write_course(tmp_path, "zeta-course")
    write_course(tmp_path, "alpha-course")

    items = list_courses(tmp_path)

    assert [item["slug"] for item in items] == ["alpha-course", "zeta-course"]


def test_course_item_carries_exactly_the_agreed_keys(tmp_path: Path) -> None:
    """No key may be added or dropped, because the frontend reads this list.

    Args:
        tmp_path: The empty directory pytest provides for this test.

    Returns:
        Nothing. The test fails when the key set differs from the agreement.
    """
    write_course(tmp_path, "python-101")

    item = list_courses(tmp_path)[0]

    assert set(item) == EXPECTED_ITEM_KEYS


def test_course_item_repeats_the_values_of_the_course_json(tmp_path: Path) -> None:
    """The item carries the values the course file holds.

    Args:
        tmp_path: The empty directory pytest provides for this test.

    Returns:
        Nothing. The test fails when a value differs from the course file.
    """
    write_course(
        tmp_path,
        "python-101",
        title="Python 入门",
        status="published",
        duration="12 小时",
    )

    item = list_courses(tmp_path)[0]

    assert item["slug"] == "python-101"
    assert item["title"] == "Python 入门"
    assert item["description"] == "学会构建一个可恢复的 Agent"
    assert item["status"] == "published"
    assert item["duration"] == "12 小时"


def test_chapters_count_the_lessons_of_the_course(tmp_path: Path) -> None:
    """A course with three lessons is a course with three chapters.

    Args:
        tmp_path: The empty directory pytest provides for this test.

    Returns:
        Nothing. The test fails when the chapter count is wrong.
    """
    write_course(
        tmp_path,
        "python-101",
        lessons=[{"number": 1}, {"number": 2}, {"number": 3}],
    )

    item = list_courses(tmp_path)[0]

    assert item["chapters"] == 3


def test_chapters_are_zero_when_the_course_has_no_lesson_list(tmp_path: Path) -> None:
    """A course file without a lesson list is a course without chapters.

    Args:
        tmp_path: The empty directory pytest provides for this test.

    Returns:
        Nothing. The test fails when the chapter count is not zero.
    """
    write_course(tmp_path, "python-101", lessons="不是一个列表")

    item = list_courses(tmp_path)[0]

    assert item["chapters"] == 0


def test_a_folder_without_a_course_json_is_skipped(tmp_path: Path) -> None:
    """A folder that is not a course does not break the list.

    Args:
        tmp_path: The empty directory pytest provides for this test.

    Returns:
        Nothing. The test fails when the other course is not listed.
    """
    (tmp_path / "not-a-course").mkdir()
    write_course(tmp_path, "python-101")

    items = list_courses(tmp_path)

    assert [item["slug"] for item in items] == ["python-101"]


def test_a_course_with_a_broken_course_json_is_skipped(tmp_path: Path) -> None:
    """A course file that cannot be read does not break the list.

    Args:
        tmp_path: The empty directory pytest provides for this test.

    Returns:
        Nothing. The test fails when the other course is not listed.
    """
    broken = tmp_path / "broken-course"
    broken.mkdir()
    (broken / "course.json").write_text("{ 这不是 JSON", encoding="utf-8")
    write_course(tmp_path, "python-101")

    items = list_courses(tmp_path)

    assert [item["slug"] for item in items] == ["python-101"]


def test_a_course_json_that_is_not_an_object_is_skipped(tmp_path: Path) -> None:
    """A course file that holds a list is not a course file.

    Args:
        tmp_path: The empty directory pytest provides for this test.

    Returns:
        Nothing. The test fails when the other course is not listed.
    """
    broken = tmp_path / "broken-course"
    broken.mkdir()
    (broken / "course.json").write_text("[]", encoding="utf-8")
    write_course(tmp_path, "python-101")

    items = list_courses(tmp_path)

    assert [item["slug"] for item in items] == ["python-101"]


def test_hidden_folders_are_skipped(tmp_path: Path) -> None:
    """A hidden folder is not a course.

    Args:
        tmp_path: The empty directory pytest provides for this test.

    Returns:
        Nothing. The test fails when the hidden folder shows up.
    """
    hidden = tmp_path / ".hidden-course"
    hidden.mkdir()
    (hidden / "course.json").write_text("{}", encoding="utf-8")
    write_course(tmp_path, "python-101")

    items = list_courses(tmp_path)

    assert [item["slug"] for item in items] == ["python-101"]


def test_folders_whose_name_is_not_a_legal_slug_are_skipped(tmp_path: Path) -> None:
    """A folder that could never be addressed is not a course.

    Args:
        tmp_path: The empty directory pytest provides for this test.

    Returns:
        Nothing. The test fails when the illegal folder shows up.
    """
    illegal = tmp_path / "Python 101"
    illegal.mkdir()
    (illegal / "course.json").write_text("{}", encoding="utf-8")
    write_course(tmp_path, "python-101")

    items = list_courses(tmp_path)

    assert [item["slug"] for item in items] == ["python-101"]


def test_a_missing_courses_root_lists_no_courses(tmp_path: Path) -> None:
    """A courses root that does not exist yet holds no course.

    Args:
        tmp_path: The empty directory pytest provides for this test.

    Returns:
        Nothing. The test fails when the scanner raises instead of
        answering with an empty list.
    """
    assert list_courses(tmp_path / "nowhere") == []


def test_get_course_returns_the_course_of_that_slug(tmp_path: Path) -> None:
    """One course can be read out of the root by its slug.

    Args:
        tmp_path: The empty directory pytest provides for this test.

    Returns:
        Nothing. The test fails when the course is not found.
    """
    write_course(tmp_path, "python-101", title="Python 入门")

    course = get_course("python-101", tmp_path)

    assert course is not None
    assert course["slug"] == "python-101"
    assert course["title"] == "Python 入门"


def test_get_course_returns_none_for_an_unknown_slug(tmp_path: Path) -> None:
    """A course that does not exist is not an error, it is nothing.

    Args:
        tmp_path: The empty directory pytest provides for this test.

    Returns:
        Nothing. The test fails when the scanner raises instead of
        answering with None.
    """
    assert get_course("python-101", tmp_path) is None


def test_get_course_returns_none_when_the_course_json_is_missing(tmp_path: Path) -> None:
    """A folder without a course file holds no course either.

    Args:
        tmp_path: The empty directory pytest provides for this test.

    Returns:
        Nothing. The test fails when the scanner raises instead of
        answering with None.
    """
    (tmp_path / "python-101").mkdir()

    assert get_course("python-101", tmp_path) is None


def test_get_course_refuses_a_slug_that_could_leave_the_courses_root(
    tmp_path: Path,
) -> None:
    """The path guard still holds: an illegal slug is refused, not looked up.

    Args:
        tmp_path: The empty directory pytest provides for this test.

    Returns:
        Nothing. The test fails when the illegal slug is accepted.
    """
    with pytest.raises(ValueError):
        get_course("../secrets", tmp_path)


def test_get_course_refuses_a_slug_with_illegal_characters(tmp_path: Path) -> None:
    """An upper case slug is not a course name.

    Args:
        tmp_path: The empty directory pytest provides for this test.

    Returns:
        Nothing. The test fails when the illegal slug is accepted.
    """
    with pytest.raises(ValueError):
        get_course("Python-101", tmp_path)
