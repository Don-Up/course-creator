"""Reading and writing the chapters of a course.

A chapter is one Markdown file of the course.  Reading one hands out the
content together with its fingerprint, so an editor can send that
fingerprint back when it saves.  A save whose fingerprint does not match
what is on the disk any more is refused: two people editing the same
chapter must not lose one another's work silently.

Before a file is replaced, the old content is copied into
`.agent-history/<ts>/` of the course, and the version that was written is
recorded in the `chapter_versions` table of P2.1.

The courses root is not read here: the caller decides where the courses
live, the same way `app.courses.common` does it.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.courses.common import (
    ConcurrencyConflict,
    _safe_child,
    content_hash,
    snapshot_file,
    write_text_atomic,
)
from app.db import database, utcnow

CHAPTER_DIRECTORY = "lessons"
CHAPTER_SUFFIX = ".md"
DEFAULT_REASON = "手工编辑"


def _read_metadata(course_root: Path) -> dict[str, Any]:
    """Read the course file of one course.

    Args:
        course_root: The folder of one course, for example
            courses/python-101/.

    Returns:
        The content of the course file as a dictionary, or an empty
        dictionary when the file is missing or cannot be read.  A course
        without a readable course file still has chapters on the disk.
    """
    path = course_root / "course.json"
    if not path.is_file():
        return {}
    try:
        metadata = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return metadata if isinstance(metadata, dict) else {}


def _lesson_path(course_root: Path, key: str) -> str | None:
    """Find the path of a chapter in the lesson list of the course.

    The lesson list is what the blueprint writes down, so it is the place
    that says which file belongs to which chapter.  A key matches when it
    is the number, the code, the path or the name of the lesson.

    Args:
        course_root: The folder of one course, for example
            courses/python-101/.
        key: The key the caller asked for, for example "1".

    Returns:
        The path of the chapter inside the course, for example
        "lessons/01.md", or None when the lesson list does not know the
        key.
    """
    lessons = _read_metadata(course_root).get("lessons")
    if not isinstance(lessons, list):
        return None
    for lesson in lessons:
        if not isinstance(lesson, dict):
            continue
        markdown = str(lesson.get("markdown") or "")
        candidates = {
            str(lesson.get("number") or ""),
            str(lesson.get("code") or ""),
            markdown,
            Path(markdown).stem,
        }
        if key in candidates and markdown:
            return markdown
    return None


def _chapter_relative_path(course_root: Path, key: str) -> str:
    """Turn the key of a chapter into a path inside the course.

    A key that names one lesson of the course list keeps the path that
    lesson has.  Every other key without a slash names a file in the
    `lessons/` folder, and a key with a slash is a path inside the course.

    Args:
        course_root: The folder of one course, for example
            courses/python-101/.
        key: The key the caller asked for, for example "01".

    Returns:
        The path of the chapter inside the course, for example
        "lessons/01.md".
    """
    known = _lesson_path(course_root, key)
    if known is not None:
        return known
    if "/" in key:
        return key
    if Path(key).suffix:
        return f"{CHAPTER_DIRECTORY}/{key}"
    return f"{CHAPTER_DIRECTORY}/{key}{CHAPTER_SUFFIX}"


def resolve_chapter_path(course_root: Path, key: str) -> Path:
    """Return the file of one chapter, refusing anything outside the course.

    Args:
        course_root: The folder of one course, for example
            courses/python-101/.
        key: The key of the chapter, for example "01".

    Returns:
        The path of the chapter file.  The file itself does not have to
        exist yet.
        Raises ValueError("章节标识不合法") when the key is empty, and
        ValueError("文件路径越界") when the key points outside the course.
    """
    if not key or not key.strip():
        raise ValueError("章节标识不合法")
    relative = _chapter_relative_path(course_root, key)
    try:
        return _safe_child(course_root, relative)
    except ValueError as error:
        raise ValueError("文件路径越界") from error


def _updated_at(path: Path) -> str:
    """Return the moment a file was changed the last time.

    Args:
        path: The file to look at, for example
            courses/python-101/lessons/01.md.

    Returns:
        The time as a timezone aware ISO 8601 string, for example
        "2026-10-27T08:31:05.123456+00:00".
    """
    return datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()


def list_chapters(course_root: Path) -> list[dict[str, Any]]:
    """List the chapters of a course in the order the course file gives.

    The lesson list of the course file is the only place that says which
    chapter exists and what it is called, so the list is read from there
    and not from the folder: a chapter that was planned but not written
    yet is still a chapter of the course.

    The key of a chapter is the one the single chapter route accepts, so
    a key taken from this list can be read back with
    `GET /api/courses/{slug}/chapters/{key}` without a second guess.

    Args:
        course_root: The folder of one course, for example
            courses/python-101/.

    Returns:
        One item per chapter: the key, the number, the title and the path
        of the Markdown file inside the course.  A lesson without a
        Markdown file is left out, because there is nothing to read.
    """
    lessons = _read_metadata(course_root).get("lessons")
    if not isinstance(lessons, list):
        return []
    items: list[dict[str, Any]] = []
    for lesson in lessons:
        if not isinstance(lesson, dict):
            continue
        markdown = str(lesson.get("markdown") or "")
        if not markdown:
            continue
        raw_number = lesson.get("number")
        number = raw_number if isinstance(raw_number, int) else None
        items.append(
            {
                "key": str(raw_number) if raw_number is not None else Path(markdown).stem,
                "number": number if number is not None else len(items) + 1,
                "title": str(lesson.get("title") or Path(markdown).stem),
                "path": markdown,
            }
        )
    return items


def read_chapter(course_root: Path, key: str) -> dict[str, Any]:
    """Read one chapter of a course.

    Args:
        course_root: The folder of one course, for example
            courses/python-101/.
        key: The key of the chapter, for example "01".

    Returns:
        The key, the path, the content, the fingerprint of the content and
        the moment the file was changed the last time.
        Raises ValueError when the key is empty or points outside the
        course, and FileNotFoundError when there is no such chapter.
    """
    path = resolve_chapter_path(course_root, key)
    if not path.is_file():
        raise FileNotFoundError(f"章节不存在：{key}")
    content = path.read_text(encoding="utf-8")
    root = course_root.resolve()
    return {
        "key": key,
        "path": path.relative_to(root).as_posix(),
        "content": content,
        "content_hash": content_hash(content),
        "updated_at": _updated_at(path),
    }


def _record_version(
    course_root: Path,
    key: str,
    source_path: str,
    digest: str,
    snapshot_path: str,
    reason: str,
) -> None:
    """Write the version that was just saved into the version table.

    Args:
        course_root: The folder of one course, for example
            courses/python-101/.
        key: The key of the chapter, for example "01".
        source_path: The path of the chapter inside the course, for
            example "lessons/01.md".
        digest: The fingerprint of the content that was written.
        snapshot_path: The path of the snapshot of the content that was
            replaced, for example
            ".agent-history/20261027T083105123456Z/lessons/01.md".
        reason: Why the chapter was saved, for example "手工编辑".

    Returns:
        Nothing. The row is written inside one transaction, so a failure
        leaves no half written version behind.
    """
    with database() as connection:
        connection.execute(
            """
            INSERT INTO chapter_versions (
                id, course_slug, chapter_key, source_path, content_hash,
                snapshot_path, reason, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                course_root.name,
                key,
                source_path,
                digest,
                snapshot_path,
                reason,
                utcnow(),
            ),
        )


