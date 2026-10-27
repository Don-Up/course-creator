"""Behaviour tests of the run query API.

The browser polls a run while the agent works, so the answer of
`GET /api/runs/{id}` has to be three things at once: complete enough to
draw the timeline, the same every time it is asked, and free of the
machine's own material -- no path of this computer and no prompt of the
model.

The tests therefore write a run with all four parts, read it back through
the API, and watch the answer: the four named parts are there, the internal
material is not, an unknown run is a 404, and the answer does not change
when the database is opened again.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.db import database, initialize_database
from app.main import app
from app.workflow.repository import (
    append_event,
    create_run_record,
    record_run_artifact,
)

RUN_ID = "run-1"
OTHER_RUN_ID = "run-2"
COURSE_SLUG = "python-101"

# The two things the answer must never carry: a path of this machine and
# the prompt of the model.
INTERNAL_PATH = "C:\\Users\\10691\\Documents\\course\\lessons\\01.md"
MODEL_PROMPT = "你是一位资深课程架构师，请严格输出 JSON。"


def make_run() -> None:
    """Write a run with an event and an artifact into the throwaway database.

    The material of the machine is put into the run on purpose: the request
    that started it carries a path, and the artifact carries both a path
    and a prompt.

    Returns:
        Nothing. The rows are left in the database of the test.
    """
    create_run_record(
        run_id=RUN_ID,
        course_slug=COURSE_SLUG,
        mode="guided",
        provider="codex_gateway",
        model="llm-gateway--kimi-k3",
        request={"title": "Python 入门", "materials": [INTERNAL_PATH]},
    )
    append_event(RUN_ID, "stage.completed", "intake", "任务定义完成", {"attempt": 1})
    record_run_artifact(
        RUN_ID,
        "intake",
        "intake.agent",
        "任务定义",
        {
            "headline": "任务定义完成",
            "file": INTERNAL_PATH,
            "system_prompt": MODEL_PROMPT,
        },
        {"markdown": "# 任务", "system_prompt": MODEL_PROMPT},
        source="model",
    )


def test_reading_a_run_gives_the_four_named_parts(use_temp_database: Path) -> None:
    """The answer of a run has the run, its events, its artifacts and its steps.

    Args:
        use_temp_database: The throwaway database this test writes into.

    Returns:
        Nothing. The test fails when one of the four parts is missing or
        when the run itself is not the one that was written.
    """
    make_run()

    with TestClient(app) as client:
        response = client.get(f"/api/runs/{RUN_ID}")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"run", "events", "artifacts", "workflow_steps"}
    assert body["run"]["id"] == RUN_ID
    assert body["run"]["course_slug"] == COURSE_SLUG
    assert body["run"]["status"] == "QUEUED"
    assert body["run"]["current_step"] == "intake"
    assert body["run"]["active_command"] is None
    assert [event["event_type"] for event in body["events"]] == [
        "run.created",
        "stage.completed",
    ]
    assert body["artifacts"][0]["title"] == "任务定义"
    assert len(body["workflow_steps"]) == 7
    assert body["workflow_steps"][0]["id"] == "intake"
    assert body["workflow_steps"][0]["status"] == "active"
    assert body["workflow_steps"][1]["status"] == "pending"


def test_the_answer_holds_no_path_of_this_machine_and_no_prompt(
    use_temp_database: Path,
) -> None:
    """Nothing of the machine's own material reaches the browser.

    The path of this computer is replaced by a placeholder, the prompt of
    the model is dropped, and the request that started the run stays in the
    database.  What is meant to be read is still there.

    Args:
        use_temp_database: The throwaway database this test writes into.

    Returns:
        Nothing. The test fails when the path or the prompt shows up in the
        answer, or when the presentation lost the part meant for a person.
    """
    make_run()

    with TestClient(app) as client:
        response = client.get(f"/api/runs/{RUN_ID}")

    text = response.text
    assert INTERNAL_PATH not in text
    assert "10691" not in text
    assert MODEL_PROMPT not in text
    assert "system_prompt" not in text
    assert "materials" not in text
    assert "request" not in response.json()["run"]

    presentation = response.json()["artifacts"][0]["presentation"]
    assert presentation["headline"] == "任务定义完成"
    assert presentation["file"] == "<path>"
    assert "system_prompt" not in presentation


def test_an_unknown_run_is_a_404(use_temp_database: Path) -> None:
    """A run that is not there is a 404, not an empty answer.

    Args:
        use_temp_database: The throwaway database this test writes into.

    Returns:
        Nothing. The test fails when the answer is not a 404.
    """
    with TestClient(app) as client:
        response = client.get("/api/runs/does-not-exist")

    assert response.status_code == 404


def test_a_url_and_a_relative_path_survive_the_cleaning(use_temp_database: Path) -> None:
    """Only the paths of this machine are cleaned away.

    The research agent collects urls, and the artifacts point at the files
    of the course by a path that is relative to the course.  Both say
    nothing about the machine they were written on, so both have to survive.

    Args:
        use_temp_database: The throwaway database this test writes into.

    Returns:
        Nothing. The test fails when a url or a relative path is replaced.
    """
    make_run()
    with database() as connection:
        connection.execute(
            """
            INSERT INTO run_artifacts (
                id, run_id, step, node, title, source,
                presentation_json, raw_output_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "artifact-2",
                RUN_ID,
                "research",
                "research.agent",
                "资料检索",
                "model",
                '{"url": "https://example.com/docs/a.html", "file": "lessons/01.md"}',
                "{}",
                "2026-10-27T08:00:00+00:00",
            ),
        )

    with TestClient(app) as client:
        response = client.get(f"/api/runs/{RUN_ID}")

    presentation = response.json()["artifacts"][1]["presentation"]
    assert presentation["url"] == "https://example.com/docs/a.html"
    assert presentation["file"] == "lessons/01.md"


