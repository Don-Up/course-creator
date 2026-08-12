"""SQLite persistence for Worker commands and idempotent node executions."""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.db import database, row_to_dict, utcnow

COMMAND_TERMINAL_STATUSES = {"SUCCEEDED", "FAILED", "CANCELLED", "WAITING_APPROVAL"}


def _lease_deadline(seconds: int) -> str:
    return (datetime.now(UTC) + timedelta(seconds=seconds)).isoformat()


def enqueue_command(run_id: str, kind: str, payload: dict[str, Any] | None = None, *, command_id: str | None = None) -> tuple[dict[str, Any], bool]:
    command_id = command_id or str(uuid.uuid4())
    now = utcnow()
    with database() as connection:
        existing = connection.execute("SELECT * FROM commands WHERE id = ?", (command_id,)).fetchone()
        if existing:
            return row_to_dict(existing) or {}, True
        connection.execute("INSERT INTO commands (id, run_id, kind, payload_json, status, created_at, updated_at) VALUES (?, ?, ?, ?, 'PENDING', ?, ?)", (command_id, run_id, kind, json.dumps(payload or {}, ensure_ascii=False), now, now))
        row = connection.execute("SELECT * FROM commands WHERE id = ?", (command_id,)).fetchone()
    from app.workflow.repository import append_event
    append_event(run_id, "command.queued", "intake", f"执行命令已入队：{kind}", {"command_id": command_id, "kind": kind})
    return row_to_dict(row) or {}, False


def claim_next_command(worker_id: str, lease_seconds: int) -> dict[str, Any] | None:
    now = utcnow()
    with database() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT * FROM commands WHERE status IN ('PENDING', 'RETRYABLE') OR (status IN ('LEASED', 'RUNNING') AND lease_expires_at < ?) ORDER BY created_at LIMIT 1", (now,)).fetchone()
        if not row:
            return None
        command_id = row["id"]
        cursor = connection.execute("UPDATE commands SET status = 'LEASED', leased_by = ?, lease_expires_at = ?, heartbeat_at = ?, attempt_count = attempt_count + 1, started_at = COALESCE(started_at, ?), updated_at = ? WHERE id = ? AND (status IN ('PENDING', 'RETRYABLE') OR (status IN ('LEASED', 'RUNNING') AND lease_expires_at < ?))", (worker_id, _lease_deadline(lease_seconds), now, now, now, command_id, now))
        if cursor.rowcount != 1:
            return None
        claimed = connection.execute("SELECT * FROM commands WHERE id = ?", (command_id,)).fetchone()
    value = row_to_dict(claimed) or {}
    from app.workflow.repository import append_event
    append_event(value["run_id"], "command.leased", "intake", "Worker 已领取执行命令", {"command_id": command_id, "worker_id": worker_id})
    return value


def renew_command_lease(command_id: str, worker_id: str, lease_seconds: int) -> bool:
    now = utcnow()
    with database() as connection:
        cursor = connection.execute("UPDATE commands SET status = 'RUNNING', lease_expires_at = ?, heartbeat_at = ?, updated_at = ? WHERE id = ? AND leased_by = ? AND status IN ('LEASED', 'RUNNING')", (_lease_deadline(lease_seconds), now, now, command_id, worker_id))
    return cursor.rowcount == 1


def finish_command(command_id: str, worker_id: str, status: str, *, error: str | None = None) -> None:
    if status not in COMMAND_TERMINAL_STATUSES | {"RETRYABLE"}:
        raise ValueError(f"非法 Command 状态：{status}")
    now = utcnow()
    with database() as connection:
        connection.execute("UPDATE commands SET status = ?, error_message = ?, finished_at = ?, updated_at = ?, lease_expires_at = NULL WHERE id = ? AND leased_by = ?", (status, error, now if status in COMMAND_TERMINAL_STATUSES else None, now, command_id, worker_id))


def request_run_stop(run_id: str) -> None:
    with database() as connection:
        connection.execute("UPDATE commands SET cancel_requested = 1, updated_at = ? WHERE run_id = ? AND status IN ('PENDING', 'LEASED', 'RUNNING', 'RETRYABLE')", (utcnow(), run_id))
    from app.workflow.repository import append_event
    append_event(run_id, "run.stop_requested", "intake", "已请求停止；Worker 将在当前安全边界停止")


