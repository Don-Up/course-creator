from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.config import get_settings
from app.agents.protocols import CourseAgent
from app.workflow.node_context import WorkflowContext
from app.workflow.nodes.generation import create_generation_nodes
from app.workflow.nodes.planning import create_planning_nodes
from app.workflow.nodes.quality import create_quality_nodes
from app.workflow.nodes.release import create_release_nodes
from app.workflow.nodes.repair import create_repair_nodes
from app.workflow.services.context_packs import _projected
from app.workflow.state import CourseAgentState


def build_course_graph(run_id: str, provider: CourseAgent, checkpointer):
    """Compile the persisted course-production graph without owning node logic."""
    context = WorkflowContext(run_id, provider, get_settings())
    planning = create_planning_nodes(context)
    generation = create_generation_nodes(context)
    repair = create_repair_nodes(context, global_change_patch=planning.global_change_patch)
    quality = create_quality_nodes(context)
    release = create_release_nodes(
        context,
        global_change_patch=planning.global_change_patch,
        prepare_quality_review=quality.prepare_course_quality_review,
    )

    builder = StateGraph(CourseAgentState)
    builder.add_node("draft_mission", _projected(run_id, "mission", "任务定义", planning.draft_mission, provider))
    builder.add_node("revise_workspace", _projected(run_id, "mission", "任务定义增量修订", planning.revise_workspace, provider))
    builder.add_node("reconcile_global_requirements", _projected(run_id, "blueprint", "全局要求同步", planning.reconcile_global_requirements, provider))
    builder.add_node("approve_mission", planning.approve_mission)
    builder.add_node("research_sources", _projected(run_id, "blueprint", "资料检索与来源整理", planning.research_sources, provider))
    builder.add_node("draft_blueprint", _projected(run_id, "blueprint", "课程蓝图", planning.draft_blueprint, provider))
    builder.add_node("verify_workspace_contract", _projected(run_id, "blueprint", "工作区一致性门禁", planning.verify_workspace_contract, provider))
    builder.add_node("record_contract_retry", planning.record_contract_retry)
    builder.add_node("approve_blueprint", planning.approve_blueprint)
    builder.add_node("plan_batches", _projected(run_id, "batch_plan", "批次规划", planning.plan_batches, provider))
    builder.add_node("approve_plan", planning.approve_plan)
    builder.add_node("generate_batch", _projected(run_id, "generation", "批次生成与质量检查", generation.generate_batch, provider))
    builder.add_node("repair_batch_chapters", _projected(run_id, "generation", "批次定向修复", repair.repair_open_chapters, provider))
    builder.add_node("repair_open_chapters", _projected(run_id, "quality", "整课质量闭环定向修复", repair.repair_open_chapters, provider))
    builder.add_node("request_batch_review", repair.request_batch_review)
    builder.add_node("approve_batch", release.approve_batch)
    builder.add_node("prepare_course_quality_review", _projected(run_id, "quality", "整课质量 Review", quality.prepare_course_quality_review, provider))
    builder.add_node("course_quality_review", _projected(run_id, "quality", "整课质量闭环", quality.course_quality_review, provider))
    builder.add_node("prepare_release_review", _projected(run_id, "release", "整课总结", release.prepare_release_review, provider))
    builder.add_node("release_approval", release.release_approval)
    builder.add_node("finalize", _projected(run_id, "release", "整课收束", release.finalize, provider))
    builder.add_node("stop", release.stop)
    builder.add_edge(START, "draft_mission")
    builder.add_edge("draft_mission", "approve_mission")
    builder.add_edge("prepare_course_quality_review", "course_quality_review")
    builder.add_conditional_edges("reconcile_global_requirements", planning.route_global_reconciliation, {"audit": "verify_workspace_contract", "research": "research_sources", "blueprint": "draft_blueprint"})
    builder.add_conditional_edges("approve_mission", planning.route_mission, {"revise": "revise_workspace", "continue": "research_sources", "stop": "stop"})
    builder.add_conditional_edges("revise_workspace", planning.route_workspace_revision, {"research": "research_sources", "blueprint": "draft_blueprint", "audit": "verify_workspace_contract"})
    builder.add_edge("research_sources", "draft_blueprint")
    builder.add_edge("draft_blueprint", "verify_workspace_contract")
    builder.add_conditional_edges("verify_workspace_contract", planning.route_workspace_contract, {"repair": "record_contract_retry", "continue": "approve_blueprint"})
    builder.add_edge("record_contract_retry", "reconcile_global_requirements")
    builder.add_conditional_edges("approve_blueprint", planning.route_mission, {"revise": "reconcile_global_requirements", "continue": "plan_batches", "stop": "stop"})
    builder.add_edge("plan_batches", "approve_plan")
    builder.add_conditional_edges("approve_plan", planning.route_mission, {"revise": "reconcile_global_requirements", "continue": "generate_batch", "stop": "stop"})
    builder.add_conditional_edges("generate_batch", generation.route_generated_batch, {"retry": "generate_batch", "next": "generate_batch", "repair": "repair_batch_chapters", "complete": "prepare_course_quality_review", "manual": "request_batch_review"})
    builder.add_conditional_edges("request_batch_review", release.route_batch_review, {"retry": "generate_batch", "next": "generate_batch", "complete": "prepare_course_quality_review", "course_quality": "prepare_course_quality_review", "stop": "stop"})
    builder.add_conditional_edges("approve_batch", release.route_batch, {"revise": "generate_batch", "next": "generate_batch", "complete": "prepare_course_quality_review", "manual": "stop", "stop": "stop"})
    builder.add_conditional_edges("course_quality_review", quality.route_course_quality, {"repair": "repair_open_chapters", "release": "prepare_release_review", "stop": "stop"})
    builder.add_conditional_edges("repair_batch_chapters", repair.route_quality_repair, {"next": "repair_batch_chapters", "batch_complete": "generate_batch", "course_quality": "prepare_course_quality_review", "manual": "request_batch_review"})
    builder.add_conditional_edges("repair_open_chapters", repair.route_quality_repair, {"next": "repair_open_chapters", "batch_complete": "generate_batch", "course_quality": "prepare_course_quality_review", "manual": "request_batch_review"})
    builder.add_edge("prepare_release_review", "release_approval")
    builder.add_conditional_edges("release_approval", release.route_release, {"refresh": "prepare_release_review", "quality": "prepare_course_quality_review", "publish": "finalize"})
    builder.add_edge("finalize", END)
    builder.add_edge("stop", END)
    return builder.compile(checkpointer=checkpointer)
