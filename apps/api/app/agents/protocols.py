"""Capability contracts for the course generation agents.

`CourseAgent` freezes the agent capability boundary as a `typing.Protocol`:
the signatures below are a contract that later phases implement, not code to
be improved.  Only the ten capabilities introduced by P1.2 are declared here.
The remaining seven (`revise_workspace`, `audit_workspace_consistency`,
`revise_chapter`, `enrich_chapter`, `apply_repair_patch`,
`classify_reference_section`, `rewrite_section`) arrive in P3.8 together with
their output schemas.

The output types are deliberately *not* imported: `MissionOutput`,
`BlueprintOutput`, `ResearchPlanOutput`, `ResearchCurationOutput`,
`HumanizerOutput`, `SemanticReviewOutput`, `ContinuityOutput`,
`RepairCapabilityPlan` and `OutputPresentation` are created by P3.8 together
with `app/schemas.py`.  Because this module uses
`from __future__ import annotations`, annotations are never evaluated at
runtime, so the unresolved names stay harmless until P3.8 adds the imports.
Until then every signature that mentions one of them carries a `# noqa: F821`
marker; P3.8 replaces those markers with the real import.
"""

from __future__ import annotations

from typing import Protocol


class CourseAgent(Protocol):
    """The capability boundary every course agent has to satisfy."""

    name: str

    def create_mission(self, request: dict) -> MissionOutput:  # noqa: F821
        """Turn the intake request into a structured mission."""
        ...

    def create_blueprint(
        self, request: dict, mission: str
    ) -> BlueprintOutput:  # noqa: F821
        """Plan the modules and chapters that fulfil the mission."""
        ...

    def plan_research(
        self, request: dict, mission: str
    ) -> ResearchPlanOutput:  # noqa: F821
        """Plan which sources have to be researched for the course."""
        ...

    def curate_research(
        self, policy: str, candidates: dict
    ) -> ResearchCurationOutput:  # noqa: F821
        """Select and structure the research candidates under the source policy."""
        ...

    def generate_chapter(self, context: dict) -> str:
        """Write one chapter from its context pack."""
        ...

    def humanize(self, markdown: str) -> HumanizerOutput:  # noqa: F821
        """Rewrite the chapter into student-facing prose."""
        ...

    def semantic_review(
        self, markdown: str, context: dict
    ) -> SemanticReviewOutput:  # noqa: F821
        """Review the chapter for meaning, coverage and correctness."""
        ...

    def extract_continuity(
        self, markdown: str, context: dict
    ) -> ContinuityOutput:  # noqa: F821
        """Extract the continuity facts the next chapter has to respect."""
        ...

    def plan_repair(
        self,
        task: dict,
        markdown: str,
        context: dict,
    ) -> RepairCapabilityPlan:  # noqa: F821
        """Plan how a failed chapter is repaired."""
        ...

    def present_output(
        self, step: str, label: str, output: dict
    ) -> OutputPresentation:  # noqa: F821
        """Present a workflow step result to the user."""
        ...
