from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from app.config import get_settings


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    course_slug TEXT NOT NULL,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    current_step TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    request_json TEXT NOT NULL,
    interrupt_type TEXT,
    interrupt_payload_json TEXT,
    error_message TEXT,
    trace_id TEXT,
    budget_policy_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    run_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    step TEXT NOT NULL,
    message TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    trace_id TEXT,
    span_id TEXT,
    parent_span_id TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES runs(id)
);

CREATE TABLE IF NOT EXISTS chapter_versions (
    id TEXT PRIMARY KEY,
    course_slug TEXT NOT NULL,
    chapter_key TEXT NOT NULL,
    source_path TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    snapshot_path TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_artifacts (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    step TEXT NOT NULL,
    node TEXT NOT NULL,
    title TEXT NOT NULL,
    source TEXT NOT NULL,
    presentation_json TEXT NOT NULL,
    raw_output_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES runs(id)
);

CREATE TABLE IF NOT EXISTS repair_tasks (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    course_slug TEXT NOT NULL,
    batch_id TEXT,
    chapter INTEGER,
    category TEXT NOT NULL,
    severity TEXT NOT NULL,
    finding_kind TEXT NOT NULL DEFAULT 'quality',
    blocking INTEGER NOT NULL DEFAULT 1,
    disposition TEXT NOT NULL DEFAULT 'repair',
    path TEXT NOT NULL,
    issue TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    success_criteria_json TEXT NOT NULL,
    status TEXT NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    latest_verification_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES runs(id)
);

CREATE INDEX IF NOT EXISTS idx_repair_tasks_run_status
ON repair_tasks(run_id, status);

CREATE TABLE IF NOT EXISTS trace_spans (
    id TEXT PRIMARY KEY, trace_id TEXT NOT NULL, run_id TEXT NOT NULL, parent_span_id TEXT,
    command_id TEXT, node_execution_id TEXT, stage TEXT, kind TEXT NOT NULL, name TEXT NOT NULL,
    status TEXT NOT NULL, attributes_json TEXT NOT NULL DEFAULT '{}', error_code TEXT,
    error_message TEXT, started_at TEXT NOT NULL, ended_at TEXT, duration_ms INTEGER,
    FOREIGN KEY(run_id) REFERENCES runs(id)
);
CREATE INDEX IF NOT EXISTS idx_trace_spans_run_started ON trace_spans(run_id, started_at);
CREATE INDEX IF NOT EXISTS idx_trace_spans_trace_parent ON trace_spans(trace_id, parent_span_id, started_at);

CREATE TABLE IF NOT EXISTS budget_ledger_entries (
    id TEXT PRIMARY KEY, run_id TEXT NOT NULL, trace_id TEXT NOT NULL, span_id TEXT NOT NULL,
    stage TEXT, node_execution_id TEXT, agent_id TEXT, provider TEXT, model TEXT,
    entry_type TEXT NOT NULL, input_tokens INTEGER, output_tokens INTEGER, total_tokens INTEGER,
    estimated_cost_microusd INTEGER, duration_ms INTEGER, pricing_version TEXT, created_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES runs(id), FOREIGN KEY(span_id) REFERENCES trace_spans(id)
);
CREATE INDEX IF NOT EXISTS idx_budget_ledger_run_created ON budget_ledger_entries(run_id, created_at);

CREATE TABLE IF NOT EXISTS budget_adjustments (
    id TEXT PRIMARY KEY, run_id TEXT NOT NULL, trace_id TEXT NOT NULL, span_id TEXT,
    previous_policy_json TEXT NOT NULL, next_policy_json TEXT NOT NULL, reason TEXT NOT NULL,
    created_at TEXT NOT NULL, FOREIGN KEY(run_id) REFERENCES runs(id)
);

CREATE INDEX IF NOT EXISTS idx_repair_tasks_course_chapter_status
ON repair_tasks(course_slug, chapter, status);

CREATE TABLE IF NOT EXISTS repair_task_attempts (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    attempt_number INTEGER NOT NULL,
    phase TEXT NOT NULL,
    plan_json TEXT,
    patch_json TEXT,
    verification_json TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(task_id) REFERENCES repair_tasks(id)
);

CREATE TABLE IF NOT EXISTS commands (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    leased_by TEXT,
    lease_expires_at TEXT,
    heartbeat_at TEXT,
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES runs(id)
);

CREATE INDEX IF NOT EXISTS idx_commands_claim
ON commands(status, lease_expires_at, created_at);

CREATE TABLE IF NOT EXISTS node_executions (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    command_id TEXT,
    node_id TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    leased_by TEXT,
    lease_expires_at TEXT,
    heartbeat_at TEXT,
    checkpoint_ref TEXT,
    output_json TEXT,
    error_message TEXT,
    started_at TEXT,
    finished_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(run_id, node_id, input_hash),
    FOREIGN KEY(run_id) REFERENCES runs(id),
    FOREIGN KEY(command_id) REFERENCES commands(id)
);

CREATE INDEX IF NOT EXISTS idx_node_executions_claim
ON node_executions(status, lease_expires_at);

CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    run_id TEXT,
    artifact_type TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    storage_uri TEXT NOT NULL,
    producer_execution_id TEXT,
    scope_json TEXT NOT NULL,
    sensitivity TEXT NOT NULL,
    base_content_hash TEXT,
    status TEXT NOT NULL,
    is_current INTEGER NOT NULL DEFAULT 0,
    verification_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES runs(id)
);

CREATE INDEX IF NOT EXISTS idx_artifacts_current_scope
ON artifacts(artifact_type, scope_json, is_current, created_at);

