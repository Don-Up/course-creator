from __future__ import annotations

import json
import uuid
from typing import Any

from app.db import database, row_to_dict, utcnow
from app.config import get_settings
from app.course_service import load_course_quality_snapshot
from app.workflow.definitions import (
    REVIEW_STEP_ORDER,
    REVIEW_WORKFLOW_STEPS,
    STEP_ORDER,
    WORKFLOW_STEPS,
)
from app.workflow.repair_tasks import list_repair_tasks
from app.workflow.command_repository import command_projection


def _is_creation_request(request: dict[str, Any]) -> bool:
    workflow_scope = request.get("workflow_scope")
    if workflow_scope:
        return workflow_scope == "new_course"
    scope = request.get("scope")
    return scope not in {"review_course", "regenerate_course"}


def create_run_record(
    run_id: str,
    course_slug: str,
    mode: str,
    provider: str,
    model: str,
    request: dict[str, Any],
    budget_policy: dict[str, Any] | None = None,
) -> None:
    now = utcnow()
    with database() as connection:
        connection.execute(
            """
            INSERT INTO runs (
                id, course_slug, mode, status, current_step, provider, model,
                request_json, trace_id, budget_policy_json, created_at, updated_at
            ) VALUES (?, ?, ?, 'QUEUED', 'intake', ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                course_slug,
                mode,
                provider,
                model,
                json.dumps(request, ensure_ascii=False),
                run_id,
                json.dumps(budget_policy or {}, ensure_ascii=False),
                now,
                now,
            ),
        )
    append_event(run_id, "run.created", "intake", "课程 Agent Run 已创建")
    from app.observability.tracing import start_span
    start_span(run_id, kind="run", name="Run", span_id=f"run:{run_id}")


def append_event(
    run_id: str,
    event_type: str,
    step: str,
    message: str,
    payload: dict[str, Any] | None = None,
    trace=None,
) -> None:
    if trace is None:
        from app.observability.context import current_trace
        trace = current_trace()
    with database() as connection:
        connection.execute(
            """
            INSERT INTO run_events (
                id, run_id, event_type, step, message, payload_json, trace_id, span_id, parent_span_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                run_id,
                event_type,
                step,
                message,
                json.dumps(payload or {}, ensure_ascii=False),
                getattr(trace, "trace_id", None), getattr(trace, "span_id", None), getattr(trace, "parent_span_id", None),
                utcnow(),
            ),
        )


