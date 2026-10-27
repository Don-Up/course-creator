"""Output schemas of the course generation agents.

These models are the typed return values of the `CourseAgent` protocol:
the agents answer with real models instead of bare dictionaries, so the
workflow layer can rely on a field contract and Pydantic can reject an
impossible value before it reaches a stage output.

The thirteen models P1.3 needs live here, plus the `CourseCreate` that
P1.5 added for the intake form: it is the one request model of this
module.  P1.6 adds the two response models of the course list, and P1.7
adds the answer of the creation API.  P2.4 adds the four models of the
editor, the API that reads and writes a chapter and a workspace file.
P2.5 adds the models of the run read model, the answer the browser polls
while the agent works.  The schemas of the agent stages arrive with P3.8.
"""

from __future__ import annotations

from typing import Any, Literal

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


class ChapterSummary(BaseModel):
    """One chapter as the chapter list shows it.

    The key is the one the single chapter route accepts, so a chapter
    taken from the list can be read back without a second guess.  The
    path is inside the course, never an absolute path of this machine.
    """

    key: str
    number: int
    title: str
    path: str


class ChapterList(BaseModel):
    """The answer of `GET /api/courses/{slug}/chapters`."""

    items: list[ChapterSummary] = Field(default_factory=list)


class ChapterRead(BaseModel):
    """One chapter as the editor shows it.

    The content hash is the fingerprint of the content, and it is what the
    editor sends back as `expected_hash` when it saves.  The snapshot path
    is only filled in by a save: it points at the copy of the content that
    the save replaced.
    """

    key: str
    path: str
    content: str
    content_hash: str
    updated_at: str
    snapshot_path: str = ""


class ChapterSave(BaseModel):
    """The body of a chapter save.

    The expected hash is the fingerprint the editor read.  When the file on
    the disk does not carry that fingerprint any more, the save is refused
    with a 409 instead of overwriting the other editor's work.
    """

    content: str
    expected_hash: str = Field(min_length=64, max_length=64)


class WorkspaceFileRead(BaseModel):
    """One file of the workspace as the editor shows it.

    The content hash is the fingerprint of the content, and it is what the
    editor sends back as `expected_hash` when it saves.  The snapshot path
    is only filled in by a save: it points at the copy of the content that
    the save replaced.
    """

    name: str
    path: str
    content: str
    content_hash: str
    size: int
    updated_at: str
    snapshot_path: str = ""


class WorkspaceFileSave(BaseModel):
    """The body of a workspace file save.

    The expected hash is the fingerprint the editor read.  When the file on
    the disk does not carry that fingerprint any more, the save is refused
    with a 409 instead of overwriting the other editor's work.
    """

    content: str
    expected_hash: str = Field(min_length=64, max_length=64)


class RunCommandRead(BaseModel):
    """One command of a run as the browser sees it.

    The payload of a command stays in the database: it is the machine's own
    instruction, not something a person reads.
    """

    id: str
    kind: str
    status: str
    attempt_count: int = 0
    created_at: str
    updated_at: str


class RunRead(BaseModel):
    """One run as the browser sees it.

    The fields are the ones of the `runs` row that a person reads.  The
    request that started the run, the payload of an approval and the budget
    policy are not here: they are the machine's own notes, and the later
    phases grow them into the assembled prompt.

    The active command is the command the run is still waiting on.  It is
    None when there is none, and it is what tells the frontend that a run
    which already failed may still get going again.
    """

    id: str
    course_slug: str
    mode: str
    status: str
    current_step: str
    provider: str
    model: str
    interrupt_type: str | None = None
    error_message: str | None = None
    trace_id: str | None = None
    created_at: str
    updated_at: str
    active_command: RunCommandRead | None = None


class RunEventRead(BaseModel):
    """One event of a run as the browser sees it.

    The payload of an event stays in the database.  The event itself says
    what happened, in which stage and when, and that is what a timeline
    is made of.
    """

    seq: int
    id: str
    event_type: str
    step: str
    message: str
    created_at: str


class RunArtifactRead(BaseModel):
    """One artifact of a run as the browser sees it.

    The presentation is the artifact as it was written for a person to
    read.  The untouched model output behind it is not part of the answer.
    """

    id: str
    step: str
    node: str
    title: str
    source: str
    presentation: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class WorkflowStepRead(BaseModel):
    """One stage of the workflow as the browser shows it.

    The status says where the stage stands: "completed", "active" or
    "pending".
    """

    id: str
    title: str
    description: str
    user_input: str
    model_output: str
    status: str


class RunDetail(BaseModel):
    """The answer of `GET /api/runs/{run_id}`.

    The four parts are the ones the browser needs: where the run is, what
    it has done, what it produced, and how far the seven stages have come.
    """

    run: RunRead
    events: list[RunEventRead] = Field(default_factory=list)
    artifacts: list[RunArtifactRead] = Field(default_factory=list)
    workflow_steps: list[WorkflowStepRead] = Field(default_factory=list)


class RunSummary(BaseModel):
    """One run as the run list shows it.

    The list is a way into the runs, so it carries the fields that say
    which run this is and where it stands, and nothing else.
    """

    id: str
    course_slug: str
    mode: str
    status: str
    current_step: str
    created_at: str
    updated_at: str


class RunList(BaseModel):
    """The answer of `GET /api/runs`."""

    items: list[RunSummary] = Field(default_factory=list)


class WorkflowNodeRead(BaseModel):
    """One node of the workflow topology as the browser sees it.

    The node is one unit of work of the workflow.  The stage says which
    phase it belongs to, and the position says where it sits in the graph.
    """

    id: str
    stage: str
    title: str
    description: str
    position: int


class WorkflowEdgeRead(BaseModel):
    """One transition between two nodes of the workflow topology."""

    source: str
    target: str


class WorkflowPhaseRead(BaseModel):
    """One phase of the workflow topology as the browser sees it.

    The nodes are the ids of the units of work that belong to the phase.
    """

    id: str
    title: str
    description: str
    user_input: str
    model_output: str
    nodes: list[str] = Field(default_factory=list)


class WorkflowSnapshotRead(BaseModel):
    """The answer of `GET /api/workflow`.

    The topology of the workflow, as the graph of the workflow says: the
    phases, the nodes and the transitions between the nodes.
    """

    version: int
    id: str
    name: str
    phases: list[WorkflowPhaseRead] = Field(default_factory=list)
    nodes: list[WorkflowNodeRead] = Field(default_factory=list)
    edges: list[WorkflowEdgeRead] = Field(default_factory=list)
