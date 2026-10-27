"""Contract tests for the first batch of agent output schemas.

P1.3 lands the thirteen output models the `CourseAgent` protocol returns,
and P1.5 adds `CourseCreate`, the intake model of the creation API.
The point of the models is not that the classes exist but that they reject
impossible values: the fake runtime and the real providers that arrive
later have to share one field contract, so a score outside its range or an
unknown decision has to fail loudly instead of travelling through the
workflow.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from app import schemas

EXPECTED_MODELS = frozenset(
    {
        "MissionOutput",
        "ChapterPlan",
        "ModulePlan",
        "BlueprintOutput",
        "ResearchPlanOutput",
        "CuratedSource",
        "ResearchCurationOutput",
        "HumanizerOutput",
        "RepairTaskVerification",
        "SemanticReviewOutput",
        "ContinuityOutput",
        "RepairCapabilityPlan",
        "OutputPresentation",
        "CourseCreate",
        "CourseSummary",
        "CourseList",
        "CourseCreated",
    }
)


def test_schemas_module_exposes_exactly_the_agreed_models():
    """P1.3 owns thirteen models, P1.5 the intake, P1.6 the course list.

    P1.7 adds the answer of the creation API.  The set is pinned so that a
    schema cannot slip in early: the workspace schemas belong to P3.8.
    """
    exported = {
        name
        for name, value in vars(schemas).items()
        if isinstance(value, type)
        and value is not BaseModel
        and issubclass(value, BaseModel)
    }

    assert exported == EXPECTED_MODELS


def test_humanizer_output_accepts_a_score_inside_its_range():
    """A humanizer score is a quality grade, so it never exceeds 50."""
    output = schemas.HumanizerOutput(revised_markdown="# 标题", score=30)

    assert output.score == 30
    assert output.issues == []


def test_humanizer_output_rejects_a_score_above_fifty():
    """A score of 51 cannot be a grade, so validation has to reject it."""
    with pytest.raises(ValidationError):
        schemas.HumanizerOutput(revised_markdown="# 标题", score=51)


def test_semantic_review_output_accepts_a_ready_decision():
    output = schemas.SemanticReviewOutput(score=90, decision="ready")

    assert output.decision == "ready"
    assert output.score == 90


def test_semantic_review_output_rejects_an_unknown_decision():
    """Only the three agreed decisions are legal."""
    with pytest.raises(ValidationError):
        schemas.SemanticReviewOutput(score=90, decision="maybe")


def test_blueprint_output_requires_a_course_title():
    """A blueprint without a course title cannot be rendered or released."""
    with pytest.raises(ValidationError):
        schemas.BlueprintOutput(modules=[])
