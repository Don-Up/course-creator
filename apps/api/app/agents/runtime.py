from __future__ import annotations

from app.agents.course_runtime import CourseAgentRuntime
from app.agents.fake_runtime import FakeProvider
from app.agents.protocols import CourseAgent


def create_course_agent(
    provider_name: str | None = None,
    model_name: str | None = None,
) -> CourseAgent:
    """Bind curriculum behavior to a provider-neutral model transport."""

    if (provider_name or "").lower() == "fake":
        return FakeProvider()

    from app.provider import create_model_transport

    return CourseAgentRuntime(create_model_transport(provider_name, model_name))
