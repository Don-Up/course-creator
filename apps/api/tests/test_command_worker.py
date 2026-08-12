from types import SimpleNamespace
import sqlite3

from app import db
from app.workflow.command_repository import (
    claim_next_command,
    claim_node_execution,
    command_projection,
    complete_node_execution,
    enqueue_command,
    finish_command,
    request_run_stop,
)
from app.workflow.repository import create_run_record


def _database(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "get_settings", lambda: SimpleNamespace(database_path=tmp_path / "agent.db"))
    create_run_record("run-command", "demo", "guided", "fake", "fake-model", {"workflow_scope": "new_course"})


def test_command_id_is_idempotent_and_can_be_claimed_once(tmp_path, monkeypatch):
    _database(tmp_path, monkeypatch)
    first, duplicate = enqueue_command("run-command", "START", command_id="command-1")
    second, repeated = enqueue_command("run-command", "START", command_id="command-1")

    assert duplicate is False
    assert repeated is True
    assert first["id"] == second["id"] == "command-1"
    assert claim_next_command("worker-a", 30)["id"] == "command-1"
    assert claim_next_command("worker-b", 30) is None


def test_expired_command_lease_is_taken_over(tmp_path, monkeypatch):
    _database(tmp_path, monkeypatch)
    enqueue_command("run-command", "START", command_id="command-1")
    claimed = claim_next_command("worker-a", 30)
    with db.database() as connection:
        connection.execute("UPDATE commands SET lease_expires_at = ? WHERE id = ?", ("2000-01-01T00:00:00+00:00", claimed["id"]))

    recovered = claim_next_command("worker-b", 30)

    assert recovered["id"] == "command-1"
    assert recovered["leased_by"] == "worker-b"
    assert recovered["attempt_count"] == 2


def test_node_execution_reuses_only_committed_output(tmp_path, monkeypatch):
    _database(tmp_path, monkeypatch)
    claimed, _ = enqueue_command("run-command", "START", command_id="command-1")
    assert claim_next_command("worker-a", 30)["id"] == claimed["id"]

    state, execution = claim_node_execution("run-command", "command-1", "draft_mission", "input-1", "worker-a", 30)
    assert state == "claimed"
    complete_node_execution(execution["id"], "worker-a", {"mission": "已提交"})

    state, reused = claim_node_execution("run-command", "command-1", "draft_mission", "input-1", "worker-b", 30)
    assert state == "reused"
    assert reused["output"] == {"mission": "已提交"}


def test_stop_marks_active_command_for_cooperative_cancellation(tmp_path, monkeypatch):
    _database(tmp_path, monkeypatch)
    enqueue_command("run-command", "START", command_id="command-1")
    claim_next_command("worker-a", 30)

    request_run_stop("run-command")

    with db.database() as connection:
        command = connection.execute("SELECT cancel_requested FROM commands WHERE id = 'command-1'").fetchone()
    assert command["cancel_requested"] == 1


def test_read_model_exposes_active_command_and_node_timeline(tmp_path, monkeypatch):
    _database(tmp_path, monkeypatch)
    enqueue_command("run-command", "START", command_id="command-1")
    claim_next_command("worker-a", 30)
    _, execution = claim_node_execution("run-command", "command-1", "draft_mission", "input-1", "worker-a", 30)

    projection = command_projection("run-command")

    assert projection["active_command"]["id"] == "command-1"
    assert projection["current_node_execution"]["id"] == execution["id"]
    assert projection["command_timeline"][0]["kind"] == "START"
    assert projection["node_execution_timeline"][0]["node_id"] == "draft_mission"


def test_legacy_execution_tables_are_upgraded_before_a_command_is_written(tmp_path, monkeypatch):
    database_path = tmp_path / "agent.db"
    with sqlite3.connect(database_path) as connection:
        connection.executescript("""
        CREATE TABLE commands (id TEXT PRIMARY KEY, command_type TEXT NOT NULL, aggregate_id TEXT NOT NULL,
          payload_json TEXT NOT NULL, status TEXT NOT NULL, leased_by TEXT, lease_expires_at TEXT,
          heartbeat_at TEXT, attempt_count INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL DEFAULT 3,
          cancel_requested INTEGER NOT NULL DEFAULT 0, error_json TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE node_executions (id TEXT PRIMARY KEY, run_id TEXT NOT NULL, node_id TEXT NOT NULL,
          stage TEXT NOT NULL, attempt INTEGER NOT NULL DEFAULT 1, input_hash TEXT NOT NULL, status TEXT NOT NULL,
          leased_by TEXT, lease_expires_at TEXT, heartbeat_at TEXT, checkpoint_ref TEXT, started_at TEXT,
          finished_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(run_id, node_id, input_hash));
        """)
    monkeypatch.setattr(db, "get_settings", lambda: SimpleNamespace(database_path=database_path))
    create_run_record("run-migration", "demo", "guided", "fake", "fake-model", {"workflow_scope": "new_course"})

    command, duplicate = enqueue_command("run-migration", "START", command_id="migration-command")

    assert duplicate is False
    assert command["kind"] == "START"
    with sqlite3.connect(database_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(commands)")}
    assert {"run_id", "kind", "error_message", "started_at", "finished_at"}.issubset(columns)
