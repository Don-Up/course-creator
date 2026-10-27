"""Path guards and atomic JSON writes for the course workspace.

Every course directory lives at ``courses/<slug>/``.  `_safe_course_root` and
`_safe_child` are the only sanctioned way to turn a slug or a relative path
into a real filesystem path: both refuse anything that leaves the directory
they are given.  `_write_json_atomic` persists JSON in one replacement, so a
reader never observes a half-written document.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _safe_course_root(slug: str, courses_root: Path) -> Path:
    """Return the folder that holds one course, refusing anything that escapes.

    Args:
        slug: The short name of the course, for example "python-101".
            It has to match SLUG_PATTERN: lower case letters, digits and
            single dashes only.
        courses_root: The directory that holds every course folder,
            for example courses/.

    Returns:
        The folder this course would live in, inside courses_root.
        Raises ValueError("课程 slug 不合法") if the slug does not match
        the pattern, or if the resulting folder would leave courses_root.
    """
    if not SLUG_PATTERN.fullmatch(slug):
        raise ValueError("课程 slug 不合法")

    candidate = courses_root / slug
    if not candidate.resolve().is_relative_to(courses_root.resolve()):
        raise ValueError("课程 slug 不合法")
    return candidate


def _safe_child(root: Path, relative: str) -> Path:
    """Return the real path of a file that lives inside a course folder.

    Args:
        root: The folder the path has to stay inside,
            for example courses/python-101/.
        relative: The path relative to that folder,
            for example "chapters/01.md".

    Returns:
        The resolved path of the file inside root.
        Raises ValueError("文件路径越界") if the path is absolute, or if it
        resolves to a place outside root.
    """
    normalized = relative.replace("\\", "/")
    windows_path = PureWindowsPath(normalized)
    posix_absolute = PurePosixPath(normalized).is_absolute()
    if posix_absolute or windows_path.drive or windows_path.root:
        raise ValueError("文件路径越界")

    candidate = (root / normalized).resolve()
    if not candidate.is_relative_to(root.resolve()):
        raise ValueError("文件路径越界")
    return candidate


def content_hash(text: str) -> str:
    """Return the fingerprint of a piece of text.

    Args:
        text: The text to fingerprint, for example one chapter body.

    Returns:
        The sha256 digest of the text as 64 lower case hex characters. The
        same text always gives the same fingerprint, so a later step can
        tell that a chapter really changed without storing the text again.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Write a dictionary as JSON, so a reader never sees a half written file.

    Args:
        path: The file to write, for example
            courses/python-101/course.json. Its parent directory has to
            exist already; a wrong path has to surface immediately instead
            of being hidden by a silent mkdir.
        payload: The dictionary to store, for example
            {"title": "Python 入门"}.

    Returns:
        Nothing. The new content replaces the old one in a single step, and
        if that step fails the old file stays untouched and no temporary
        file is left behind.
    """
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
