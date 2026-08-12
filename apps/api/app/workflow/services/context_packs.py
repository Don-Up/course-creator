from __future__ import annotations

import hashlib
import json
import re
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

from langgraph.errors import GraphInterrupt
from app.config import get_settings
from app.agents.protocols import CourseAgent
from app.workflow.command_repository import claim_node_execution, complete_node_execution, fail_node_execution, is_command_cancel_requested
from app.workflow.repository import append_event, get_run_record, record_run_artifact, update_run
from app.workflow.execution_context import current_execution
from app.observability.context import TraceContext, trace_scope
from app.observability.tracing import finish_span, start_span
from app.workflow.state import CourseAgentState
from app.workflow.services.batch_planning import _plain_title
from app.workflow.services.workspace_contract import _read_workspace_context, _write_json


def _retry_initial_chapter_write(
    write: Callable[[int], str],
    *,
    max_attempts: int,
    on_retry: Callable[[int, Exception], None],
) -> str:
    """Retry only a bodyless chapter write; never conflate it with QA repair."""
    last_error: Exception | None = None
    for call_attempt in range(1, max_attempts + 1):
        try:
            return write(call_attempt)
        except Exception as exc:
            last_error = exc
            if call_attempt < max_attempts:
                on_retry(call_attempt, exc)
    assert last_error is not None
    raise last_error


def _chapter_resume_stage(
    previous_result: dict[str, Any], markdown: str | None,
) -> str | None:
    """Return the exact unfinished stage for a persisted chapter body."""
    if not markdown:
        return None
    stage = previous_result.get("pending_stage")
    if stage in {"enriching", "humanizing", "semantic_review", "continuity"}:
        return str(stage)
    attempts = previous_result.get("attempts") or []
    last_attempt = attempts[-1] if attempts else {}
    legacy_stage = last_attempt.get("failed_stage") if isinstance(last_attempt, dict) else None
    return legacy_stage if legacy_stage in {"enriching", "humanizing", "semantic_review"} else None


