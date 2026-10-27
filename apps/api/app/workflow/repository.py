"""The ledger of a run: every state change leaves a row behind.

`app/workflow/repository.py` owns the `runs` and `run_events` tables, and it
puts together the read model the API later hands to the browser: the run
itself, its events, its artifacts, and the seven workflow steps with the
state each one is in.  The artifacts themselves live in
`app/workflow/artifacts.py`, and this module re-exports the two functions
that read and write them.

The rule it follows is simple: a run that changed something has to be able to
say what changed, in which stage, and when.

A stage that finishes writes three things at once: the run moves on, the
event is written down, and the artifact is stored.  They share one
transaction, so a stage that breaks half way leaves nothing behind at all.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from app.db import database, row_to_dict, utcnow
from app.workflow.artifacts import (
    insert_run_artifact,
    list_run_artifacts,
    record_run_artifact,
)
from app.workflow.definitions import STEP_ORDER, WORKFLOW_STEPS

__all__ = [
    "append_event",
    "create_run_record",
    "get_run_record",
    "list_run_artifacts",
    "list_run_records",
    "record_run_artifact",
    "record_stage_output",
    "update_run",
]


def _trace_value(trace: Any, name: str, fallback: str | None = None) -> str | None:
    """Read one field out of a trace context, be it a mapping or an object.

    Args:
        trace: The trace context, for example {"trace_id": "trace-1"}.
        name: The field to read, for example "trace_id".
        fallback: The value to use when the trace does not carry the field.

    Returns:
        The value of the field, or the fallback when it is missing.
    """
    if trace is None:
        return fallback
    if isinstance(trace, dict):
        value = trace.get(name)
    else:
        value = getattr(trace, name, None)
    return value if value is not None else fallback


def _run_row(connection: sqlite3.Connection, run_id: str) -> dict[str, Any] | None:
    """Read one row of `runs` and decode it.

    Args:
        connection: The open connection to read through.
        run_id: The run to read, for example "run-1".

    Returns:
        The row as a dictionary, or None when there is no such run.
    """
    row = connection.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    return row_to_dict(row)


def _step_index(current_step: str) -> int:
    """Find where a stage sits in the workflow, treating an unknown stage as the first.

    Args:
        current_step: The stage the run is at, for example "mission".

    Returns:
        The position of that stage in `STEP_ORDER`, or 0 when the stage is
        not part of the workflow.  A run whose stage nobody recognises is
        shown at the beginning instead of breaking the read model.
    """
    if current_step in STEP_ORDER:
        return STEP_ORDER.index(current_step)
    return 0


def _insert_event(
    connection: sqlite3.Connection,
    run_id: str,
    event_type: str,
    step: str,
    message: str,
    payload: dict[str, Any] | None = None,
    trace: Any | None = None,
) -> dict[str, Any]:
    """Write one event into the ledger of a run, inside a given transaction.

    Args:
        connection: The open connection, inside the caller's transaction.
        run_id: The run this event belongs to, for example "run-1".
        event_type: What happened, for example "run.created".
        step: The stage the event belongs to, for example "intake".
        message: A short line a human can read, for example "任务定义完成".
        payload: The details of the event, for example {"attempt": 1}.
        trace: The trace context, for example {"trace_id": "trace-1"}.

    Returns:
        The new row of `run_events`, decoded into a dictionary.
    """
    event_id = str(uuid.uuid4())
    now = utcnow()
    connection.execute(
        """
        INSERT INTO run_events (
            id, run_id, event_type, step, message, payload_json,
            trace_id, span_id, parent_span_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            run_id,
            event_type,
            step,
            message,
            json.dumps(payload or {}, ensure_ascii=False),
            _trace_value(trace, "trace_id", run_id),
            _trace_value(trace, "span_id"),
            _trace_value(trace, "parent_span_id"),
            now,
        ),
    )
    row = connection.execute(
        "SELECT * FROM run_events WHERE id = ?", (event_id,)
    ).fetchone()
    return row_to_dict(row) or {}


