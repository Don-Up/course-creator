"""Runtime enforcement for declared teaching-Agent responsibilities."""
from __future__ import annotations

from typing import Any, Callable

from app.agents.definitions import AgentDefinition, get_agent_definition
from app.agents.protocols import CourseAgent


_OPERATIONS: dict[str, set[str]] = {
    "writer.agent": {"generate_chapter", "revise_chapter", "enrich_chapter"},
    "reviewer.agent": {
        "humanize", "semantic_review", "extract_continuity", "classify_reference_section",
    },
    "repair.agent": {
        "plan_repair", "apply_repair_patch", "rewrite_section", "revise_chapter", "enrich_chapter",
    },
}
_MODEL_POLICIES = {
    "writer.agent": "writer.v1",
    "reviewer.agent": "review.v1",
    "repair.agent": "repair.v1",
}


class AgentInvocationDenied(PermissionError):
    """Raised when a Workflow tries to use an Agent outside its declaration."""


class TeachingAgentRuntime:
    """Invoke the existing provider-backed Agent only through its definition.

    The existing ``CourseAgent`` methods are intentionally retained as provider
    compatibility adapters.  Workflow handlers call this runtime instead, so
    Agent ID, version, role and permitted operation become executable rules.
    """

    def __init__(self, delegate: CourseAgent) -> None:
        self.delegate = delegate
        self.name = delegate.name

    def definition(self, agent_id: str) -> AgentDefinition:
        return get_agent_definition(agent_id)

    def invoke(self, agent_id: str, operation: str, *args: Any, **kwargs: Any) -> Any:
        definition = self.definition(agent_id)
        expected_policy = _MODEL_POLICIES.get(definition.id)
        if definition.model_policy_ref != expected_policy:
            raise AgentInvocationDenied(
                f"{definition.id}@{definition.version} 的模型策略不匹配："
                f"{definition.model_policy_ref}"
            )
        allowed = _OPERATIONS.get(definition.id, set())
        if operation not in allowed:
            raise AgentInvocationDenied(
                f"{definition.id}@{definition.version} 未声明操作：{operation}"
            )
        callback: Callable[..., Any] | None = getattr(self.delegate, operation, None)
        if not callable(callback):
            raise AgentInvocationDenied(f"当前 Agent Runtime 不支持操作：{operation}")
        return callback(*args, **kwargs)
