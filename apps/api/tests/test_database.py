"""Behaviour tests for the SQLite schema and the connection helper.

``app/db.py`` owns the thirteen tables the later phases read from and the
``database()`` context manager that hands out a connection.  The tests
therefore look at a throwaway database file: the tables have to be there,
initialising twice has to be harmless, the JSON columns have to come back
as objects, and a failure inside the context manager has to leave no
trace behind.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

import pytest

from app.db import database, initialize_database, row_to_dict, utcnow

EXPECTED_TABLES = (
    "runs",
    "run_events",
    "run_artifacts",
    "artifacts",
    "artifact_edges",
    "chapter_versions",
    "repair_tasks",
    "repair_task_attempts",
    "commands",
    "node_executions",
    "trace_spans",
    "budget_ledger_entries",
    "budget_adjustments",
)


@pytest.fixture
def initialized_database(temp_database_path: Path) -> Path:
    """Create the schema in a throwaway database and hand back its path.

    Args:
        temp_database_path: The private database file of this test.

    Returns:
        The path of the database the schema was written to.
    """
    initialize_database(temp_database_path)
    return temp_database_path


def table_names(path: Path) -> set[str]:
    """Return the names of every table in the database at ``path``.

    Args:
        path: The database file to look into, for example
            ``tmp_path / "agent.db"``.

    Returns:
        The table names, without the bookkeeping table SQLite creates on
        its own for autoincrementing columns.
    """
    with closing(sqlite3.connect(path)) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    return {str(row[0]) for row in rows} - {"sqlite_sequence"}


def insert_run(connection: sqlite3.Connection, run_id: str = "run-1") -> None:
    """Write one row into ``runs`` so that events can hang off it.

    Args:
        connection: The open connection to write through.
        run_id: The identifier of the run, for example "run-1".

    Returns:
        Nothing. The row is committed when the surrounding context manager
        leaves its block.
    """
    now = utcnow()
    connection.execute(
        """
        INSERT INTO runs (
            id, course_slug, mode, status, current_step, provider, model,
            request_json, trace_id, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            "python-101",
            "full",
            "RUNNING",
            "intake",
            "codex_gateway",
            "llm-gateway--kimi-k3",
            json.dumps({"title": "Python 入门"}),
            run_id,
            now,
            now,
        ),
    )


@pytest.mark.parametrize("table", EXPECTED_TABLES)
def test_initialize_database_creates_every_table(
    initialized_database: Path,
    table: str,
) -> None:
    """Each of the thirteen tables has to exist after the first initialisation.

    Args:
        initialized_database: The throwaway database the schema was written to.
        table: The table that has to be there, for example "run_events".

    Returns:
        Nothing. The test fails when the table is missing.
    """
    with closing(sqlite3.connect(initialized_database)) as connection:
        found = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()

    assert found is not None, f"表 {table} 没有建出来"


def test_initialize_database_creates_exactly_the_thirteen_tables(
    initialized_database: Path,
) -> None:
    """No table may be missing and none may be added on the side.

    Args:
        initialized_database: The throwaway database the schema was written to.

    Returns:
        Nothing. The test fails when the table set differs from the agreement.
    """
    assert table_names(initialized_database) == set(EXPECTED_TABLES)


