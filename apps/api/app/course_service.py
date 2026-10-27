"""The door the API routes use to reach the courses.

`app/courses/catalog.py` knows how to read a courses root; this module is
the only place that knows where that root is.  The routes call the facade,
so the courses root can move without touching them, and the scanner stays
free of any dependency on the settings.

Creating a course goes through the same door: the facade hands the intake
form to `app.courses.scaffold` and reads the new course back from the
disk, so the answer of the creation API is the very item the course list
shows.
"""

from __future__ import annotations

from typing import Any

from app.config import get_settings
from app.courses import catalog, scaffold
from app.schemas import CourseCreate

__all__ = ["create_course", "get_course", "list_courses"]


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
