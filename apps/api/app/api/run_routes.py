"""The HTTP routes that expose the runs and their read model.

The read model of a run is what the browser polls while the agent works:
where the run stands, what it has done and what it produced.  It is built
from the four parts `app.workflow.repository.get_run_record()` returns, and
it is **projected** before it leaves this module: only the fields on the
whitelist are copied, the keys that carry internal material are dropped,
and the paths of this machine are replaced by a placeholder.

Two rules turn that projection into a contract rather than a habit:

* **Whitelist.** A field that is not named here is not in the answer.  The
  request that started the run, the payload of an approval and the budget
  policy stay in the database: they are the machine's own notes, and the
  later phases grow them into the assembled prompt.
* **No internal material.** A key such as ``prompt`` or ``api_key`` is
  dropped wherever it shows up, and a path that points into this computer
  is replaced by ``<path>``.  The reference implementation hands out the
  untouched model output of every artifact; this one does not.

The projection is deliberately kept in this module and not in the
repository: the repository owns what a run *is*, this module owns what a
run *looks like from the outside*.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, HTTPException

from app.schemas import (
    RunArtifactRead,
    RunDetail,
    RunEventRead,
    RunList,
    RunRead,
    WorkflowStepRead,
)
from app.workflow.commands import get_active_command
from app.workflow.repository import get_run_record, list_run_records

router = APIRouter(prefix="/api/runs", tags=["runs"])

RUN_FIELDS = (
    "id",
    "course_slug",
    "mode",
    "status",
    "current_step",
    "provider",
    "model",
    "interrupt_type",
    "error_message",
    "trace_id",
    "created_at",
    "updated_at",
)
EVENT_FIELDS = ("seq", "id", "event_type", "step", "message", "created_at")
ARTIFACT_FIELDS = (
    "id",
    "step",
    "node",
    "title",
    "source",
    "presentation",
    "created_at",
)
COMMAND_FIELDS = ("id", "kind", "status", "attempt_count", "created_at", "updated_at")
SUMMARY_FIELDS = (
    "id",
    "course_slug",
    "mode",
    "status",
    "current_step",
    "created_at",
    "updated_at",
)

# Keys that never reach the browser, wherever they show up: credentials, the
# prompt of the model and the untouched answer of the model.
HIDDEN_KEYS = frozenset(
    {
        "access_token",
        "api_key",
        "authorization",
        "cookie",
        "messages",
        "password",
        "prompt",
        "raw_output",
        "raw_response",
        "refresh_token",
        "secret",
        "system_prompt",
        "token",
        "user_prompt",
    }
)

# What a path of this machine is replaced by.
PATH_PLACEHOLDER = "<path>"

# The characters that end a path.  A Chinese full stop ends it too, so a
# path at the end of a sentence does not swallow the sentence.
_PATH_END = r"\s\"'<>|,;)\]}:：，。、；？！）【】《》「」"
WINDOWS_PATH_RE = re.compile(rf"[A-Za-z]:[\\/](?![\\/])[^{_PATH_END}]*")
UNC_PATH_RE = re.compile(rf"\\\\[^{_PATH_END}]*")
HOME_PATH_RE = re.compile(rf"/(?:Users|home)/[A-Za-z0-9._-]+[^{_PATH_END}]*")


def _scrub_text(text: str) -> str:
    """Replace the paths of this machine by a placeholder.

    Args:
        text: The text to clean, for example an error message.

    Returns:
        The text with every absolute path of this computer replaced by
        "<path>".  A relative path such as "lessons/01.md" is left alone:
        it says nothing about the machine it was written on.
    """
    cleaned = WINDOWS_PATH_RE.sub(PATH_PLACEHOLDER, text)
    cleaned = UNC_PATH_RE.sub(PATH_PLACEHOLDER, cleaned)
    return HOME_PATH_RE.sub(PATH_PLACEHOLDER, cleaned)


def _scrub(value: Any) -> Any:
    """Drop the internal material out of a value of any shape.

    Args:
        value: The value to clean, for example the presentation of an
            artifact.

    Returns:
        The value without the hidden keys and without the paths of this
        machine.  A list keeps its order, a dictionary keeps the keys that
        are not hidden, and everything else is returned as it is.
    """
    if isinstance(value, dict):
        return {
            key: _scrub(item)
            for key, item in value.items()
            if key.lower() not in HIDDEN_KEYS
        }
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    if isinstance(value, str):
        return _scrub_text(value)
    return value


def _pick(row: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    """Copy the named fields out of a row and clean them.

    Args:
        row: The row to read, for example the row of `runs`.
        fields: The names of the fields that are allowed out.

    Returns:
        A dictionary with the fields that the row has, cleaned.
    """
    return _scrub({field: row[field] for field in fields if field in row})


def _run_read(row: dict[str, Any], active_command: dict[str, Any] | None) -> RunRead:
    """Build the run of the answer out of its row.

    Args:
        row: The row of `runs`, decoded.
        active_command: The command the run is still waiting on, or None.

    Returns:
        The run as the browser sees it.
    """
    read = _pick(row, RUN_FIELDS)
    if active_command is not None:
        read["active_command"] = _pick(active_command, COMMAND_FIELDS)
    return RunRead(**read)


def _workflow_step_read(step: dict[str, Any]) -> WorkflowStepRead:
    """Build one stage of the workflow out of its definition.

    Args:
        step: The definition of the stage, for example the one of
            "intake", with the status of that stage added to it.

    Returns:
        The stage as the browser sees it.
    """
    return WorkflowStepRead(
        id=step["id"],
        title=step["title"],
        description=step["description"],
        user_input=step["user_input"],
        model_output=step["model_output"],
        status=step["status"],
    )


@router.get("", response_model=RunList)
def read_runs(course_slug: str | None = None) -> RunList:
    """Answer with the runs of the system.

    Args:
        course_slug: The course whose runs are wanted, for example
            "python-101".  Every run when it is not given.

    Returns:
        The runs, newest first.  Every item says which run this is, which
        course it belongs to and where it stands.
    """
    return RunList(
        items=[
            _scrub(_pick(row, SUMMARY_FIELDS))
            for row in list_run_records(course_slug)
        ]
    )


@router.get("/{run_id}", response_model=RunDetail)
def read_run(run_id: str) -> RunDetail:
    """Answer with one run and everything that belongs to it.

    Args:
        run_id: The run to read, for example "run-1".

    Returns:
        The run, its events, its artifacts and the seven stages of the
        workflow with the state each one is in.
        Raises HTTPException(404) when there is no such run.
    """
    record = get_run_record(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Run 不存在")
    return RunDetail(
        run=_run_read(record["run"], get_active_command(run_id)),
        events=[
            RunEventRead(**_pick(event, EVENT_FIELDS))
            for event in record["events"]
        ],
        artifacts=[
            RunArtifactRead(**_pick(artifact, ARTIFACT_FIELDS))
            for artifact in record["artifacts"]
        ],
        workflow_steps=[
            _workflow_step_read(step) for step in record["workflow_steps"]
        ],
    )
