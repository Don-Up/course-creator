"""Permission-checked adapters for course-side effects used by Workflow handlers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.courses.tools import run_course_tool
from app.courses.workspace import apply_workspace_patch_plan


@dataclass(frozen=True)
class ToolManifest:
    id: str
    callers: frozenset[str]
    idempotent: bool


TOOL_MANIFESTS = {
    "course.source_contract": ToolManifest(
        "course.source_contract", frozenset({"workflow.generation", "workflow.quality", "workflow.repair", "workflow.review"}), True,
    ),
    "course.build": ToolManifest(
        "course.build", frozenset({"workflow.generation", "workflow.quality", "workflow.repair", "workflow.review"}), False,
    ),
    "course.validate": ToolManifest(
        "course.validate", frozenset({"workflow.generation", "workflow.quality", "workflow.repair", "workflow.review"}), True,
    ),
    "workspace.patch": ToolManifest(
        "workspace.patch", frozenset({"workflow.planning"}), False,
    ),
}


class ToolInvocationDenied(PermissionError):
    pass


class ToolRuntime:
    """The only Workflow-facing entry point for declared course tools."""

    def execute(self, tool_id: str, *, caller: str, **arguments: Any) -> Any:
        manifest = TOOL_MANIFESTS.get(tool_id)
        if manifest is None:
            raise ToolInvocationDenied(f"未注册工具：{tool_id}")
        if caller not in manifest.callers:
            raise ToolInvocationDenied(f"{caller} 无权调用 {tool_id}")
        if tool_id == "workspace.patch":
            return apply_workspace_patch_plan(
                arguments["course_slug"], arguments["patches"], reason=arguments["reason"],
            )
        action = tool_id.removeprefix("course.")
        return run_course_tool(
            arguments["course_slug"], action,
            chapter_numbers=arguments.get("chapter_numbers"),
        )
