from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, TypeVar

from pydantic import BaseModel

from app.agents.context import (
    _CORE_WORKSPACE_LIMIT, _LARGE_WORKSPACE_LIMIT, _NOTES_WORKSPACE_LIMIT,
    _HUMANIZER_PROTOCOL, _audit_workspace_projection, _clip_text,
    _ground_repair_verifications, _ground_semantic_issues, _planning_request,
    _semantic_review_context, _teaching_skill_packet, _workspace_projection,
)
from app.providers.protocols import ModelTransport
from app.observability.context import current_trace, current_invocation_metrics, set_invocation_metrics
from app.observability.tracing import finish_span, start_span
from app.observability.budget import record_model_usage
from app.schemas import (
    BlueprintOutput, ContinuityOutput, HumanizerPatchOutput, HumanizerOutput, MissionOutput,
    OutputPresentation, ResearchCurationOutput, ResearchPlanOutput, RepairCapabilityPlan,
    RepairPatchOutput, ReferenceSectionDecision, SectionRewriteOutput, SemanticReviewOutput,
    WorkspaceConsistencyOutput, WorkspaceRevisionOutput,
)

OutputT = TypeVar("OutputT", bound=BaseModel)

class CourseAgentRuntime:
    """Course-specific Agent runtime built on a generic model transport."""

    def __init__(self, transport: ModelTransport) -> None:
        self.transport = transport
        self.settings = transport.settings
        self.name = transport.name

    def _structured(
        self,
        schema: type[OutputT],
        prompt: str,
        **kwargs: Any,
    ) -> OutputT:
        return self._measured_invoke("结构化模型调用", lambda: self.transport.invoke_structured(schema, prompt, **kwargs))

    def _measured_invoke(self, operation: str, callback):
        trace = current_trace()
        if not trace:
            return callback()
        span = start_span(trace.run_id, kind="model", name=operation, stage=trace.stage, attributes={"provider": self.name, "operation": operation})
        set_invocation_metrics(None)
        try:
            value = callback()
        except Exception as exc:
            metrics = current_invocation_metrics()
            if metrics:
                record_model_usage(trace.run_id, span["id"], metrics, stage=trace.stage)
            finish_span(span["id"], "FAILED", error=exc)
            raise
        metrics = current_invocation_metrics()
        if metrics:
            record_model_usage(trace.run_id, span["id"], metrics, stage=trace.stage)
            finish_span(span["id"], "SUCCEEDED", attributes={"provider": metrics.provider, "model": metrics.model, "input_tokens": metrics.input_tokens, "output_tokens": metrics.output_tokens, "total_tokens": metrics.total_tokens, "response_status": metrics.response_status})
        else:
            finish_span(span["id"], "SUCCEEDED")
        return value

    def _invoke_with_hard_timeout(
        self,
        operation: str,
        callback,
        *,
        timeout_seconds: int | None = None,
    ):
        del operation, timeout_seconds
        return callback()

    def create_mission(self, request: dict) -> MissionOutput:
        return self._structured(
            MissionOutput,
            "你是课程产品负责人。根据输入写出具体、可验收的中文课程 MISSION.md。"
            "必须覆盖受众、学习成果、范围、前置、交付、来源政策、人工闸门和成功标准。"
            "不要写宣传口号。若输入含全局变更请求，最新请求优先于旧任务和当前工作区内容；"
            "必须把技术路线、章节数量和范围等变更写成新的唯一事实，不得保留旧方案。"
            "输入：\n" + json.dumps(_planning_request(request), ensure_ascii=False, indent=2),
            max_output_tokens=self.settings.llm_mission_max_output_tokens,
        )

    def revise_workspace(self, revision: dict) -> WorkspaceRevisionOutput:
        workspace = revision.get("workspace") if isinstance(revision, dict) else {}
        safe_workspace = _workspace_projection(
            workspace,
            {
                "MISSION.md": _CORE_WORKSPACE_LIMIT,
                "COURSE-GENERATION-SPEC.md": _CORE_WORKSPACE_LIMIT,
                "RESOURCES.md": _LARGE_WORKSPACE_LIMIT,
                "NOTES.md": _NOTES_WORKSPACE_LIMIT,
                "COURSE-BLUEPRINT.md": _CORE_WORKSPACE_LIMIT,
            },
        )
        revision_input = {
            "feedback": str(revision.get("feedback") or "").strip(),
            "workspace": safe_workspace,
        }
        return self._structured(
            WorkspaceRevisionOutput,
            "你是课程工作区增量修订 Agent。基于已确认的 Workspace 和本轮用户要求，"
            "只输出最小、可验证的跨文件补丁计划，不得重写完整课程任务定义。"
            "patches 中每条 original 必须逐字摘自对应文件且只出现一次；只列真正受影响的文件。"
            "MISSION.md 与 COURSE-GENERATION-SPEC.md 可以定向替换；"
            "RESOURCES.md 和 NOTES.md 的 replacement 必须保留 original 并在其后追加内容，"
            "不得删除用户资料或既有迭代记录。COURSE-BLUEPRINT.md 只有存在且确受影响时才修改。"
            "如果用户要求改变章节数量或来源政策，分别填写 preferred_chapter_count 或 source_policy。"
            "输入：\n"
            + json.dumps(revision_input, ensure_ascii=False, indent=2),
            hard_timeout_seconds=self.settings.llm_long_content_hard_timeout_seconds,
            # A reasoning-capable Gateway spends this shared budget on both
            # internal reasoning and the final JSON. Revisions therefore use
            # the normal long-output ceiling instead of a small patch budget.
            max_output_tokens=self.settings.llm_max_output_tokens,
            reasoning_effort="low",
            transport_timeout_seconds=self.settings.llm_long_content_hard_timeout_seconds,
        )

    def _blueprint_planning_structured(
        self,
        schema: type[OutputT],
        prompt: str,
    ) -> OutputT:
        """Use one high-reasoning, long-running profile for blueprint work."""
        return self._structured(
            schema,
            prompt,
            hard_timeout_seconds=self.settings.llm_long_content_hard_timeout_seconds,
            max_output_tokens=self.settings.llm_max_output_tokens,
            transport_timeout_seconds=self.settings.llm_long_content_hard_timeout_seconds,
        )

    def _long_writing_model(self):
        """Expose the old text-model shape while delegating to ModelTransport."""

        transport = self.transport
        settings = self.settings

        class LongWritingModel:
            def invoke(self, prompt: str) -> SimpleNamespace:
                content = self_outer._measured_invoke("章节正文生成", lambda: transport.invoke_text(
                    "章节正文生成", prompt, hard_timeout_seconds=settings.llm_long_content_hard_timeout_seconds,
                    max_output_tokens=settings.llm_chapter_max_output_tokens,
                    transport_timeout_seconds=settings.llm_long_content_hard_timeout_seconds,
                ))
                return SimpleNamespace(content=content)

        self_outer = self
        return LongWritingModel()

    def create_blueprint(self, request: dict, mission: str) -> BlueprintOutput:
        return self._blueprint_planning_structured(
            BlueprintOutput,
            "你是严格执行 teach-generator 的教材架构师。根据任务和 MISSION 设计模块化课程蓝图。"
            "先按学习成果与知识依赖设计每章自己的学习路径，再选择一个正文主类型："
            "opening_closing、environment、language、framework、mechanism 或 integrated_practice。"
            "不要把任一模板目录当成课程目录；每章只能有一个主类型，必要时可在 design_notes 记录辅助模块。"
            "模块按能力台阶、先修与叙事连续性划分，不机械平均章节。每章必须写清成果、先修、承接、交付后续，"
            "并输出 pedagogy_type、primary_teaching_task、instructor_voice、learning_path 与 template_modules："
            "learning_path 记录本章自己的认知或操作推进，template_modules 只列实际借用的模板模块；"
            "标题、成果与顺序必须能让零基础读者逐步建立能力。"
            "全局变更请求与 MISSION 中确认的技术路线是唯一依据；不得沿用旧蓝图中的框架、"
            "章节数或模块范围。"
            f"\n任务：{json.dumps(_planning_request(request, include_resources=True), ensure_ascii=False)}"
            f"\nMISSION：\n{_clip_text(mission, _CORE_WORKSPACE_LIMIT)}",
        )

    def plan_research(self, request: dict, mission: str) -> ResearchPlanOutput:
        return self._blueprint_planning_structured(
            ResearchPlanOutput,
            "你是课程资料研究员。为即将制作的课程制定公开资料检索计划。"
            "给出 2-6 条简洁英文或中文检索词，覆盖：核心概念、课程实际使用的框架/API、"
            "相关标准或论文，以及项目需要时的安全/部署资料；优先定位官方文档、标准、论文和维护方教程。"
            "不要编造 URL，不要把检索计划当成资料清单。"
            f"\n课程任务：{json.dumps(_planning_request(request, include_resources=True), ensure_ascii=False)}"
            f"\nMISSION：\n{_clip_text(mission, _CORE_WORKSPACE_LIMIT)}",
        )

    def curate_research(self, policy: str, candidates: dict) -> ResearchCurationOutput:
        return self._blueprint_planning_structured(
            ResearchCurationOutput,
            "你是课程资料审校员。只能从给定的网页候选中筛选资料，绝不可编造 URL。"
            "每条资料说明它将支持课程中的什么事实、API 或实践，并优先覆盖每一个核心模块，"
            "而不是堆砌同一主题的链接。"
            "若来源政策要求官方资料，只选择官方文档、标准、论文或维护方材料；"
            "只有明确允许时才选择社区资料。候选不足时如实返回空列表并说明缺口。"
            "每条来源 reason 不超过 160 字，sources 最多 16 条。"
            f"\n来源政策：{policy}\n网页候选：{_clip_text(json.dumps(candidates, ensure_ascii=False), 24000)}",
        )

    def audit_workspace_consistency(
        self,
        mission: str,
        blueprint: dict,
        workspace: dict,
        change_requests: list[dict],
    ) -> WorkspaceConsistencyOutput:
        return self._blueprint_planning_structured(
            WorkspaceConsistencyOutput,
            "你是课程生产系统的一致性审校员。检查任务定义、课程蓝图、生成规格、"
            "课程元数据、生成计划和自动检索资料，是否都落实了全部全局变更请求。"
            "尤其检查技术路线、章节数量、模块范围与来源政策是否残留旧版本。"
            "只有所有受控文件一致时才返回 pass；否则返回 repair，并给出可执行问题。"
            "不要把用户补充资料中的历史链接误判为课程技术路线。"
            f"\n全局变更请求：{json.dumps(change_requests, ensure_ascii=False)}"
            f"\nMISSION：\n{_clip_text(mission, _CORE_WORKSPACE_LIMIT)}"
            f"\n蓝图：{_clip_text(json.dumps(blueprint, ensure_ascii=False), _CORE_WORKSPACE_LIMIT)}"
            f"\n受控工作区文件：{json.dumps(_audit_workspace_projection(workspace), ensure_ascii=False)}",
        )

    def generate_chapter(self, context: dict) -> str:
        skill_packet = _teaching_skill_packet(context)
        model = self._long_writing_model()
        response = self._invoke_with_hard_timeout(
            "章节正文生成",
            lambda: model.invoke(
                "你是中文技术课程讲师和责任编辑。你必须严格依照后附的 teach-generator 写作契约，"
                "而非套用通用教程套路，创作一章可直接交付给学生的 Markdown 正文。\n\n"
                "写作顺序：先从 Context Pack 中提取学习成果、受众起点、前后章承接、批准来源和上轮反馈；"
                "设计一条自己的认知/操作路径；再有选择地使用本章模板模块。至少讲透一个核心问题，"
                "所有示例、操作、图和练习都要给出可观察结果或判断标准。不能靠罗列 API、堆代码、"
                "重复总结或文末凑字数制造篇幅。\n\n"
                "输出限制：只输出完整 Markdown 正文；首行使用一级章节标题，章首只保留预计学习时间和"
                "一句话总结；引用只使用已批准资源并贴近其支撑的断言；末尾给出本章实际使用的参考文献。"
                "绝不写生成过程、评分、工作区、模板或对话提示。\n\n"
                + skill_packet
                + "\n\n# Context Pack（唯一事实与课程约束）\n"
                + json.dumps(context, ensure_ascii=False, indent=2)
            ),
            timeout_seconds=self.settings.llm_long_content_hard_timeout_seconds,
        )
        return str(response.content)

    def humanize(self, markdown: str) -> HumanizerOutput:
        # Returning an entire long chapter inside structured JSON makes a
        # thinking-capable model spend its completion budget on both reasoning
        # and JSON escaping. Ask for precise prose patches instead, then apply
        # them locally. Code blocks, links and unaffected teaching sections
        # remain byte-for-byte intact.
        result = self._structured(
            HumanizerPatchOutput,
            "你是 humanizer-zh 的中文技术课程编辑。审阅下列 Markdown，只返回少量、可精确"
            "定位的散文改写补丁；不要重写整章，不要修改代码块、URL、术语标记、数字或标题结构。"
            "每个 patches.original 必须是正文中连续出现的原文，replacement 是替换后的自然表达。"
            "最多 14 个补丁；若无需修改，patches 返回空数组。\n\n"
            + _HUMANIZER_PROTOCOL
            + "\n\n# 待编辑 Markdown\n"
            + markdown,
            hard_timeout_seconds=self.settings.llm_humanizer_hard_timeout_seconds,
            max_output_tokens=self.settings.llm_semantic_review_max_output_tokens,
            transport_timeout_seconds=self.settings.llm_humanizer_hard_timeout_seconds,
        )
        revised = markdown
        applied = 0
        for patch in result.patches:
            # Exact, single replacements make a malformed model patch harmless
            # and prevent a repeated phrase from changing unrelated sections.
            if patch.original in revised:
                revised = revised.replace(patch.original, patch.replacement, 1)
                applied += 1
        issues = list(result.issues)
        if len(result.patches) != applied:
            issues.append(f"{len(result.patches) - applied} 个 Humanizer 补丁未命中原文，已跳过")
        return HumanizerOutput(
            revised_markdown=revised,
            score=result.score,
            issues=issues,
        )

    def semantic_review(self, markdown: str, context: dict) -> SemanticReviewOutput:
        review_context = _semantic_review_context(context)
        result = self._structured(
            SemanticReviewOutput,
            "你是 teach-generator 第二阶段课程评价量规审校员。独立审校实际章节，不能相信作者自述。"
            "先查 blocker：关键断言无可核验来源、引用不支持断言、核心学习成果遗漏、错误示例/操作、"
            "初学者无法跨越的前置断层、Humanizer 改坏事实/代码/引用、审校材料不足。任一 blocker 必须 reject。"
            "然后按量规六维评分：学习目标与覆盖 20，事实与证据 25，受众适配与脚手架 15，"
            "解释深度与连贯性 15，练习与反馈 15，语言与教师感 10。ready 的条件是总分>=85、"
            "每维至少 3、没有 blocker/major、Humanizer>=45；70-84 或存在 major 是 manual_review；"
            "低于70或任一维度为0是 reject。issues 中每条必须严格使用“[级别] 问题 | 证据：『正文中"
            "连续出现的原文片段』 | 建议：...”格式；证据必须逐字来自本章，不得把推测、历史问题或"
            "其他章节内容写成问题。没有可逐字引用证据时，不得输出该 issue。"
            "提出定向修订建议；不得给笼统的“扩写”“更自然”。"
            "审校输出必须简洁：最多 8 条 issues、4 条 strengths；每条不超过 120 字。"
            "如果审校上下文包含 active_repair_tasks，必须在 repair_verifications 中逐项验证其成功判据："
            "resolved=true 必须引用修复后新增或变化的正文作为 evidence_excerpt；原问题中的触发句、"
            "练习要求或待补充断言只能证明任务来源，不能证明缺口仍然存在或已经解决。若目标已经解决，"
            "不得在 issues 中原样重复该问题。不要为没有列出的任务虚构验证结果。"
            f"\n审校上下文：{json.dumps(review_context, ensure_ascii=False)}"
            f"\n正文：\n{markdown}",
            hard_timeout_seconds=self.settings.llm_semantic_review_hard_timeout_seconds,
            max_output_tokens=self.settings.llm_semantic_review_max_output_tokens,
        )
        grounded_issues = _ground_semantic_issues(markdown, result.issues)
        active_tasks = list(review_context.get("active_repair_tasks") or [])
        grounded_verifications = _ground_repair_verifications(
            markdown, active_tasks, result.repair_verifications
        )
        resolved_issue_texts = {
            str(task.get("issue") or "")
            for task in active_tasks
            if grounded_verifications.get(str(task.get("id") or ""), {}).get("resolved")
        }
        grounded_issues = [
            issue for issue in grounded_issues if issue not in resolved_issue_texts
        ]
        # An ungrounded finding is not repair evidence.  Treat a verdict with
        # no remaining verifiable findings as ready so it cannot create an
        # infinite repair loop around a claim that is absent from the chapter.
        decision = result.decision if grounded_issues else "ready"
        ignored_count = len(result.issues) - len(grounded_issues)
        return SemanticReviewOutput(
            score=result.score,
            decision=decision,
            issues=grounded_issues,
            strengths=[
                *result.strengths,
                *(
                    [f"已忽略 {ignored_count} 条缺少有效证据或已由定向验证核销的审校结论。"]
                    if ignored_count else []
                ),
            ],
            repair_verifications=list(grounded_verifications.values()),
        )

    def extract_continuity(self, markdown: str, context: dict) -> ContinuityOutput:
        return self._structured(
            ContinuityOutput,
            "从已生成章节提取供后续章节使用的连续性账本。只记录正文实际建立的内容："
            "短摘要、已定义术语、已建立事实、尚未闭合的问题、下一章需要承接的桥接点。"
            "不要复制整章，不要加入正文没有的结论。"
            "summary 不超过 500 字；每个列表最多 8 项、每项不超过 100 字。"
            f"\n章节计划：{json.dumps(context.get('chapter', {}), ensure_ascii=False)}"
            f"\n正文：\n{markdown}",
            hard_timeout_seconds=self.settings.llm_continuity_hard_timeout_seconds,
            max_output_tokens=self.settings.llm_continuity_max_output_tokens,
        )

    def revise_chapter(self, markdown: str, context: dict) -> str:
        skill_packet = _teaching_skill_packet(context)
        model = self._long_writing_model()
        response = self._invoke_with_hard_timeout(
            "章节定向修订",
            lambda: model.invoke(
                "你是严格执行 teach-generator 的中文技术课程责任编辑。根据明确的质量证据定向修订 Markdown。"
                "保留已达标段落、正确事实、代码、术语和引用；只修复被指出的段落、前置、示例、边界、"
                "练习或承接，绝不把一章重排成通用模板。修改后保持本章正文类型的教学路径和可观察完成证据。"
                "返回完整 Markdown，不附解释，不暴露内部质量流程。\n\n"
                + skill_packet
                + f"\n上下文：{json.dumps(context, ensure_ascii=False, indent=2)}"
                + f"\n原文：\n{markdown}"
            ),
            timeout_seconds=self.settings.llm_long_content_hard_timeout_seconds,
        )
        return str(response.content)

    def enrich_chapter(self, markdown: str, context: dict, issues: list[str]) -> str:
        """A dedicated content-depth pass; it expands missing teaching layers, not filler."""
        model = self._long_writing_model()
        response = self._invoke_with_hard_timeout(
            "章节内容丰富化",
            lambda: model.invoke(
                "你是技术课程内容丰富化 Agent。仅根据质量证据，在原有 Markdown 的恰当位置补齐"
                "缺失的教学层：最小前置、概念/机制解释、短小可观察示例、反例或边界、练习与反馈。"
                "不要在文末堆砌总结、泛泛案例、重复段落或无关 API；保留正确内容、代码、链接和章节结构。"
                "必须让补充内容服务学习成果，并达到课程规定的有效内容体量。返回完整 Markdown，不附说明。"
                + _teaching_skill_packet(context)
                + f"\n\n质量证据：{json.dumps(issues, ensure_ascii=False)}"
                + f"\n\nContext Pack：{json.dumps(context, ensure_ascii=False, indent=2)}"
                + f"\n\n原文：\n{markdown}"
            ),
            timeout_seconds=self.settings.llm_long_content_hard_timeout_seconds,
        )
        return str(response.content)

    def plan_repair(self, task: dict, markdown: str, context: dict) -> RepairCapabilityPlan:
        excerpt = markdown[:12000]
        return self._structured(
            RepairCapabilityPlan,
            "你是课程质量 RepairTask 规划 Agent。只规划当前证据对应的最小修改，不输出正文。"
            "可用能力：markdown_format、link_reference、code_structure、teaching_scaffold、"
            "source_contract、content_enrichment、humanizer、section_rewrite、chapter_rewrite。"
            "除非原任务明确需要重构，否则 scope 必须是 paragraph 或 section；不能选择 chapter_rewrite。"
            "target_anchors 必须逐字来自正文，每项不超过 180 字。验证计划必须能核验成功判据。"
            f"\n任务：{json.dumps(task, ensure_ascii=False)}\n上下文：{json.dumps(context, ensure_ascii=False)}\n正文节选：\n{excerpt}",
            hard_timeout_seconds=self.settings.llm_semantic_review_hard_timeout_seconds,
            max_output_tokens=self.settings.llm_semantic_review_max_output_tokens,
        )

    def apply_repair_patch(self, task: dict, markdown: str, context: dict, plan: RepairCapabilityPlan) -> RepairPatchOutput:
        result = self._structured(
            RepairPatchOutput,
            "你是课程质量局部修复 Agent。只返回锚点范围内的原文替换补丁，不能返回整章。"
            "每个 original 必须逐字来自当前正文；replacement 只解决本 RepairTask 的成功判据，保留其余结构、代码、引用与术语。"
            f"\n任务：{json.dumps(task, ensure_ascii=False)}\n计划：{plan.model_dump_json()}\n正文：\n{markdown}",
            hard_timeout_seconds=self.settings.llm_long_content_hard_timeout_seconds,
            max_output_tokens=self.settings.llm_semantic_review_max_output_tokens,
        )
        if result.task_id != str(task.get("id", "")):
            raise ValueError("RepairPatchOutput task_id 与当前 RepairTask 不一致")
        # The graph owns the recovery policy for a stale/missing anchor. A
        # model patch mismatch is a task-level outcome, never a reason to
        # abort the whole quality queue before other chapters can be handled.
        return result

    def classify_reference_section(
        self, diagnostic: dict, candidates: list[dict], context: dict
    ) -> ReferenceSectionDecision:
        result = self._structured(
            ReferenceSectionDecision,
            "你是 Markdown 区块角色识别 Agent。标题使用开放词汇，不能依赖固定同义词表或正则。"
            "请结合二级标题在章节中的位置、其后直到下一个二级标题的节点类型、链接数量和内容节选，"
            "判断哪个候选承担本章参考资料/来源清单的语义角色。不要输出或改写 Markdown；证据不足时返回 ambiguous。"
            f"\n结构诊断：{json.dumps(diagnostic, ensure_ascii=False)}"
            f"\n候选区块：{json.dumps(candidates, ensure_ascii=False)}"
            f"\n课程上下文：{json.dumps(context, ensure_ascii=False)}",
            hard_timeout_seconds=self.settings.llm_semantic_review_hard_timeout_seconds,
            max_output_tokens=self.settings.llm_semantic_review_max_output_tokens,
        )
        candidate_ids = {str(item.get("node_id") or item.get("nodeId") or "") for item in candidates}
        if result.node_id is not None and result.node_id not in candidate_ids:
            raise ValueError("参考文献角色识别返回了候选集合之外的节点")
        if result.role == "references" and not result.node_id:
            raise ValueError("参考文献角色识别缺少候选节点")
        return result

    def rewrite_section(
        self, task: dict, markdown: str, context: dict, *, expected_hash: str
    ) -> SectionRewriteOutput:
        result = self._structured(
            SectionRewriteOutput,
            "你是课程结构修复的纯 LLM 小节兜底 Agent。只有确定性 AST 修复和锚点补丁失败后才调用你。"
            "只重写一个与当前 RepairTask 直接相关的完整小节；original_section 必须逐字存在于正文，"
            "replacement_section 保留该小节正确事实、代码、链接和教学内容，不得触碰其他小节或整章。"
            f"\nRepairTask：{json.dumps(task, ensure_ascii=False)}"
            f"\n期望源哈希：{expected_hash}"
            f"\n课程上下文：{json.dumps(context, ensure_ascii=False)}"
            f"\n当前正文：\n{markdown}",
            hard_timeout_seconds=self.settings.llm_long_content_hard_timeout_seconds,
            max_output_tokens=self.settings.llm_semantic_review_max_output_tokens,
        )
        if result.task_id != str(task.get("id") or ""):
            raise ValueError("小节重写 task_id 与当前 RepairTask 不一致")
        if result.expected_hash != expected_hash:
            raise ValueError("小节重写基于过期的源文件哈希")
        if result.original_section not in markdown:
            raise ValueError("小节重写锚点未命中当前正文")
        return result

    def present_output(
        self,
        step: str,
        label: str,
        output: dict,
    ) -> OutputPresentation:
        return self._structured(
            OutputPresentation,
            "你是课程生产系统的结果解读 Agent。把节点原始输出整理成用户可快速阅读的"
            "展示摘要。保留结论、关键产物、指标、问题和下一步；不得虚构原始输出中"
            "不存在的事实。不要复述完整 JSON。输入可能带有"
            "__presentation_projection__ 标记或“展示摘要已省略”提示：这只表示给你的"
            "摘要输入被有意压缩，绝不能据此声称原始模型输出被截断、内容缺失或需要关注。"
            f"\n节点：{step} / {label}"
            f"\n原始输出：{json.dumps(output, ensure_ascii=False, default=str)}",
            max_output_tokens=self.settings.llm_presentation_max_output_tokens,
        )
