"""The door the API routes use to reach the courses.

`app/courses/catalog.py` knows how to read a courses root; this module is
the only place that knows where that root is.  The routes call the facade,
so the courses root can move without touching them, and the scanner stays
free of any dependency on the settings.

Creating a course goes through the same door: the facade hands the intake
form to `app.courses.scaffold` and reads the new course back from the
disk, so the answer of the creation API is the very item the course list
shows.

The editor goes through the same door as well.  The chapter and the
workspace modules know how to read and write a file, but not where the
courses live; the facade is what connects the two.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.config import get_settings
from app.courses import catalog, chapters, scaffold, workspace
from app.courses.common import _safe_course_root
from app.schemas import CourseCreate

__all__ = [
    "create_course",
    "get_course",
    "list_courses",
    "read_chapter",
    "read_workspace_file",
    "save_chapter",
    "save_workspace_file",
]


def list_courses() -> list[dict[str, Any]]:
    """List every course of the courses root.

    Returns:
        One item per course, ordered by slug.  The shape of an item is the
        one `app.courses.catalog` builds.
    """
    return catalog.list_courses(get_settings().courses_root)


def get_course(slug: str) -> dict[str, Any] | None:
    """Read one course out of the courses root.

    Args:
        slug: The short name of the course, for example "python-101".

    Returns:
        The item of that course, or None when no course has this slug.
        Raises ValueError("课程 slug 不合法") when the slug does not match
        the shared pattern.
    """
    return catalog.get_course(slug, get_settings().courses_root)


def create_course(request: CourseCreate) -> dict[str, Any]:
    """Create one course and answer with the item the course list shows.

    The course is written first and read back afterwards, so the answer
    comes from the disk and not from the form that was submitted: the
    course of the creation answer and the course of the course list are
    the same item.

    Args:
        request: The intake form the user submitted, for example a
            CourseCreate with the slug "python-101".

    Returns:
        The item of the new course: the slug, the title, the description,
        the number of chapters, the status and the duration.
    Raises FileExistsError when a course with this slug is already there:
        an existing course is never overwritten.
    Raises ValueError("课程 slug 不合法") when the slug does not match
        the shared pattern.
    """
    courses_root = get_settings().courses_root
    scaffold.create_course_scaffold(request, courses_root)
    course = catalog.get_course(request.slug, courses_root)
    if course is None:
        raise RuntimeError(f"课程刚落盘就读不到：{request.slug}")
    return course


def _course_root(slug: str) -> Path:
    """Return the folder of one course, refusing anything outside the root.

    Args:
        slug: The short name of the course, for example "python-101".

    Returns:
        The folder of that course.
        Raises ValueError("课程 slug 不合法") when the slug does not match
        the shared pattern, and FileNotFoundError when there is no such
        course.
    """
    root = _safe_course_root(slug, get_settings().courses_root)
    if not root.is_dir():
        raise FileNotFoundError(f"课程不存在：{slug}")
    return root


def read_chapter(slug: str, key: str) -> dict[str, Any]:
    """Read one chapter of a course.

    Args:
        slug: The short name of the course, for example "python-101".
        key: The key of the chapter, for example "01".

    Returns:
        The chapter: the key, the path, the content, the fingerprint of
        the content and the moment it was changed the last time.
        Raises ValueError when the slug is illegal or the key points
        outside the course, and FileNotFoundError when the course or the
        chapter does not exist.
    """
    return chapters.read_chapter(_course_root(slug), key)


def save_chapter(
    slug: str,
    key: str,
    content: str,
    expected_hash: str,
    *,
    reason: str = chapters.DEFAULT_REASON,
) -> dict[str, Any]:
    """Write one chapter of a course, but only when nobody else changed it.

    Args:
        slug: The short name of the course, for example "python-101".
        key: The key of the chapter, for example "01".
        content: The new content of the chapter.
        expected_hash: The fingerprint the caller read.
        reason: Why the chapter was saved, for example "手工编辑".

    Returns:
        The chapter as it is after the save.
        Raises ValueError when the slug is illegal or the key points
        outside the course, FileNotFoundError when the course or the
        chapter does not exist, and ConcurrencyConflict when the
        fingerprint does not match what is on the disk.
    """
    return chapters.save_chapter(
        _course_root(slug), key, content, expected_hash, reason=reason
    )


def read_workspace_file(slug: str, name: str) -> dict[str, Any]:
    """Read one file of the workspace of a course.

    Args:
        slug: The short name of the course, for example "python-101".
        name: The name of the workspace file, for example "NOTES.md".

    Returns:
        The file: the name, the path, the content, the fingerprint of the
        content, the size of the file and the moment it was changed the
        last time.
        Raises ValueError when the slug is illegal or the name points
        outside the workspace, and FileNotFoundError when the course or
        the file does not exist.
    """
    return workspace.read_workspace_file(_course_root(slug), name)


def save_workspace_file(
    slug: str,
    name: str,
    content: str,
    expected_hash: str,
) -> dict[str, Any]:
    """Write one file of the workspace, but only when nobody else changed it.

    Args:
        slug: The short name of the course, for example "python-101".
        name: The name of the workspace file, for example "NOTES.md".
        content: The new content of the file.
        expected_hash: The fingerprint the caller read.

    Returns:
        The file as it is after the save.
        Raises ValueError when the slug is illegal or the name points
        outside the workspace, FileNotFoundError when the course or the
        file does not exist, and ConcurrencyConflict when the fingerprint
        does not match what is on the disk.
    """
    return workspace.save_workspace_file(
        _course_root(slug), name, content, expected_hash
    )
