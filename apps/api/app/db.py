"""SQLite storage for the course agent.

`app/db.py` owns two things: the schema of the thirteen tables the later
phases read from (`SCHEMA`), and the small set of helpers that open a
connection to them (`initialize_database`, `database`, `row_to_dict`,
`utcnow`).

The database is a local file under `.course-agent/`.  It holds the facts
about runs and their artefacts -- never the course text itself, which
stays in `courses/<slug>/lessons/*.md`.
"""

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

CREATE UNIQUE INDEX IF NOT EXISTS idx_run_artifacts_identity
ON run_artifacts(run_id, node, source);

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

JSON_COLUMNS = (
    "request_json",
    "budget_policy_json",
    "interrupt_payload_json",
    "payload_json",
    "presentation_json",
    "raw_output_json",
    "scope_json",
    "verification_json",
    "evidence_json",
    "success_criteria_json",
    "latest_verification_json",
    "plan_json",
    "patch_json",
    "output_json",
    "attributes_json",
    "previous_policy_json",
    "next_policy_json",
)


def utcnow() -> str:
    """Return the current moment as a timezone aware ISO 8601 string.

    Args:
        Nothing.

    Returns:
        The current UTC time, for example "2026-10-27T08:31:05.123456+00:00".
        Every timestamp written into the database uses this format, so the
        rows can be sorted and compared as plain text.
    """
    return datetime.now(UTC).isoformat()


def initialize_database(path: Path | None = None) -> None:
    """Create the thirteen tables in the database file, if they are not there.

    The script uses ``CREATE TABLE IF NOT EXISTS`` throughout, so calling
    this a second time on the same file changes nothing and keeps the rows
    that are already stored.  A missing parent directory is created on the
    way.

    Args:
        path: The database file to write, for example
            ``.course-agent/agent.db``.  When it is None the path comes
            from the settings, which is the normal way to call it.

    Returns:
        Nothing. The file exists with the full schema once this returns.
        Raises sqlite3.OperationalError when the file cannot be opened or
        written.
    """
    target = path or get_settings().database_path
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(target, timeout=30, isolation_level="")
    try:
        connection.executescript(SCHEMA)
    finally:
        connection.close()


@contextmanager
def database() -> Iterator[sqlite3.Connection]:
    """Open a connection to the business database and hand it to the caller.

    The schema is checked on the way in, so a caller never has to ask
    whether the tables exist.  Leaving the block normally commits what was
    written; an exception inside the block rolls the transaction back, so a
    half finished step leaves no rows behind.

    Args:
        Nothing. The database file comes from the settings.

    Yields:
        An open connection whose rows come back as ``sqlite3.Row`` objects,
        so that ``row_to_dict`` can turn them into plain dictionaries.
    """
    path = get_settings().database_path
    initialize_database(path)
    connection = sqlite3.connect(
        path,
        timeout=30,
        check_same_thread=False,
        isolation_level="",
    )
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
    """Turn a database row into a plain dictionary and decode its JSON columns.

    The columns whose name ends in ``_json`` hold a JSON document as text.
    They are decoded and stored under the shorter name, so ``payload_json``
    becomes ``payload`` and holds an object instead of a string.

    Args:
        row: The row to convert, for example the result of
            ``connection.execute("SELECT * FROM runs WHERE id = ?")``.  It
            may be None, which means there was no such row.

    Returns:
        The row as a dictionary, with every JSON column decoded.  It is
        None when the given row was None, so that a missing record stays
        distinguishable from an empty one.
    """
    if row is None:
        return None
    value = dict(row)
    for key in JSON_COLUMNS:
        if key not in value:
            continue
        raw = value.pop(key)
        value[key.removesuffix("_json")] = json.loads(raw) if raw else None
    return value
