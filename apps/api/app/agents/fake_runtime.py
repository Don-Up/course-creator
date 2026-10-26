"""The offline agent runtime used before a real provider exists.

`FakeProvider` implements the ten capabilities of the `CourseAgent` protocol
without a key, a network call or a single byte of persistence: every method
is a pure function that derives its answer from its input.  The outputs are
stable, so the workflow can be exercised end to end while Phase 1 still has
no model provider.

`fail_at` injects a failure on demand.  Every tier raises `RuntimeError`
except the humanizer, which degrades to a low but *valid* score -- a quality
loop has to react to a poor grade, and an exception there would break the
flow instead of exercising it.
"""

from __future__ import annotations

from app.schemas import (
    BlueprintOutput,
    ChapterPlan,
    ContinuityOutput,
    CuratedSource,
    HumanizerOutput,
    MissionOutput,
    ModulePlan,
    OutputPresentation,
    RepairCapabilityPlan,
    ResearchCurationOutput,
    ResearchPlanOutput,
    SemanticReviewOutput,
)

# The failure tiers map the injected `fail_at` value onto the method it
# breaks.  `generation` is the stage id, so it shares the entry of the
# `generate_chapter` method -- but the error message always names the
# method, because that is what the caller called.
FAILURE_TARGETS: dict[str, str] = {
    "create_mission": "create_mission",
    "create_blueprint": "create_blueprint",
    "plan_research": "plan_research",
    "curate_research": "curate_research",
    "generation": "generate_chapter",
    "generate_chapter": "generate_chapter",
    "humanize": "humanize",
    "semantic_review": "semantic_review",
    "extract_continuity": "extract_continuity",
    "plan_repair": "plan_repair",
    "present_output": "present_output",
}

# The demo blueprint plans at most four chapters, so four titles are enough.
DEMO_CHAPTER_TITLES = ("课程导览", "核心概念", "动手实践", "回顾与练习")


def _render_value(value: object) -> str:
    """Render an intake value as markdown.

    The intake payload carries free-form values: a string stays as it is, a
    list becomes a bullet list.
    """
    if isinstance(value, list):
        return "\n".join(f"- {item}" for item in value)
    return str(value)


