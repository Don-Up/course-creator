"""Reading and writing the files in the workspace of a course.

The workspace is the folder the agent and the user write their notes
into: `NOTES.md`, `RESOURCES.md`, `COURSE-GENERATION-SPEC.md` and the
`learning-records/` folder.  Reading a file hands out its fingerprint, so
an editor can send that fingerprint back when it saves.  A save whose
fingerprint does not match what is on the disk any more is refused, the
same way a chapter is.

Before a file is replaced, the old content is copied into
`.agent-history/<ts>/` of the course, so a change can be taken back.

The courses root is not read here: the caller decides where the courses
live, the same way `app.courses.common` does it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.courses.common import (
    ConcurrencyConflict,
    HISTORY_DIRECTORY,
    _safe_child,
    content_hash,
    snapshot_file,
    write_text_atomic,
)

WORKSPACE_DIRECTORY = "workspace"

EDITABLE_SUFFIXES = frozenset({".md", ".txt", ".json", ".yaml", ".yml"})


def resolve_workspace_path(course_root: Path, name: str) -> Path:
    """Return the file of one workspace entry, refusing anything else.

    The name is a path inside the workspace folder.  A name that leaves the
    workspace is refused, and so is a name that points into the history of
    the course: the history is written by the editor, never by a person.

    Args:
        course_root: The folder of one course, for example
            courses/python-101/.
        name: The name of the workspace file, for example "NOTES.md".

    Returns:
        The path of the file.  The file itself does not have to exist yet.
        Raises ValueError("Workspace 文件路径不合法") when the name is empty
        or points into the history, ValueError("文件路径越界") when the name
        points outside the workspace, and ValueError("该文件不支持在线编辑")
        when the file is not one the editor can write.
    """
    if not name or not name.strip():
        raise ValueError("Workspace 文件路径不合法")
    if HISTORY_DIRECTORY in Path(name).parts:
        raise ValueError("Workspace 文件路径不合法")

    workspace_root = (course_root.resolve() / WORKSPACE_DIRECTORY).resolve()
    try:
        path = _safe_child(workspace_root, name)
    except ValueError as error:
        raise ValueError("文件路径越界") from error

    if path.suffix.lower() not in EDITABLE_SUFFIXES:
        raise ValueError("该文件不支持在线编辑")
    return path


def _updated_at(path: Path) -> str:
    """Return the moment a file was changed the last time.

    Args:
        path: The file to look at, for example
            courses/python-101/workspace/NOTES.md.

    Returns:
        The time as a timezone aware ISO 8601 string, for example
        "2026-10-27T08:31:05.123456+00:00".
    """
    return datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()


def read_workspace_file(course_root: Path, name: str) -> dict[str, Any]:
    """Read one file of the workspace of a course.

    Args:
        course_root: The folder of one course, for example
            courses/python-101/.
        name: The name of the workspace file, for example "NOTES.md".

    Returns:
        The name, the path, the content, the fingerprint of the content,
        the size of the file and the moment it was changed the last time.
        Raises ValueError when the name is empty, points outside the
        workspace or names a file the editor cannot write, and
        FileNotFoundError when there is no such file.
    """
    path = resolve_workspace_path(course_root, name)
    if not path.is_file():
        raise FileNotFoundError(f"文件不存在：{name}")
    content = path.read_text(encoding="utf-8")
    root = course_root.resolve()
    return {
        "name": name,
        "path": path.relative_to(root).as_posix(),
        "content": content,
        "content_hash": content_hash(content),
        "size": path.stat().st_size,
        "updated_at": _updated_at(path),
    }


def save_workspace_file(
    course_root: Path,
    name: str,
    content: str,
    expected_hash: str,
) -> dict[str, Any]:
    """Write one file of the workspace, but only when nobody else changed it.

    The fingerprint the caller read has to match the fingerprint of the
    file on the disk.  When it does not, the write is refused and the file
    stays as it is: the person who is behind has to look at both versions
    before they decide which one wins.

    Args:
        course_root: The folder of one course, for example
            courses/python-101/.
        name: The name of the workspace file, for example "NOTES.md".
        content: The new content of the file.
        expected_hash: The fingerprint the caller read, for example the
            `content_hash` a read handed out.

    Returns:
        The file as it is after the save: the name, the path, the new
        content, its fingerprint, the size of the file, the moment it was
        changed and the path of the snapshot of the content that was
        replaced.
        Raises ValueError when the name is empty, points outside the
        workspace or names a file the editor cannot write,
        FileNotFoundError when there is no such file, and
        ConcurrencyConflict when the fingerprint does not match.
    """
    path = resolve_workspace_path(course_root, name)
    root = course_root.resolve()
    relative = path.relative_to(root).as_posix()

    current = path.read_text(encoding="utf-8") if path.is_file() else ""
    if content_hash(current) != expected_hash:
        raise ConcurrencyConflict("内容已被其他编辑器修改，请刷新并比较后再保存")

    snapshot = snapshot_file(root, path, relative)
    write_text_atomic(path, content)

    saved = read_workspace_file(course_root, name)
    saved["snapshot_path"] = snapshot.relative_to(root).as_posix()
    return saved
