from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, Field


class ModelPolicy(BaseModel):
    """Model limits selected by an Agent, never by the course domain."""

    id: str
    capability: Literal["planning", "long_writing", "review", "repair", "presentation"]
    reasoning_effort: str | None = None
    max_output_tokens_setting: str
    transport_timeout_setting: str | None = None
    hard_timeout_setting: str | None = None


class AgentDefinition(BaseModel):
    """A versioned declaration of one teaching responsibility."""

    id: str
    version: str = "v1"
    role: str
    input_schema: str
    output_schema: str
    prompt_ref: str
    context_policy_ref: str
    tool_ids: list[str] = Field(default_factory=list)
    model_policy_ref: str
    output_artifact_type: str


MODEL_POLICIES = {
    "planning.v1": ModelPolicy(
        id="planning.v1",
        capability="planning",
        max_output_tokens_setting="llm_max_output_tokens",
        transport_timeout_setting="llm_long_content_hard_timeout_seconds",
        hard_timeout_setting="llm_long_content_hard_timeout_seconds",
    ),
    "writer.v1": ModelPolicy(
        id="writer.v1",
        capability="long_writing",
        max_output_tokens_setting="llm_chapter_max_output_tokens",
        transport_timeout_setting="llm_long_content_hard_timeout_seconds",
        hard_timeout_setting="llm_long_content_hard_timeout_seconds",
    ),
    "review.v1": ModelPolicy(
        id="review.v1",
        capability="review",
        max_output_tokens_setting="llm_semantic_review_max_output_tokens",
        hard_timeout_setting="llm_semantic_review_hard_timeout_seconds",
    ),
    "repair.v1": ModelPolicy(
        id="repair.v1",
        capability="repair",
        max_output_tokens_setting="llm_semantic_review_max_output_tokens",
        hard_timeout_setting="llm_long_content_hard_timeout_seconds",
    ),
    "presenter.v1": ModelPolicy(
        id="presenter.v1",
        capability="presentation",
        max_output_tokens_setting="llm_presentation_max_output_tokens",
    ),
}


AGENT_DEFINITIONS = {
    definition.id: definition
    for definition in [
        AgentDefinition(
            id="mission.agent",
            role="课程任务定义与增量工作区修订",
            input_schema="CourseRequest | WorkspaceRevisionRequest",
            output_schema="MissionOutput | WorkspaceRevisionOutput",
            prompt_ref="app.agents.course_runtime:mission",
            context_policy_ref="planning_request.v1",
            tool_ids=["workspace.read"],
            model_policy_ref="planning.v1",
            output_artifact_type="mission",
        ),
        AgentDefinition(
            id="research.agent",
            role="课程资料检索计划与候选资料筛选",
            input_schema="Mission | SourcePolicy | SearchCandidates",
            output_schema="ResearchPlanOutput | ResearchCurationOutput",
            prompt_ref="app.agents.course_runtime:research",
            context_policy_ref="planning_request.v1",
            tool_ids=["source.search"],
            model_policy_ref="planning.v1",
            output_artifact_type="source_pack",
        ),
        AgentDefinition(
            id="blueprint.agent",
            role="课程模块、章节与教学路径设计",
            input_schema="CourseRequest | Mission | SourcePack",
            output_schema="BlueprintOutput",
            prompt_ref="app.agents.course_runtime:blueprint",
            context_policy_ref="planning_request.v1",
            tool_ids=["workspace.read"],
            model_policy_ref="planning.v1",
            output_artifact_type="blueprint",
        ),
        AgentDefinition(
            id="writer.agent",
            role="学生可见章节正文写作",
            input_schema="ChapterContextPack",
            output_schema="Markdown",
            prompt_ref="app.agents.course_runtime:writer",
            context_policy_ref="teaching_skill_packet.v1",
            model_policy_ref="writer.v1",
            output_artifact_type="chapter_draft",
        ),
        AgentDefinition(
            id="reviewer.agent",
            role="教学质量、语义与连续性审校",
            input_schema="ChapterDraft | ReviewContext",
            output_schema="HumanizerOutput | SemanticReviewOutput | ContinuityOutput",
            prompt_ref="app.agents.course_runtime:reviewer",
            context_policy_ref="semantic_review_context.v1",
            tool_ids=["source.read"],
            model_policy_ref="review.v1",
            output_artifact_type="quality_result",
        ),
        AgentDefinition(
            id="repair.agent",
            role="章节质量问题定向修复",
            input_schema="RepairTask | ChapterDraft | ChapterContextPack",
            output_schema="RepairCapabilityPlan | RepairPatchOutput | SectionRewriteOutput",
            prompt_ref="app.agents.course_runtime:repair",
            context_policy_ref="repair_context.v1",
            model_policy_ref="repair.v1",
            output_artifact_type="repair_plan",
        ),
        AgentDefinition(
            id="presenter.agent",
            role="运行产物的用户可读摘要",
            input_schema="NodeOutputProjection",
            output_schema="OutputPresentation",
            prompt_ref="app.agents.course_runtime:presenter",
            context_policy_ref="presentation_projection.v1",
            model_policy_ref="presenter.v1",
            output_artifact_type="presentation",
        ),
    ]
}


class AgentRegistry(Protocol):
    def get(self, agent_id: str, version: str = "v1") -> AgentDefinition: ...


class TeachingAgentRegistry:
    def get(self, agent_id: str, version: str = "v1") -> AgentDefinition:
        definition = AGENT_DEFINITIONS.get(agent_id)
        if definition is None or definition.version != version:
            raise KeyError(f"未知教学 Agent：{agent_id}@{version}")
        return definition


def get_agent_definition(agent_id: str, version: str = "v1") -> AgentDefinition:
    return TeachingAgentRegistry().get(agent_id, version)