def test_initialize_database_twice_keeps_the_rows_already_written(
    temp_database_path: Path,
) -> None:
    """Initialising a second time is harmless and destroys nothing.

    Args:
        temp_database_path: The private database file of this test.

    Returns:
        Nothing. The test fails when the second initialisation raised or
        when the row written in between is gone.
    """
    initialize_database(temp_database_path)
    with closing(sqlite3.connect(temp_database_path)) as connection:
        connection.execute(
            """
            INSERT INTO chapter_versions (
                id, course_slug, chapter_key, source_path, content_hash,
                snapshot_path, reason, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "version-1",
                "python-101",
                "ch-01",
                "courses/python-101/lessons/01.md",
                "abc123",
                "courses/python-101/workspace/snapshots/01.md",
                "manual",
                utcnow(),
            ),
        )
        connection.commit()

    initialize_database(temp_database_path)

    with closing(sqlite3.connect(temp_database_path)) as connection:
        rows = connection.execute(
            "SELECT content_hash FROM chapter_versions WHERE id = ?",
            ("version-1",),
        ).fetchall()
    assert rows == [("abc123",)]


def test_row_to_dict_decodes_the_json_columns_and_drops_the_suffix(
    use_temp_database: Path,
) -> None:
    """A stored JSON document comes back as an object under a shorter name.

    Args:
        use_temp_database: The throwaway database this test writes into.

    Returns:
        Nothing. The test fails when the column keeps its suffix or stays
        a string.
    """
    with database() as connection:
        insert_run(connection)
        connection.execute(
            """
            INSERT INTO run_events (
                id, run_id, event_type, step, message, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "event-1",
                "run-1",
                "run.created",
                "intake",
                "Run 已创建",
                json.dumps({"answer": 42}, ensure_ascii=False),
                utcnow(),
            ),
        )
        row = connection.execute(
            "SELECT id, event_type, payload_json FROM run_events WHERE id = ?",
            ("event-1",),
        ).fetchone()

    result = row_to_dict(row)

    assert result is not None
    assert result["payload"] == {"answer": 42}
    assert "payload_json" not in result
    assert result["event_type"] == "run.created"


def test_row_to_dict_returns_none_when_there_is_no_row() -> None:
    """A missing row has to stay distinguishable from an empty one.

    Args:
        Nothing.

    Returns:
        Nothing. The test fails when the helper invents an empty result.
    """
    assert row_to_dict(None) is None


def test_database_rolls_the_transaction_back_when_the_body_raises(
    use_temp_database: Path,
) -> None:
    """A failure inside the block leaves no half written row behind.

    Args:
        use_temp_database: The throwaway database this test writes into.

    Returns:
        Nothing. The test fails when the row survived the rollback.
    """
    with pytest.raises(RuntimeError):
        with database() as connection:
            insert_run(connection)
            raise RuntimeError("这一步失败了")

    with database() as connection:
        stored = connection.execute("SELECT COUNT(*) FROM runs").fetchone()

    assert stored is not None
    assert stored[0] == 0


def test_database_keeps_the_row_when_the_body_succeeds(
    use_temp_database: Path,
) -> None:
    """A block that finishes normally commits what it wrote.

    Args:
        use_temp_database: The throwaway database this test writes into.

    Returns:
        Nothing. The test fails when the committed row is missing.
    """
    with database() as connection:
        insert_run(connection)

    with database() as connection:
        stored = connection.execute("SELECT COUNT(*) FROM runs").fetchone()

    assert stored is not None
    assert stored[0] == 1


def test_database_enforces_the_foreign_keys(
    use_temp_database: Path,
) -> None:
    """An event that points at no run has to be refused.

    Args:
        use_temp_database: The throwaway database this test writes into.

    Returns:
        Nothing. The test fails when the dangling event was accepted.
    """
    with pytest.raises(sqlite3.IntegrityError):
        with database() as connection:
            connection.execute(
                """
                INSERT INTO run_events (
                    id, run_id, event_type, step, message, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "event-orphan",
                    "run-does-not-exist",
                    "run.created",
                    "intake",
                    "没有主人的事件",
                    "{}",
                    utcnow(),
                ),
            )


def test_utcnow_is_a_timestamp_with_a_timezone() -> None:
    """Every stored timestamp has to say which timezone it is in.

    Args:
        Nothing.

    Returns:
        Nothing. The test fails when the stamp cannot be read back as a
        timezone aware moment.
    """
    stamp = utcnow()

    parsed = datetime.fromisoformat(stamp)
    assert parsed.tzinfo is not None
