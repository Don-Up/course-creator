"""Immutable chapter artifacts and optimistic workspace commits.

The lesson file remains the student-facing Markdown source of truth.  This
adapter makes every Agent or human mutation create an immutable copy first,
then updates that source atomically only when the expected base revision still
matches.  It deliberately does not make SQLite and the filesystem pretend to
be one transaction: an interrupted write leaves an inspectable candidate and
the next attempt is protected by the content hash.
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.courses.common import _safe_child, _safe_course_root, content_hash
from app.db import database, row_to_dict, utcnow
from app.workflow.execution_context import current_execution


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(content)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def _artifact_directory(run_id: str | None, artifact_id: str) -> Path:
    return get_settings().data_root / "artifacts" / (run_id or "manual") / artifact_id


def commit_chapter_candidate(
    *,
    course_slug: str,
    relative_path: str,
    content: str,
    expected_hash: str | None,
    reason: str,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Persist a candidate before atomically making it the current draft.

    ``expected_hash`` is the only authority for replacing an existing lesson.
    A mismatch is a real concurrent-edit conflict, never an implicit overwrite.
    """
    root = _safe_course_root(course_slug)
    target = _safe_child(root, relative_path)
    target_exists = target.exists()
    current_content = target.read_text(encoding="utf-8") if target_exists else ""
    current_hash = content_hash(current_content)
    if expected_hash is not None and current_hash != expected_hash:
        raise RuntimeError("章节已发生变化，请刷新后重新执行本次修改")

    artifact_id = str(uuid.uuid4())
    value_hash = content_hash(content)
    execution = current_execution.get()
    producer_execution_id = execution.node_execution_id if execution else None
    scope = {"course_slug": course_slug, "path": relative_path}
    directory = _artifact_directory(run_id, artifact_id)
    content_path = directory / "content.md"
    _atomic_write(content_path, content)
    metadata = {
        "id": artifact_id,
        "artifact_type": "chapter_candidate",
        "schema_version": "1.0",
        "content_hash": value_hash,
        "scope": scope,
        "base_content_hash": current_hash if target_exists else None,
        "reason": reason,
        "producer_execution_id": producer_execution_id,
        "created_at": utcnow(),
    }
    _atomic_write(directory / "metadata.json", json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")

    storage_uri = str(content_path.relative_to(get_settings().data_root))
    with database() as connection:
        parent = connection.execute(
            "SELECT id FROM artifacts WHERE artifact_type = 'chapter_candidate' AND scope_json = ? AND is_current = 1",
            (json.dumps(scope, ensure_ascii=False, sort_keys=True),),
        ).fetchone()
        now = utcnow()
        connection.execute(
            """INSERT INTO artifacts (
                id, run_id, artifact_type, schema_version, content_hash, storage_uri,
                producer_execution_id, scope_json, sensitivity, base_content_hash,
                status, is_current, created_at, updated_at
            ) VALUES (?, ?, 'chapter_candidate', '1.0', ?, ?, ?, ?, 'internal', ?, 'CANDIDATE', 1, ?, ?)""",
            (artifact_id, run_id, value_hash, storage_uri, producer_execution_id,
             json.dumps(scope, ensure_ascii=False, sort_keys=True),
             current_hash if target_exists else None, now, now),
        )
        connection.execute(
            "UPDATE artifacts SET is_current = 0, updated_at = ? WHERE artifact_type = 'chapter_candidate' AND scope_json = ? AND id != ?",
            (now, json.dumps(scope, ensure_ascii=False, sort_keys=True), artifact_id),
        )
        if parent:
            connection.execute(
                "INSERT OR IGNORE INTO artifact_edges (parent_artifact_id, child_artifact_id, relation, created_at) VALUES (?, ?, 'supersedes', ?)",
                (parent["id"], artifact_id, now),
            )
    _atomic_write(target, content)
    return {
        "id": artifact_id,
        "content_hash": value_hash,
        "base_content_hash": current_hash if target_exists else None,
        "storage_uri": storage_uri,
        "status": "CANDIDATE",
    }


def verify_chapter_candidate(artifact_id: str, evidence: dict[str, Any]) -> None:
    with database() as connection:
        cursor = connection.execute(
            "UPDATE artifacts SET status = 'VERIFIED', verification_json = ?, updated_at = ? WHERE id = ? AND status = 'CANDIDATE'",
            (json.dumps(evidence, ensure_ascii=False, default=str), utcnow(), artifact_id),
        )
    if cursor.rowcount != 1:
        raise KeyError(f"候选章节 Artifact 不存在或已不是待验证状态：{artifact_id}")


def reject_chapter_candidate(artifact_id: str, evidence: dict[str, Any]) -> None:
    with database() as connection:
        connection.execute(
            "UPDATE artifacts SET status = 'REJECTED', is_current = 0, verification_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(evidence, ensure_ascii=False, default=str), utcnow(), artifact_id),
        )


def get_chapter_artifact(artifact_id: str) -> dict[str, Any] | None:
    with database() as connection:
        return row_to_dict(connection.execute("SELECT * FROM artifacts WHERE id = ?", (artifact_id,)).fetchone())
