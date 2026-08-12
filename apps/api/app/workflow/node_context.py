from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Callable

from app.config import Settings
from app.agents.protocols import CourseAgent
from app.agents.executor import TeachingAgentRuntime
from app.tools import ToolRuntime
from app.workflow.repository import append_event
from app.observability.tracing import span_scope, start_span


@dataclass(frozen=True)
class WorkflowContext:
    """Dependencies shared by node factories for one compiled workflow."""

    run_id: str
    provider: CourseAgent
    settings: Settings
    agents: TeachingAgentRuntime = field(init=False)
    tools: ToolRuntime = field(default_factory=ToolRuntime)

    def __post_init__(self) -> None:
        object.__setattr__(self, "agents", TeachingAgentRuntime(self.provider))

    def invoke_agent(self, agent_id: str, operation: str, *args: Any, **kwargs: Any) -> Any:
        definition = self.agents.definition(agent_id)
        span = start_span(self.run_id, kind="agent", name=operation, attributes={"agent_id": definition.id, "agent_version": definition.version, "operation": operation})
        with span_scope(span):
            append_event(self.run_id, "agent.invoked", "generation", f"{definition.id}@{definition.version} 执行 {operation}", {"agent_id": definition.id, "agent_version": definition.version, "operation": operation, "model_policy": definition.model_policy_ref})
            return self.agents.invoke(agent_id, operation, *args, **kwargs)

    def execute_tool(self, tool_id: str, *, caller: str, **arguments: Any) -> Any:
        span = start_span(self.run_id, kind="tool", name=tool_id, attributes={"tool_id": tool_id, "operation": caller})
        with span_scope(span):
            append_event(self.run_id, "tool.invoked", "generation", f"{caller} 调用 {tool_id}", {"tool_id": tool_id, "caller": caller})
            return self.tools.execute(tool_id, caller=caller, **arguments)

    def timed_generation_operation(
        self,
        event_name: str,
        message: str,
        *,
        chapter: int | None = None,
        attempt: int | None = None,
        operation: Callable[[], Any],
    ) -> Any:
        payload = {
            key: value
            for key, value in {"chapter": chapter, "attempt": attempt}.items()
            if value is not None
        }
        append_event(self.run_id, f"{event_name}.started", "generation", message, payload)
        started = perf_counter()
        try:
            result = operation()
        except Exception as exc:
            append_event(
                self.run_id,
                f"{event_name}.failed",
                "generation",
                f"{message}失败：{str(exc)[:180]}",
                {
                    **payload,
                    "duration_ms": round((perf_counter() - started) * 1000),
                    "error": str(exc)[:1000],
                },
            )
            raise
        append_event(
            self.run_id,
            f"{event_name}.completed",
            "generation",
            f"{message}完成",
            {**payload, "duration_ms": round((perf_counter() - started) * 1000)},
        )
        return result

    def timed_quality_operation(
        self,
        operation_name: str,
        message: str,
        *,
        chapter: int | None = None,
        repair_round: int | None = None,
        operation: Callable[[], Any],
    ) -> Any:
        payload = {
            key: value
            for key, value in {
                "chapter": chapter,
                "repair_round": repair_round,
            }.items()
            if value is not None
        }
        append_event(
            self.run_id,
            f"quality.repair.{operation_name}.started",
            "quality",
            message,
            payload,
        )
        started = perf_counter()
        try:
            result = operation()
        except Exception as exc:
            append_event(
                self.run_id,
                f"quality.repair.{operation_name}.failed",
                "quality",
                f"{message}失败：{str(exc)[:180]}",
                {
                    **payload,
                    "duration_ms": round((perf_counter() - started) * 1000),
                    "error": str(exc)[:1000],
                },
            )
            raise
        append_event(
            self.run_id,
            f"quality.repair.{operation_name}.completed",
            "quality",
            f"{message}完成",
            {**payload, "duration_ms": round((perf_counter() - started) * 1000)},
        )
        return result
