from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.courses.common import _write_json_atomic
from app.db import utcnow

def load_course_quality_snapshot(root: Path) -> dict[str, Any]:
    path = root / "quality" / "course-quality-snapshot.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        value = {}
    if not isinstance(value, dict):
        value = {}
    return {
        "revision": value.get("revision") if isinstance(value.get("revision"), str) else None,
        "chapters": value.get("chapters") if isinstance(value.get("chapters"), list) else [],
        "course_integration": value.get("course_integration") if isinstance(value.get("course_integration"), dict) else {},
        "source_contract_gate": value.get("source_contract_gate") if isinstance(value.get("source_contract_gate"), dict) else {},
        "build_gate": value.get("build_gate") if isinstance(value.get("build_gate"), dict) else {},
        "artifact_gate": value.get("artifact_gate") if isinstance(value.get("artifact_gate"), dict) else {},
        "quality_cycle": value.get("quality_cycle") if isinstance(value.get("quality_cycle"), dict) else {},
    }


def write_course_quality_snapshot(
    course_root: Path,
    batch_results: list[dict[str, Any]],
    *,
    repair_tasks: list[dict[str, Any]] | None = None,
    course_integration: dict[str, Any] | None = None,
    source_contract: dict[str, Any] | None = None,
    build: dict[str, Any] | None = None,
    artifact_validation: dict[str, Any] | None = None,
    quality_cycle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist the one current quality fact base used by all course views."""
    # Several evidence items can belong to one chapter. An open task must
    # remain visible even if another, older task for that chapter was already
    # verified; otherwise the UI would incorrectly announce that repair is
    # finished. When all tasks are closed, retain the latest status.
    task_status: dict[int, str] = {}
    closed_task_statuses = {"fixed_verified", "fixed_static_only", "stale_evidence"}
    for task in repair_tasks or []:
        chapter = task.get("chapter")
        if not isinstance(chapter, int):
            continue
        status = str(task.get("status") or "detected")
        previous = task_status.get(chapter)
        if previous is None or (
            previous in closed_task_statuses and status not in closed_task_statuses
        ):
            task_status[chapter] = status
    # ``batch_results`` is append-only workflow history. A retry therefore
    # produces another record for the same batch id. The snapshot must never
    # show both the failed first attempt and the repaired current attempt.
    latest_by_batch: dict[str, dict[str, Any]] = {}
    unkeyed_results: list[dict[str, Any]] = []
    for result in batch_results:
        batch = result.get("batch") or {}
        batch_id = batch.get("id")
        if isinstance(batch_id, str) and batch_id:
            latest_by_batch[batch_id] = result
        else:
            unkeyed_results.append(result)

    chapters_by_number: dict[int, dict[str, Any]] = {}
    for result in [*unkeyed_results, *latest_by_batch.values()]:
        batch = result.get("batch") or {}
        gates = result.get("quality_gates") or {}
        integration = (gates.get("stage_3_batch_integration") or {}).get("passed")
        for chapter in result.get("chapters") or []:
            number = chapter.get("chapter")
            if not isinstance(number, int):
                continue
            semantic = chapter.get("semantic_review") or {}
            chapters_by_number[number] = {
                "chapter": number,
                "path": str(chapter.get("path") or ""),
                "effective_chars": chapter.get("effective_chars"),
                "effective_char_min": chapter.get("effective_char_min"),
                "humanizer_score": chapter.get("humanizer_score"),
                "semantic_decision": semantic.get("decision"),
                "chapter_passed": bool(chapter.get("passed")),
                "batch_id": batch.get("id"),
                "batch_integration_passed": integration if isinstance(integration, bool) else None,
                "repair_status": task_status.get(number),
                "updated_at": utcnow(),
            }
    revision = utcnow()
    payload = {
        "revision": revision,
        "chapters": sorted(chapters_by_number.values(), key=lambda item: item["chapter"]),
        "course_integration": dict(course_integration or {}),
        "source_contract_gate": dict(source_contract or {}),
        "build_gate": dict(build or {}),
        "artifact_gate": dict(artifact_validation or {}),
        "quality_cycle": dict(quality_cycle or {}),
    }
    for chapter in payload["chapters"]:
        chapter["course_integration_passed"] = payload["course_integration"].get("passed")
    _write_json_atomic(course_root / "quality" / "course-quality-snapshot.json", payload)
    return payload
