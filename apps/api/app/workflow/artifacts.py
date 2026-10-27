"""What a run produced: the artifact, its content record and where it came from.

`app/workflow/artifacts.py` owns the three tables that hold the output of a
stage.  `run_artifacts` is the run scoped view a person reads: the title, the
presentation and the untouched model output.  `artifacts` is the content
record: what the artifact is, how sensitive it is and which version of the
schema it follows.  `artifact_edges` is the lineage: which earlier artifact
this one was built on.

The three are written in one transaction, so a stage that breaks half way
leaves nothing behind at all.  A run artifact is identified by its run, its
node and its source, so writing the same one twice changes nothing.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from app.courses.common import content_hash
from app.db import database, row_to_dict, utcnow


def content_digest(presentation: dict[str, Any], raw_output: dict[str, Any]) -> str:
    """Fingerprint the content of one artifact.

    Args:
        presentation: The artifact as it is shown to a person, for example
            {"headline": "任务定义完成"}.
        raw_output: The untouched model output behind it, for example
            {"markdown": "..."}.

    Returns:
        The sha256 digest of the two, as 64 lower case hex characters.  The
        same content always gives the same fingerprint.
    """
    payload = {"presentation": presentation, "raw_output": raw_output}
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return content_hash(text)


def write_artifact_rows(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    artifact_id: str,
    step: str,
    node: str,
    digest: str,
    now: str,
) -> None:
    """Write the content record of one artifact and where it comes from.

    The content record (`artifacts`) says what the artifact is, and the
    lineage (`artifact_edges`) says which earlier artifact it was built on.
    The parent is the artifact that was written last in this run, so the
    artifacts of a run form one chain in the order they were produced.

    Args:
        connection: The open connection, inside the caller's transaction.
        run_id: The run the artifact belongs to, for example "run-1".
        artifact_id: The id of the artifact, the same one `run_artifacts`
            uses.
        step: The stage the artifact came from, for example "mission".
        node: The node that produced it, for example "mission.agent".
        digest: The fingerprint of the content, for example a sha256 digest.
        now: The moment to write into `created_at` and `updated_at`.

    Returns:
        Nothing. The rows are written inside the caller's transaction, so a
        failure here takes the whole stage down with it.
    """
    parent = connection.execute(
        "SELECT id FROM artifacts WHERE run_id = ? ORDER BY rowid DESC LIMIT 1",
        (run_id,),
    ).fetchone()
    scope = json.dumps(
        {"node": node, "run_id": run_id, "step": step},
        ensure_ascii=False,
        sort_keys=True,
    )
    connection.execute(
        """
        INSERT INTO artifacts (
            id, run_id, artifact_type, schema_version, content_hash, storage_uri,
            producer_execution_id, scope_json, sensitivity, base_content_hash,
            status, is_current, verification_json, created_at, updated_at
        ) VALUES (
            ?, ?, ?, '1.0', ?, ?, NULL, ?, 'internal', NULL, 'RECORDED', 1, NULL, ?, ?
        )
        """,
        (
            artifact_id,
            run_id,
            step,
            digest,
            f"run://{run_id}/artifacts/{artifact_id}",
            scope,
            now,
            now,
        ),
    )
    if parent is not None:
        connection.execute(
            """
            INSERT OR IGNORE INTO artifact_edges (
                parent_artifact_id, child_artifact_id, relation, created_at
            ) VALUES (?, ?, 'derives_from', ?)
            """,
            (parent["id"], artifact_id, now),
        )


def insert_run_artifact(
    connection: sqlite3.Connection,
    run_id: str,
    step: str,
    node: str,
    title: str,
    presentation: dict[str, Any],
    raw_output: dict[str, Any],
    source: str,
) -> dict[str, Any]:
    """Write one artifact of a run into the ledger, inside a given transaction.

    Args:
        connection: The open connection, inside the caller's transaction.
        run_id: The run this artifact belongs to, for example "run-1".
        step: The stage the artifact came from, for example "mission".
        node: The node that produced it, for example "mission.agent".
        title: A short title a human can read, for example "任务定义".
        presentation: The artifact as it is shown to a person, for example
            {"headline": "任务定义完成"}.
        raw_output: The untouched model output behind it, for example
            {"markdown": "..."}.
        source: Where the artifact came from, for example "model".

    Returns:
        The new row of `run_artifacts`, decoded into a dictionary.  When the
        same artifact was already written, the row that was there before.
    """
    existing = connection.execute(
        "SELECT * FROM run_artifacts WHERE run_id = ? AND node = ? AND source = ?",
        (run_id, node, source),
    ).fetchone()
    if existing is not None:
        return row_to_dict(existing) or {}

    artifact_id = str(uuid.uuid4())
    now = utcnow()
    connection.execute(
        """
        INSERT INTO run_artifacts (
            id, run_id, step, node, title, source,
            presentation_json, raw_output_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            artifact_id,
            run_id,
            step,
            node,
            title,
            source,
            json.dumps(presentation, ensure_ascii=False, default=str),
            json.dumps(raw_output, ensure_ascii=False, default=str),
            now,
        ),
    )
    write_artifact_rows(
        connection,
        run_id=run_id,
        artifact_id=artifact_id,
        step=step,
        node=node,
        digest=content_digest(presentation, raw_output),
        now=now,
    )
    row = connection.execute(
        "SELECT * FROM run_artifacts WHERE id = ?", (artifact_id,)
    ).fetchone()
    return row_to_dict(row) or {}


def record_run_artifact(
    run_id: str,
    step: str,
    node: str,
    title: str,
    presentation: dict[str, Any],
    raw_output: dict[str, Any],
    source: str = "model",
) -> dict[str, Any]:
    """Write one artifact of a run into the ledger.

    Three tables are written in one transaction: the run scoped view
    (`run_artifacts`), the content record (`artifacts`) and the lineage
    (`artifact_edges`).  When one of them fails, none of them is kept.

    A run artifact is identified by its run, its node and its source.  Writing
    the same one twice changes nothing: the row that is already there is
    handed back instead of a second one being added.

    Args:
        run_id: The run this artifact belongs to, for example "run-1".
        step: The stage the artifact came from, for example "mission".
        node: The node that produced it, for example "mission.agent".
        title: A short title a human can read, for example "任务定义".
        presentation: The artifact as it is shown to a person, for example
            {"headline": "任务定义完成"}.
        raw_output: The untouched model output behind it, for example
            {"markdown": "..."}.
        source: Where the artifact came from, for example "model" or
            "system".

    Returns:
        The new row of `run_artifacts`, decoded into a dictionary.  When the
        same artifact was already written, the row that was there before.
    """
    with database() as connection:
        return insert_run_artifact(
            connection, run_id, step, node, title, presentation, raw_output, source
        )


def list_run_artifacts(run_id: str) -> list[dict[str, Any]]:
    """List the artifacts of a run, oldest first.

    Args:
        run_id: The run whose artifacts are wanted, for example "run-1".

    Returns:
        One dictionary per artifact, in the order they were written.
    """
    with database() as connection:
        rows = connection.execute(
            "SELECT * FROM run_artifacts WHERE run_id = ? ORDER BY created_at, rowid",
            (run_id,),
        ).fetchall()
    return [row_to_dict(row) or {} for row in rows]
