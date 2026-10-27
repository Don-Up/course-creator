"""The door the API routes use to reach the courses.

`app/courses/catalog.py` knows how to read a courses root; this module is
the only place that knows where that root is.  The routes call the facade,
so the courses root can move without touching them, and the scanner stays
free of any dependency on the settings.
"""

from __future__ import annotations

from typing import Any

from app.config import get_settings
from app.courses import catalog

__all__ = ["get_course", "list_courses"]


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
