from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from langgraph.types import interrupt
from app.research_service import search_public_web
from app.workflow.node_context import WorkflowContext
from app.workflow.repository import get_run_record
from app.workflow.services.batch_planning import _blueprint_markdown, _make_batches
from app.workflow.services.context_packs import _sync_requested_chapter_count, _sync_resources_policy
from app.workflow.services.workspace_contract import (
    _effective_source_policy,
    _read_workspace_context,
    _reconciliation_route,
    _sync_workspace_contract,
    _workspace_contract_snapshot,
    _workspace_revision_route,
    _write_json,
    _write_research_to_resources,
)
from app.workflow.state import CourseAgentState


def create_planning_nodes(context: WorkflowContext) -> SimpleNamespace:
    run_id = context.run_id
    provider = context.provider
    settings = context.settings

    def _recovered_change_requests(state: CourseAgentState) -> list[dict[str, Any]]:
        known = list(state.get('global_change_requests', []))
        known_keys = {(item.get('step'), item.get('request')) for item in known}
        historic = get_run_record(state['run_id']) or {}
        for event in historic.get('events', []):
            if event.get('event_type') != 'approval.resolved':
                continue
            feedback = str((event.get('payload') or {}).get('feedback', '')).strip()
            item = {'step': event.get('step', 'unknown'), 'request': feedback}
            if feedback and (item['step'], item['request']) not in known_keys:
                known.append(item)
                known_keys.add((item['step'], item['request']))
        return known

    def _global_change_patch(state: CourseAgentState, decision: dict[str, Any], step: str) -> dict[str, Any]:
        feedback = decision.get('feedback', '').strip()
        existing_changes = list(state.get('global_change_requests', []))
        changes = _recovered_change_requests(state)
        recovered_legacy_changes = len(changes) > len(existing_changes)
        if decision.get('action') == 'REVISE' and feedback:
            changes.append({'step': step, 'request': feedback})
        if changes:
            _sync_requested_chapter_count(settings.courses_root / state['course_slug'], changes)
            _write_json(settings.courses_root / state['course_slug'] / 'workspace' / 'change-requests.agent.json', {'requests': changes})
        return {'feedback': feedback, 'global_change_requests': changes, 'approval': 'REVISE' if decision['action'] == 'APPROVE' and recovered_legacy_changes else decision['action']}

    def _apply_workspace_revision(state: CourseAgentState) -> dict[str, Any]:
        """Apply a confirmed mission change as small Workspace patches.

            A revision starts from the approved documents. It never sends the
            original, long course intake back through the full MISSION writer.
            """
        course_root = settings.courses_root / state['course_slug']
        changes = state.get('global_change_requests', [])
        feedback = str(state.get('feedback') or '').strip()
        if not feedback and changes:
            feedback = str(changes[-1].get('request') or '').strip()
        workspace = _read_workspace_context(course_root, {'MISSION.md': 65536, 'COURSE-GENERATION-SPEC.md': 65536, 'RESOURCES.md': 48000, 'NOTES.md': 32000, 'COURSE-BLUEPRINT.md': 65536})
        result = provider.revise_workspace({'feedback': feedback, 'workspace': workspace})
        applied = context.execute_tool('workspace.patch', caller='workflow.planning', course_slug=state['course_slug'], patches=[patch.model_dump(mode='json') for patch in result.patches], reason=result.change_summary)
        mission_path = course_root / 'workspace' / 'MISSION.md'
        mission = mission_path.read_text(encoding='utf-8')
        request = dict(state['request'])
        if result.preferred_chapter_count is not None:
            request['preferred_chapter_count'] = result.preferred_chapter_count
        if result.source_policy:
            request['source_policy'] = result.source_policy
        return {'request': request, 'mission_markdown': mission, 'mission_assumptions': [f'增量修订：{result.change_summary}'], 'workspace_revision': {**result.model_dump(mode='json'), **applied}, 'feedback': ''}

    def draft_mission(state: CourseAgentState) -> dict[str, Any]:
        if state.get('mission_markdown') and state.get('global_change_requests'):
            return _apply_workspace_revision(state)
        request = dict(state['request'])
        course_root = settings.courses_root / state['course_slug']
        request['workspace'] = _read_workspace_context(course_root)
        changes = state.get('global_change_requests', [])
        if changes:
            request['global_change_requests'] = changes
            request['revision_feedback'] = changes[-1]['request']
        if state.get('feedback'):
            request['consistency_feedback'] = state['feedback']
        result = provider.create_mission(request)
        target = course_root / 'workspace' / 'MISSION.md'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(result.mission_markdown.rstrip() + '\n', encoding='utf-8')
        return {'mission_markdown': result.mission_markdown, 'mission_assumptions': result.assumptions, 'feedback': ''}

    def revise_workspace(state: CourseAgentState) -> dict[str, Any]:
        return _apply_workspace_revision(state)

    def reconcile_global_requirements(state: CourseAgentState) -> dict[str, Any]:
        """Reconcile a global requirement as a minimal Workspace patch.

            This node is also used after the consistency gate.  It must never
            rewrite the complete MISSION or re-run research/blueprint work just
            because one controlled sentence retained an old fact.
            """
        course_root = settings.courses_root / state['course_slug']
        changes = state.get('global_change_requests', [])
        revision = _apply_workspace_revision(state)
        request = revision['request']
        policy = _effective_source_policy(request, changes)
        _sync_resources_policy(course_root, policy)
        requested_count = _sync_requested_chapter_count(course_root, changes)
        return {**revision, 'global_sync': {'requested_chapter_count': requested_count, 'source_policy': policy, 'updated_files': revision['workspace_revision'].get('changed_files', []), 'reconciliation_route': _reconciliation_route(revision)}}

    def route_workspace_revision(state: CourseAgentState) -> str:
        return _workspace_revision_route(state, settings.courses_root / state['course_slug'])

    def route_global_reconciliation(state: CourseAgentState) -> str:
        return _reconciliation_route(state)

    def approve_mission(state: CourseAgentState) -> dict[str, Any]:
        decision = interrupt({'type': 'MISSION_APPROVAL', 'step': 'mission', 'title': '确认课程任务定义', 'output': state['mission_markdown'], 'actions': ['APPROVE', 'REVISE', 'STOP']})
        return _global_change_patch(state, decision, 'mission')

    def route_mission(state: CourseAgentState) -> str:
        action = state.get('approval')
        if action == 'REVISE':
            return 'revise'
        if action == 'STOP':
            return 'stop'
        return 'continue'

    def draft_blueprint(state: CourseAgentState) -> dict[str, Any]:
        request = dict(state['request'])
        course_root = settings.courses_root / state['course_slug']
        request['workspace'] = _read_workspace_context(course_root)
        changes = state.get('global_change_requests', [])
        if changes:
            request['global_change_requests'] = changes
            request['revision_feedback'] = changes[-1]['request']
        result = provider.create_blueprint(request, state['mission_markdown'])
        value = result.model_dump(mode='json')
        (course_root / 'workspace' / 'COURSE-BLUEPRINT.md').write_text(_blueprint_markdown(value), encoding='utf-8')
        _write_json(course_root / 'workspace' / 'blueprint.agent.json', value)
        return {'blueprint': value, 'workspace_sync': _sync_workspace_contract(course_root, value), 'feedback': ''}

    def verify_workspace_contract(state: CourseAgentState) -> dict[str, Any]:
        course_root = settings.courses_root / state['course_slug']
        sync = _sync_workspace_contract(course_root, state['blueprint'])
        audit = provider.audit_workspace_consistency(state['mission_markdown'], state['blueprint'], _workspace_contract_snapshot(course_root), state.get('global_change_requests', [])).model_dump(mode='json')
        result = {**audit, 'contract_sync': sync}
        _write_json(course_root / 'workspace' / 'consistency-report.agent.json', result)
        return {'workspace_consistency': result}

    def route_workspace_contract(state: CourseAgentState) -> str:
        audit = state.get('workspace_consistency', {})
        if audit.get('decision') == 'repair' and state.get('consistency_retry_count', 0) < 2:
            return 'repair'
        return 'continue'

    def record_contract_retry(state: CourseAgentState) -> dict[str, Any]:
        audit = state.get('workspace_consistency', {})
        issues = '；'.join(audit.get('issues', []))
        return {'feedback': issues, 'consistency_retry_count': state.get('consistency_retry_count', 0) + 1}

    def research_sources(state: CourseAgentState) -> dict[str, Any]:
        request = dict(state['request'])
        course_root = settings.courses_root / state['course_slug']
        changes = state.get('global_change_requests', [])
        if changes:
            request['global_change_requests'] = changes
        policy = _effective_source_policy(request, changes)
        _sync_resources_policy(course_root, policy)
        if policy == '仅限使用内部提供材料':
            research = {'policy': policy, 'skipped': True, 'reason': '来源政策限制为内部提供材料，未执行公开网页检索。', 'queries': [], 'sources': [], 'notes': ['可在 RESOURCES.md 中补充用户授权的内部资料。']}
        else:
            plan = provider.plan_research({**request, 'workspace': _read_workspace_context(course_root)}, state['mission_markdown'])
            candidates = search_public_web(plan.queries)
            curated = provider.curate_research(policy, candidates)
            research = {'policy': policy, 'skipped': False, 'queries': plan.queries, 'search_rationale': plan.search_rationale, 'sources': [item.model_dump(mode='json') for item in curated.sources], 'notes': [*curated.notes, *candidates.get('errors', [])], 'candidate_count': len(candidates.get('results', []))}
        _write_research_to_resources(course_root, research)
        _write_json(course_root / 'workspace' / 'research.agent.json', research)
        return {'research': research}

    def approve_blueprint(state: CourseAgentState) -> dict[str, Any]:
        decision = interrupt({'type': 'BLUEPRINT_APPROVAL', 'step': 'blueprint', 'title': '确认模块与章节蓝图', 'output': state['blueprint'], 'actions': ['APPROVE', 'REVISE', 'STOP']})
        return _global_change_patch(state, decision, 'blueprint')

    def plan_batches(state: CourseAgentState) -> dict[str, Any]:
        batches = _make_batches(state['blueprint'])
        course_root = settings.courses_root / state['course_slug']
        _write_json(course_root / 'workspace' / 'generation-plan.agent.json', {'batches': batches, 'strategy': '依赖优先：批次默认顺序执行，每批最多 4 章', 'execution': {'batch_mode': 'sequential', 'chapter_mode': 'sequential_by_default', 'max_parallel_chapters': 1, 'rule': '当前按章节顺序执行；后续只有蓝图明确无前后依赖时才可提高并行度。'}})
        return {'batches': batches, 'current_batch_index': 0, 'continuity_ledger': [], 'batch_results': [], 'retry_count': 0, 'quality_cycle_queue': [], 'quality_cycle_attempts': {}, 'quality_cycle_discovery_sweeps': 0, 'quality_refunded_legacy_tasks': [], 'quality_repair_queue': [], 'quality_repair_active': False, 'batch_repair_queue': [], 'batch_repair_active': False, 'batch_repair_batch_id': None}

    def approve_plan(state: CourseAgentState) -> dict[str, Any]:
        decision = interrupt({'type': 'BATCH_PLAN_APPROVAL', 'step': 'batch_plan', 'title': '确认课程生成批次', 'output': {'batches': state['batches']}, 'actions': ['APPROVE', 'REVISE', 'STOP']})
        return _global_change_patch(state, decision, 'batch_plan')

    return SimpleNamespace(draft_mission=draft_mission, revise_workspace=revise_workspace, reconcile_global_requirements=reconcile_global_requirements, route_workspace_revision=route_workspace_revision, route_global_reconciliation=route_global_reconciliation, approve_mission=approve_mission, route_mission=route_mission, draft_blueprint=draft_blueprint, verify_workspace_contract=verify_workspace_contract, route_workspace_contract=route_workspace_contract, record_contract_retry=record_contract_retry, research_sources=research_sources, approve_blueprint=approve_blueprint, plan_batches=plan_batches, approve_plan=approve_plan, global_change_patch=_global_change_patch)
