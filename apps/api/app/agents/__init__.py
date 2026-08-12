"""Teaching-agent definitions and runtimes.

This package owns curriculum-specific prompts, context policies and output
contracts. Model transports deliberately do not import it.
"""

from app.agents.definitions import AgentDefinition, AgentRegistry, ModelPolicy, get_agent_definition
from app.agents.executor import AgentInvocationDenied, TeachingAgentRuntime
from app.agents.runtime import CourseAgent, create_course_agent

__all__ = [
    "AgentDefinition",
    "AgentInvocationDenied",
    "AgentRegistry",
    "CourseAgent",
    "ModelPolicy",
    "TeachingAgentRuntime",
    "create_course_agent",
    "get_agent_definition",
]