def update_budget_policy(run_id: str, policy: dict[str, Any], *, reason: str = "用户更新课程预算") -> None:
    now = utcnow()
    with database() as connection:
        row = connection.execute("SELECT budget_policy_json, trace_id FROM runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            raise ValueError("Run 不存在")
        previous = row[0] or "{}"
        next_policy = json.dumps(policy, ensure_ascii=False)
        connection.execute("UPDATE runs SET budget_policy_json = ?, updated_at = ? WHERE id = ?", (next_policy, now, run_id))
        connection.execute("INSERT INTO budget_adjustments (id, run_id, trace_id, previous_policy_json, next_policy_json, reason, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)", (str(uuid.uuid4()), run_id, row[1] or run_id, previous, next_policy, reason[:500], now))


def record_run_artifact(
    run_id: str,
    step: str,
    node: str,
    title: str,
    presentation: dict[str, Any],
    raw_output: dict[str, Any],
    source: str = "model",
) -> None:
    with database() as connection:
        connection.execute(
            """
            INSERT INTO run_artifacts (
                id, run_id, step, node, title, source,
                presentation_json, raw_output_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                run_id,
                step,
                node,
                title,
                source,
                json.dumps(presentation, ensure_ascii=False, default=str),
                json.dumps(raw_output, ensure_ascii=False, default=str),
                utcnow(),
            ),
        )


def list_run_artifacts(run_id: str) -> list[dict[str, Any]]:
    with database() as connection:
        rows = connection.execute(
            "SELECT * FROM run_artifacts WHERE run_id = ? ORDER BY created_at, id",
            (run_id,),
        ).fetchall()
    return [_normalize_legacy_interrupt_artifact(row_to_dict(row) or {}) for row in rows]


def _normalize_legacy_interrupt_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    """Render old misclassified LangGraph pauses without erasing history.

    Versions before the GraphInterrupt guard saved a system diagnostic whose
    error text began with ``(Interrupt(value=...)``. It is a successful
    approval pause, not a model error. Keep the raw output for auditability
    but correct the user-facing interpretation during reads.
    """
    raw = artifact.get("raw_output")
    error = str(raw.get("error") or "") if isinstance(raw, dict) else ""
    if artifact.get("source") != "system" or not error.startswith("(Interrupt(value="):
        return artifact
    presentation = dict(artifact.get("presentation") or {})
    return {
        **artifact,
        "source": "recovered",
        "title": "历史审批暂停记录",
        "presentation": {
            **presentation,
            "headline": "整课质量闭环等待确认",
            "conclusion": "该记录是 LangGraph 的正常人工确认暂停，不是模型调用失败。整课 Review 产物已保留。",
            "highlights": ["可直接在当前整课质量闭环确认或发起定向修复。"],
            "issues": [],
            "next_action": "查看本轮整课 Review 清单后继续处理。",
        },
    }


def update_run(
    run_id: str,
    *,
    status: str | None = None,
    step: str | None = None,
    interrupt_type: str | None = None,
    interrupt_payload: dict[str, Any] | None = None,
    error_message: str | None = None,
    clear_interrupt: bool = False,
    clear_error: bool = False,
) -> None:
    fields = ["updated_at = ?"]
    values: list[Any] = [utcnow()]
    if status is not None:
        fields.append("status = ?")
        values.append(status)
    if step is not None:
        fields.append("current_step = ?")
        values.append(step)
    if clear_interrupt:
        fields.extend(["interrupt_type = NULL", "interrupt_payload_json = NULL"])
    elif interrupt_type is not None:
        fields.extend(["interrupt_type = ?", "interrupt_payload_json = ?"])
        values.extend(
            [interrupt_type, json.dumps(interrupt_payload or {}, ensure_ascii=False)]
        )
    if error_message is not None:
        fields.append("error_message = ?")
        values.append(error_message)
    elif clear_error:
        fields.append("error_message = NULL")
    values.append(run_id)
    with database() as connection:
        connection.execute(
            f"UPDATE runs SET {', '.join(fields)} WHERE id = ?",
            values,
        )


def get_run_record(run_id: str) -> dict[str, Any] | None:
    with database() as connection:
        run = row_to_dict(
            connection.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        )
        if not run:
            return None
        # A release gate whose checkpoint already holds the review summary can
        # lose its DB interrupt (process killed between the graph write and the
        # runtime write). Rebuild a minimal payload so the UI still offers the
        # regenerate / publish actions instead of rendering two empty panels.
        if (
            run.get("current_step") == "release"
            and run.get("status") == "WAITING_APPROVAL"
            and not run.get("interrupt_payload")
        ):
            run["interrupt_type"] = "RELEASE_APPROVAL"
            run["interrupt_payload"] = {
                "type": "RELEASE_APPROVAL",
                "step": "release",
                "title": "确认整课生成结果",
                "output": {"release_review_ready": False},
                "actions": ["REVISE"],
            }
        rows = connection.execute(
            "SELECT * FROM run_events WHERE run_id = ? ORDER BY seq",
            (run_id,),
        ).fetchall()
    run["events"] = [row_to_dict(row) for row in rows]
    from app.observability.budget import get_budget_projection
    run["budget"] = get_budget_projection(run_id)
    run.update(command_projection(run_id))
    run["revision"] = f"{run['updated_at']}:{run['events'][-1]['seq'] if run['events'] else 0}"
    run["artifacts"] = list_run_artifacts(run_id)
    # RepairTask is the canonical current quality fact base.  Older runs have
    # no rows and continue to render their immutable artifact history.
    run["repair_tasks"] = list_repair_tasks(run_id)
    run["repair_task_summary"] = {
        "open": sum(1 for task in run["repair_tasks"] if task.get("status") not in {"fixed_verified", "fixed_static_only", "stale_evidence"}),
        "verified": sum(1 for task in run["repair_tasks"] if task.get("status") == "fixed_verified"),
        "needs_human": sum(1 for task in run["repair_tasks"] if task.get("status") in {"human_decision_required", "needs_runtime_verification"}),
    }
    # Artifacts are an immutable timeline. The article page needs the current
    # facts after a repair, so expose the atomically-written course snapshot
    # alongside every run read instead of reconstructing it from history.
    run["course_quality_snapshot"] = load_course_quality_snapshot(
        get_settings().courses_root / run["course_slug"]
    )
    run["quality_cycle"] = run["course_quality_snapshot"].get("quality_cycle") or {}
    creation_run = _is_creation_request(run.get("request") or {})
    definitions = WORKFLOW_STEPS if creation_run else REVIEW_WORKFLOW_STEPS
    step_order = STEP_ORDER if creation_run else REVIEW_STEP_ORDER
    # Older creation Runs exposed batch approval as a separate `quality` step.
    # New creation Runs use a real all-course quality gate, so only translate
    # the legacy batch-approval interrupt.
    if (
        creation_run
        and run["current_step"] == "quality"
        and (run.get("interrupt_type") in {"BATCH_APPROVAL", "BATCH_REVIEW_REQUIRED"})
    ):
        run["legacy_current_step"] = "quality"
        run["current_step"] = "generation"
        if run.get("interrupt_payload"):
            run["interrupt_payload"]["step"] = "generation"
    # A Run paused before the dedicated quality-repair node existed may have
    # already resumed from the all-course quality gate into `generate_batch`.
    # Preserve its actual checkpoint, but present it as the quality closure so
    # the UI never appears to travel backwards into the production node.
    if creation_run and run["current_step"] == "generation":
        quality_revise_events = [
            event
            for event in run["events"]
            if event.get("event_type") == "approval.resolved"
            and event.get("step") == "quality"
            and "REVISE" in event.get("message", "")
        ]
        if quality_revise_events:
            run["legacy_current_step"] = "generation"
            run["quality_repair_in_progress"] = True
            run["current_step"] = "quality"
            if run.get("interrupt_payload"):
                if run.get("interrupt_type") == "BATCH_REVIEW_REQUIRED":
                    # The old checkpoint is about to be migrated through the
                    # all-course Review. Do not leak its first-batch request
                    # into the quality screen as if it were the current task.
                    run["interrupt_type"] = "COURSE_QUALITY_REVIEW_PENDING"
                    run["interrupt_payload"] = {
                        "type": "COURSE_QUALITY_REVIEW_PENDING",
                        "step": "quality",
                        "title": "开始整课质量 Review",
                        "output": {
                            "status": "待汇总",
                            "message": "将汇总全部批次的最新质量结果，并生成仅针对未达标章节的修复清单。",
                        },
                        "actions": ["REVISE", "STOP"],
                    }
                else:
                    run["interrupt_payload"]["step"] = "quality"
    current_index = step_order.get(run["current_step"], 0)
    run_finished = run["status"] == "COMPLETED"
    run["workflow_steps"] = [
        {
            **definition,
            "status": (
                "completed"
                if index < current_index or (run_finished and index == current_index)
                else "active"
                if index == current_index
                else "pending"
            ),
        }
        for index, definition in enumerate(definitions)
    ]
    return run


def list_run_records(course_slug: str | None = None) -> list[dict[str, Any]]:
    with database() as connection:
        if course_slug:
            rows = connection.execute(
                "SELECT * FROM runs WHERE course_slug = ? ORDER BY created_at DESC",
                (course_slug,),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM runs ORDER BY created_at DESC LIMIT 100"
            ).fetchall()
    return [row_to_dict(row) for row in rows]


def recover_stale_runs() -> None:
    with database() as connection:
        rows = connection.execute(
            "SELECT id, current_step FROM runs WHERE status = 'RUNNING'"
        ).fetchall()
        for row in rows:
            connection.execute(
                """
                UPDATE runs
                SET status = 'FAILED',
                    error_message = '本地进程在节点执行期间退出，请从最近检查点重试',
                    updated_at = ?
                WHERE id = ?
                """,
                (utcnow(), row["id"]),
            )
            connection.execute(
                """
                INSERT INTO run_events (
                    id, run_id, event_type, step, message, payload_json, created_at
                ) VALUES (?, ?, 'run.recovered_as_failed', ?, ?, '{}', ?)
                """,
                (
                    str(uuid.uuid4()),
                    row["id"],
                    row["current_step"],
                    "检测到未完成的本地执行，已保留检查点",
                    utcnow(),
                ),
            )