class FakeProvider:
    """A deterministic, offline implementation of the `CourseAgent` protocol."""

    name = "fake"

    def __init__(self, fail_at: str | None = None) -> None:
        if fail_at is not None and fail_at not in FAILURE_TARGETS:
            raise ValueError(
                f"Unknown fail_at {fail_at!r}; "
                f"expected one of {sorted(FAILURE_TARGETS)}."
            )
        self.fail_at = fail_at

    def _fails_at(self, method_name: str) -> bool:
        """Whether the injected failure targets `method_name`."""
        if self.fail_at is None:
            return False
        return FAILURE_TARGETS[self.fail_at] == method_name

    def _raise_if_failing(self, method_name: str) -> None:
        """Raise the injected failure for `method_name`."""
        if self._fails_at(method_name):
            raise RuntimeError(f"FakeProvider failed at {method_name}.")

    def create_mission(self, request: dict) -> MissionOutput:
        """Turn the intake request into a structured mission."""
        self._raise_if_failing("create_mission")
        title = request["title"]
        markdown = "\n".join(
            [
                f"# {title}：课程任务定义",
                "",
                "## 目标受众",
                "",
                _render_value(request["audience"]),
                "",
                "## 学习成果",
                "",
                _render_value(request["goals"]),
                "",
                "## 内容范围",
                "",
                _render_value(request["scope"]),
                "",
                "## 来源政策",
                "",
                _render_value(request["source_policy"]),
                "",
                "## 交付与审核",
                "",
                "本任务定义由 Fake Provider 演示生成，交付与审核由用户决定。",
                "",
            ]
        )
        return MissionOutput(
            mission_markdown=markdown,
            assumptions=["Fake Provider 演示输出"],
        )

    def create_blueprint(self, request: dict, mission: str) -> BlueprintOutput:
        """Plan the modules and chapters that fulfil the mission."""
        self._raise_if_failing("create_blueprint")
        title = request["title"]
        # The demo never plans more than four chapters: the fake is a
        # workflow probe, not a course outline.
        count = min(int(request.get("preferred_chapter_count", 4)), 4)
        module = ModulePlan(
            title="模块一：Fake Provider 演示模块",
            goal=f"完成《{title}》的 Fake Provider 演示内容。",
            narrative="本模块用于在没有真实 Provider 时验证工作流的结构与产物。",
            chapters=[self._demo_chapter(index, count) for index in range(count)],
        )
        return BlueprintOutput(
            course_title=title,
            modules=[module],
            design_notes=[
                "Fake Provider 仅用于本地演示，真实内容生成需要配置模型 Provider"
            ],
        )

    def _demo_chapter(self, index: int, count: int) -> ChapterPlan:
        """Build the demo chapter at `index` of a `count` chapters blueprint."""
        number = index + 1
        title = f"第 {number} 章：{DEMO_CHAPTER_TITLES[index]}"
        prerequisites: list[str] = []
        continuity_out: list[str] = []
        if index > 0:
            prerequisites = [f"第 {number - 1} 章：{DEMO_CHAPTER_TITLES[index - 1]}"]
        if index + 1 < count:
            continuity_out = [f"第 {number + 1} 章：{DEMO_CHAPTER_TITLES[index + 1]}"]
        return ChapterPlan(
            number=number,
            title=title,
            learning_outcome=(
                f"理解「{DEMO_CHAPTER_TITLES[index]}」的核心内容并完成一次练习。"
            ),
            prerequisites=prerequisites,
            continuity_in=list(prerequisites),
            continuity_out=continuity_out,
            learning_path=["概念导入", "要点讲解", "动手练习"],
            template_modules=["章节导入", "概念讲解", "小结与练习"],
        )

    def plan_research(self, request: dict, mission: str) -> ResearchPlanOutput:
        """Plan which sources have to be researched for the course."""
        self._raise_if_failing("plan_research")
        title = request["title"]
        return ResearchPlanOutput(
            queries=[f"{title} official documentation"],
            search_rationale=(
                "Fake Provider 只安排一次官方文档检索，用于演示研究环节的输入输出形状。"
            ),
        )

    def curate_research(self, policy: str, candidates: dict) -> ResearchCurationOutput:
        """Select and structure the research candidates under the source policy."""
        self._raise_if_failing("curate_research")
        results = candidates.get("results", [])
        if not results:
            return ResearchCurationOutput(
                sources=[],
                notes=["未获得可用网页候选。"],
            )
        first = results[0]
        source = CuratedSource(
            title=first.get("title") or "检索结果",
            url=first.get("url", ""),
            reason=f"Fake Provider 按来源政策「{policy}」选取的第一条候选。",
            source_type="official",
        )
        return ResearchCurationOutput(sources=[source])

    def generate_chapter(self, context: dict) -> str:
        """Write one chapter from its context pack."""
        self._raise_if_failing("generate_chapter")
        chapter = context["chapter"]
        title = chapter["title"]
        lines = [
            f"# {title}",
            "",
            "## 本章任务",
            "",
            chapter["learning_outcome"],
            "",
            "## 本章内容",
            "",
            f"Fake Provider 为《{title}》生成的演示正文。",
            "",
        ]
        continuity_in = chapter.get("continuity_in") or []
        continuity_out = chapter.get("continuity_out") or []
        if continuity_in:
            lines += ["## 承接上文", "", *[f"- {item}" for item in continuity_in], ""]
        if continuity_out:
            lines += ["## 铺垫下文", "", *[f"- {item}" for item in continuity_out], ""]
        return "\n".join(lines)

    def humanize(self, markdown: str) -> HumanizerOutput:
        """Rewrite the chapter into student-facing prose."""
        if self._fails_at("humanize"):
            # The only degraded tier: a low but valid grade, so the quality
            # loop has something to react to.
            return HumanizerOutput(
                revised_markdown=markdown,
                score=30,
                issues=["Fake Provider 故意返回低分，用于触发质量闭环。"],
            )
        return HumanizerOutput(revised_markdown=markdown, score=47, issues=[])

    def semantic_review(self, markdown: str, context: dict) -> SemanticReviewOutput:
        """Review the chapter for meaning, coverage and correctness."""
        self._raise_if_failing("semantic_review")
        return SemanticReviewOutput(
            score=90,
            decision="ready",
            issues=[],
            strengths=["Fake Provider 的演示章节结构完整，可以进入下一步。"],
        )

    def extract_continuity(self, markdown: str, context: dict) -> ContinuityOutput:
        """Extract the continuity facts the next chapter has to respect."""
        self._raise_if_failing("extract_continuity")
        chapter = context.get("chapter") or {}
        return ContinuityOutput(
            summary=chapter.get("learning_outcome", "Fake Provider 章节"),
            established_facts=["本章的 Fake Provider 演示内容已完成。"],
            bridge_to_next=list(chapter.get("continuity_out", [])),
        )

    def plan_repair(
        self,
        task: dict,
        markdown: str,
        context: dict,
    ) -> RepairCapabilityPlan:
        """Plan how a failed chapter is repaired."""
        self._raise_if_failing("plan_repair")
        return RepairCapabilityPlan(
            task_id=str(task.get("id", "fake")),
            selected_capabilities=["teaching_scaffold"],
            target_anchors=["## 本章任务"],
            reasoning_summary="Fake Provider 只使用教学脚手架级别的返工能力。",
            verification_plan=["复核返工后的章节任务与学习成果是否一致。"],
        )

    def present_output(self, step: str, label: str, output: dict) -> OutputPresentation:
        """Present a workflow step result to the user."""
        self._raise_if_failing("present_output")
        # `step` has no special branch in Phase 1: the presentation of a
        # stage result is the same for every stage.
        highlights = [f"产出字段：{key}" for key in list(output)[:5]]
        return OutputPresentation(
            headline=f"{label}已完成",
            conclusion=f"Fake Provider 已生成 {label} 的 {len(output)} 个产出字段。",
            highlights=highlights,
            metrics={"产出字段数": len(output)},
            next_action="请确认本阶段产出后再进入下一步。",
        )
