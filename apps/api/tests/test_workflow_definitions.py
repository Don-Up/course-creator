"""Contract tests for the seven-stage workflow definitions.

The stage ids, their order and their wording are a product contract rather
than an implementation detail: the frontend renders these fields directly.
The tests therefore pin the exact values instead of merely checking that the
structures exist.
"""

from __future__ import annotations

from app.workflow.definitions import (
    REVIEW_STEP_ORDER,
    REVIEW_WORKFLOW_STEPS,
    STEP_ORDER,
    WORKFLOW_STEPS,
)

EXPECTED_STEP_ORDER = [
    "intake",
    "mission",
    "blueprint",
    "batch_plan",
    "generation",
    "quality",
    "release",
]

EXPECTED_STEP_FIELDS = frozenset(
    {"id", "title", "description", "user_input", "model_output"}
)

EXPECTED_WORKFLOW_STEPS = [
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

EXPECTED_REVIEW_QUALITY_STEP = {
    "id": "quality",
    "title": "课程 Review",
    "description": "审阅或重生成既有课程内容",
    "user_input": "选择章节、补充审阅要求并确认处理结果",
    "model_output": "章节审校、质量报告与修改结果",
}


def test_step_order_pins_the_seven_stage_product_contract():
    """The stage ids and their order are fixed by the product contract."""
    assert STEP_ORDER == EXPECTED_STEP_ORDER


def test_workflow_steps_expose_exactly_the_five_contract_fields():
    """Every stage carries the five contract fields -- no more, no less."""
    assert len(WORKFLOW_STEPS) == len(STEP_ORDER)

    for step, expected_id in zip(WORKFLOW_STEPS, STEP_ORDER, strict=True):
        assert set(step) == EXPECTED_STEP_FIELDS
        assert step["id"] == expected_id

    assert [step["id"] for step in WORKFLOW_STEPS] == STEP_ORDER


def test_workflow_steps_carry_the_agreed_wording():
    """The Chinese copy is part of the contract and must not drift."""
    assert WORKFLOW_STEPS == EXPECTED_WORKFLOW_STEPS


def test_review_flow_reuses_every_stage_except_its_quality_stage():
    """Review keeps the same stages and order; only `quality` differs."""
    assert REVIEW_STEP_ORDER == STEP_ORDER
    assert len(REVIEW_WORKFLOW_STEPS) == len(WORKFLOW_STEPS)

    creation_steps = {step["id"]: step for step in WORKFLOW_STEPS}
    review_steps = {step["id"]: step for step in REVIEW_WORKFLOW_STEPS}

    assert set(review_steps) == set(creation_steps)

    review_quality = review_steps["quality"]
    assert review_quality == EXPECTED_REVIEW_QUALITY_STEP
    assert review_quality["title"] != creation_steps["quality"]["title"]

    # The remaining stages are reused verbatim, field for field -- and as the
    # very same dict objects, so the two flows can never drift apart.
    for step_id, review_step in review_steps.items():
        if step_id == "quality":
            continue
        assert review_step == creation_steps[step_id]
        assert review_step is creation_steps[step_id]
