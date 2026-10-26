"""Behaviour tests for the fake agent runtime.

`FakeProvider` is the only agent implementation Phase 1 has.  Three
properties matter and are pinned here: it is deterministic (the same input
always produces the same output), it needs no key and no network, and it
can inject a failure on demand so the workflow's error paths can be
exercised before a real provider exists.
"""

from __future__ import annotations

import pytest

from app.agents.fake_runtime import FakeProvider
from app.agents.protocols import CourseAgent
from app.agents.runtime import create_course_agent
from app.schemas import BlueprintOutput, HumanizerOutput, SemanticReviewOutput

MISSION_REQUEST = {
    "title": "Python 入门",
    "audience": "零基础学员",
    "goals": ["能写出一个可运行的小程序"],
    "scope": "覆盖变量、函数与数据结构",
    "source_policy": "只使用官方文档",
}

CHAPTER_CONTEXT = {
    "chapter": {
        "title": "第 1 章：课程导览",
        "learning_outcome": "理解课程结构并完成第一个练习",
    }
}

# One entry per capability that can be made to fail, mapped to the arguments
# the capability needs.  The lookup keeps the failure test free of ten
# near-identical call sites.
CALL_ARGUMENTS = {
    "create_mission": (MISSION_REQUEST,),
    "create_blueprint": ({"title": "Python 入门"}, "mission"),
    "plan_research": ({"title": "Python 入门"}, "mission"),
    "curate_research": ("official", {}),
    "generate_chapter": (CHAPTER_CONTEXT,),
    "semantic_review": ("# 标题", {}),
    "extract_continuity": ("# 标题", {}),
    "plan_repair": ({"id": "task-1"}, "# 标题", {}),
    "present_output": ("mission", "任务定义", {"mission_markdown": "# 标题"}),
}


def _invoke(provider: FakeProvider, method_name: str):
    """Call one capability of the provider with valid arguments."""
    return getattr(provider, method_name)(*CALL_ARGUMENTS[method_name])


def test_humanize_returns_a_valid_high_score():
    """The default humanizer hands back a grade the workflow can accept."""
    provider = FakeProvider()

    output = provider.humanize("# 标题\n\n正文")

    assert isinstance(output, HumanizerOutput)
    assert output.score == 47
    assert output.revised_markdown == "# 标题\n\n正文"
    assert output.issues == []


def test_semantic_review_returns_ready():
    """The default reviewer passes the chapter on."""
    provider = FakeProvider()

    output = provider.semantic_review("# 标题", {})

    assert isinstance(output, SemanticReviewOutput)
    assert output.decision == "ready"
    assert output.score == 90
    assert output.issues == []
    assert len(output.strengths) == 1


@pytest.mark.parametrize(
    ("preferred_chapter_count", "expected_chapters"),
    [(12, 4), (2, 2), (None, 4)],
)
def test_blueprint_never_plans_more_than_four_chapters(
    preferred_chapter_count, expected_chapters
):
    """The chapter count is capped at four and defaults to four."""
    provider = FakeProvider()
    request = {"title": "Python 入门"}
    if preferred_chapter_count is not None:
        request["preferred_chapter_count"] = preferred_chapter_count

    blueprint = provider.create_blueprint(request, "mission")

    assert isinstance(blueprint, BlueprintOutput)
    assert blueprint.course_title == "Python 入门"
    assert len(blueprint.modules) == 1
    assert blueprint.modules[0].title == "模块一：Fake Provider 演示模块"
    assert len(blueprint.modules[0].chapters) == expected_chapters


def test_blueprint_is_deterministic():
    """The same provider answers the same question the same way."""
    provider = FakeProvider()

    first = provider.create_blueprint({"title": "Python 入门"}, "mission")
    second = provider.create_blueprint({"title": "Python 入门"}, "mission")

    assert first == second


@pytest.mark.parametrize(
    ("fail_at", "method_name"),
    [
        ("create_mission", "create_mission"),
        ("create_blueprint", "create_blueprint"),
        ("plan_research", "plan_research"),
        ("curate_research", "curate_research"),
        ("generation", "generate_chapter"),
        ("generate_chapter", "generate_chapter"),
        ("semantic_review", "semantic_review"),
        ("extract_continuity", "extract_continuity"),
        ("plan_repair", "plan_repair"),
        ("present_output", "present_output"),
    ],
)
def test_injected_failure_raises_runtime_error(fail_at, method_name):
    """Every failure tier raises with the same fixed message."""
    provider = FakeProvider(fail_at=fail_at)

    with pytest.raises(RuntimeError) as excinfo:
        _invoke(provider, method_name)

    assert str(excinfo.value) == f"FakeProvider failed at {method_name}."


def test_generation_failure_is_triggered_by_the_generation_alias():
    """`generation` is the stage id, `generate_chapter` the method name."""
    provider = FakeProvider(fail_at="generation")

    with pytest.raises(RuntimeError) as excinfo:
        provider.generate_chapter(CHAPTER_CONTEXT)

    assert str(excinfo.value) == "FakeProvider failed at generate_chapter."


def test_humanize_failure_degrades_instead_of_raising():
    """The humanizer tier fails with a low but valid score.

    A degraded grade is what a quality loop has to react to; raising an
    exception there would break the flow instead of exercising it.
    """
    provider = FakeProvider(fail_at="humanize")

    output = provider.humanize("# 标题")

    assert output.score == 30
    assert len(output.issues) == 1


def test_unknown_failure_point_is_rejected_at_construction():
    """A typo in `fail_at` must not turn into a silent no-op."""
    with pytest.raises(ValueError):
        FakeProvider(fail_at="nope")


def test_factory_returns_the_fake_provider():
    """The factory hands out the fake runtime, and it satisfies the protocol."""
    agent = create_course_agent("fake")

    assert isinstance(agent, FakeProvider)
    assert isinstance(agent, CourseAgent)
    assert agent.name == "fake"


def test_factory_is_case_insensitive():
    assert isinstance(create_course_agent("FAKE"), FakeProvider)


def test_factory_refuses_an_unavailable_provider():
    """Phase 1 has no real provider, so every other name is refused."""
    with pytest.raises(NotImplementedError):
        create_course_agent("codex_gateway")


def test_factory_has_no_default_provider():
    """The default must not fall back to a provider that does not exist."""
    with pytest.raises(NotImplementedError):
        create_course_agent()