def _update_run(
    connection: sqlite3.Connection,
    run_id: str,
    *,
    status: str | None = None,
    step: str | None = None,
    interrupt_type: str | None = None,
    interrupt_payload: dict[str, Any] | None = None,
    error_message: str | None = None,
    clear_interrupt: bool = False,
    clear_error: bool = False,
) -> dict[str, Any]:
    """Change the state of a run, inside a given transaction.

    Args:
        connection: The open connection, inside the caller's transaction.
        run_id: The run to change, for example "run-1".
        status: The new run status, for example "RUNNING".
        step: The stage the run is at now, for example "mission".
        interrupt_type: The kind of approval the run waits for, for example
            "MISSION_APPROVAL".
        interrupt_payload: The details of that approval, for example
            {"type": "MISSION_APPROVAL"}.
        error_message: The reason the run failed, for example "生成失败了".
        clear_interrupt: True takes the interrupt and its payload away.
        clear_error: True takes the error message away.

    Returns:
        The updated row of `runs`, decoded into a dictionary.
    Raises ValueError: when there is no run with this id.
    """
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
    cursor = connection.execute(
        f"UPDATE runs SET {', '.join(fields)} WHERE id = ?",
        values,
    )
    if cursor.rowcount == 0:
        raise ValueError("Run 不存在")
    row = _run_row(connection, run_id)
    return row or {}