def is_command_cancel_requested(command_id: str) -> bool:
    with database() as connection:
        row = connection.execute("SELECT cancel_requested FROM commands WHERE id = ?", (command_id,)).fetchone()
    return bool(row and row["cancel_requested"])


def claim_node_execution(run_id: str, command_id: str, node_id: str, input_hash: str, worker_id: str, lease_seconds: int) -> tuple[str, dict[str, Any]]:
    now = utcnow()
    with database() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT * FROM node_executions WHERE run_id = ? AND node_id = ? AND input_hash = ?", (run_id, node_id, input_hash)).fetchone()
        if row and row["status"] == "SUCCEEDED":
            return "reused", row_to_dict(row) or {}
        if row and row["status"] == "RUNNING" and row["lease_expires_at"] and row["lease_expires_at"] >= now:
            return "busy", row_to_dict(row) or {}
        if row:
            connection.execute("UPDATE node_executions SET command_id = ?, status = 'RUNNING', attempt_count = attempt_count + 1, leased_by = ?, lease_expires_at = ?, heartbeat_at = ?, started_at = ?, updated_at = ?, error_message = NULL WHERE id = ?", (command_id, worker_id, _lease_deadline(lease_seconds), now, now, now, row["id"]))
        else:
            execution_id = str(uuid.uuid4())
            connection.execute("INSERT INTO node_executions (id, run_id, command_id, node_id, input_hash, status, attempt_count, leased_by, lease_expires_at, heartbeat_at, started_at, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 'RUNNING', 1, ?, ?, ?, ?, ?, ?)", (execution_id, run_id, command_id, node_id, input_hash, worker_id, _lease_deadline(lease_seconds), now, now, now, now))
        claimed = connection.execute("SELECT * FROM node_executions WHERE run_id = ? AND node_id = ? AND input_hash = ?", (run_id, node_id, input_hash)).fetchone()
    return "claimed", row_to_dict(claimed) or {}


def complete_node_execution(execution_id: str, worker_id: str, output: dict[str, Any]) -> None:
    now = utcnow()
    with database() as connection:
        connection.execute("UPDATE node_executions SET status = 'SUCCEEDED', output_json = ?, finished_at = ?, updated_at = ?, lease_expires_at = NULL WHERE id = ? AND leased_by = ?", (json.dumps(output, ensure_ascii=False, default=str), now, now, execution_id, worker_id))


def fail_node_execution(execution_id: str, worker_id: str, error: str) -> None:
    with database() as connection:
        connection.execute("UPDATE node_executions SET status = 'FAILED', error_message = ?, updated_at = ?, lease_expires_at = NULL WHERE id = ? AND leased_by = ?", (error[:2000], utcnow(), execution_id, worker_id))


def command_projection(run_id: str) -> dict[str, Any]:
    """Small read model for the workbench; raw command payloads stay private."""
    with database() as connection:
        commands = connection.execute("SELECT id, kind, status, attempt_count, max_attempts, leased_by, lease_expires_at, heartbeat_at, cancel_requested, error_message, created_at, started_at, finished_at, updated_at FROM commands WHERE run_id = ? ORDER BY created_at DESC LIMIT 12", (run_id,)).fetchall()
        nodes = connection.execute("SELECT id, command_id, node_id, input_hash, status, attempt_count, leased_by, lease_expires_at, heartbeat_at, error_message, started_at, finished_at, updated_at FROM node_executions WHERE run_id = ? ORDER BY updated_at DESC LIMIT 12", (run_id,)).fetchall()
    command_items = [row_to_dict(row) or {} for row in commands]
    node_items = [row_to_dict(row) or {} for row in nodes]
    active = next((item for item in command_items if item.get("status") in {"PENDING", "LEASED", "RUNNING", "RETRYABLE"}), None)
    current_node = next((item for item in node_items if item.get("status") == "RUNNING"), None)
    return {"active_command": active, "command_timeline": command_items, "current_node_execution": current_node, "node_execution_timeline": node_items}
