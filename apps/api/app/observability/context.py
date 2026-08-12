from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator

from app.observability.contracts import InvocationMetrics


@dataclass(frozen=True)
class TraceContext:
    trace_id: str
    run_id: str
    span_id: str | None = None
    parent_span_id: str | None = None
    command_id: str | None = None
    node_execution_id: str | None = None
    stage: str | None = None


_trace: ContextVar[TraceContext | None] = ContextVar("course_agent_trace", default=None)
_invocation_metrics: ContextVar[InvocationMetrics | None] = ContextVar("course_agent_invocation_metrics", default=None)


def current_trace() -> TraceContext | None:
    return _trace.get()


def set_invocation_metrics(metrics: InvocationMetrics | None) -> None:
    _invocation_metrics.set(metrics)


def current_invocation_metrics() -> InvocationMetrics | None:
    return _invocation_metrics.get()


@contextmanager
def trace_scope(trace: TraceContext) -> Iterator[TraceContext]:
    token = _trace.set(trace)
    try:
        yield trace
    finally:
        _trace.reset(token)
