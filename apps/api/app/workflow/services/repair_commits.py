"""Candidate-commit helpers shared by deterministic repair stages."""
from __future__ import annotations

import hashlib
from typing import Any, Callable

from app.workflow.services.artifact_commits import (
    commit_chapter_candidate,
    verify_chapter_candidate,
)


def commit_deterministic_repair(
    *,
    course_slug: str,
    relative_path: str,
    original_markdown: str,
    repaired_markdown: str,
    reason: str,
    run_id: str,
    operations: list[str],
    source_contract: Callable[[], dict[str, Any]],
) -> dict[str, Any] | None:
    """Persist deterministic edits before later optional model operations."""
    content = repaired_markdown.rstrip() + "\n"
    if content == original_markdown:
        return None
    candidate = commit_chapter_candidate(
        course_slug=course_slug,
        relative_path=relative_path,
        content=content,
        expected_hash=hashlib.sha256(original_markdown.encode("utf-8")).hexdigest(),
        reason=reason,
        run_id=run_id,
    )
    contract = source_contract()
    if contract.get("succeeded"):
        verify_chapter_candidate(
            candidate["id"],
            {
                "gate": "deterministic_repair",
                "source_revision": contract.get("source_revision"),
                "operations": operations,
            },
        )
    return {
        "candidate_id": candidate["id"],
        "content": content,
        "source_contract_passed": bool(contract.get("succeeded")),
    }
