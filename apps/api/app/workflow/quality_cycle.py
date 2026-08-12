"""Checkpoint-safe convergence state for the course-wide quality loop.

This module is deliberately pure. LangGraph nodes may stop between any two
operations and persist this JSON-serializable state without replaying a model
call or trusting historical prose as current quality evidence.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal


ESCALATION_LEVELS = ("deterministic", "llm_patch", "section_rewrite", "chapter_rewrite")
PHASE_ORDER = {
    "TITLE_MISSING": 0,
    "INTRO_NON_CANONICAL": 1,
    "REFERENCE_SECTION_MISSING": 2,
}


def _queue_task_id(item: dict[str, Any], issue: str, index: int) -> str:
    task_ids = [str(value) for value in item.get("task_ids", []) if str(value)]
    if index < len(task_ids):
        return task_ids[index]
    identity = "|".join(
        (
            str(item.get("path") or ""),
            str(item.get("chapter") or ""),
            issue,
        )
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]


def merge_repair_queue(
    queue: list[dict[str, Any]],
    discovered: list[dict[str, Any]],
    *,
    attempts: dict[str, int],
    max_attempts: int,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """Merge issue-granular tasks into chapter-granular repair sweeps.

    RepairTask identity and attempt limits remain issue-granular, while the
    execution queue groups all active tasks for the same chapter and path.
    This lets a repair node apply every known patch before running expensive
    chapter-wide quality gates once.
    """
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    order: list[tuple[str, str]] = []
    known: set[str] = set()
    added: list[str] = []
    deferred: list[str] = []

    def append_item(item: dict[str, Any], *, report_addition: bool) -> None:
        key = (str(item.get("chapter") or ""), str(item.get("path") or ""))
        if key not in grouped:
            grouped[key] = {
                **item,
                "issues": [],
                "task_ids": [],
                "repair_agents": [],
                "contract_diagnostics": [],
            }
            order.append(key)
        group = grouped[key]
        for agent in item.get("repair_agents", []):
            if agent not in group["repair_agents"]:
                group["repair_agents"].append(agent)
        for diagnostic in item.get("contract_diagnostics", []):
            if diagnostic not in group["contract_diagnostics"]:
                group["contract_diagnostics"].append(diagnostic)
        issues = [str(value) for value in item.get("issues", []) if str(value)]
        for index, issue in enumerate(issues):
            task_id = _queue_task_id(item, issue, index)
            if task_id in known:
                continue
            if int(attempts.get(task_id, 0)) >= max_attempts:
                deferred.append(task_id)
                continue
            known.add(task_id)
            group["issues"].append(issue)
            group["task_ids"].append(task_id)
            if report_addition:
                added.append(task_id)

    for item in queue:
        append_item(item, report_addition=False)
    for item in discovered:
        append_item(item, report_addition=True)
    merged = [grouped[key] for key in order if grouped[key]["task_ids"]]
    return merged, added, deferred


def merge_same_cycle_discoveries(
    queue: list[dict[str, Any]],
    discovered: list[dict[str, Any]],
    *,
    attempts: dict[str, int],
    max_attempts: int,
    discovery_sweeps: int,
    max_discovery_sweeps: int,
) -> tuple[list[dict[str, Any]], list[str], list[str], int]:
    """Bound feedback discoveries that would otherwise keep one cycle alive.

    A RepairTask can already have its own retry budget. This is a separate
    cycle-level budget for newly discovered tasks: after the allowed number of
    re-entry sweeps, findings are handed to human review instead of reopening
    the queue indefinitely.
    """
    if discovered and discovery_sweeps >= max_discovery_sweeps:
        deferred = list(dict.fromkeys(
            str(task_id)
            for item in discovered
            for task_id in item.get("task_ids", [])
            if str(task_id)
        ))
        return queue, [], deferred, discovery_sweeps
    merged, added, deferred = merge_repair_queue(
        queue, discovered, attempts=attempts, max_attempts=max_attempts
    )
    return (
        merged,
        added,
        deferred,
        discovery_sweeps + (1 if added else 0),
    )


def chapter_repair_sweep_tasks(
    item: dict[str, Any], *, active_task_ids: list[str]
) -> list[dict[str, str]]:
    """Return aligned RepairTasks for one chapter-level execution sweep."""
    issues = [str(value) for value in item.get("issues", [])]
    task_ids = [str(value) for value in item.get("task_ids", [])]
    issue_by_task = {
        task_id: issues[index] if index < len(issues) else "质量问题"
        for index, task_id in enumerate(task_ids)
    }
    return [
        {"task_id": task_id, "issue": issue_by_task.get(task_id, "质量问题")}
        for task_id in active_task_ids
    ]


def detect_quality_regressions(
    *, before: dict[str, Any], after: dict[str, Any]
) -> list[str]:
    """Return newly-failing gates that a targeted repair is not allowed to commit."""
    regressions: list[str] = []
    before_minimum = int(before.get("effective_char_min") or 0)
    after_minimum = int(after.get("effective_char_min") or before_minimum)
    before_chars = int(before.get("effective_chars") or 0)
    after_chars = int(after.get("effective_chars") or 0)
    if before_minimum and before_chars >= before_minimum and after_chars < after_minimum:
        regressions.append(
            f"有效字符从通过回退为未通过（{before_chars} → {after_chars}）"
        )
    before_humanizer = before.get("humanizer_score")
    after_humanizer = after.get("humanizer_score")
    if (
        isinstance(before_humanizer, (int, float))
        and before_humanizer >= 45
        and isinstance(after_humanizer, (int, float))
        and after_humanizer < 45
    ):
        regressions.append(
            f"Humanizer 从通过回退为未通过（{before_humanizer} → {after_humanizer}）"
        )
    # A semantic review is an open-ended discovery pass, not a deterministic
    # transaction invariant. Different valid reviews can surface a new issue
    # after a targeted patch; those findings belong in the current repair
    # cycle, while rolling back the patch would recreate the issue just fixed.
    new_codes = sorted(
        set(str(value) for value in after.get("contract_codes", []))
        - set(str(value) for value in before.get("contract_codes", []))
    )
    if new_codes:
        regressions.append(f"新增 Markdown 结构违规：{'、'.join(new_codes)}")
    return regressions


def refund_legacy_semantic_rollback_attempts(
    attempts: dict[str, int],
    tasks: list[dict[str, Any]],
    *,
    already_refunded: list[str],
) -> tuple[dict[str, int], list[str]]:
    """Refund attempts consumed by the removed semantic rollback rule once."""
    updated = dict(attempts)
    refunded = list(already_refunded)
    refunded_set = set(refunded)
    marker = "教学语义与事实审校从通过回退为未通过"
    for task in tasks:
        task_id = str(task.get("id") or "")
        if not task_id or task_id in refunded_set:
            continue
        verification = task.get("verification") or {}
        historical_issues = verification.get("remaining_issues") or []
        if not any(marker in str(issue) for issue in historical_issues):
            continue
        updated[task_id] = max(0, int(updated.get(task_id, 0)) - 1)
        refunded.append(task_id)
        refunded_set.add(task_id)
    return updated, refunded


def diagnostic_fingerprint(diagnostic: dict[str, Any], course_slug: str = "") -> str:
    identity = [
        course_slug,
        str(diagnostic.get("path") or ""),
        str(diagnostic.get("code") or ""),
        str(diagnostic.get("node_id") or diagnostic.get("nodeId") or ""),
        str(diagnostic.get("actual") or ""),
    ]
    return hashlib.sha256("|".join(identity).encode("utf-8")).hexdigest()[:32]


def _task(diagnostic: dict[str, Any], course_slug: str, cycle_id: str) -> dict[str, Any]:
    code = str(diagnostic.get("code") or "UNKNOWN")
    return {
        "id": diagnostic_fingerprint(diagnostic, course_slug),
        "cycle_id": cycle_id,
        "code": code,
        "path": str(diagnostic.get("path") or ""),
        "node_id": diagnostic.get("node_id") or diagnostic.get("nodeId"),
        "actual": str(diagnostic.get("actual") or ""),
        "severity": str(diagnostic.get("severity") or "error"),
        "line": int(diagnostic.get("line") or 1),
        "success_criteria": list(diagnostic.get("success_criteria") or diagnostic.get("successCriteria") or []),
        "candidates": list(diagnostic.get("candidates") or []),
        "status": "detected",
        "escalation_level": "deterministic",
        "attempt_count": 0,
        "verification": None,
    }


def _sort_queue(queue: list[dict[str, Any]]) -> list[dict[str, Any]]:
    severity = {"error": 0, "blocker": 0, "warning": 1, "major": 1, "minor": 2}
    return sorted(
        queue,
        key=lambda item: (
            severity.get(str(item.get("severity")), 3),
            PHASE_ORDER.get(str(item.get("code")), 50),
            str(item.get("path") or ""),
            int(item.get("line") or 0),
        ),
    )


def _progress_hash(state: dict[str, Any], lesson_hashes: list[dict[str, Any]] | None = None) -> str:
    value = {
        "open": [item["id"] for item in state.get("queue", [])],
        "files": sorted(
            (str(item.get("path") or ""), str(item.get("hash") or ""))
            for item in lesson_hashes or []
        ),
    }
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest()


def start_quality_cycle(
    cycle_id: str,
    diagnostics: list[dict[str, Any]],
    *,
    course_slug: str = "",
) -> dict[str, Any]:
    state = {
        "cycle_id": cycle_id,
        "course_slug": course_slug,
        "iteration": 1,
        "queue": _sort_queue([_task(item, course_slug, cycle_id) for item in diagnostics]),
        "history": [],
        "new_issue_count": len(diagnostics),
        "no_progress_count": 0,
        "escalation_level": "deterministic",
        "source_gate": {"passed": not diagnostics},
        "build_gate": {"passed": False},
        "artifact_gate": {"passed": False},
    }
    state["progress_hash"] = _progress_hash(state)
    return state


def mark_task_verified(
    state: dict[str, Any], task_id: str, *, verification: dict[str, Any] | None
) -> dict[str, Any]:
    required = {"diagnostic_code", "outcome", "source_revision", "verified_at"}
    if not verification or not required.issubset(verification) or verification.get("outcome") != "passed":
        raise ValueError("RepairTask 只有规则复验通过并附带完整证据后才能关闭")
    next_state = {**state, "queue": [dict(item) for item in state.get("queue", [])], "history": list(state.get("history", []))}
    found = False
    remaining = []
    for task in next_state["queue"]:
        if task.get("id") != task_id:
            remaining.append(task)
            continue
        found = True
        if verification["diagnostic_code"] != task.get("code"):
            raise ValueError("规则复验诊断码与 RepairTask 不一致")
        next_state["history"].append({**task, "status": "fixed_verified", "verification": verification})
    if not found:
        raise KeyError(task_id)
    next_state["queue"] = remaining
    return next_state


def merge_contract_report(state: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    next_state = {
        **state,
        "iteration": int(state.get("iteration", 0)) + 1,
        "history": list(state.get("history", [])),
    }
    course_slug = str(state.get("course_slug") or "")
    current = {item["id"]: dict(item) for item in state.get("queue", [])}
    seen: dict[str, dict[str, Any]] = {}
    new_count = 0
    for diagnostic in report.get("diagnostics") or []:
        candidate = _task(diagnostic, course_slug, str(state["cycle_id"]))
        task_id = candidate["id"]
        if task_id in current:
            candidate = {**current[task_id], **candidate, "status": current[task_id].get("status", "detected")}
        else:
            # A diagnostic that reappears after a prior verification is a new
            # live task in the same cycle, not a silently trusted old result.
            new_count += 1
        seen[task_id] = candidate
    for task_id, task in current.items():
        if task_id not in seen:
            next_state["history"].append({
                **task,
                "status": "stale_evidence",
                "verification": {"outcome": "absent_in_fresh_full_scan"},
            })
    next_state["queue"] = _sort_queue(list(seen.values()))
    next_state["new_issue_count"] = new_count
    next_state["source_gate"] = {"passed": not next_state["queue"]}
    progress = _progress_hash(next_state, report.get("lessons") or [])
    next_state["no_progress_count"] = (
        int(state.get("no_progress_count", 0)) + 1
        if progress == state.get("progress_hash") else 0
    )
    next_state["progress_hash"] = progress
    return next_state


def plan_escalation(task: dict[str, Any], *, previous: str) -> dict[str, Any]:
    if previous == "deterministic":
        level = "llm_patch"
    elif previous == "llm_patch":
        level = "section_rewrite"
    elif previous == "section_rewrite" and task.get("structural_damage"):
        level = "chapter_rewrite"
    else:
        level = "pause"
    required_gates = ["source_contract"]
    if level == "chapter_rewrite":
        required_gates = [
            "effective_chars", "humanizer", "semantic", "continuity", "source_contract", "build"
        ]
    return {"level": level, "required_gates": required_gates}


def next_cycle_action(
    state: dict[str, Any],
) -> Literal["repair", "rescan", "build", "escalate", "pause", "release"]:
    if state.get("queue"):
        if int(state.get("no_progress_count", 0)) >= 2:
            escalation = plan_escalation(
                state["queue"][0], previous=str(state.get("escalation_level") or "deterministic")
            )
            return "escalate" if escalation["level"] != "pause" else "pause"
        return "repair"
    if not (state.get("source_gate") or {}).get("passed"):
        return "rescan"
    if not (state.get("build_gate") or {}).get("passed"):
        return "build"
    if not (state.get("artifact_gate") or {}).get("passed"):
        return "rescan"
    return "release"
