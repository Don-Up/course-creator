from __future__ import annotations

import json
import re
from typing import Any

from app.config import get_settings
from app.workflow.repository import get_run_record
from app.workflow.state import CourseAgentState


def _plain_title(value: str) -> str:
    return re.sub(r"^第\s*\d+\s*章[：:\s]*", "", value).strip()


def _latest_batch_results(state: CourseAgentState) -> list[dict[str, Any]]:
    """Canonicalize retry history: only the latest result for each batch counts."""
    latest_by_id = {
        item.get("batch", {}).get("id"): item
        for item in state.get("batch_results", [])
        if item.get("batch", {}).get("id")
    }
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for batch in state.get("batches", []):
        batch_id = batch.get("id")
        if not batch_id or batch_id not in latest_by_id or batch_id in seen:
            continue
        seen.add(batch_id)
        results.append(latest_by_id[batch_id])
    return results


def _contract_codes_requiring_llm(
    diagnostics: list[dict[str, Any]], *, handled: set[str]
) -> list[str]:
    """Return only structure diagnostics not already repaired deterministically."""
    return list(
        dict.fromkeys(
            str(item.get("code") or "UNKNOWN")
            for item in diagnostics
            if str(item.get("code") or "UNKNOWN") not in handled
        )
    )


def _normalize_reference_node(markdown: str, node_id: str) -> tuple[str, bool]:
    """Normalize the exact AST node selected by the semantic classifier."""
    try:
        _kind, raw_offset = node_id.split(":", 1)
        offset = int(raw_offset)
    except (ValueError, AttributeError):
        return markdown, False
    if offset < 0 or offset >= len(markdown):
        return markdown, False
    line_end = markdown.find("\n", offset)
    if line_end < 0:
        line_end = len(markdown)
    current = markdown[offset:line_end]
    if not current.strip():
        return markdown, False
    replacement = "## 参考文献"
    normalized = markdown[:offset] + replacement + markdown[line_end:]
    return normalized, normalized != markdown


def _repair_issue_is_resolved(
    issue: str,
    *,
    contract_codes: set[str],
    remaining_issues: list[str],
    humanizer_score: int | float | None,
    effective_chars: int,
    effective_minimum: int,
    semantic_decision: str | None,
) -> bool:
    code_match = re.match(r"\[([A-Z_]+)\]", issue)
    if code_match:
        return code_match.group(1) not in contract_codes
    lowered = issue.lower()
    if "humanizer" in lowered:
        return isinstance(humanizer_score, (int, float)) and humanizer_score >= 45
    if "有效字符" in issue or "字数" in issue:
        return effective_chars >= effective_minimum
    if any(marker in issue for marker in ("[blocker]", "[Blocker]", "[major]", "[Major]", "[minor]", "[Minor]", "语义", "事实", "连续性")):
        return issue not in remaining_issues
    return issue not in remaining_issues


def _blueprint_markdown(blueprint: dict[str, Any]) -> str:
    lines = [f"# {blueprint['course_title']}：课程蓝图", ""]
    for module_index, module in enumerate(blueprint["modules"], start=1):
        lines.extend(
            [
                f"## 模块 {module_index}：{module['title']}",
                "",
                f"- 模块目标：{module['goal']}",
                f"- 叙事主线：{module['narrative']}",
                "",
            ]
        )
        for chapter in module["chapters"]:
            lines.extend(
                [
                    f"### 第 {chapter['number']} 章：{_plain_title(chapter['title'])}",
                    "",
                    f"- 学习成果：{chapter['learning_outcome']}",
                    f"- 先修：{'、'.join(chapter['prerequisites']) or '无'}",
                    f"- 承接：{'、'.join(chapter['continuity_in']) or '课程或模块起点'}",
                    f"- 交付后续：{'、'.join(chapter['continuity_out']) or '模块收束'}",
                    f"- 正文主类型：{chapter.get('pedagogy_type', 'language')}",
                    f"- 主教学任务：{chapter.get('primary_teaching_task', '概念讲解')}",
                    f"- 讲师风格：{chapter.get('instructor_voice', '耐心教练型')}",
                    f"- 本章学习路径：{' → '.join(chapter.get('learning_path', [])) or '由章节学习成果确定'}",
                    f"- 实际借用模板模块：{'、'.join(chapter.get('template_modules', [])) or '按主类型选择必要模块'}",
                    "",
                ]
            )
    if blueprint.get("design_notes"):
        lines.extend(["## 设计备注", ""])
        lines.extend(f"- {item}" for item in blueprint["design_notes"])
        lines.append("")
    return "\n".join(lines)


