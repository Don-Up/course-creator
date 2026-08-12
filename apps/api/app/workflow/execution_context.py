"""Per-command context propagated into LangGraph's synchronous node thread."""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionContext:
    command_id: str
    worker_id: str
    lease_seconds: int
    node_execution_id: str | None = None


current_execution: ContextVar[ExecutionContext | None] = ContextVar("current_execution", default=None)
