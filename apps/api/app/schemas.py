from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class CourseCreate(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    audience: str = Field(min_length=2, max_length=500)
    goals: str = Field(min_length=5, max_length=3000)
    scope: str = Field(min_length=2, max_length=3000)
    source_policy: str = Field(default="允许使用用户资料与公开官方资料")
    delivery: str = Field(default="Markdown + HTML")
    preferred_chapter_count: int = Field(default=12, ge=1, le=60)
    effective_char_min: int = Field(default=12000, ge=1000, le=50000)
    token_budget_mtokens: float | None = Field(default=None, ge=0.01, le=10000)
    provider: str = Field(default="codex_gateway")
    model: str = Field(default="llm-gateway--kimi-k3")


class ChapterUpdate(BaseModel):
    content: str = Field(min_length=1)
    expected_hash: str
    reason: str = Field(default="在课程工作台中编辑")
    rebuild: bool = False


class WorkspaceFileUpdate(BaseModel):
    content: str
    expected_hash: str


class WorkspaceResourceUpload(BaseModel):
    filename: str = Field(min_length=1, max_length=180)
    content_base64: str
    media_type: str = Field(default="application/octet-stream", max_length=120)


class WorkspaceResourceNote(BaseModel):
    content: str = Field(min_length=1, max_length=20000)


class ApprovalResolve(BaseModel):
    action: Literal["APPROVE", "REVISE", "STOP"]
    feedback: str = Field(default="", max_length=5000)


class RunContinue(BaseModel):
    """Resume a run from its latest persisted LangGraph checkpoint."""

    feedback: str = Field(default="", max_length=5000)


class ProviderPreferencesUpdate(BaseModel):
    provider: Literal["codex_gateway", "deepseek"]
    model: str = Field(min_length=1, max_length=160)
    deepseek_api_key: str = Field(default="", max_length=500)
    llm_base_url: str = Field(default="", max_length=500)


class RunStart(BaseModel):
    provider: str = "codex_gateway"
    model: str = "llm-gateway--kimi-k3"
    scope: Literal["new_course", "review_course", "regenerate_course"] = "review_course"
    chapter_keys: list[str] = Field(default_factory=list)
    instruction: str = Field(default="", max_length=5000)


class MissionOutput(BaseModel):
    mission_markdown: str
    assumptions: list[str] = Field(default_factory=list)


class WorkspacePatch(BaseModel):
    path: Literal[
        "MISSION.md",
        "COURSE-GENERATION-SPEC.md",
        "RESOURCES.md",
        "NOTES.md",
        "COURSE-BLUEPRINT.md",
    ]
    original: str = Field(min_length=1, max_length=65536)
    replacement: str = Field(min_length=1, max_length=98304)
    reason: str = Field(default="", max_length=280)


class WorkspaceRevisionOutput(BaseModel):
    change_summary: str = Field(min_length=1, max_length=1200)
    patches: list[WorkspacePatch] = Field(min_length=1, max_length=6)
    preferred_chapter_count: int | None = Field(default=None, ge=1, le=60)
    source_policy: str | None = Field(default=None, max_length=300)
    downstream_impacts: list[str] = Field(default_factory=list, max_length=12)


class ChapterPlan(BaseModel):
    number: int
    title: str
    learning_outcome: str
    prerequisites: list[str] = Field(default_factory=list)
    continuity_in: list[str] = Field(default_factory=list)
    continuity_out: list[str] = Field(default_factory=list)
    pedagogy_type: Literal[
        "opening_closing",
        "environment",
        "language",
        "framework",
        "mechanism",
        "integrated_practice",
    ] = "language"
    primary_teaching_task: str = "概念讲解"
    instructor_voice: str = "耐心教练型"
    learning_path: list[str] = Field(default_factory=list)
    template_modules: list[str] = Field(default_factory=list)


class ModulePlan(BaseModel):
    title: str
    goal: str
    narrative: str
    chapters: list[ChapterPlan]


class BlueprintOutput(BaseModel):
    course_title: str
    modules: list[ModulePlan]
    design_notes: list[str] = Field(default_factory=list)


class ResearchPlanOutput(BaseModel):
    queries: list[str] = Field(default_factory=list)
    search_rationale: str = ""


class CuratedSource(BaseModel):
    title: str
    url: str
    reason: str
    source_type: Literal["official", "standard", "paper", "community"] = "official"


class ResearchCurationOutput(BaseModel):
    sources: list[CuratedSource] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class WorkspaceConsistencyOutput(BaseModel):
    decision: Literal["pass", "repair"]
    issues: list[str] = Field(default_factory=list)
    canonical_requirements: list[str] = Field(default_factory=list)


class HumanizerOutput(BaseModel):
    revised_markdown: str
    score: int = Field(ge=0, le=50)
    issues: list[str] = Field(default_factory=list)


class HumanizerPatch(BaseModel):
    original: str = Field(min_length=1, max_length=1200)
    replacement: str = Field(min_length=1, max_length=1600)
    reason: str = Field(default="", max_length=240)


class HumanizerPatchOutput(BaseModel):
    score: int = Field(ge=0, le=50)
    issues: list[str] = Field(default_factory=list)
    patches: list[HumanizerPatch] = Field(default_factory=list, max_length=14)


class RepairTaskVerification(BaseModel):
    task_id: str
    resolved: bool
    evidence_excerpt: str = Field(default="", max_length=1200)
    reason: str = Field(default="", max_length=800)


class SemanticReviewOutput(BaseModel):
    score: int = Field(ge=0, le=100)
    decision: Literal["ready", "manual_review", "reject"]
    issues: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    repair_verifications: list[RepairTaskVerification] = Field(default_factory=list)


class ReferenceSectionCandidate(BaseModel):
    node_id: str
    depth: int
    title: str
    line: int
    relative_position: float = Field(ge=0, le=1)
    child_kinds: list[str] = Field(default_factory=list)
    external_link_count: int = Field(ge=0)
    excerpt: str


class ReferenceSectionDecision(BaseModel):
    role: Literal["references", "not_references", "ambiguous"]
    node_id: str | None = None
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=800)
    recommended_action: Literal[
        "canonicalize_heading", "llm_patch", "section_rewrite", "human_review"
    ]


