"""Persistent, evidence-led quality repair tasks.

This module deliberately knows nothing about LangGraph.  It turns a quality
finding into a durable unit of work whose original evidence can be invalidated
when a later patch has already changed the relevant source text.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from typing import Any

from app.db import database, row_to_dict, utcnow


OPEN_STATUSES = {
    "detected",
    "planned",
    "patched",
    "verifying",
    "unresolved",
    "escalated",
    "verifying_rule",
    "escalation_required",
    "llm_patch",
    "section_rewrite",
    "chapter_rewrite",
}
CLOSED_STATUSES = {
    "fixed_verified",
    "fixed_static_only",
    "stale_evidence",
    "advisory_accepted",
}


def classify_quality_finding(
    issue: str,
    *,
    origin: str = "quality",
    effective_chars: int | None = None,
    effective_char_min: int | None = None,
) -> dict[str, str | bool]:
    """Classify a finding by its producer and verification contract.

    The producer is the authoritative signal for runtime incidents. Text only
    refines course findings that already came from a quality or contract
    producer, so a code example mentioning ``tool_call`` is never mistaken
    for an internal tool-runtime failure.
    """
    if origin == "operation":
        return {
            "finding_kind": "runtime",
            "blocking": False,
            "disposition": "incident",
        }
    if origin in {"source_contract", "build"} or re.search(
        r"\[(?:INTRO_NON_CANONICAL|REFERENCE_SECTION_MISSING|TITLE_MISSING|"
        r"EXTERNAL_LINK_BEFORE_REFERENCES|MARKDOWN_UNCLOSED_FENCE|"
        r"CONTENT_PRIVATE_PATH|METADATA_TARGET_MISSING)\]",
        issue,
    ):
        return {
            "finding_kind": "deterministic",
            "blocking": True,
            "disposition": "repair",
        }
    if origin in {"source_registration", "advisory"} or "[minor]" in issue.lower():
        return {
            "finding_kind": "quality",
            "blocking": False,
            "disposition": "advisory",
        }
    if (
        effective_chars is not None
        and effective_char_min
        and effective_chars < effective_char_min
        and (effective_char_min - effective_chars) / effective_char_min <= 0.05
    ):
        return {
            "finding_kind": "quality",
            "blocking": False,
            "disposition": "advisory",
        }
    return {
        "finding_kind": "quality",
        "blocking": True,
        "disposition": "repair",
    }


def _is_legacy_operation_failure(issue: str) -> bool:
    return issue.startswith(
        (
            "正文生成失败：",
            "内容丰富化失败：",
            "Humanizer 失败：",
            "语义审校失败：",
            "连续性账本提取失败：",
        )
    )


def split_quality_issues(
    issues: list[str],
    *,
    origin: str = "quality",
    effective_chars: int | None = None,
    effective_char_min: int | None = None,
) -> tuple[list[str], list[str], list[str]]:
    """Separate repairable findings from advisory notes and operation incidents.

    The prefix bridge only handles checkpoints produced before operation
    incidents had their own event path. New call sites should pass
    ``origin="operation"`` instead of relying on these legacy prefixes.
    """
    repairable: list[str] = []
    advisory: list[str] = []
    incidents: list[str] = []
    for issue in issues:
        finding = classify_quality_finding(
            issue,
            origin="operation" if _is_legacy_operation_failure(issue) else origin,
            effective_chars=effective_chars,
            effective_char_min=effective_char_min,
        )
        if finding["disposition"] == "repair":
            repairable.append(issue)
        elif finding["disposition"] == "incident":
            incidents.append(issue)
        else:
            advisory.append(issue)
    return repairable, advisory, incidents


def _severity(issue: str) -> str:
    lowered = issue.lower()
    if "[blocker]" in lowered or "阻塞" in issue:
        return "blocker"
    if "[major]" in lowered or "严重" in issue:
        return "major"
    return "minor"


def _category(issue: str) -> str:
    lowered = issue.lower()
    if any(token in issue for token in ("代码围栏", "章首", "外部链接", "本地链接", "私有路径")):
        return "markdown_format"
    if any(token in lowered for token in ("import", "nameerror", "foreignkey", "参数", "cli")):
        return "code_structure"
    if any(token in lowered for token in ("示例", "练习", "脚手架", "教学")):
        return "teaching_scaffold_gap"
    if any(token in lowered for token in ("事实", "api", "ragas", "配置", "运行")):
        return "runnable_example_gap"
    if "有效字符" in issue or "字数" in issue:
        return "content_enrichment"
    if "humanizer" in lowered:
        return "humanizer"
    return "quality_issue"


def _quoted_source(markdown: str, issue: str) -> str:
    grounded = re.search(r"证据[：:]\s*『([^』]+)』", issue)
    if grounded:
        return grounded.group(1).strip()[:800]
    if any(marker in issue for marker in (
        "确定性构建或校验未通过",
        "学生可见内容触发披露边界检查",
    )):
        # A generic build/validation error has no chapter-local source anchor.
        # Picking the longest prose line made its identity change whenever an
        # unrelated revision changed the body, which reset the bounded retry
        # budget. Keep it ungrounded until a fresh review supplies evidence.
        return ""
    lines = [line.strip() for line in markdown.splitlines() if line.strip() and not line.startswith("#")]
    return max(lines, key=len)[:800] if lines else markdown[:800]


def _success_criteria(category: str) -> list[str]:
    defaults = {
        "markdown_format": ["目标 Markdown 规则满足", "确定性检查通过"],
        "code_structure": ["涉及名称均已导入或定义", "代码结构检查通过"],
        "teaching_scaffold_gap": ["提供可模仿的最小示例", "练习有明确验收方式"],
        "runnable_example_gap": ["依赖与配置完整", "示例拥有可验证的运行说明"],
        "content_enrichment": ["满足章节有效字符约束", "补充内容保持教学连续性"],
        "humanizer": ["Humanizer 评分达到门槛"],
    }
    return defaults.get(category, ["原始问题不再可由当前正文复现", "相关质量门复核通过"])


def normalize_quality_issue(
    *, course_slug: str, run_id: str, batch_id: str | None, chapter: int | None,
    issue: str, path: str, markdown: str, origin: str = "quality",
    effective_chars: int | None = None, effective_char_min: int | None = None,
) -> dict[str, Any]:
    category = _category(issue)
    finding = classify_quality_finding(
        issue,
        origin=origin,
        effective_chars=effective_chars,
        effective_char_min=effective_char_min,
    )
    quote = _quoted_source(markdown, issue)
    fingerprint = "|".join(
        (
            course_slug,
            path,
            str(chapter or ""),
            category,
            str(finding["finding_kind"]),
            quote,
        )
    )
    task_id = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:32]
    return {
        "id": task_id,
        "run_id": run_id,
        "course_slug": course_slug,
        "batch_id": batch_id,
        "chapter": chapter,
        "category": category,
        "severity": _severity(issue),
        "finding_kind": finding["finding_kind"],
        "blocking": finding["blocking"],
        "disposition": finding["disposition"],
        "path": path,
        "issue": issue,
        "evidence": {"quoted_source": quote, "path": path, "chapter": chapter, "issue": issue},
        "success_criteria": _success_criteria(category),
        "status": "detected",
        "attempt_count": 0,
    }


def _task(row: Any) -> dict[str, Any]:
    item = row_to_dict(row) or {}
    item["verification"] = item.pop("latest_verification", None)
    return item


def create_or_refresh_task(draft: dict[str, Any]) -> dict[str, Any]:
    """Create a task or reuse its evidence identity without reopening closed work."""
    with database() as connection:
        existing = connection.execute("SELECT * FROM repair_tasks WHERE id = ?", (draft["id"],)).fetchone()
        if existing:
            return _task(existing)
        now = utcnow()
        connection.execute(
            """INSERT INTO repair_tasks (
                id, run_id, course_slug, batch_id, chapter, category, severity,
                finding_kind, blocking, disposition, path,
                issue, evidence_json, success_criteria_json, status, attempt_count,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                draft["id"], draft["run_id"], draft["course_slug"], draft.get("batch_id"),
                draft.get("chapter"), draft["category"], draft["severity"],
                draft["finding_kind"], int(bool(draft["blocking"])), draft["disposition"],
                draft["path"],
                draft["issue"], json.dumps(draft["evidence"], ensure_ascii=False),
                json.dumps(draft["success_criteria"], ensure_ascii=False), draft.get("status", "detected"),
                int(draft.get("attempt_count", 0)), now, now,
            ),
        )
        return _task(connection.execute("SELECT * FROM repair_tasks WHERE id = ?", (draft["id"],)).fetchone())


