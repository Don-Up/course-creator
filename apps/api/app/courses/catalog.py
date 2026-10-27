"""Reading the courses that live in the courses root.

The course list is not written by hand: every folder under the courses root
that carries a `course.json` is one course, and the fields the API shows are
read from that file.  A folder without a `course.json` is not a course yet
and is skipped, so half finished work in the courses root never breaks the
list.

The courses root is passed in explicitly instead of read from the settings
singleton, for the same reason as `app.courses.common`: the caller decides
where the courses live.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.courses.common import SLUG_PATTERN, _safe_course_root

COURSE_FILE = "course.json"


def _read_metadata(course_root: Path) -> dict[str, Any] | None:
    """Read the course file of one course folder.

    Args:
        course_root: The folder of one course, for example
            courses/python-101/.

    Returns:
        The content of the course file as a dictionary, or None when the
        folder is not a course: the file is missing, unreadable, not valid
        JSON, or not a JSON object.  A course that cannot be read is
        skipped instead of breaking the whole list.
    """
    path = course_root / COURSE_FILE
    if not path.is_file():
        return None
    try:
        metadata = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(metadata, dict):
        return None
    return metadata


def _course_item(course_root: Path, metadata: dict[str, Any]) -> dict[str, Any]:
    """Project the course file of one course into the item the API shows.

    Args:
        course_root: The folder of one course, for example
            courses/python-101/.
        metadata: The content of its course file, for example
            {"title": "Python 入门", "lessons": []}.

    Returns:
        The item of the course list: the slug, the title, the description,
        the number of chapters, the status and the duration.  The slug is
        the name of the folder, because that name is the address of the
        course and the route uses it to read the course again.
    """
    lessons = metadata.get("lessons")
    chapters = len(lessons) if isinstance(lessons, list) else 0
    return {
        "slug": course_root.name,
        "title": metadata.get("title") or course_root.name,
        "description": metadata.get("description") or "",
        "chapters": chapters,
        "status": metadata.get("status") or "preparing",
        "duration": metadata.get("duration") or "",
    }


def list_courses(courses_root: Path) -> list[dict[str, Any]]:
    """List every course that lives in the courses root.

    Args:
        courses_root: The directory that holds every course folder,
            for example courses/.

    Returns:
        One item per course, ordered by slug.  Folders that are not a
        course are left out: no course file, an unreadable course file, a
        hidden folder, and a folder whose name is not a legal slug.
    """
    if not courses_root.is_dir():
        return []
    items: list[dict[str, Any]] = []
    for course_root in sorted(courses_root.iterdir()):
        if not course_root.is_dir() or course_root.name.startswith("."):
            continue
        if not SLUG_PATTERN.fullmatch(course_root.name):
            continue
        metadata = _read_metadata(course_root)
        if metadata is None:
            continue
        items.append(_course_item(course_root, metadata))
    return items


def get_course(slug: str, courses_root: Path) -> dict[str, Any] | None:
    """Read one course out of the courses root.

    Args:
        slug: The short name of the course, for example "python-101".
        courses_root: The directory that holds every course folder,
            for example courses/.

    Returns:
        The item of that course, or None when no course has this slug.
        Raises ValueError("课程 slug 不合法") when the slug does not match
        the shared pattern: a slug that could point outside the courses
        root is refused, not looked up.
    """
    course_root = _safe_course_root(slug, courses_root)
    metadata = _read_metadata(course_root)
    if metadata is None:
        return None
    return _course_item(course_root, metadata)