def _make_batches(blueprint: dict[str, Any], max_size: int = 4) -> list[dict[str, Any]]:
    batches: list[dict[str, Any]] = []
    for module_index, module in enumerate(blueprint["modules"], start=1):
        chapters = module["chapters"]
        for offset in range(0, len(chapters), max_size):
            selected = chapters[offset : offset + max_size]
            batches.append(
                {
                    # `m` means production batch, not blueprint module.  The
                    # older module-based key made a third batch look like
                    # ``m2-08-10`` whenever it happened to be in module 2.
                    # Keep the module separately so every surface has one
                    # unambiguous batch identity.
                    "id": f"m{len(batches) + 1}-{selected[0]['number']:02d}-{selected[-1]['number']:02d}",
                    "ordinal": len(batches) + 1,
                    "display_label": f"批次 {len(batches) + 1} · 第 {selected[0]['number']}–{selected[-1]['number']} 章",
                    "module_index": module_index - 1,
                    "module_title": module["title"],
                    "chapter_numbers": [item["number"] for item in selected],
                    "chapter_titles": [_plain_title(item["title"]) for item in selected],
                }
            )
    return batches


def _batch_display_label(batch: dict[str, Any]) -> str:
    """Return a readable label while remaining compatible with old checkpoints."""
    if isinstance(batch.get("display_label"), str):
        return batch["display_label"]
    numbers = batch.get("chapter_numbers") or []
    ordinal = batch.get("ordinal")
    chapter_range = (
        f"第 {numbers[0]}–{numbers[-1]} 章" if numbers else "章节范围待确认"
    )
    return f"批次 {ordinal if isinstance(ordinal, int) else batch.get('id', '—')} · {chapter_range}"


def _generation_cursor_exhausted(state: CourseAgentState) -> bool:
    """Return whether a resumed run has consumed every planned batch."""
    return int(state.get("current_batch_index", 0)) >= len(state.get("batches", []))


def _batch_repair_completion_route(state: CourseAgentState) -> str:
    """Do not re-enter generation after the final batch repair completes."""
    return "course_quality" if _generation_cursor_exhausted(state) else "batch_complete"


def _canonicalize_batch_results(state: CourseAgentState) -> list[dict[str, Any]]:
    """Return latest results with a stable, production-order display identity.

    Checkpoints created before the batch-key correction still contain ids such
    as ``m2-08-10``.  They remain valid internal lookup keys, but are never
    allowed to leak into user-facing reports as a misleading batch number.
    """
    results = _latest_batch_results(state)
    results.sort(
        key=lambda result: min(result.get("batch", {}).get("chapter_numbers") or [10**9])
    )
    canonical: list[dict[str, Any]] = []
    for ordinal, result in enumerate(results, start=1):
        batch = dict(result.get("batch", {}))
        numbers = [int(number) for number in batch.get("chapter_numbers", [])]
        if numbers:
            batch["display_id"] = f"m{ordinal}-{numbers[0]:02d}-{numbers[-1]:02d}"
            batch["display_label"] = f"批次 {ordinal} · 第 {numbers[0]}–{numbers[-1]} 章"
        else:
            batch["display_id"] = f"m{ordinal}"
            batch["display_label"] = f"批次 {ordinal}"
        batch["ordinal"] = ordinal
        canonical.append({**result, "batch": batch})
    return canonical