CREATE TABLE IF NOT EXISTS artifact_edges (
    parent_artifact_id TEXT NOT NULL,
    child_artifact_id TEXT NOT NULL,
    relation TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(parent_artifact_id, child_artifact_id, relation),
    FOREIGN KEY(parent_artifact_id) REFERENCES artifacts(id),
    FOREIGN KEY(child_artifact_id) REFERENCES artifacts(id)
);
"""


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


def initialize_database(path: Path | None = None) -> None:
    target = path or get_settings().database_path
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(target) as connection:
        connection.executescript(SCHEMA)
        _migrate_execution_tables(connection)
        _migrate_observability_tables(connection)
        _migrate_repair_task_findings(connection)


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}


def _migrate_execution_tables(connection: sqlite3.Connection) -> None:
    """Upgrade the earlier Command prototype without discarding local Run history."""
    commands = _table_columns(connection, "commands")
    nodes = _table_columns(connection, "node_executions")
    command_target = {"run_id", "kind", "error_message", "started_at", "finished_at"}
    node_target = {"command_id", "attempt_count", "output_json", "error_message"}
    if command_target.issubset(commands) and node_target.issubset(nodes):
        return
    if nodes and not node_target.issubset(nodes):
        connection.execute("ALTER TABLE node_executions RENAME TO node_executions_legacy_v1")
    if commands and not command_target.issubset(commands):
        connection.execute("ALTER TABLE commands RENAME TO commands_legacy_v1")
    connection.executescript(SCHEMA)
    legacy_commands = _table_columns(connection, "commands_legacy_v1") if "commands_legacy_v1" in _tables(connection) else set()
    if legacy_commands:
        connection.execute(
            """INSERT INTO commands (id, run_id, kind, payload_json, status, leased_by, lease_expires_at,
            heartbeat_at, attempt_count, max_attempts, cancel_requested, error_message, created_at, updated_at)
            SELECT legacy.id, legacy.aggregate_id, legacy.command_type, legacy.payload_json, legacy.status,
            legacy.leased_by, legacy.lease_expires_at, legacy.heartbeat_at, legacy.attempt_count,
            legacy.max_attempts, legacy.cancel_requested, legacy.error_json, legacy.created_at, legacy.updated_at
            FROM commands_legacy_v1 AS legacy JOIN runs ON runs.id = legacy.aggregate_id"""
        )
    legacy_nodes = _table_columns(connection, "node_executions_legacy_v1") if "node_executions_legacy_v1" in _tables(connection) else set()
    if legacy_nodes:
        connection.execute(
            """INSERT INTO node_executions (id, run_id, node_id, input_hash, status, attempt_count, leased_by,
            lease_expires_at, heartbeat_at, checkpoint_ref, started_at, finished_at, created_at, updated_at)
            SELECT legacy.id, legacy.run_id, legacy.node_id, legacy.input_hash, legacy.status, legacy.attempt,
            legacy.leased_by, legacy.lease_expires_at, legacy.heartbeat_at, legacy.checkpoint_ref,
            legacy.started_at, legacy.finished_at, legacy.created_at, legacy.updated_at
            FROM node_executions_legacy_v1 AS legacy JOIN runs ON runs.id = legacy.run_id"""
        )
    connection.execute("DROP TABLE IF EXISTS node_executions_legacy_v1")
    connection.execute("DROP TABLE IF EXISTS commands_legacy_v1")
    connection.executescript("""
    CREATE INDEX IF NOT EXISTS idx_commands_claim ON commands(status, lease_expires_at, created_at);
    CREATE INDEX IF NOT EXISTS idx_node_executions_claim ON node_executions(status, lease_expires_at);
    """)
    _migrate_observability_tables(connection)


def _migrate_observability_tables(connection: sqlite3.Connection) -> None:
    for table, columns in {
        "runs": {"trace_id": "TEXT", "budget_policy_json": "TEXT NOT NULL DEFAULT '{}'"},
        "run_events": {"trace_id": "TEXT", "span_id": "TEXT", "parent_span_id": "TEXT"},
    }.items():
        existing = _table_columns(connection, table)
        for name, definition in columns.items():
            if name not in existing:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
    connection.executescript(SCHEMA)
    connection.execute("UPDATE runs SET trace_id = id WHERE trace_id IS NULL OR trace_id = ''")
    connection.execute("UPDATE runs SET budget_policy_json = '{}' WHERE budget_policy_json IS NULL OR budget_policy_json = ''")


def _migrate_repair_task_findings(connection: sqlite3.Connection) -> None:
    columns = {
        "finding_kind": "TEXT NOT NULL DEFAULT 'quality'",
        "blocking": "INTEGER NOT NULL DEFAULT 1",
        "disposition": "TEXT NOT NULL DEFAULT 'repair'",
    }
    existing = _table_columns(connection, "repair_tasks")
    for name, definition in columns.items():
        if name not in existing:
            connection.execute(f"ALTER TABLE repair_tasks ADD COLUMN {name} {definition}")
    connection.executescript(SCHEMA)


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}


@contextmanager
def database() -> Iterator[sqlite3.Connection]:
    path = get_settings().database_path
    initialize_database(path)
    connection = sqlite3.connect(path, timeout=30, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    value = dict(row)
    for key in (
        "request_json",
        "budget_policy_json",
        "attributes_json",
        "previous_policy_json",
        "next_policy_json",
        "interrupt_payload_json",
        "payload_json",
        "presentation_json",
        "raw_output_json",
        "evidence_json",
        "success_criteria_json",
        "latest_verification_json",
        "plan_json",
        "patch_json",
        "verification_json",
        "output_json",
        "scope_json",
        "verification_json",
    ):
        if key in value:
            raw = value.pop(key)
            value[key.removesuffix("_json")] = json.loads(raw) if raw else None
    return value
