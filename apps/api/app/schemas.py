"""Output schemas of the course generation agents.

These models are the typed return values of the `CourseAgent` protocol:
the agents answer with real models instead of bare dictionaries, so the
workflow layer can rely on a field contract and Pydantic can reject an
impossible value before it reaches a stage output.

The thirteen models P1.3 needs live here, plus the `CourseCreate` that
P1.5 added for the intake form: it is the one request model of this
module.  P1.6 adds the two response models of the course list, and P1.7
adds the answer of the creation API.  The workspace schemas arrive with
P3.8.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.courses.common import SLUG_PATTERN


class MissionOutput(BaseModel):
    mission_markdown: str
    assumptions: list[str] = Field(default_factory=list)


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


class HumanizerOutput(BaseModel):
    revised_markdown: str
    score: int = Field(ge=0, le=50)
    issues: list[str] = Field(default_factory=list)


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


class ContinuityOutput(BaseModel):
    summary: str
    established_terms: list[str] = Field(default_factory=list)
    established_facts: list[str] = Field(default_factory=list)
    open_loops: list[str] = Field(default_factory=list)
    bridge_to_next: list[str] = Field(default_factory=list)


class RepairCapabilityPlan(BaseModel):
    task_id: str
    scope: Literal["paragraph", "section", "chapter"] = "section"
    selected_capabilities: list[
        Literal[
            "markdown_format",
            "link_reference",
            "code_structure",
            "teaching_scaffold",
            "source_contract",
            "content_enrichment",
            "humanizer",
            "section_rewrite",
            "chapter_rewrite",
        ]
    ] = Field(default_factory=list, max_length=4)
    target_anchors: list[str] = Field(default_factory=list, max_length=6)
    reasoning_summary: str = Field(min_length=1, max_length=800)
    verification_plan: list[str] = Field(default_factory=list, max_length=6)


class OutputPresentation(BaseModel):
    headline: str
    conclusion: str
    highlights: list[str] = Field(default_factory=list)
    metrics: dict[str, str | int | float | bool] = Field(default_factory=dict)
    issues: list[str] = Field(default_factory=list)
    next_action: str = ""


class CourseCreate(BaseModel):
    """The intake form a user submits to create a course.

    This is the only request model of the module: the creation API of P1.7
    takes it as the body of `POST /api/courses`.  The slug uses the pattern
    of `app.courses.common.SLUG_PATTERN`, so the API and the path guard can
    never disagree about what a legal course folder looks like.
    """

    title: str = Field(min_length=2, max_length=120)
    slug: str = Field(pattern=SLUG_PATTERN.pattern)
    audience: str = Field(min_length=2, max_length=500)
    goals: str = Field(min_length=5, max_length=3000)
    scope: str = Field(min_length=2, max_length=3000)
    source_policy: str = "允许使用用户资料与公开官方资料"
    delivery: str = "Markdown + HTML"
    preferred_chapter_count: int = Field(default=12, ge=1, le=60)
    effective_char_min: int = Field(default=12000, ge=1000, le=50000)
    token_budget_mtokens: float | None = Field(default=None, ge=0.01, le=10000)
    provider: str = "codex_gateway"
    model: str = "llm-gateway--kimi-k3"


class CourseSummary(BaseModel):
    """One course as the course list shows it.

    The six fields are the ones `app.courses.catalog` reads out of the
    course file.  A course that has not been generated yet is a course with
    zero chapters, and its status is "preparing".
    """

    slug: str
    title: str
    description: str
    chapters: int
    status: str
    duration: str


class CourseList(BaseModel):
    """The answer of `GET /api/courses`."""

    items: list[CourseSummary]


class CourseCreated(BaseModel):
    """The answer of `POST /api/courses`.

    The course is the item the course list shows, so the frontend has one
    shape for a course wherever it comes from.  The run id names the intake
    run of this creation; until the run tables arrive with P2.1 it is an id
    without a record behind it.  The status is the status of the new
    course, which is "preparing" because it has no chapters yet.
    """

    course: CourseSummary
    run_id: str
    status: str
