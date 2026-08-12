from __future__ import annotations

import pytest

from app.agents.executor import AgentInvocationDenied, TeachingAgentRuntime
from app.agents.fake_runtime import FakeProvider
from app.tools import ToolInvocationDenied, ToolRuntime
from app.tools import runtime as tool_runtime_module


def test_agent_runtime_allows_only_declared_role_operations():
    runtime = TeachingAgentRuntime(FakeProvider())
    content = runtime.invoke("writer.agent", "generate_chapter", {
        "chapter": {"number": 1, "title": "第 1 章", "learning_outcome": "理解运行时契约"},
    })
    assert content.startswith("# 第 1 章")
    with pytest.raises(AgentInvocationDenied, match="writer.agent@v1 未声明操作"):
        runtime.invoke("writer.agent", "semantic_review", "# 章节", {})


def test_agent_runtime_keeps_reviewer_and_repair_operations_separate():
    runtime = TeachingAgentRuntime(FakeProvider())
    review = runtime.invoke("reviewer.agent", "semantic_review", "# 正文", {})
    assert review.decision == "ready"
    with pytest.raises(AgentInvocationDenied):
        runtime.invoke("reviewer.agent", "apply_repair_patch", {}, "# 正文", {}, {})


def test_tool_runtime_rejects_undeclared_caller_and_delegates_declared_tool(monkeypatch):
    runtime = ToolRuntime()
    with pytest.raises(ToolInvocationDenied, match="无权调用"):
        runtime.execute("course.build", caller="writer.agent", course_slug="demo")
    monkeypatch.setattr(
        tool_runtime_module, "run_course_tool",
        lambda slug, action, chapter_numbers=None: {
            "slug": slug, "action": action, "chapter_numbers": chapter_numbers,
        },
    )
    assert runtime.execute(
        "course.source_contract", caller="workflow.generation", course_slug="demo",
        chapter_numbers=[1, 2],
    ) == {"slug": "demo", "action": "source_contract", "chapter_numbers": [1, 2]}


def test_workspace_patch_is_only_available_to_planning_handler(monkeypatch):
    runtime = ToolRuntime()
    with pytest.raises(ToolInvocationDenied):
        runtime.execute("workspace.patch", caller="workflow.repair", course_slug="demo", patches=[], reason="x")
    monkeypatch.setattr(
        tool_runtime_module, "apply_workspace_patch_plan",
        lambda slug, patches, reason: {"slug": slug, "patches": patches, "reason": reason},
    )
    assert runtime.execute(
        "workspace.patch", caller="workflow.planning", course_slug="demo",
        patches=[{"path": "MISSION.md"}], reason="revise",
    )["reason"] == "revise"