def _deferred_chapter_quality_result(
    *,
    chapter: int,
    title: str,
    path: str,
    markdown: str,
    effective_char_min: int,
    failure_stage: str,
    issue: str,
    attempts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Keep a generated body truthful when a later Agent has not finished."""
    effective_chars = _effective_char_count(markdown) if markdown else 0
    body_generated = bool(markdown.strip())
    return {
        "chapter": chapter,
        "title": title,
        "path": path,
        "humanizer_score": 0,
        "effective_chars": effective_chars,
        "effective_char_min": effective_char_min,
        "semantic_review": {
            "decision": "pending" if body_generated else "reject",
            "issues": [issue],
        },
        "attempts": attempts,
        "continuity_output": {},
        "passed": False,
        "deferred": True,
        "body_generated": body_generated,
        "pending_stage": failure_stage if body_generated else "writing",
        "issues": [issue],
    }


def _latest_requested_chapter_count(changes: list[dict[str, Any]]) -> int | None:
    requested: list[int] = []
    pattern = re.compile(r"(?:扩充到|要求(?:的)?(?:是|为)?|改成|调整为|共计?)\s*(\d+)\s*章")
    for change in changes:
        requested.extend(int(value) for value in pattern.findall(str(change.get("request", ""))))
    return requested[-1] if requested else None


def _sync_requested_chapter_count(course_root: Path, changes: list[dict[str, Any]]) -> int | None:
    count = _latest_requested_chapter_count(changes)
    if count is None:
        return None
    spec_path = course_root / "workspace" / "COURSE-GENERATION-SPEC.md"
    spec = spec_path.read_text(encoding="utf-8") if spec_path.exists() else "# 课程生成规格\n\n"
    expected_line = f"- 期望章节数：{count}（全局变更已确认，待蓝图同步）"
    updated = re.sub(r"^- 期望章节数：.*$", expected_line, spec, flags=re.MULTILINE)
    if updated == spec and "期望章节数：" not in spec:
        updated = spec.rstrip() + "\n" + expected_line + "\n"
    if updated != spec:
        spec_path.write_text(updated, encoding="utf-8")
    metadata_path = course_root / "course.json"
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("requested_chapter_count") != count:
            metadata["requested_chapter_count"] = count
            _write_json(metadata_path, metadata)
    return count


def _sync_resources_policy(course_root: Path, policy: str) -> None:
    path = course_root / "workspace" / "RESOURCES.md"
    if not path.exists():
        return
    content = path.read_text(encoding="utf-8")
    updated = re.sub(
        r"(## 来源政策\n\n)[\s\S]*?(?=\n## |\Z)",
        rf"\g<1>{policy}\n",
        content,
        count=1,
    )
    if updated != content:
        path.write_text(updated, encoding="utf-8")


def _effective_char_count(markdown: str) -> int:
    # Fence markers are only syntax at the beginning of a line.  A lesson may
    # legitimately explain Markdown using inline `` ` ``` ` `` text; treating
    # that prose as an opener would hide every following paragraph until the
    # next real fence and falsely report a large content deficit.
    value = re.sub(
        r"(?ms)^[ \t]*(`{3,}|~{3,})[^\n]*\n.*?^[ \t]*\1[ \t]*$",
        "",
        markdown,
    )
    value = re.sub(r"!\[[^\]]*]\([^)]+\)", "", value)
    value = re.sub(r"\[([^\]]+)]\([^)]+\)", r"\1", value)
    value = re.sub(r"[#>*_`|~\-\s]", "", value)
    return len(value)


def _effective_content_deficit(markdown: str, minimum: int) -> tuple[int, int]:
    effective_chars = _effective_char_count(markdown)
    return effective_chars, max(0, minimum - effective_chars)


def _relevant_ledger(
    ledger: list[dict[str, Any]],
    module_title: str,
    limit: int = 8,
) -> list[dict[str, Any]]:
    module_entries = [item for item in ledger if item.get("module") == module_title]
    previous_entries = [item for item in ledger if item.get("module") != module_title]
    return [*previous_entries[-2:], *module_entries[-limit:]]


def _context_pack(
    state: CourseAgentState,
    module: dict[str, Any],
    chapter: dict[str, Any],
    ledger: list[dict[str, Any]],
    feedback: str = "",
) -> dict[str, Any]:
    chapters = module["chapters"]
    position = next(
        index for index, item in enumerate(chapters) if item["number"] == chapter["number"]
    )
    course_root = get_settings().courses_root / state["course_slug"]
    return {
        "schema_version": 1,
        "course_context": {
            "title": state["blueprint"]["course_title"],
            "mission": state["mission_markdown"],
            "request": state["request"],
            "global_change_requests": state.get("global_change_requests", []),
            # Writing needs sources and the active spec, not an unlimited
            # dump of every historical note. This leaves room for the
            # chapter-specific plan and the selected teach-generator assets.
            "workspace": _read_workspace_context(
                course_root,
                {
                    "RESOURCES.md": 48000,
                    "COURSE-GENERATION-SPEC.md": 65536,
                    "NOTES.md": 32000,
                },
            ),
        },
        "module_context": {
            "title": module["title"],
            "goal": module["goal"],
            "narrative": module["narrative"],
            "chapter_sequence": [
                {
                    "number": item["number"],
                    "title": _plain_title(item["title"]),
                    "learning_outcome": item["learning_outcome"],
                }
                for item in chapters
            ],
        },
        "chapter": {**chapter, "title": _plain_title(chapter["title"])},
        "neighbor_context": {
            "previous": chapters[position - 1] if position > 0 else None,
            "next": chapters[position + 1] if position + 1 < len(chapters) else None,
        },
        "continuity_ledger": _relevant_ledger(ledger, module["title"]),
        "feedback": feedback,
    }


def _presentation_projection(value: Any, depth: int = 0) -> Any:
    if depth > 5:
        return "[内容层级较深，已在展示摘要输入中省略]"
    if isinstance(value, str):
        if len(value) <= 1200:
            return value
        return value[:1200] + (
            f"\n[展示摘要已省略其余 {len(value) - 1200} 字符；"
            "完整原始产物已持久化，不能据此判断原始产物是否完整]"
        )
    if isinstance(value, list):
        projected = [_presentation_projection(item, depth + 1) for item in value[:12]]
        if len(value) > 12:
            projected.append(f"[其余 {len(value) - 12} 项保留在原始输出]")
        return projected
    if isinstance(value, dict):
        projected = {
            str(key): _presentation_projection(item, depth + 1)
            for key, item in list(value.items())[:30]
        }
        if depth == 0:
            projected["__presentation_projection__"] = True
        return projected
    return value


def _projected(
    run_id: str,
    step: str,
    label: str,
    function: Callable[[CourseAgentState], dict[str, Any]],
    provider: CourseAgent,
):
    def node(state: CourseAgentState) -> dict[str, Any]:
        execution = current_execution.get()
        execution_id: str | None = None
        node_context_token = None
        if execution:
            input_hash = hashlib.sha256(
                json.dumps(state, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest()
            claim, execution_row = claim_node_execution(
                run_id, execution.command_id, function.__name__, input_hash,
                execution.worker_id, execution.lease_seconds,
            )
            if claim == "reused" and isinstance(execution_row.get("output"), dict):
                append_event(run_id, "node.reused", step, f"{label}复用已提交节点结果", {"node_execution_id": execution_row["id"]})
                return execution_row["output"]
            if claim == "busy":
                raise RuntimeError(f"节点 {function.__name__} 正由其他 Worker 执行")
            execution_id = execution_row["id"]
            if is_command_cancel_requested(execution.command_id):
                raise RuntimeError("Run 已请求停止")
            node_context_token = current_execution.set(
                replace(execution, node_execution_id=execution_id)
            )
        update_run(run_id, status="RUNNING", step=step, clear_interrupt=True)
        append_event(run_id, "node.started", step, f"{label}开始")
        node_span = start_span(run_id, kind="node", name=function.__name__, node_execution_id=execution_id, stage=step, attributes={"workflow_node": function.__name__})
        node_trace = trace_scope(TraceContext(trace_id=run_id, run_id=run_id, span_id=node_span["id"], parent_span_id=node_span.get("parent_span_id"), command_id=node_span.get("command_id"), node_execution_id=execution_id, stage=step))
        node_trace.__enter__()
        try:
            patch = function(state)
        except GraphInterrupt:
            # `interrupt()` is LangGraph's expected durable pause signal. It
            # carries a user-facing approval payload and must reach the graph
            # runtime untouched; treating it as a provider failure corrupts
            # the run state and hides the confirmation UI.
            if execution_id and execution:
                fail_node_execution(execution_id, execution.worker_id, "等待人工确认")
            if node_context_token is not None:
                current_execution.reset(node_context_token)
            finish_span(node_span["id"], "WAITING_APPROVAL")
            node_trace.__exit__(None, None, None)
            raise
        except Exception as exc:
            diagnostics = getattr(exc, "diagnostics", None)
            payload: dict[str, Any] = {"error": str(exc)[:1000]}
            if isinstance(diagnostics, dict):
                payload["gateway"] = diagnostics
            presentation = {
                "headline": f"{label}未完成",
                "conclusion": "模型调用未产生可用最终文本；系统已完成本轮定向重试并保留检查点。",
                "highlights": [
                    f"响应状态：{diagnostics.get('response_status', 'unknown')}"
                    if isinstance(diagnostics, dict)
                    else "响应状态：未知",
                    f"未完成原因：{diagnostics.get('incomplete_reason') or '未提供'}"
                    if isinstance(diagnostics, dict)
                    else "请查看错误详情后重试或切换模型。",
                ],
                "metrics": diagnostics.get("usage", {}) if isinstance(diagnostics, dict) else {},
                "issues": [str(exc)[:500]],
                "next_action": "可在当前节点继续重试；已完成节点和工作区产物不会重新生成。",
            }
            record_run_artifact(
                run_id,
                step,
                function.__name__,
                f"{label}调用诊断",
                presentation,
                payload,
                "system",
            )
            append_event(
                run_id,
                "node.failed",
                step,
                f"{label}失败：{str(exc)[:180]}",
                payload,
            )
            if execution_id and execution:
                fail_node_execution(execution_id, execution.worker_id, str(exc))
            if node_context_token is not None:
                current_execution.reset(node_context_token)
            finish_span(node_span["id"], "FAILED", error=exc)
            node_trace.__exit__(None, None, None)
            raise
        try:
            presentation = provider.present_output(
                step,
                label,
                _presentation_projection(patch),
            ).model_dump(mode="json")
        except Exception as exc:
            presentation = {
                "headline": f"{label}已完成",
                "conclusion": "节点产物已保存，结果解读暂时不可用。",
                "highlights": [f"已保存字段：{key}" for key in list(patch)[:5]],
                "metrics": {"产出字段数": len(patch)},
                "issues": [f"结果解读失败：{str(exc)[:160]}"],
                "next_action": "可以展开原始输出继续审核。",
            }
        record_run_artifact(
            run_id,
            step,
            function.__name__,
            label,
            presentation,
            patch,
        )
        append_event(run_id, "node.completed", step, f"{label}完成", {"keys": list(patch)})
        if execution_id and execution:
            complete_node_execution(execution_id, execution.worker_id, patch)
        if node_context_token is not None:
            current_execution.reset(node_context_token)
        finish_span(node_span["id"], "SUCCEEDED")
        node_trace.__exit__(None, None, None)
        return patch

    return node
