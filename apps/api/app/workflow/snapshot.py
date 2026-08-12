"""Read-only projections of the executable LangGraph workflows for the UI."""
from __future__ import annotations

from typing import Any

from app.agents.definitions import AGENT_DEFINITIONS
from app.tools.runtime import TOOL_MANIFESTS
from app.workflow.definitions import REVIEW_WORKFLOW_STEPS, WORKFLOW_STEPS


_PHASES = [
    ("intake", "课程需求", "课程请求在创建 Run 前被校验并持久化。"),
    ("mission", "任务定义", "课程任务、人工确认和全局要求的入口。"),
    ("blueprint", "模块与课程蓝图", "资料、蓝图、工作区契约与回路。"),
    ("batch_plan", "生成批次", "按模块边界划分可恢复的生产单元。"),
    ("generation", "批次生产循环", "章节生产、批次质量门与批次人工审核。"),
    ("quality", "整课质量闭环", "整课审校与定向 RepairTask 修复。"),
    ("release", "整课确认", "发布审阅、发布或停止。"),
]


def _node(
    id: str,
    phase: str,
    title: str,
    *,
    handler: str,
    execution_mode: str = "deterministic",
    agents: tuple[str, ...] = (),
    tools: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "id": id, "phase": phase, "title": title, "handler": handler,
        "execution_mode": execution_mode,
        "agents": list(agents), "tools": list(tools),
    }


def _course_topology() -> dict[str, Any]:
    nodes = [
        _node("intake", "intake", "课程需求", handler="API create_course / start_run", execution_mode="system"),
        _node("draft_mission", "mission", "生成任务定义", handler="planning.draft_mission", execution_mode="llm", agents=("mission.agent",)),
        _node("approve_mission", "mission", "确认任务定义", handler="planning.approve_mission", execution_mode="approval"),
        _node("revise_workspace", "mission", "增量修订工作区", handler="planning.revise_workspace", execution_mode="hybrid", agents=("mission.agent",), tools=("workspace.patch",)),
        _node("research_sources", "blueprint", "检索与整理资料", handler="planning.research_sources", execution_mode="llm", agents=("research.agent",)),
        _node("draft_blueprint", "blueprint", "生成课程蓝图", handler="planning.draft_blueprint", execution_mode="llm", agents=("blueprint.agent",)),
        _node("verify_workspace_contract", "blueprint", "工作区一致性门禁", handler="planning.verify_workspace_contract"),
        _node("record_contract_retry", "blueprint", "记录契约重试", handler="planning.record_contract_retry"),
        _node("reconcile_global_requirements", "blueprint", "同步全局要求", handler="planning.reconcile_global_requirements"),
        _node("approve_blueprint", "blueprint", "确认课程蓝图", handler="planning.approve_blueprint", execution_mode="approval"),
        _node("plan_batches", "batch_plan", "规划生成批次", handler="planning.plan_batches"),
        _node("approve_plan", "batch_plan", "确认批次计划", handler="planning.approve_plan", execution_mode="approval"),
        _node("generate_batch", "generation", "生成批次与质量检查", handler="generation.generate_batch", execution_mode="hybrid", agents=("writer.agent", "reviewer.agent"), tools=("course.source_contract", "course.build", "course.validate")),
        _node("repair_batch_chapters", "generation", "批次定向修复", handler="repair.repair_open_chapters", execution_mode="hybrid", agents=("repair.agent", "reviewer.agent"), tools=("course.source_contract", "course.build", "course.validate")),
        _node("request_batch_review", "generation", "请求批次人工审核", handler="repair.request_batch_review", execution_mode="approval"),
        # The executable builder still registers this legacy handler but has
        # no incoming edge. Keeping it in the snapshot makes that topology
        # fact visible instead of silently presenting a fictional route.
        _node("approve_batch", "generation", "批次确认（当前未接入）", handler="release.approve_batch", execution_mode="approval"),
        _node("repair_open_chapters", "quality", "定向修复章节", handler="repair.repair_open_chapters", execution_mode="hybrid", agents=("repair.agent", "reviewer.agent"), tools=("course.source_contract", "course.build", "course.validate")),
        _node("prepare_course_quality_review", "quality", "准备整课质量审阅", handler="quality.prepare_course_quality_review"),
        _node("course_quality_review", "quality", "执行整课质量闭环", handler="quality.course_quality_review", execution_mode="hybrid", agents=("reviewer.agent",), tools=("course.source_contract", "course.build", "course.validate")),
        _node("prepare_release_review", "release", "整理发布审阅", handler="release.prepare_release_review"),
        _node("release_approval", "release", "最终发布确认", handler="release.release_approval", execution_mode="approval"),
        _node("finalize", "release", "完成并发布", handler="release.finalize", execution_mode="system"),
        _node("stop", "release", "停止 Run", handler="release.stop", execution_mode="system"),
    ]
    routes = [
        # Intake is performed by the API before LangGraph starts. The
        # projection keeps this handoff visible as the first course path.
        ("intake", "draft_mission", "创建 Run 后执行"),
        ("START", "draft_mission", "开始"), ("draft_mission", "approve_mission", "产出任务定义"),
        ("approve_mission", "revise_workspace", "要求修改"), ("approve_mission", "research_sources", "继续"), ("approve_mission", "stop", "停止"),
        ("revise_workspace", "research_sources", "需要检索"), ("revise_workspace", "draft_blueprint", "直接更新蓝图"), ("revise_workspace", "verify_workspace_contract", "执行审计"),
        ("research_sources", "draft_blueprint", "资料已整理"), ("draft_blueprint", "verify_workspace_contract", "蓝图已生成"),
        ("verify_workspace_contract", "record_contract_retry", "需要修复"), ("verify_workspace_contract", "approve_blueprint", "通过"),
        ("record_contract_retry", "reconcile_global_requirements", "重新同步"),
        ("reconcile_global_requirements", "verify_workspace_contract", "审计"), ("reconcile_global_requirements", "research_sources", "检索"), ("reconcile_global_requirements", "draft_blueprint", "重建蓝图"),
        ("approve_blueprint", "reconcile_global_requirements", "要求修改"), ("approve_blueprint", "plan_batches", "继续"), ("approve_blueprint", "stop", "停止"),
        ("plan_batches", "approve_plan", "批次已规划"), ("approve_plan", "reconcile_global_requirements", "要求修改"), ("approve_plan", "generate_batch", "开始生产"), ("approve_plan", "stop", "停止"),
        ("generate_batch", "generate_batch", "下一章 / 重试"), ("generate_batch", "repair_batch_chapters", "需要定向修复"), ("generate_batch", "request_batch_review", "转人工"), ("generate_batch", "prepare_course_quality_review", "批次全部完成"),
        ("request_batch_review", "generate_batch", "继续生产或重试"), ("request_batch_review", "prepare_course_quality_review", "进入整课质量"), ("request_batch_review", "stop", "停止"),
        ("prepare_course_quality_review", "course_quality_review", "开始审校"), ("course_quality_review", "repair_open_chapters", "存在待修复项"), ("course_quality_review", "prepare_release_review", "质量通过"), ("course_quality_review", "stop", "停止"),
        ("repair_batch_chapters", "repair_batch_chapters", "继续批次修复"), ("repair_batch_chapters", "generate_batch", "批次修复完成"), ("repair_batch_chapters", "request_batch_review", "需要人工处理"),
        ("repair_open_chapters", "repair_open_chapters", "下一项修复"), ("repair_open_chapters", "prepare_course_quality_review", "整课修复完成"), ("repair_open_chapters", "request_batch_review", "需要人工处理"),
        ("prepare_release_review", "release_approval", "等待决定"), ("release_approval", "prepare_release_review", "刷新审阅"), ("release_approval", "prepare_course_quality_review", "继续修复"), ("release_approval", "finalize", "发布"),
        ("finalize", "END", "结束"), ("stop", "END", "结束"),
    ]
    return {"mode": "new_course", "title": "新课程生产主图", "steps": WORKFLOW_STEPS, "phases": _PHASES, "nodes": nodes, "edges": [{"from": source, "to": target, "label": label} for source, target, label in routes]}


