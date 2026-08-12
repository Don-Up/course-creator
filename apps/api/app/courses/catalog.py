from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.courses.common import _safe_course_root, _write_json_atomic
from app.courses.quality import load_course_quality_snapshot
from app.db import utcnow

TITLE_FALLBACKS = {
    "langchain-langgraph-from-beginner-to-advanced": "LangChain + LangGraph 从入门到进阶",
}
def _first_heading(path: Path) -> str | None:
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^#\s+(.+)$", line)
        if match:
            return match.group(1).strip()
    return None


def _infer_lessons(root: Path) -> list[dict[str, Any]]:
    candidates = sorted((root / "lessons").glob("*.md"))
    if not candidates:
        candidates = sorted((root / "markdown").glob("*.md"))
    lessons: list[dict[str, Any]] = []
    for index, path in enumerate(candidates, start=1):
        if path.name.startswith("course"):
            continue
        title = _first_heading(path) or path.stem
        number_match = re.match(r"^0*(\d+)", path.stem)
        number = int(number_match.group(1)) if number_match else index
        lessons.append(
            {
                "number": number,
                "title": re.sub(r"^第\s*\d+\s*章[　\s]*", "", title),
                "summary": "",
                "status": "available",
                "markdown": str(path.relative_to(root)),
                "href": "",
            }
        )
    return lessons


def _load_descriptor(root: Path) -> dict[str, Any]:
    metadata_path = root / "course.json"
    metadata: dict[str, Any] = {}
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    stored_lessons = metadata.get("allLessons") or metadata.get("lessons") or []
    # A batch writes each Markdown source as soon as that chapter clears its
    # chapter-level gates, while course.json is synchronized at the end of the
    # batch. Merge the filesystem view so a just-finished chapter is readable
    # in the UI immediately instead of waiting for its neighbours.
    inferred_lessons = _infer_lessons(root)
    known_markdown = {str(item.get("markdown", "")) for item in stored_lessons}
    known_numbers = {item.get("number") for item in stored_lessons}
    lessons = [
        *stored_lessons,
        *[
            item
            for item in inferred_lessons
            if item.get("markdown") not in known_markdown
            and item.get("number") not in known_numbers
        ],
    ]
    title = (
        metadata.get("title")
        or TITLE_FALLBACKS.get(root.name)
        or _first_heading(root / "workspace" / "MISSION.md")
        or root.name
    )
    available = [item for item in lessons if item.get("markdown")]
    quality_files = (
        list((root / "quality").glob("*.md")) if (root / "quality").exists() else []
    )
    return {
        "slug": root.name,
        "title": title,
        "description": metadata.get("description", ""),
        "status": metadata.get("status", "workspace"),
        "duration": metadata.get("duration", ""),
        "chapter_count": len(available),
        "quality_report_count": len(quality_files),
        "has_workspace": (root / "workspace").is_dir(),
        "has_course_json": metadata_path.exists(),
        "workflow_run_id": metadata.get("workflow_run_id"),
        "lessons": available,
    }


def list_courses() -> list[dict[str, Any]]:
    settings = get_settings()
    courses = []
    for root in sorted(settings.courses_root.iterdir()):
        if root.is_dir() and not root.name.startswith("."):
            courses.append(_load_descriptor(root))
    return courses


def get_course(slug: str) -> dict[str, Any]:
    root = _safe_course_root(slug)
    if not root.is_dir():
        raise FileNotFoundError(slug)
    descriptor = _load_descriptor(root)
    descriptor["workspace_files"] = (
        [str(path.relative_to(root)) for path in sorted((root / "workspace").glob("*.md"))]
        if (root / "workspace").exists()
        else []
    )
    descriptor["course_quality_snapshot"] = load_course_quality_snapshot(root)
    return descriptor


def publish_course(slug: str, *, workflow_run_id: str | None = None) -> dict[str, Any]:
    """Commit the user-approved release to course metadata and catalog."""
    root = _safe_course_root(slug)
    metadata_path = root / "course.json"
    if not metadata_path.is_file():
        raise FileNotFoundError("course.json")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("课程元数据无法读取，无法发布") from error
    if not isinstance(metadata, dict):
        raise ValueError("课程元数据格式不合法，无法发布")

    published_at = utcnow()
    metadata["status"] = "published"
    metadata["published_at"] = published_at
    metadata["publication"] = {
        "status": "published",
        "published_at": published_at,
        "workflow_run_id": workflow_run_id or metadata.get("workflow_run_id"),
    }
    _write_json_atomic(metadata_path, metadata)

    catalog_path = root.parent / "catalog.json"
    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        catalog = {"schemaVersion": 1, "courses": []}
    if not isinstance(catalog, dict):
        catalog = {"schemaVersion": 1, "courses": []}
    entries = catalog.get("courses")
    if not isinstance(entries, list):
        entries = []
    lessons = metadata.get("allLessons") or metadata.get("lessons") or []
    entry = {
        "slug": slug,
        "title": metadata.get("title") or slug,
        "description": metadata.get("description") or "",
        "href": f"./{slug}/index.html",
        "chapters": len(lessons),
        "duration": metadata.get("duration") or "",
        "status": "published",
    }
    matching = next(
        (index for index, value in enumerate(entries) if isinstance(value, dict) and value.get("slug") == slug),
        None,
    )
    if matching is None:
        entries.append(entry)
    else:
        entries[matching] = {**entries[matching], **entry}
    catalog["schemaVersion"] = catalog.get("schemaVersion", 1)
    catalog["courses"] = entries
    _write_json_atomic(catalog_path, catalog)
    return get_course(slug)
