from __future__ import annotations

from app.schemas import (
    BlueprintOutput, ChapterPlan, ContinuityOutput, HumanizerOutput, MissionOutput, ModulePlan,
    OutputPresentation, ResearchCurationOutput, ResearchPlanOutput, RepairCapabilityPlan,
    RepairPatchOutput, ReferenceSectionDecision, SectionRewriteOutput, SemanticReviewOutput,
    WorkspaceConsistencyOutput, WorkspaceRevisionOutput,
)

class FakeProvider:
    name = "fake"

    def create_mission(self, request: dict) -> MissionOutput:
        markdown = (
            f"# {request['title']}：课程任务定义\n\n"
            f"## 目标受众\n\n{request['audience']}\n\n"
            f"## 学习成果\n\n{request['goals']}\n\n"
            f"## 内容范围\n\n{request['scope']}\n\n"
            f"## 来源政策\n\n{request['source_policy']}\n\n"
            "## 交付与审核\n\n交付 Markdown 与 HTML。蓝图、批次和发布均由用户确认。\n"
        )
        return MissionOutput(
            mission_markdown=markdown, assumptions=["Fake Provider 演示输出"]
        )

    def revise_workspace(self, revision: dict) -> WorkspaceRevisionOutput:
        workspace = revision.get("workspace", {})
        mission = str(workspace.get("MISSION.md", ""))
        marker = mission.strip().splitlines()[-1] if mission.strip() else "# 课程 MISSION"
        return WorkspaceRevisionOutput(
            change_summary="Fake Provider 已记录本次 Workspace 增量修订。",
            patches=[
                {
                    "path": "MISSION.md",
                    "original": marker,
                    "replacement": marker + "\n\n> 本次增量要求已记录，待后续蓝图同步。",
                    "reason": "验证 Workspace 补丁链路",
                }
            ],
            downstream_impacts=["课程蓝图"],
        )

    def create_blueprint(self, request: dict, mission: str) -> BlueprintOutput:
        count = min(int(request.get("preferred_chapter_count", 4)), 4)
        chapters = [
            ChapterPlan(
                number=index,
                title=f"第 {index} 章：示例学习任务",
                learning_outcome=f"完成第 {index} 个可观察学习成果",
                prerequisites=[] if index == 1 else [f"第 {index - 1} 章"],
                continuity_in=[] if index == 1 else [f"承接第 {index - 1} 章结论"],
                continuity_out=[] if index == count else [f"为第 {index + 1} 章准备概念"],
            )
            for index in range(1, count + 1)
        ]
        return BlueprintOutput(
            course_title=request["title"],
            modules=[
                ModulePlan(
                    title="模块一：Fake Provider 演示模块",
                    goal="验证本地工作流、审批和持久状态",
                    narrative="从任务定义推进到可审阅章节",
                    chapters=chapters,
                )
            ],
            design_notes=["真实内容生成请配置 DeepSeek"],
        )

    def plan_research(self, request: dict, mission: str) -> ResearchPlanOutput:
        return ResearchPlanOutput(
            queries=[f"{request['title']} official documentation"],
            search_rationale="Fake Provider 用于验证资料检索节点。",
        )

    def curate_research(self, policy: str, candidates: dict) -> ResearchCurationOutput:
        results = candidates.get("results", [])
        if not results:
            return ResearchCurationOutput(notes=["未获得可用网页候选。"])
        first = results[0]
        return ResearchCurationOutput(
            sources=[
                {
                    "title": first["title"] or "检索结果",
                    "url": first["url"],
                    "reason": "用于验证来源写入和课程上下文。",
                    "source_type": "official",
                }
            ]
        )

    def audit_workspace_consistency(
        self,
        mission: str,
        blueprint: dict,
        workspace: dict,
        change_requests: list[dict],
    ) -> WorkspaceConsistencyOutput:
        return WorkspaceConsistencyOutput(
            decision="pass",
            canonical_requirements=["Fake Provider 跳过语义一致性审校。"],
        )

    def generate_chapter(self, context: dict) -> str:
        chapter = context["chapter"]
        return (
            f"# {chapter['title']}\n\n"
            "> 预计学习时间：30 分钟\n"
            "> 一句话总结：使用 Fake Provider 验证章节生成与质量流程。\n\n"
            "## 本章任务\n\n"
            f"{chapter['learning_outcome']}。\n\n"
            "## 连续性说明\n\n"
            f"本章输入：{', '.join(chapter.get('continuity_in', [])) or '课程起点'}。\n\n"
            f"本章输出：{', '.join(chapter.get('continuity_out', [])) or '模块收束'}。\n\n"
            "## 练习\n\n记录当前工作流节点，并确认页面刷新后状态没有丢失。\n\n"
            "## 参考文献\n\n- 本地课程任务定义与课程蓝图。\n"
        )

    def humanize(self, markdown: str) -> HumanizerOutput:
        return HumanizerOutput(revised_markdown=markdown, score=47, issues=[])

    def semantic_review(self, markdown: str, context: dict) -> SemanticReviewOutput:
        return SemanticReviewOutput(
            score=90,
            decision="ready",
            issues=[],
            strengths=["Fake Provider 用于验证状态机，不用于证明真实课程质量"],
        )

    def extract_continuity(self, markdown: str, context: dict) -> ContinuityOutput:
        chapter = context.get("chapter", {})
        return ContinuityOutput(
            summary=chapter.get("learning_outcome", "Fake Provider 章节"),
            established_terms=[],
            established_facts=[chapter.get("learning_outcome", "完成演示")],
            open_loops=[],
            bridge_to_next=chapter.get("continuity_out", []),
        )

    def revise_chapter(self, markdown: str, context: dict) -> str:
        instruction = context.get("instruction", "按要求修订")
        return markdown.rstrip() + f"\n\n<!-- Fake Provider 修订：{instruction} -->\n"

    def enrich_chapter(self, markdown: str, context: dict, issues: list[str]) -> str:
        return markdown.rstrip() + "\n\n## 补充理解与练习\n\n根据本章规则修改一个示例，并解释观察到的结果。\n"

    def plan_repair(self, task: dict, markdown: str, context: dict) -> RepairCapabilityPlan:
        return RepairCapabilityPlan(task_id=str(task.get("id", "fake")), selected_capabilities=["teaching_scaffold"], target_anchors=[markdown[:80] or "正文"], reasoning_summary="Fake Provider 仅验证任务边界。", verification_plan=["检查原始问题是否消失"])

    def apply_repair_patch(self, task: dict, markdown: str, context: dict, plan: RepairCapabilityPlan) -> RepairPatchOutput:
        anchor = plan.target_anchors[0] if plan.target_anchors else markdown[:80]
        return RepairPatchOutput(task_id=str(task.get("id", "fake")), patches=[{"original": anchor, "replacement": anchor + "\n\n补充一个可观察的最小示例。", "reason": "补齐教学脚手架"}])

    def rewrite_section(self, task: dict, markdown: str, context: dict, *, expected_hash: str) -> SectionRewriteOutput:
        return SectionRewriteOutput(
            task_id=str(task.get("id", "fake")), expected_hash=expected_hash,
            original_section=markdown, replacement_section=markdown + "\n\n补充修复。",
            reason="Fake Provider 小节兜底",
        )

    def classify_reference_section(self, diagnostic: dict, candidates: list[dict], context: dict) -> ReferenceSectionDecision:
        candidate = candidates[-1] if candidates else {}
        node_id = candidate.get("node_id") or candidate.get("nodeId")
        return ReferenceSectionDecision(
            role="references" if node_id else "ambiguous", node_id=node_id,
            confidence=0.9 if node_id else 0.0, reason="Fake Provider 根据章末候选返回。",
            recommended_action="canonicalize_heading" if node_id else "human_review",
        )

    def present_output(
        self,
        step: str,
        label: str,
        output: dict,
    ) -> OutputPresentation:
        if step == "quality":
            result = (
                output.get("review_result") or (output.get("batch_results") or [{}])[-1]
            )
            validation = result.get("validation", {})
            chapters = result.get("chapters", [])
            return OutputPresentation(
                headline=f"{label}已完成",
                conclusion=(
                    "确定性检查通过，结果已进入人工确认。"
                    if validation.get("succeeded")
                    else "检查发现问题，需要查看问题清单。"
                ),
                highlights=[
                    f"处理章节：{len(chapters)}",
                    f"作用域：{result.get('scope') or result.get('batch', {}).get('id', '当前课程')}",
                ],
                metrics={
                    "检查通过": bool(validation.get("succeeded")),
                    "章节数": len(chapters),
                },
                issues=[] if validation.get("succeeded") else ["确定性检查未通过"],
                next_action="查看摘要与原始输出后决定批准或停止。",
            )
        return OutputPresentation(
            headline=f"{label}已完成",
            conclusion="节点产物已保存，可以展开查看原始输出。",
            highlights=[f"产出字段：{key}" for key in list(output)[:5]],
            metrics={"产出字段数": len(output)},
            next_action="检查本步产物后继续工作流。",
        )
