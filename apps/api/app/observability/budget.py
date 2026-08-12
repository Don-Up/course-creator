from __future__ import annotations

import json
import uuid
from typing import Any

from app.db import database, row_to_dict, utcnow
from app.observability.contracts import InvocationMetrics


def record_model_usage(run_id: str, span_id: str, metrics: InvocationMetrics, *, stage: str | None = None, node_execution_id: str | None = None, agent_id: str | None = None) -> dict[str, Any]:
    total = metrics.total_tokens
    if total is None and metrics.input_tokens is not None and metrics.output_tokens is not None:
        total = metrics.input_tokens + metrics.output_tokens
    with database() as connection:
        connection.execute("""INSERT INTO budget_ledger_entries (id, run_id, trace_id, span_id, stage, node_execution_id, agent_id, provider, model, entry_type, input_tokens, output_tokens, total_tokens, estimated_cost_microusd, duration_ms, pricing_version, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'model_call', ?, ?, ?, ?, ?, ?, ?)""", (str(uuid.uuid4()), run_id, run_id, span_id, stage, node_execution_id, agent_id, metrics.provider, metrics.model, metrics.input_tokens, metrics.output_tokens, total, metrics.estimated_cost_microusd, metrics.duration_ms, metrics.pricing_version, utcnow()))
    snapshot = get_budget_projection(run_id)
    if snapshot["status"] == "EXCEEDED":
        from app.workflow.repository import append_event
        if not snapshot.get("threshold_event_recorded"):
            append_event(run_id, "budget.threshold_exceeded", stage or "generation", "课程预算阈值已超出；系统继续执行并记录实际消耗", {"violations": snapshot["violations"]})
    return snapshot


def get_budget_projection(run_id: str) -> dict[str, Any]:
    with database() as connection:
        run = connection.execute("SELECT budget_policy_json FROM runs WHERE id = ?", (run_id,)).fetchone()
        rows = connection.execute("SELECT * FROM budget_ledger_entries WHERE run_id = ? ORDER BY created_at, id", (run_id,)).fetchall()
        threshold_event = connection.execute("SELECT 1 FROM run_events WHERE run_id = ? AND event_type = 'budget.threshold_exceeded' LIMIT 1", (run_id,)).fetchone()
        adjustments = connection.execute("SELECT * FROM budget_adjustments WHERE run_id = ? ORDER BY created_at, id", (run_id,)).fetchall()
    policy = json.loads(run[0] or "{}") if run else {}
    entries = [row_to_dict(row) or {} for row in rows]
    totals = {"input_tokens": sum(item.get("input_tokens") or 0 for item in entries), "output_tokens": sum(item.get("output_tokens") or 0 for item in entries), "total_tokens": sum(item.get("total_tokens") or 0 for item in entries), "model_calls": len(entries), "estimated_cost_microusd": sum(item.get("estimated_cost_microusd") or 0 for item in entries) if any(item.get("estimated_cost_microusd") is not None for item in entries) else None}
    limits = {"total_tokens": policy.get("max_total_tokens"), "input_tokens": policy.get("max_input_tokens"), "output_tokens": policy.get("max_output_tokens"), "model_calls": policy.get("max_model_calls"), "estimated_cost_microusd": policy.get("max_estimated_cost_microusd")}
    violations = [{"metric": metric, "limit": limit, "actual": totals[metric]} for metric, limit in limits.items() if limit is not None and totals[metric] is not None and totals[metric] > limit]
    return {"effective_policy": policy, "usage_totals": totals, "remaining": {key: None if limit is None or totals[key] is None else limit - totals[key] for key, limit in limits.items()}, "status": "EXCEEDED" if violations else "WITHIN_LIMIT", "violations": violations, "top_consumers": entries[-10:], "latest_adjustments": [row_to_dict(row) for row in adjustments], "threshold_event_recorded": bool(threshold_event)}
