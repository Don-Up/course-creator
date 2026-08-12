from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from langgraph.types import interrupt
from app.course_service import publish_course
from app.workflow.node_context import WorkflowContext
from app.workflow.repository import append_event
from app.workflow.services.batch_planning import _latest_batch_results, build_release_review
from app.workflow.state import CourseAgentState


def create_release_nodes(context: WorkflowContext, *, global_change_patch, prepare_quality_review) -> SimpleNamespace:
    run_id = context.run_id
    provider = context.provider
    settings = context.settings
    _global_change_patch = global_change_patch
    prepare_course_quality_review = prepare_quality_review

    def approve_batch(state: CourseAgentState) -> dict[str, Any]:
        result = state['batch_results'][-1]
        actions = ['REVISE', 'STOP'] if not result['passed'] else ['APPROVE', 'REVISE', 'STOP']
        decision = interrupt({'type': 'BATCH_APPROVAL', 'step': 'generation', 'title': f"确认批次 {result['batch']['id']}", 'output': result, 'actions': actions})
        action = decision['action']
        patch: dict[str, Any] = _global_change_patch(state, decision, 'generation')
        if action == 'APPROVE':
            patch['current_batch_index'] = state['current_batch_index'] + 1
            patch['retry_count'] = 0
        elif action == 'REVISE':
            patch['retry_count'] = state.get('retry_count', 0) + 1
        return patch

    def route_batch(state: CourseAgentState) -> str:
        if state.get('approval') == 'STOP':
            return 'stop'
        if state.get('approval') == 'REVISE':
            return 'manual' if state.get('retry_count', 0) >= 3 else 'revise'
        return 'complete' if state['current_batch_index'] >= len(state['batches']) else 'next'

    def route_batch_review(state: CourseAgentState) -> str:
        if state.get('approval') == 'STOP':
            return 'stop'
        if state.get('quality_repair_active'):
            return 'course_quality'
        if state.get('approval') == 'APPROVE':
            return 'complete' if state['current_batch_index'] >= len(state['batches']) else 'next'
        return 'retry'

    def release_approval(state: CourseAgentState) -> dict[str, Any]:
        quality_report = state.get('course_quality_report', {})
        release_review = state.get('release_review')
        if not release_review:
            release_review = build_release_review(run_id, dict(state))
        open_issues = quality_report.get('unresolved', [])
        decision = interrupt({'type': 'RELEASE_APPROVAL', 'step': 'release', 'title': '确认整课生成结果' if not open_issues else '确认带未解决问题的整课结果', 'output': {'release_review': release_review, 'release_review_ready': bool(release_review), 'batches': _latest_batch_results(state), 'continuity_ledger': state.get('continuity_ledger', []), 'course_quality_report': quality_report, 'has_open_quality_issues': bool(open_issues)}, 'actions': ['REGENERATE_SUMMARY', 'REVISE', 'APPROVE'] if release_review else ['REGENERATE_SUMMARY', 'REVISE']})
        if not isinstance(decision, dict):
            return {'approval': ''}
        patch: dict[str, Any] = {'release_review': release_review, 'feedback': decision.get('feedback', '').strip(), 'approval': decision['action']}
        if decision['action'] == 'REVISE':
            patch['quality_repair_active'] = False
            patch['quality_repair_queue'] = []
            patch['retry_count'] = 0
        return patch

    def route_release(state: CourseAgentState) -> str:
        if state.get('approval') == 'REGENERATE_SUMMARY':
            return 'refresh'
        if state.get('approval') == 'REVISE':
            return 'quality'
        return 'publish'

    def prepare_release_review(state: CourseAgentState) -> dict[str, Any]:
        fresh_quality = prepare_course_quality_review(state)
        release_state = {**dict(state), **fresh_quality}
        return {**fresh_quality, 'release_review': build_release_review(run_id, release_state)}

    def finalize(state: CourseAgentState) -> dict[str, Any]:
        unresolved = state.get('course_quality_report', {}).get('unresolved', [])
        published = publish_course(state['course_slug'], workflow_run_id=run_id)
        append_event(run_id, 'course.published', 'release', '课程已发布，课程元数据与目录索引已同步', {'course_status': published['status'], 'open_quality_issue_count': sum((len(item.get('chapters', [])) for item in unresolved))})
        return {'final_status': 'PUBLISHED_WITH_OPEN_ISSUES' if unresolved else 'PUBLISHED', 'open_quality_issue_count': sum((len(item.get('chapters', [])) for item in unresolved))}

    def stop(state: CourseAgentState) -> dict[str, Any]:
        return {'final_status': 'STOPPED'}

    return SimpleNamespace(approve_batch=approve_batch, route_batch=route_batch, route_batch_review=route_batch_review, release_approval=release_approval, route_release=route_release, prepare_release_review=prepare_release_review, finalize=finalize, stop=stop)
