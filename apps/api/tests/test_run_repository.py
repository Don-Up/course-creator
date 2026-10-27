"""Behaviour tests for the run ledger.

``app/workflow/repository.py`` is the only place that writes the run tables.
The tests therefore look at the rows themselves: a new run has to leave a
row in ``runs`` and a first event, a finished stage has to leave an event, a
failure has to leave an error message, and the read model has to tell the
seven stages apart by their state.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.workflow.definitions import WORKFLOW_STEPS
from app.workflow.repository import (
    append_event,
    create_run_record,
    get_run_record,
    list_run_artifacts,
    list_run_records,
    record_run_artifact,
    update_run,
)

RUN_ID = "run-1"


def start_run(**overrides: Any) -> dict[str, Any]:
    """Create a run in the throwaway database and return its row.

    Args:
        overrides: The fields to replace, for example ``{"run_id": "run-2"}``.

    Returns:
        The new row of ``runs``, decoded into a dictionary.
    """
    arguments: dict[str, Any] = {
        "run_id": RUN_ID,
        "course_slug": "python-101",
        "mode": "guided",
        "provider": "codex_gateway",
        "model": "llm-gateway--kimi-k3",
        "request": {"title": "Python 入门"},
    }
    arguments.update(overrides)
    return create_run_record(**arguments)


def test_a_new_run_leaves_a_row_and_a_first_event(use_temp_database: Path) -> None:
    """Starting a run writes one row into ``runs`` and one event into ``run_events``.

    Args:
        use_temp_database: The throwaway database this test writes into.

    Returns:
        Nothing. The test fails when the row or the first event is missing.
    """
    run = start_run()

    assert run["id"] == RUN_ID
    assert run["status"] == "QUEUED"
    assert run["current_step"] == "intake"
    assert run["course_slug"] == "python-101"
    assert run["request"] == {"title": "Python 入门"}

    record = get_run_record(RUN_ID)
    assert record is not None
    assert len(record["events"]) == 1
    assert record["events"][0]["event_type"] == "run.created"
    assert record["events"][0]["step"] == "intake"


def test_the_run_carries_its_own_trace_id(use_temp_database: Path) -> None:
    """The run id and the trace id are the same string.

    Args:
        use_temp_database: The throwaway database this test writes into.

    Returns:
        Nothing. The test fails when the two ids differ.
    """
    run = start_run()

    assert run["trace_id"] == run["id"] == RUN_ID


def test_every_stage_leaves_an_artifact_with_a_full_presentation(
    use_temp_database: Path,
) -> None:
    """One artifact per stage, and the presentation comes back whole.

    Args:
        use_temp_database: The throwaway database this test writes into.

    Returns:
        Nothing. The test fails when an artifact is missing or a field of
        the presentation was dropped on the way in.
    """
    start_run()

    for step in ("intake", "mission", "blueprint"):
        record_run_artifact(
            RUN_ID,
            step,
            f"{step}.node",
            f"{step} 产物",
            {
                "headline": f"{step} 好了",
                "highlights": ["要点一", "要点二"],
                "issues": [],
            },
            {"raw": step},
        )

    artifacts = list_run_artifacts(RUN_ID)
    assert [item["step"] for item in artifacts] == ["intake", "mission", "blueprint"]
    assert artifacts[0]["title"] == "intake 产物"
    assert artifacts[0]["source"] == "model"
    assert artifacts[0]["presentation"]["headline"] == "intake 好了"
    assert artifacts[0]["presentation"]["highlights"] == ["要点一", "要点二"]
    assert artifacts[0]["raw_output"] == {"raw": "intake"}


def test_a_finished_stage_leaves_an_event(use_temp_database: Path) -> None:
    """Finishing a stage appends one event and moves the run on.

    Args:
        use_temp_database: The throwaway database this test writes into.

    Returns:
        Nothing. The test fails when the event was not appended.
    """
    start_run()
    update_run(RUN_ID, status="RUNNING", step="mission")

    append_event(RUN_ID, "stage.completed", "mission", "任务定义完成")

    record = get_run_record(RUN_ID)
    assert record is not None
    assert [event["event_type"] for event in record["events"]] == [
        "run.created",
        "stage.completed",
    ]
    assert record["events"][-1]["message"] == "任务定义完成"


def test_a_failed_run_leaves_an_event_and_an_error_message(
    use_temp_database: Path,
) -> None:
    """A failure is written down in the events and on the run itself.

    Args:
        use_temp_database: The throwaway database this test writes into.

    Returns:
        Nothing. The test fails when the error message or the event is missing.
    """
    start_run()
    update_run(RUN_ID, status="RUNNING", step="generation")
    append_event(RUN_ID, "run.failed", "generation", "这一批生成失败了")
    update_run(RUN_ID, status="FAILED", error_message="这一批生成失败了")

    record = get_run_record(RUN_ID)
    assert record is not None
    assert record["run"]["status"] == "FAILED"
    assert record["run"]["error_message"] == "这一批生成失败了"
    assert record["events"][-1]["event_type"] == "run.failed"


def test_an_interrupt_and_an_error_can_be_taken_away(use_temp_database: Path) -> None:
    """A waiting run that starts over has no interrupt and no error left.

    Args:
        use_temp_database: The throwaway database this test writes into.

    Returns:
        Nothing. The test fails when one of the two was left behind.
    """
    start_run()
    update_run(
        RUN_ID,
        status="WAITING_APPROVAL",
        interrupt_type="MISSION_APPROVAL",
        interrupt_payload={"type": "MISSION_APPROVAL", "step": "mission"},
        error_message="上一次失败了",
    )

    cleared = update_run(RUN_ID, status="RUNNING", clear_interrupt=True, clear_error=True)

    assert cleared["interrupt_type"] is None
    assert cleared["interrupt_payload"] is None
    assert cleared["error_message"] is None


def test_the_read_model_marks_every_stage(use_temp_database: Path) -> None:
    """The seven stages are told apart by their state.

    Args:
        use_temp_database: The throwaway database this test writes into.

    Returns:
        Nothing. The test fails when a stage carries the wrong state.
    """
    start_run()
    update_run(RUN_ID, status="RUNNING", step="mission")

    record = get_run_record(RUN_ID)
    assert record is not None
    steps = record["workflow_steps"]
    assert [step["id"] for step in steps] == [step["id"] for step in WORKFLOW_STEPS]
    assert [step["status"] for step in steps] == [
        "completed",
        "active",
        "pending",
        "pending",
        "pending",
        "pending",
        "pending",
    ]
    assert steps[1]["title"] == WORKFLOW_STEPS[1]["title"]


def test_a_finished_run_has_no_active_stage_left(use_temp_database: Path) -> None:
    """A completed run marks every stage as done.

    Args:
        use_temp_database: The throwaway database this test writes into.

    Returns:
        Nothing. The test fails when a stage is still active.
    """
    start_run()
    update_run(RUN_ID, status="COMPLETED", step="release")

    record = get_run_record(RUN_ID)
    assert record is not None
    assert [step["status"] for step in record["workflow_steps"]] == ["completed"] * 7


def test_an_unknown_stage_is_treated_as_the_first_one(use_temp_database: Path) -> None:
    """A stage nobody knows does not break the read model.

    Args:
        use_temp_database: The throwaway database this test writes into.

    Returns:
        Nothing. The test fails when the read model raised instead.
    """
    start_run()
    update_run(RUN_ID, status="RUNNING", step="not-a-stage")

    record = get_run_record(RUN_ID)
    assert record is not None
    assert record["workflow_steps"][0]["status"] == "active"


def test_an_unknown_run_has_no_record(use_temp_database: Path) -> None:
    """Asking for a run that was never started gives nothing back.

    Args:
        use_temp_database: The throwaway database this test reads from.

    Returns:
        Nothing. The test fails when a record was invented.
    """
    assert get_run_record("run-does-not-exist") is None


def test_updating_a_run_that_does_not_exist_is_refused(
    use_temp_database: Path,
) -> None:
    """A typo in the run id must not pass silently.

    Args:
        use_temp_database: The throwaway database this test writes into.

    Returns:
        Nothing. The test fails when the update was accepted.
    """
    with pytest.raises(ValueError):
        update_run("run-does-not-exist", status="RUNNING")


def test_an_event_can_carry_a_trace_context(use_temp_database: Path) -> None:
    """An event written inside a trace keeps the ids of that trace.

    Args:
        use_temp_database: The throwaway database this test writes into.

    Returns:
        Nothing. The test fails when the trace ids were dropped.
    """
    start_run()

    append_event(
        RUN_ID,
        "stage.started",
        "mission",
        "任务定义开始",
        payload={"attempt": 1},
        trace={"trace_id": "trace-1", "span_id": "span-1"},
    )

    record = get_run_record(RUN_ID)
    assert record is not None
    event = record["events"][-1]
    assert event["trace_id"] == "trace-1"
    assert event["span_id"] == "span-1"
    assert event["parent_span_id"] is None
    assert event["payload"] == {"attempt": 1}


def test_an_event_without_a_trace_falls_back_to_the_run(use_temp_database: Path) -> None:
    """Before a trace context exists, the run id is the trace id.

    Args:
        use_temp_database: The throwaway database this test writes into.

    Returns:
        Nothing. The test fails when the event lost its trace id.
    """
    start_run()

    record = get_run_record(RUN_ID)
    assert record is not None
    assert record["events"][0]["trace_id"] == RUN_ID


def test_listing_the_runs_of_a_course(use_temp_database: Path) -> None:
    """The runs of one course can be listed, and the other courses stay out.

    Args:
        use_temp_database: The throwaway database this test reads from.

    Returns:
        Nothing. The test fails when a run of another course shows up.
    """
    start_run()
    start_run(run_id="run-2")
    start_run(run_id="run-3", course_slug="other-course")

    runs = list_run_records("python-101")

    assert {run["id"] for run in runs} == {RUN_ID, "run-2"}
    assert len(list_run_records()) == 3