def save_chapter(
    course_root: Path,
    key: str,
    content: str,
    expected_hash: str,
    *,
    reason: str = DEFAULT_REASON,
) -> dict[str, Any]:
    """Write one chapter of a course, but only when nobody else changed it.

    The fingerprint the caller read has to match the fingerprint of the
    file on the disk.  When it does not, the write is refused and the file
    stays as it is: the person who is behind has to look at both versions
    before they decide which one wins.

    Args:
        course_root: The folder of one course, for example
            courses/python-101/.
        key: The key of the chapter, for example "01".
        content: The new content of the chapter.
        expected_hash: The fingerprint the caller read, for example the
            `content_hash` a read handed out.
        reason: Why the chapter was saved, for example "手工编辑".

    Returns:
        The chapter as it is after the save: the key, the path, the new
        content, its fingerprint, the moment it was changed and the path
        of the snapshot of the content that was replaced.
        Raises ValueError when the key is empty or points outside the
        course, FileNotFoundError when there is no such chapter, and
        ConcurrencyConflict when the fingerprint does not match.
    """
    path = resolve_chapter_path(course_root, key)
    root = course_root.resolve()
    relative = path.relative_to(root).as_posix()

    current = path.read_text(encoding="utf-8") if path.is_file() else ""
    if content_hash(current) != expected_hash:
        raise ConcurrencyConflict("内容已被其他编辑器修改，请刷新并比较后再保存")

    snapshot = snapshot_file(root, path, relative)
    write_text_atomic(path, content)
    try:
        _record_version(
            root,
            key,
            relative,
            content_hash(content),
            snapshot.relative_to(root).as_posix(),
            reason,
        )
    except Exception:
        write_text_atomic(path, current)
        raise

    saved = read_chapter(course_root, key)
    saved["snapshot_path"] = snapshot.relative_to(root).as_posix()
    return saved
