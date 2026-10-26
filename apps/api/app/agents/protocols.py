"""Capability contracts for the course generation agents.

`CourseAgent` freezes the agent capability boundary as a `typing.Protocol`:
the signatures below are a contract that later phases implement, not code to
be improved.  Only the ten capabilities introduced by P1.2 are declared here.
The remaining seven (`revise_workspace`, `audit_workspace_consistency`,
`revise_chapter`, `enrich_chapter`, `apply_repair_patch`,
`classify_reference_section`, `rewrite_section`) arrive in P3.8 together with
their output schemas.

The output types are provided by P1.3's `app/schemas.py`; P3.8 adds the
remaining schemas and the remaining seven methods.

The protocol is runtime-checkable, so `isinstance(agent, CourseAgent)` is
the evidence that an implementation really covers the whole boundary.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.schemas import (
    BlueprintOutput,
    ContinuityOutput,
    HumanizerOutput,
    MissionOutput,
    OutputPresentation,
    RepairCapabilityPlan,
    ResearchCurationOutput,
    ResearchPlanOutput,
    SemanticReviewOutput,
)


@runtime_checkable
class CourseAgent(Protocol):
    """The capability boundary every course agent has to satisfy."""

    name: str

    def create_mission(self, request: dict) -> MissionOutput:
        """Turn the intake request into a structured mission."""
        ...

    def create_blueprint(
        self, request: dict, mission: str
    ) -> BlueprintOutput:
        """Plan the modules and chapters that fulfil the mission."""
        ...

    def plan_research(
        self, request: dict, mission: str
    ) -> ResearchPlanOutput:
        """Plan which sources have to be researched for the course."""
        ...

    def curate_research(
        self, policy: str, candidates: dict
    ) -> ResearchCurationOutput:
        """Select and structure the research candidates under the source policy."""
        ...

    def generate_chapter(self, context: dict) -> str:
        """Write one chapter from its context pack."""
        ...

    def humanize(self, markdown: str) -> HumanizerOutput:
        """Rewrite the chapter into student-facing prose."""
        ...

    def semantic_review(
        self, markdown: str, context: dict
    ) -> SemanticReviewOutput:
        """Review the chapter for meaning, coverage and correctness."""
        ...

    def extract_continuity(
        self, markdown: str, context: dict
    ) -> ContinuityOutput:
        """Extract the continuity facts the next chapter has to respect."""
        ...

    def plan_repair(
        self,
        task: dict,
        markdown: str,
        context: dict,
    ) -> RepairCapabilityPlan:
        """Plan how a failed chapter is repaired."""
        ...

    def present_output(
        self, step: str, label: str, output: dict
    ) -> OutputPresentation:
        """Present a workflow step result to the user."""
        ...
