"""The commands of a run, seen from the side the browser looks at them.

`app/worker/commands.py` (P6.1) owns the queue side of the `commands`
table: enqueuing a command, leasing it to a worker and taking it back when
the worker died.  This module owns the read side: whether a run still has
a command that is going to do something.

A command is **active** when it is not in a terminal state.  The terminal
states are the ones the contract freezes: `SUCCEEDED` / `FAILED` /
`CANCELLED` / `WAITING_APPROVAL` / `RETRYABLE`.  The lower case spelling of
the worker queue (`done`) is read as the same thing as `SUCCEEDED`, so the
answer does not change when the worker lands.
"""

from __future__ import annotations

from typing import Any

from app.db import database, row_to_dict

TERMINAL_COMMAND_STATUSES = frozenset(
    {"succeeded", "failed", "cancelled", "waiting_approval", "retryable", "done"}
)


def get_active_command(run_id: str) -> dict[str, Any] | None:
    """Read the command a run is still waiting on.

    Args:
        run_id: The run whose command is wanted, for example "run-1".

    Returns:
        The newest command of the run that is not in a terminal state, or
        None when the run has no command left to do.  Only the fields the
        browser needs are given back: the payload of a command stays in the
        database, because it is the machine's own instruction.
    """
    placeholders = ", ".join("?" for _ in TERMINAL_COMMAND_STATUSES)
    query = f"""
        SELECT id, kind, status, attempt_count, created_at, updated_at
        FROM commands
        WHERE run_id = ? AND LOWER(status) NOT IN ({placeholders})
        ORDER BY created_at DESC, rowid DESC LIMIT 1
    """
    with database() as connection:
        row = connection.execute(
            query, (run_id, *sorted(TERMINAL_COMMAND_STATUSES))
        ).fetchone()
    return row_to_dict(row)