def test_reading_a_run_again_after_the_database_is_opened_again_gives_the_same_answer(
    use_temp_database: Path,
) -> None:
    """The answer of a run does not change when the database is opened again.

    This is the restart of the API: the file is opened once more and the
    schema is checked, and the answer has to be the very same one.  The
    rows are looked at in the file itself, so the answer cannot come out
    of a memory that survived the restart.

    Args:
        use_temp_database: The throwaway database this test writes into.

    Returns:
        Nothing. The test fails when the two answers differ or when the run
        is not really in the file.
    """
    make_run()

    with TestClient(app) as client:
        first = client.get(f"/api/runs/{RUN_ID}")

    initialize_database(use_temp_database)

    with TestClient(app) as client:
        second = client.get(f"/api/runs/{RUN_ID}")

    assert first.status_code == 200
    assert first.json() == second.json()

    connection = sqlite3.connect(use_temp_database)
    try:
        stored = connection.execute("SELECT COUNT(*) FROM runs").fetchone()
    finally:
        connection.close()
    assert stored[0] == 1


def test_the_run_list_shows_the_newest_run_first(use_temp_database: Path) -> None:
    """The list of the runs is ordered, and it can be narrowed to one course.

    Args:
        use_temp_database: The throwaway database this test writes into.

    Returns:
        Nothing. The test fails when the order is wrong or when the filter
        lets a run of another course through.
    """
    make_run()
    create_run_record(
        run_id=OTHER_RUN_ID,
        course_slug="another-course",
        mode="guided",
        provider="codex_gateway",
        model="llm-gateway--kimi-k3",
        request={"title": "另一门课"},
    )

    with TestClient(app) as client:
        response = client.get("/api/runs")
        filtered = client.get("/api/runs", params={"course_slug": COURSE_SLUG})

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [
        OTHER_RUN_ID,
        RUN_ID,
    ]
    assert response.json()["items"][0]["status"] == "QUEUED"
    assert [item["id"] for item in filtered.json()["items"]] == [RUN_ID]


def test_a_run_with_an_open_command_shows_that_command(use_temp_database: Path) -> None:
    """A run that waits for a command says so.

    This is what tells the frontend that a run which already failed may
    still get going again: the command is the way back.

    Args:
        use_temp_database: The throwaway database this test writes into.

    Returns:
        Nothing. The test fails when the open command is not in the answer.
    """
    make_run()
    with database() as connection:
        connection.execute(
            """
            INSERT INTO commands (id, run_id, kind, payload_json, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("command-1", RUN_ID, "RESUME", "{}", "pending", "2026-10-27T08:00:00+00:00", "2026-10-27T08:00:00+00:00"),
        )

    with TestClient(app) as client:
        response = client.get(f"/api/runs/{RUN_ID}")

    active = response.json()["run"]["active_command"]
    assert active is not None
    assert active["id"] == "command-1"
    assert active["kind"] == "RESUME"
    assert active["status"] == "pending"
