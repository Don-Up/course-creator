"""Output schemas of the course generation agents.

These models are the typed return values of the `CourseAgent` protocol:
the agents answer with real models instead of bare dictionaries, so the
workflow layer can rely on a field contract and Pydantic can reject an
impossible value before it reaches a stage output.

Only the thirteen models P1.3 needs live here.  `CourseCreate` arrives with
P1.5 and the workspace schemas with P3.8.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


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
