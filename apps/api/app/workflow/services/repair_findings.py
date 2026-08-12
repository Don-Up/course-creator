"""Compatibility handling for structured and legacy repair-queue findings."""
from __future__ import annotations

from typing import Any, Callable

from app.db import utcnow
from app.workflow.repair_tasks import split_quality_issues


def separate_repair_findings(
    *,
    raw_issues: list[str],
    task_ids: list[str],
    effective_chars: int | None,
    effective_char_min: int | None,
    accept_advisory: Callable[[str], None],
    record_incident: Callable[[str], None],
) -> tuple[list[str], list[str], list[str], list[str]]:
    """Close non-repair legacy entries and return only actionable task ids."""
    repairable, advisory, incidents = split_quality_issues(
        raw_issues,
        effective_chars=effective_chars,
        effective_char_min=effective_char_min,
    )
    task_id_by_issue = {
        issue: str(task_id)
        for issue, task_id in zip(raw_issues, task_ids)
        if str(task_id)
    }
    for issue in advisory:
        task_id = task_id_by_issue.get(issue)
        if task_id:
            accept_advisory(task_id)
    for issue in incidents:
        task_id = task_id_by_issue.get(issue)
        if task_id:
            accept_advisory(task_id)
        record_incident(issue)
    return (
        repairable,
        advisory,
        incidents,
        [task_id_by_issue[issue] for issue in repairable if issue in task_id_by_issue],
    )


def split_post_verification_findings(
    issues: list[str],
    *,
    effective_chars: int,
    effective_char_min: int,
) -> tuple[list[str], list[str], list[str]]:
    """Classify review output without mutating task state a second time."""
    repairable, advisory, incidents, _ = separate_repair_findings(
        raw_issues=issues,
        task_ids=[],
        effective_chars=effective_chars,
        effective_char_min=effective_char_min,
        accept_advisory=lambda _task_id: None,
        record_incident=lambda _issue: None,
    )
    return repairable, advisory, incidents
