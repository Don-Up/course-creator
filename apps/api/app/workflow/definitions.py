"""The seven-stage course generation workflow contract.

The stage ids, their order and their wording are a product contract rather
than an implementation detail: the frontend renders these fields directly.
This module is therefore the single source of truth -- later phases derive
their stage list from `WORKFLOW_STEPS` / `REVIEW_WORKFLOW_STEPS` instead of
repeating the ids, and `STEP_ORDER` / `REVIEW_STEP_ORDER` are derived from
those two lists so the contract is only written down once.
"""

from __future__ import annotations


WORKFLOW_STEPS: list[dict[str, str]] = [
    {
        "id": "intake",
        "title": "课程需求",
        "description": "确认课程目标、受众、范围、来源与交付形式",
        "user_input": "课程名称、受众、学习目标、内容范围、来源政策",
        "model_output": "结构化任务输入与缺失项",
    },
    {
        "id": "mission",
        "title": "任务定义",
        "description": "把课程想法变成可验收的任务",
        "user_input": "补充或修改全局课程要求；内容会同步影响后续所有工作区产物",
        "model_output": "MISSION.md 与假设清单",
    },
    {
        "id": "blueprint",
        "title": "模块与课程蓝图",
        "description": "按知识依赖和叙事连续性规划模块与章节",
        "user_input": "调整全局技术路线、模块、章节顺序、数量与学习成果",
        "model_output": "Module Context、章节计划与衔接关系",
    },
    {
        "id": "batch_plan",
        "title": "生成批次",
        "description": "沿模块边界组织可恢复的生成单元",
        "user_input": "确认或修改全局课程约束、批次、并发、预算和停止条件",
        "model_output": "批次列表与每批 Context Pack 范围",
    },
    {
        "id": "generation",
        "title": "批次生产循环",
        "description": "每批依次完成章节生成、三阶段质量门、返工与人工确认",
        "user_input": "处理当前批次问题、批准进入下一批，或要求定向返工",
        "model_output": "章节、质量门结果、连续性账本与批次进度",
    },
    {
        "id": "quality",
        "title": "整课质量闭环",
        "description": "汇总所有批次的未达标项，并仅定向修复受影响章节",
        "user_input": "确认整课质量结果，或对未通过章节发起统一定向修复",
        "model_output": "全课程质量汇总、待修复章节队列与闭环结果",
    },
    {
        "id": "release",
        "title": "整课确认",
        "description": "整课回归后交由用户决定是否完成",
        "user_input": "最终审核与发布决定",
        "model_output": "Markdown、HTML、质量记录和交付状态",
    },
]

# Derived, never written by hand: a second copy of the id list would turn the
# single source of truth into two sources of truth.
STEP_ORDER: list[str] = [step["id"] for step in WORKFLOW_STEPS]

REVIEW_WORKFLOW_STEPS: list[dict[str, str]] = [
    # Review reuses the first five stages and the last one as they are -- the
    # same dict objects, not copies -- because only the quality stage differs
    # when reviewing an existing course instead of building a new one.
    *WORKFLOW_STEPS[:-2],
    {
        "id": "quality",
        "title": "课程 Review",
        "description": "审阅或重生成既有课程内容",
        "user_input": "选择章节、补充审阅要求并确认处理结果",
        "model_output": "章节审校、质量报告与修改结果",
    },
    WORKFLOW_STEPS[-1],
]

REVIEW_STEP_ORDER: list[str] = [step["id"] for step in REVIEW_WORKFLOW_STEPS]
