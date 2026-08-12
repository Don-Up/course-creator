import sqlite3
from types import SimpleNamespace

from app import db
from app.workflow.repository import append_event, create_run_record


def _use_database(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "get_settings", lambda: SimpleNamespace(database_path=tmp_path / "agent.db"))
    return tmp_path / "agent.db"


def test_new_run_has_trace_root_and_observability_tables(tmp_path, monkeypatch):
    from app.observability.tracing import get_trace_projection

    database_path = _use_database(tmp_path, monkeypatch)
    create_run_record("run-observe", "demo", "guided", "fake", "fake-model", {})

    with sqlite3.connect(database_path) as connection:
        run = connection.execute("SELECT trace_id, budget_policy_json FROM runs WHERE id = ?", ("run-observe",)).fetchone()
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert run == ("run-observe", "{}")
    assert {"trace_spans", "budget_ledger_entries", "budget_adjustments"} <= tables
    trace = get_trace_projection("run-observe")
    assert trace["trace_id"] == "run-observe"
    assert [(span["kind"], span["name"], span["status"]) for span in trace["spans"]] == [("run", "Run", "RUNNING")]


def test_new_course_run_persists_its_initial_token_policy(tmp_path, monkeypatch):
    from app.workflow.repository import get_run_record

    _use_database(tmp_path, monkeypatch)
    create_run_record(
        "run-initial-budget", "demo", "guided", "fake", "fake-model", {},
        budget_policy={"max_total_tokens": 1_500_000},
    )

    assert get_run_record("run-initial-budget")["budget"]["effective_policy"] == {"max_total_tokens": 1_500_000}


def test_event_in_trace_scope_is_automatically_correlated(tmp_path, monkeypatch):
    from app.observability.context import TraceContext, trace_scope

    _use_database(tmp_path, monkeypatch)
    create_run_record("run-events", "demo", "guided", "fake", "fake-model", {})
    trace = TraceContext(trace_id="run-events", run_id="run-events", span_id="node-span", parent_span_id="command-span", stage="generation")

    with trace_scope(trace):
        append_event("run-events", "node.started", "generation", "开始")

    with db.database() as connection:
        event = connection.execute("SELECT trace_id, span_id, parent_span_id FROM run_events WHERE event_type = 'node.started'").fetchone()
    assert tuple(event) == ("run-events", "node-span", "command-span")


def test_budget_threshold_emits_observation_without_changing_run_status(tmp_path, monkeypatch):
    from app.observability.budget import record_model_usage
    from app.observability.contracts import InvocationMetrics
    from app.observability.tracing import start_span
    from app.workflow.repository import get_run_record, update_budget_policy

    _use_database(tmp_path, monkeypatch)
    create_run_record("run-budget", "demo", "guided", "fake", "fake-model", {})
    update_budget_policy("run-budget", {"max_total_tokens": 10}, reason="课程预算")
    model_span = start_span("run-budget", kind="model", name="测试模型调用")

    record_model_usage("run-budget", model_span["id"], InvocationMetrics(provider="fake", model="fake-model", input_tokens=4, output_tokens=8, total_tokens=12))

    run = get_run_record("run-budget")
    assert run["status"] == "QUEUED"
    assert run["budget"]["status"] == "EXCEEDED"
    assert run["budget"]["usage_totals"]["total_tokens"] == 12
    assert [event["event_type"] for event in run["events"]].count("budget.threshold_exceeded") == 1


def test_budget_and_trace_routes_return_safe_read_models(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.run_routes import build_router

    _use_database(tmp_path, monkeypatch)
    create_run_record("run-routes", "demo", "guided", "fake", "fake-model", {})
    app = FastAPI()
    app.include_router(build_router())
    client = TestClient(app)

    assert client.put("/api/runs/run-routes/budget", json={"max_total_tokens": 99}).status_code == 405
    assert client.get("/api/runs/run-routes/budget").json()["effective_policy"] == {}
    assert client.get("/api/runs/run-routes/trace").json()["spans"][0]["kind"] == "run"