def refresh_evidence(task_id: str, markdown: str) -> dict[str, Any]:
    """Close evidence that a previous patch has made obsolete, without model calls."""
    with database() as connection:
        row = connection.execute("SELECT * FROM repair_tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            raise KeyError(f"RepairTask 不存在：{task_id}")
        task = _task(row)
        quote = str((task.get("evidence") or {}).get("quoted_source") or "")
        if not quote:
            # Ungrounded tasks are closed only by a fresh complete review,
            # never by incidental body edits.
            return task
        if quote and quote in markdown:
            return task
        verification = {
            "outcome": "stale_evidence",
            "reason": "原始引用已不在当前正文中，旧问题不再驱动修复。",
            "verified_at": utcnow(),
        }
        connection.execute(
            "UPDATE repair_tasks SET status = ?, latest_verification_json = ?, updated_at = ? WHERE id = ?",
            ("stale_evidence", json.dumps(verification, ensure_ascii=False), utcnow(), task_id),
        )
        return _task(connection.execute("SELECT * FROM repair_tasks WHERE id = ?", (task_id,)).fetchone())


def list_repair_tasks(run_id: str, *, include_closed: bool = True) -> list[dict[str, Any]]:
    query = "SELECT * FROM repair_tasks WHERE run_id = ?"
    values: list[Any] = [run_id]
    if not include_closed:
        query += " AND status NOT IN (?, ?, ?)"
        values.extend(sorted(CLOSED_STATUSES))
    query += " ORDER BY CASE severity WHEN 'blocker' THEN 0 WHEN 'major' THEN 1 ELSE 2 END, chapter, created_at"
    with database() as connection:
        return [_task(row) for row in connection.execute(query, values).fetchall()]


def reconcile_open_tasks(run_id: str, live_task_ids: set[str]) -> list[str]:
    """Close historical findings absent from the latest complete Review fact base."""
    placeholders = ", ".join("?" for _ in CLOSED_STATUSES)
    with database() as connection:
        rows = connection.execute(
            f"SELECT id FROM repair_tasks WHERE run_id = ? AND status NOT IN ({placeholders})",
            [run_id, *sorted(CLOSED_STATUSES)],
        ).fetchall()
        stale_ids = [str(row["id"]) for row in rows if str(row["id"]) not in live_task_ids]
        if not stale_ids:
            return []
        verification = json.dumps(
            {
                "outcome": "stale_evidence",
                "reason": "最新整课 Review 未再复现该问题；历史记录保留但不再作为当前质量事实。",
                "verified_at": utcnow(),
            },
            ensure_ascii=False,
        )
        for task_id in stale_ids:
            connection.execute(
                "UPDATE repair_tasks SET status = ?, latest_verification_json = ?, updated_at = ? WHERE id = ?",
                ("stale_evidence", verification, utcnow(), task_id),
            )
        return stale_ids


def record_attempt(task_id: str, phase: str, *, plan: dict[str, Any] | None = None, patch: dict[str, Any] | None = None, verification: dict[str, Any] | None = None) -> None:
    with database() as connection:
        row = connection.execute("SELECT attempt_count FROM repair_tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            raise KeyError(f"RepairTask 不存在：{task_id}")
        number = int(row["attempt_count"]) + 1
        now = utcnow()
        connection.execute(
            "INSERT INTO repair_task_attempts (id, task_id, attempt_number, phase, plan_json, patch_json, verification_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), task_id, number, phase, json.dumps(plan or {}, ensure_ascii=False), json.dumps(patch or {}, ensure_ascii=False), json.dumps(verification or {}, ensure_ascii=False), now),
        )
        connection.execute("UPDATE repair_tasks SET attempt_count = ?, updated_at = ? WHERE id = ?", (number, now, task_id))


def transition_task(task_id: str, status: str, *, verification: dict[str, Any] | None = None) -> dict[str, Any]:
    if status == "fixed_verified" and not verification:
        raise ValueError("fixed_verified 必须附带验证证据")
    with database() as connection:
        connection.execute(
            "UPDATE repair_tasks SET status = ?, latest_verification_json = ?, updated_at = ? WHERE id = ?",
            (status, json.dumps(verification or {}, ensure_ascii=False), utcnow(), task_id),
        )
        row = connection.execute("SELECT * FROM repair_tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            raise KeyError(f"RepairTask 不存在：{task_id}")
        return _task(row)


def record_rule_verification(
    task_id: str,
    diagnostic_code: str,
    outcome: str,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    """Close a task only from rule-specific, revision-bound evidence."""
    verification = {
        **evidence,
        "diagnostic_code": diagnostic_code,
        "outcome": outcome,
        "source_revision": evidence.get("source_revision"),
        "verified_at": evidence.get("verified_at") or utcnow(),
    }
    if not verification["source_revision"]:
        raise ValueError("规则复验缺少 source_revision")
    status = "fixed_verified" if outcome == "passed" else "escalation_required"
    record_attempt(task_id, "rule_verification", verification=verification)
    return transition_task(task_id, status, verification=verification)