def _review_topology() -> dict[str, Any]:
    nodes = [
        _node("intake", "intake", "已有课程与处理范围", handler="API start_run", execution_mode="system"),
        _node("inspect", "quality", "检查既有课程", handler="review.inspect", execution_mode="hybrid", agents=("reviewer.agent",), tools=("course.source_contract", "course.build", "course.validate")),
        _node("approve_review", "quality", "确认 Review 结果", handler="review.approve_review", execution_mode="approval"),
        _node("finish", "release", "完成 Review", handler="review.finish", execution_mode="system"),
        _node("stop", "release", "停止 Run", handler="review.stop", execution_mode="system"),
    ]
    edges = [("START", "inspect", "开始"), ("inspect", "approve_review", "输出结果"), ("approve_review", "finish", "完成"), ("approve_review", "stop", "停止"), ("finish", "END", "结束"), ("stop", "END", "结束")]
    return {"mode": "review_course", "title": "既有课程 Review 图", "steps": REVIEW_WORKFLOW_STEPS, "phases": _PHASES, "nodes": nodes, "edges": [{"from": source, "to": target, "label": label} for source, target, label in edges]}


def workflow_snapshot() -> dict[str, Any]:
    """Return declarative UI data kept in lockstep with the supported graphs."""
    agents = [{"id": item.id, "version": item.version, "role": item.role, "model_policy": item.model_policy_ref, "tools": item.tool_ids} for item in AGENT_DEFINITIONS.values()]
    tools = [{"id": item.id, "callers": sorted(item.callers), "idempotent": item.idempotent} for item in TOOL_MANIFESTS.values()]
    return {"version": "2026-08-09", "default_mode": "new_course", "topologies": [_course_topology(), _review_topology()], "agents": agents, "tools": tools}
