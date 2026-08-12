from __future__ import annotations

import json

from app.config import get_settings


_RESUMABLE_RUN_STATUSES = {"QUEUED", "RUNNING", "WAITING_APPROVAL", "FAILED"}


def is_creation_run(course: dict, run: dict) -> bool:
    request = run.get("request") or {}
    if request.get("workflow_scope") == "new_course":
        return True
    if course.get("workflow_run_id") == run.get("id"):
        return True
    return (
        request.get("slug") == course.get("slug")
        and {"audience", "goals", "scope", "delivery"}.issubset(request)
    )


def find_resumable_creation_run(course: dict, runs: list[dict]) -> dict | None:
    return next(
        (
            run
            for run in runs
            if run["status"] in _RESUMABLE_RUN_STATUSES and is_creation_run(course, run)
        ),
        None,
    )


def attach_resumable_creation_run(course: dict, runs: list[dict]) -> dict:
    """Expose an unfinished creation Run independently of course status."""
    candidate = find_resumable_creation_run(course, runs)
    course["resumable_run_id"] = candidate["id"] if candidate else None
    course["resumable_run_step"] = (
        "generation"
        if candidate and candidate["current_step"] == "quality" and is_creation_run(course, candidate)
        else candidate["current_step"] if candidate else None
    )
    return course


def persist_primary_workflow_run(slug: str, run_id: str) -> None:
    path = get_settings().courses_root / slug / "course.json"
    metadata = json.loads(path.read_text(encoding="utf-8"))
    metadata["workflow_run_id"] = run_id
    path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
