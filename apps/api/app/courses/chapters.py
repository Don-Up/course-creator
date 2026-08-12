from __future__ import annotations

import json
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.courses.catalog import get_course
from app.courses.common import _safe_child, _safe_course_root, content_hash
from app.db import database, utcnow
from app.workflow.services.artifact_commits import commit_chapter_candidate

def _chapter_from_key(course: dict[str, Any], key: str) -> dict[str, Any]:
    for lesson in course["lessons"]:
        candidates = {
            str(lesson.get("number", "")),
            lesson.get("code", ""),
            lesson.get("markdown", ""),
            Path(lesson.get("markdown", "")).stem,
        }
        if key in candidates:
            return lesson
    raise FileNotFoundError(key)


def get_chapter(slug: str, key: str) -> dict[str, Any]:
    root = _safe_course_root(slug)
    course = get_course(slug)
    lesson = _chapter_from_key(course, key)
    path = _safe_child(root, lesson["markdown"])
    content = path.read_text(encoding="utf-8")
    return {
        "key": key,
        "number": lesson.get("number"),
        "code": lesson.get("code"),
        "title": lesson.get("title"),
        "summary": lesson.get("summary", ""),
        "path": lesson["markdown"],
        "content": content,
        "content_hash": content_hash(content),
        "updated_at": datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(),
    }


def get_course_asset(slug: str, path: str) -> Path:
    """Return an existing course asset without exposing other course files."""
    root = _safe_course_root(slug)
    assets_root = _safe_child(root, "assets")
    if not assets_root.is_dir():
        raise FileNotFoundError(path)
    if not path or Path(path).is_absolute():
        raise ValueError("课程素材路径必须位于 assets 目录内")
    asset = _safe_child(assets_root, path)
    if not asset.is_file():
        raise FileNotFoundError(path)
    return asset


def update_chapter(
    slug: str,
    key: str,
    new_content: str,
    expected_hash: str,
    reason: str,
) -> dict[str, Any]:
    current = get_chapter(slug, key)
    if current["content_hash"] != expected_hash:
        raise RuntimeError("章节已发生变化，请刷新后重新编辑")
    root = _safe_course_root(slug)
    source = _safe_child(root, current["path"])
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    snapshot = root / ".agent-history" / timestamp / current["path"]
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, snapshot)
    artifact = commit_chapter_candidate(
        course_slug=slug,
        relative_path=current["path"],
        content=new_content,
        expected_hash=expected_hash,
        reason=reason,
    )
    version_id = str(uuid.uuid4())
    with database() as connection:
        connection.execute(
            """
            INSERT INTO chapter_versions (
                id, course_slug, chapter_key, source_path, content_hash,
                snapshot_path, reason, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                version_id,
                slug,
                key,
                current["path"],
                current["content_hash"],
                str(snapshot.relative_to(root)),
                reason,
                utcnow(),
            ),
        )
    invalidation = root / "quality" / "agent-invalidations.jsonl"
    invalidation.parent.mkdir(parents=True, exist_ok=True)
    with invalidation.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "chapter": key,
                    "previousHash": current["content_hash"],
                    "newHash": content_hash(new_content),
                    "reason": reason,
                    "at": utcnow(),
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    updated = get_chapter(slug, key)
    updated["snapshot_path"] = str(snapshot.relative_to(root))
    updated["artifact_id"] = artifact["id"]
    return updated