class RepairCapabilityPlan(BaseModel):
    task_id: str
    scope: Literal["paragraph", "section", "chapter"] = "section"
    selected_capabilities: list[
        Literal[
            "markdown_format", "link_reference", "code_structure",
            "teaching_scaffold", "source_contract", "content_enrichment",
            "humanizer", "section_rewrite", "chapter_rewrite",
        ]
    ] = Field(default_factory=list, max_length=4)
    target_anchors: list[str] = Field(default_factory=list, max_length=6)
    reasoning_summary: str = Field(min_length=1, max_length=800)
    verification_plan: list[str] = Field(default_factory=list, max_length=6)


class RepairTextPatch(BaseModel):
    original: str = Field(min_length=1, max_length=8000)
    replacement: str = Field(min_length=1, max_length=10000)
    reason: str = Field(min_length=1, max_length=500)


class RepairPatchOutput(BaseModel):
    task_id: str
    scope: Literal["paragraph", "section", "chapter"] = "section"
    patches: list[RepairTextPatch] = Field(min_length=1, max_length=8)


class SectionRewriteOutput(BaseModel):
    task_id: str
    expected_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    original_section: str = Field(min_length=1, max_length=30000)
    replacement_section: str = Field(min_length=1, max_length=36000)
    reason: str = Field(min_length=1, max_length=800)


class ContinuityOutput(BaseModel):
    summary: str
    established_terms: list[str] = Field(default_factory=list)
    established_facts: list[str] = Field(default_factory=list)
    open_loops: list[str] = Field(default_factory=list)
    bridge_to_next: list[str] = Field(default_factory=list)


class OutputPresentation(BaseModel):
    headline: str
    conclusion: str
    highlights: list[str] = Field(default_factory=list)
    metrics: dict[str, str | int | float | bool] = Field(default_factory=dict)
    issues: list[str] = Field(default_factory=list)
    next_action: str = ""


class EventPayload(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict)