def create_run_record(
    run_id: str,
    course_slug: str,
    mode: str,
    provider: str,
    model: str,
    request: dict[str, Any],
    budget_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Open a new run: one row in `runs` plus the first event.

    The run starts in `QUEUED` at the first stage, and its trace id is the
    run id itself, so one trace covers the whole run.  The row and the first
    event are written in one transaction, so a run never exists without the
    event that says it was created.

    Args:
        run_id: The id of the new run, for example a uuid4 string.
        course_slug: The course this run belongs to, for example "python-101".
        mode: The run mode, for example "guided".
        provider: The model provider, for example "codex_gateway".
        model: The model name, for example "llm-gateway--kimi-k3".
        request: The request that started the run, for example the intake
            payload.  It is stored as JSON so the run can be replayed.
        budget_policy: The budget rules of this run, for example
            {"token_budget_mtokens": 20}.  An empty policy when omitted.

    Returns:
        The new row of `runs`, decoded into a dictionary.
    """
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
        _insert_event(connection, run_id, "run.created", "intake", "课程 Agent Run 已创建")
        row = _run_row(connection, run_id)
    return row or {}


def append_event(
    run_id: str,
    event_type: str,
    step: str,
    message: str,
    payload: dict[str, Any] | None = None,
    trace: Any | None = None,
) -> dict[str, Any]:
    """Write one event into the ledger of a run.

    Args:
        run_id: The run this event belongs to, for example "run-1".
        event_type: What happened, for example "run.created" or "run.failed".
        step: The stage the event belongs to, for example "intake".
        message: A short line a human can read, for example "任务定义完成".
        payload: The details of the event, for example {"attempt": 1}.  An
            empty payload when omitted.
        trace: The trace context this event happened in.  It may be a
            mapping or an object carrying "trace_id" / "span_id" /
            "parent_span_id".  Without one the event falls back to the run
            id as its trace id.

    Returns:
        The new row of `run_events`, decoded into a dictionary.
    """
    with database() as connection:
        return _insert_event(
            connection, run_id, event_type, step, message, payload, trace
        )


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
) -> dict[str, Any]:
    """Change the state of a run and write down what changed.

    Only the fields that are given are touched.  An interrupt or an error
    message is taken away when the matching clear flag is set, because
    "no error" and "the old error" are two different things.

    Args:
        run_id: The run to change, for example "run-1".
        status: The new run status, for example "RUNNING".  One of the
            statuses the contract freezes: `QUEUED` / `RUNNING` /
            `WAITING_APPROVAL` / `COMPLETED` / `FAILED` / `STOPPED`.
        step: The stage the run is at now, for example "mission".
        interrupt_type: The kind of approval the run is waiting for, for
            example "MISSION_APPROVAL".
        interrupt_payload: The details of that approval, for example
            {"type": "MISSION_APPROVAL"}.
        error_message: The reason the run failed, for example "这一批生成失败了".
        clear_interrupt: True takes the interrupt and its payload away.
        clear_error: True takes the error message away.

    Returns:
        The updated row of `runs`, decoded into a dictionary.
    Raises ValueError: when there is no run with this id.
    """
    with database() as connection:
        return _update_run(
            connection,
            run_id,
            status=status,
            step=step,
            interrupt_type=interrupt_type,
            interrupt_payload=interrupt_payload,
            error_message=error_message,
            clear_interrupt=clear_interrupt,
            clear_error=clear_error,
        )


def record_stage_output(
    run_id: str,
    step: str,
    node: str,
    title: str,
    presentation: dict[str, Any],
    raw_output: dict[str, Any],
    *,
    source: str = "model",
    status: str | None = None,
    next_step: str | None = None,
    event_type: str = "stage.completed",
    message: str | None = None,
) -> dict[str, Any]:
    """Record that a stage finished, and what it produced, in one go.

    Three things happen together: the run moves on, the event is written
    down, and the artifact is stored.  They share one transaction, so a stage
    that breaks half way leaves the run exactly as it was -- no event, no
    finished state, no half written artifact.

    The artifact is stored last on purpose.  It is the heaviest of the three
    writes and the one most likely to fail, so when it fails the two cheap
    writes before it are taken back with it.

    Args:
        run_id: The run this stage belongs to, for example "run-1".
        step: The stage that just finished, for example "mission".
        node: The node that produced the output, for example "mission.agent".
        title: A short title a human can read, for example "任务定义".
        presentation: The artifact as it is shown to a person, for example
            {"headline": "任务定义完成"}.
        raw_output: The untouched model output behind it, for example
            {"markdown": "..."}.
        source: Where the artifact came from, for example "model" or
            "system".
        status: The status the run should have afterwards, for example
            "RUNNING".  The run keeps its status when it is None.
        next_step: The stage the run moves to, for example "blueprint".  The
            run stays where it is when it is None.
        event_type: The kind of event this stage leaves, for example
            "stage.completed".
        message: The line a human reads, for example "任务定义完成".  The
            title is used when it is None.

    Returns:
        The row of `run_artifacts` that was written, decoded into a
        dictionary.
    """
    with database() as connection:
        if status is not None or next_step is not None:
            _update_run(connection, run_id, status=status, step=next_step)
        _insert_event(connection, run_id, event_type, step, message or title)
        return insert_run_artifact(
            connection, run_id, step, node, title, presentation, raw_output, source
        )


def get_run_record(run_id: str) -> dict[str, Any] | None:
    """Read the whole story of a run.

    Args:
        run_id: The run to read, for example "run-1".

    Returns:
        A dictionary with four keys: "run" (the row of `runs`), "events"
        (the events of the run, oldest first), "artifacts" (the artifacts of
        the run, oldest first) and "workflow_steps" (the seven stages, each
        with a "status" of "completed", "active" or "pending").  It is None
        when there is no such run, so a missing run stays distinguishable
        from an empty one.
    """
    with database() as connection:
        run = _run_row(connection, run_id)
        if run is None:
            return None
        event_rows = connection.execute(
            "SELECT * FROM run_events WHERE run_id = ? ORDER BY seq",
            (run_id,),
        ).fetchall()
    events = [row_to_dict(row) or {} for row in event_rows]
    current_index = _step_index(run["current_step"])
    finished = run["status"] == "COMPLETED"
    return {
        "run": run,
        "events": events,
        "artifacts": list_run_artifacts(run_id),
        "workflow_steps": [
            {
                **definition,
                "status": (
                    "completed"
                    if index < current_index or (finished and index == current_index)
                    else "active"
                    if index == current_index
                    else "pending"
                ),
            }
            for index, definition in enumerate(WORKFLOW_STEPS)
        ],
    }


def list_run_records(course_slug: str | None = None) -> list[dict[str, Any]]:
    """List the runs, newest first.

    Args:
        course_slug: The course whose runs are wanted, for example
            "python-101".  Every run when it is None.

    Returns:
        One dictionary per run, newest first.  Without a course slug the
        list stops at the hundred newest runs.
    """
    with database() as connection:
        if course_slug:
            rows = connection.execute(
                "SELECT * FROM runs WHERE course_slug = ? ORDER BY created_at DESC, rowid DESC",
                (course_slug,),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM runs ORDER BY created_at DESC, rowid DESC LIMIT 100"
            ).fetchall()
    return [row_to_dict(row) or {} for row in rows]