def _quality_gates_for_result(
    chapters: list[dict[str, Any]],
    build: dict[str, Any],
    validation: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Build the one canonical gate snapshot used by files, UI and release."""
    return {
        "stage_1_chapter_language_and_volume": {
            "passed": all(
                item.get("humanizer_score", 0) >= 45
                and item.get("effective_chars", 0) >= item.get("effective_char_min", 0)
                for item in chapters
            ),
            "label": "章节语言与有效内容门",
        },
        "stage_2_semantic_review": {
            "passed": all(
                (item.get("semantic_review") or {}).get("decision") == "ready"
                for item in chapters
            ),
            "label": "教学语义与事实审校门",
        },
        "stage_3_batch_integration": {
            "passed": bool(build.get("succeeded")) and bool(validation.get("succeeded")),
            "label": "批次构建与确定性集成门",
        },
    }


def build_release_review(run_id: str, state: dict[str, Any]) -> dict[str, Any]:
    """Aggregate one course run into the final release-review report."""
    settings = get_settings()
    course_root = settings.courses_root / state["course_slug"]
    metadata_path = course_root / "course.json"
    metadata: dict[str, Any] = {}
    if metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception:
            metadata = {}
    latest_results = _canonicalize_batch_results(state)
    chapters = [c for r in latest_results for c in r.get("chapters", [])]
    request = state.get("request", {})
    repair_history = list(state.get("quality_repair_history", []))
    run_record = get_run_record(run_id)
    events = run_record.get("events", []) if run_record else []
    model_call_events = [
        event for event in events
        if str(event.get("event_type", "")).endswith(".completed")
        and "模型" in str(event.get("message", ""))
    ]
    timed_events = [
        event for event in events
        if isinstance((event.get("payload") or {}).get("duration_ms"), (int, float))
    ]
    total_duration_ms = sum(
        (event.get("payload") or {}).get("duration_ms", 0) for event in timed_events
    )
    unresolved = state.get("course_quality_report", {}).get("unresolved", [])
    gate_rows = []
    for result in latest_results:
        batch = result.get("batch", {})
        gates = result.get("quality_gates") or {}
        gate_rows.append(
            {
                "batch": batch.get("display_label", batch.get("display_id", batch.get("id", ""))),
                "language_volume": (gates.get("stage_1_chapter_language_and_volume") or {}).get("passed"),
                "semantic": (gates.get("stage_2_semantic_review") or {}).get("passed"),
                "integration": (gates.get("stage_3_batch_integration") or {}).get("passed"),
                "passed": result.get("passed"),
            }
        )
    return {
        "course": {
            "slug": state["course_slug"],
            "title": state.get("blueprint", {}).get("course_title") or metadata.get("title", ""),
            "status": metadata.get("status", ""),
            "chapter_count": len(metadata.get("lessons") or []),
            "planned_chapter_count": metadata.get("planned_chapter_count"),
        },
        "request": {
            "audience": request.get("audience") or request.get("core_audience", ""),
            "goals": request.get("goals") or request.get("learning_goals", ""),
            "scope": request.get("scope", ""),
            "source_policy": request.get("source_policy", ""),
            "effective_char_min": request.get("effective_char_min"),
        },
        "production": {
            "batch_count": len(latest_results),
            "chapter_generated": len(chapters),
            "change_request_count": len(state.get("global_change_requests", [])),
            "quality_repair_rounds": len(repair_history),
            "repair_round_summaries": [
                {
                    "round": item.get("round"),
                    "repaired_count": item.get("repaired_count"),
                    "remaining_count": item.get("remaining_count"),
                    "build_succeeded": item.get("build_succeeded"),
                    "validation_succeeded": item.get("validation_succeeded"),
                }
                for item in repair_history
            ],
        },
        "quality": {
            "gates": gate_rows,
            "chapter_metrics": [
                {
                    "chapter": chapter.get("chapter"),
                    "title": chapter.get("title"),
                    "humanizer_score": chapter.get("humanizer_score"),
                    "effective_chars": chapter.get("effective_chars"),
                    "effective_char_min": chapter.get("effective_char_min"),
                    "semantic_decision": (chapter.get("semantic_review") or {}).get("decision"),
                    "passed": chapter.get("passed"),
                }
                for chapter in chapters
            ],
            "unresolved": unresolved,
            "unresolved_chapter_count": sum(
                len(item.get("chapters", [])) for item in unresolved
            ),
            "course_quality_passed": not unresolved,
        },
        "operations": {
            "model_operation_events": len(model_call_events),
            "timed_operation_count": len(timed_events),
            "total_operation_seconds": round(total_duration_ms / 1000, 1),
            "event_count": len(events),
        },
    }
