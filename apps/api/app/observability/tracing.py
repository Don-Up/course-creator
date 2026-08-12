from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from time import perf_counter
from typing import Any, Iterator

from app.db import database, row_to_dict, utcnow
from app.observability.context import TraceContext, current_trace, trace_scope

_SAFE_ATTRIBUTE_KEYS = {"provider", "model", "agent_id", "agent_version", "operation", "tool_id", "workflow_node", "retry_index", "input_tokens", "output_tokens", "total_tokens", "estimated_cost_usd", "response_status", "error_class"}


def start_span(run_id: str, *, kind: str, name: str, parent_span_id: str | None = None, command_id: str | None = None, node_execution_id: str | None = None, stage: str | None = None, attributes: dict[str, Any] | None = None, span_id: str | None = None) -> dict[str, Any]:
    active = current_trace()
    identifier = span_id or str(uuid.uuid4())
    parent = parent_span_id if parent_span_id is not None else (active.span_id if active else None)
    safe_attributes = {key: value for key, value in (attributes or {}).items() if key in _SAFE_ATTRIBUTE_KEYS and isinstance(value, (str, int, float, bool))}
    try:
        with database() as connection:
            connection.execute("""INSERT OR IGNORE INTO trace_spans (id, trace_id, run_id, parent_span_id, command_id, node_execution_id, stage, kind, name, status, attributes_json, started_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'RUNNING', ?, ?)""", (identifier, run_id, run_id, parent, command_id or (active.command_id if active else None), node_execution_id or (active.node_execution_id if active else None), stage or (active.stage if active else None), kind, name, json.dumps(safe_attributes, ensure_ascii=False), utcnow()))
    except sqlite3.IntegrityError:
        # Unit-level node helpers can be exercised without a persisted Run.
        # Production calls always create the Run before creating its Span.
        pass
    return {"id": identifier, "trace_id": run_id, "run_id": run_id, "parent_span_id": parent, "command_id": command_id or (active.command_id if active else None), "node_execution_id": node_execution_id or (active.node_execution_id if active else None), "stage": stage or (active.stage if active else None), "kind": kind, "name": name}


def finish_span(span_id: str, status: str, *, error: Exception | None = None, attributes: dict[str, Any] | None = None) -> None:
    with database() as connection:
        row = connection.execute("SELECT attributes_json, started_at FROM trace_spans WHERE id = ?", (span_id,)).fetchone()
        if not row:
            return
        existing = json.loads(row[0] or "{}")
        existing.update({key: value for key, value in (attributes or {}).items() if key in _SAFE_ATTRIBUTE_KEYS and isinstance(value, (str, int, float, bool))})
        started = row[1]
        from datetime import datetime
        duration = max(0, round((datetime.fromisoformat(utcnow()) - datetime.fromisoformat(started)).total_seconds() * 1000))
        connection.execute("UPDATE trace_spans SET status = ?, attributes_json = ?, error_code = ?, error_message = ?, ended_at = ?, duration_ms = ? WHERE id = ?", (status, json.dumps(existing, ensure_ascii=False), type(error).__name__ if error else None, str(error)[:500] if error else None, utcnow(), duration, span_id))


@contextmanager
def span_scope(span: dict[str, Any]) -> Iterator[dict[str, Any]]:
    context = TraceContext(trace_id=span["trace_id"], run_id=span["run_id"], span_id=span["id"], parent_span_id=span.get("parent_span_id"), command_id=span.get("command_id"), node_execution_id=span.get("node_execution_id"), stage=span.get("stage"))
    with trace_scope(context):
        try:
            yield span
        except Exception as exc:
            finish_span(span["id"], "FAILED", error=exc)
            raise
        else:
            finish_span(span["id"], "SUCCEEDED")


def get_trace_projection(run_id: str) -> dict[str, Any]:
    with database() as connection:
        rows = connection.execute("SELECT * FROM trace_spans WHERE run_id = ? ORDER BY started_at, id", (run_id,)).fetchall()
    return {"trace_id": run_id, "run_id": run_id, "spans": [row_to_dict(row) for row in rows]}
