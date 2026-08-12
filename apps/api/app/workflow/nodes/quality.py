from __future__ import annotations

import json
import re
from types import SimpleNamespace
from typing import Any

from langgraph.types import interrupt
from app.workflow.node_context import WorkflowContext
from app.workflow.quality_cycle import merge_repair_queue
from app.workflow.repair_tasks import create_or_refresh_task, list_repair_tasks, normalize_quality_issue, reconcile_open_tasks, split_quality_issues
from app.workflow.repository import append_event
from app.workflow.services.batch_planning import _canonicalize_batch_results
from app.workflow.services.course_quality import (
    _contract_repair_entries,
    _full_course_validation_after_build,
    _lesson_header_repair_entries,
    _quality_review_can_auto_complete,
    _refresh_quality_review_state,
)
from app.workflow.services.quality_integration import (
    _integration_repair_entries,
    _persist_latest_batch_quality_results,
    _refresh_quality_integration,
    _repair_agents_for_chapter,
    _revalidate_batch_integrations,
)
from app.workflow.state import CourseAgentState


def create_quality_nodes(context: WorkflowContext) -> SimpleNamespace:
    run_id = context.run_id
    provider = context.provider
    settings = context.settings

    def prepare_course_quality_review(state: CourseAgentState) -> dict[str, Any]:
        """Build the single, course-wide review fact base before asking a user.

            This is deliberately separate from the interrupt node. The projected
            node runs the Review/presentation Agent once, persists its artifact,
            and then the following node merely waits for the user's decision.
            """
        tool_runner = lambda action, **kwargs: context.execute_tool(
            f'course.{action}', caller='workflow.quality', course_slug=state['course_slug'], **kwargs,
        )
        batch_history = _revalidate_batch_integrations(state['course_slug'], state.get('batch_results', []), tool_runner=tool_runner)
        _persist_latest_batch_quality_results(settings.courses_root / state['course_slug'], batch_history)
        source_contract = tool_runner('source_contract')
        if source_contract.get('succeeded'):
            fresh_build = tool_runner('build')
            fresh_validation = _full_course_validation_after_build(
                state['course_slug'], fresh_build,
                validate_tool=lambda: tool_runner('validate'),
            )
        else:
            fresh_build = {'action': 'build', 'succeeded': False, 'exit_code': None, 'stdout': '', 'stderr': '源文件结构门未通过，构建尚未执行。', 'source_revision': source_contract.get('source_revision'), 'build_revision': None, 'scope': {'scope': 'course'}}
            fresh_validation = {**source_contract, 'stdout': json.dumps(source_contract.get('diagnostics') or [], ensure_ascii=False), 'stderr': ''}
        refreshed_history = _refresh_quality_integration(batch_history, fresh_build, fresh_validation)
        _persist_latest_batch_quality_results(settings.courses_root / state['course_slug'], refreshed_history)
        latest_results = _canonicalize_batch_results({**state, 'batch_results': refreshed_history})
        all_chapters = [chapter for result in latest_results for chapter in result.get('chapters', [])]
        header_entries = _lesson_header_repair_entries(settings.courses_root / state['course_slug'], all_chapters)
        integration_by_chapter: dict[int, dict[str, Any]] = {}
        integration_sources = [{'chapters': all_chapters, 'build': fresh_build, 'validation': fresh_validation}]
        for result in integration_sources:
            for entry in _integration_repair_entries({**result, 'chapters': all_chapters}):
                number = int(entry['chapter'])
                existing = integration_by_chapter.get(number)
                if existing:
                    existing['issues'] = list(dict.fromkeys([*existing['issues'], *entry['issues']]))
                else:
                    integration_by_chapter[number] = entry
        for entry in _contract_repair_entries(source_contract, all_chapters):
            number = int(entry['chapter'])
            existing = integration_by_chapter.get(number)
            if existing:
                existing['issues'] = list(dict.fromkeys([*existing['issues'], *entry['issues']]))
                existing['repair_agents'] = list(dict.fromkeys([*existing['repair_agents'], *entry['repair_agents']]))
                existing['contract_diagnostics'] = [*existing.get('contract_diagnostics', []), *entry.get('contract_diagnostics', [])]
            else:
                integration_by_chapter[number] = entry
        for entry in header_entries:
            number = int(entry['chapter'])
            existing = integration_by_chapter.get(number)
            if existing:
                existing['issues'] = list(dict.fromkeys([*existing['issues'], *entry['issues']]))
                existing['repair_agents'] = list(dict.fromkeys([*existing['repair_agents'], *entry['repair_agents']]))
            else:
                integration_by_chapter[number] = entry
        course_issues: list[dict[str, Any]] = []
        if not fresh_validation.get('succeeded', False) and (not integration_by_chapter):
            evidence = '\n'.join((str(result.get(key, '')) for result in (fresh_build, fresh_validation) for key in ('stdout', 'stderr') if result.get(key)))
            path_match = re.search(f"courses/{re.escape(state['course_slug'])}/([^\\s:`]+)", evidence)
            course_issues.append({'scope': 'course', 'title': '课程级构建与发布契约', 'path': path_match.group(1) if path_match else 'course.json / index.html', 'issue': '整课构建或发布产物检查未通过；该问题不属于任何单章正文。', 'repair_agents': ['异常恢复 Agent（整课构建诊断）'], 'diagnostic_evidence': evidence[:2400]})
        unresolved: list[dict[str, Any]] = []
        for result in latest_results:
            batch_numbers = {int(value) for value in result.get('batch', {}).get('chapter_numbers', [])}
            chapter_reviews: dict[int, dict[str, Any]] = {}
            for chapter in result.get('chapters', []):
                if chapter.get('passed'):
                    continue
                number = int(chapter.get('chapter'))
                chapter_reviews[number] = {'chapter': number, 'title': chapter.get('title'), 'path': chapter.get('path', ''), 'issues': list(chapter.get('issues', [])), 'repair_agents': _repair_agents_for_chapter(chapter)}
            for number, entry in integration_by_chapter.items():
                if number not in batch_numbers:
                    continue
                if number in chapter_reviews:
                    chapter_reviews[number]['issues'] = list(dict.fromkeys([*chapter_reviews[number]['issues'], *entry['issues']]))
                    chapter_reviews[number]['repair_agents'] = list(dict.fromkeys([*chapter_reviews[number]['repair_agents'], *entry['repair_agents']]))
                    chapter_reviews[number]['contract_diagnostics'] = [*chapter_reviews[number].get('contract_diagnostics', []), *entry.get('contract_diagnostics', [])]
                else:
                    chapter_reviews[number] = entry
            if chapter_reviews:
                unresolved.append({'batch': result['batch'], 'chapters': list(chapter_reviews.values()), 'batch_integration_failed': any((number in integration_by_chapter for number in batch_numbers))})
        repair_history = list(state.get('quality_repair_history', []))
        task_ids: list[str] = []
        course_root = settings.courses_root / state['course_slug']
        for batch_review in unresolved:
            batch = batch_review.get('batch', {})
            for chapter in batch_review.get('chapters', []):
                relative_path = str(chapter.get('path') or '')
                target = course_root / relative_path
                try:
                    markdown = target.read_text(encoding='utf-8') if target.exists() else ''
                except OSError:
                    markdown = ''
                chapter_task_ids: list[str] = []
                repairable_issues, advisory_issues, operation_incidents = split_quality_issues(
                    [str(issue) for issue in chapter.get('issues', [])],
                )
                chapter['issues'] = repairable_issues
                chapter['advisory_issues'] = advisory_issues
                chapter['operation_incidents'] = operation_incidents
                for incident in operation_incidents:
                    append_event(run_id, 'operation.incident', 'quality', f"第 {chapter.get('chapter')} 章：运行故障不进入整课修复队列", {'chapter': chapter.get('chapter'), 'issue': incident, 'origin': 'course_quality_review'})
                for issue in repairable_issues:
                    task = create_or_refresh_task(normalize_quality_issue(course_slug=state['course_slug'], run_id=run_id, batch_id=str(batch.get('id') or '') or None, chapter=int(chapter.get('chapter') or 0) or None, issue=str(issue), path=relative_path, markdown=markdown))
                    chapter_task_ids.append(task['id'])
                    task_ids.append(task['id'])
                chapter['repair_task_ids'] = chapter_task_ids
        stale_task_ids = reconcile_open_tasks(run_id, set(task_ids))
        if stale_task_ids:
            append_event(run_id, 'quality.repair.tasks.reconciled', 'quality', f'最新整课 Review 已关闭 {len(stale_task_ids)} 个不再复现的历史问题', {'task_ids': stale_task_ids})
        repair_tasks = list_repair_tasks(run_id)
        closed_task_statuses = {'fixed_verified', 'fixed_static_only', 'stale_evidence', 'advisory_accepted'}
        quality_cycle = {'cycle_id': str(state.get('quality_cycle_id') or f"{run_id}:quality:{max(1, int(state.get('quality_repair_round', 0)))}"), 'iteration': int(state.get('quality_cycle_iteration', 0)) + 1, 'initial_issue_count': len(repair_tasks), 'new_issue_count': sum((len(item.get('chapters', [])) for item in unresolved)), 'closed_count': sum((1 for task in repair_tasks if task.get('status') in closed_task_statuses)), 'queue_size': sum((1 for task in repair_tasks if task.get('status') not in closed_task_statuses)), 'converged': not unresolved and (not course_issues) and bool(fresh_build.get('succeeded')) and bool(fresh_validation.get('succeeded'))}
        report = {'batches': latest_results, 'unresolved': unresolved, 'course_issues': course_issues, 'summary': {'batch_count': len(state.get('batches', [])), 'unresolved_batch_count': len(unresolved), 'unresolved_chapter_count': sum((len(item['chapters']) for item in unresolved)), 'course_issue_count': len(course_issues), 'course_quality_passed': not unresolved and (not course_issues)}, 'repair_scope': '只修复未通过章节；通过章节保持原文并复用已有质量结果。', 'user_direction': state.get('feedback', ''), 'completed_repair_round': repair_history[-1]['round'] if repair_history else 0, 'previous_repair_result': repair_history[-1] if repair_history else None, 'repair_history': repair_history, 'deterministic_scan': {'succeeded': fresh_validation.get('succeeded', False), 'exit_code': fresh_validation.get('exit_code'), 'source_contract': source_contract}, 'repair_tasks': repair_tasks, 'quality_cycle': quality_cycle}
        _persist_latest_batch_quality_results(course_root, refreshed_history, repair_tasks=repair_tasks, course_integration={'passed': bool(fresh_build.get('succeeded')) and bool(fresh_validation.get('succeeded')), 'build': fresh_build, 'validation': fresh_validation, 'label': '整课构建与确定性检查'}, source_contract={'passed': bool(source_contract.get('succeeded')), 'diagnostics': source_contract.get('diagnostics') or [], 'revision': source_contract.get('source_revision')}, build={'passed': bool(fresh_build.get('succeeded')), 'revision': fresh_build.get('build_revision')}, artifact_validation={'passed': bool(fresh_validation.get('succeeded')) if fresh_build.get('succeeded') else None}, quality_cycle=quality_cycle)
        append_event(run_id, 'quality.course_review.completed', 'quality', '整课质量 Review 已完成，已汇总未达标章节与对应修复策略', report['summary'])
        return {'course_quality_report': report, 'batch_results': refreshed_history, 'repair_task_ids': task_ids, 'repair_scope': 'course', 'quality_cycle': quality_cycle, 'quality_cycle_id': quality_cycle['cycle_id'], 'quality_cycle_iteration': quality_cycle['iteration']}

    def course_quality_review(state: CourseAgentState) -> dict[str, Any]:
        """Ask for approval only after the full course Review artifact exists."""
        report = state.get('course_quality_report')
        if not report:
            fresh_quality, report = _refresh_quality_review_state(prepare_course_quality_review, state)
        unresolved = report.get('unresolved', [])
        if _quality_review_can_auto_complete(report):
            append_event(run_id, 'quality.course_review.auto_approved', 'quality', '整课质量门全部通过，自动进入整课确认', report.get('summary') or {})
            return {'approval': 'APPROVE', 'course_quality_report': report}
        decision = interrupt({'type': 'COURSE_QUALITY_REVIEW', 'step': 'quality', 'title': '确认整课质量闭环', 'output': report, 'actions': ['REVISE', 'APPROVE', 'STOP'] if unresolved else ['APPROVE', 'STOP']})
        patch: dict[str, Any] = {'feedback': decision.get('feedback', '').strip(), 'approval': decision['action']}
        if decision['action'] == 'REVISE':
            fresh_quality, report = _refresh_quality_review_state(prepare_course_quality_review, state)
            unresolved = report.get('unresolved', [])
            repair_candidates = [{**chapter, 'batch': batch_review.get('batch', {}), 'task_ids': list(chapter.get('repair_task_ids', []))} for batch_review in unresolved for chapter in batch_review.get('chapters', [])]
            repair_queue, _added, _deferred = merge_repair_queue([], repair_candidates, attempts={}, max_attempts=2)
            repair_round = int(state.get('quality_repair_round', 0)) + 1
            append_event(run_id, 'quality.repair.round.started', 'quality', f'整课定向修复第 {repair_round} 轮开始：共 {len(repair_queue)} 章', {'repair_round': repair_round, 'chapter_count': len(repair_queue), 'chapters': [item.get('chapter') for item in repair_queue]})
            patch.update({'quality_repair_queue': repair_queue, 'quality_cycle_queue': repair_queue, 'quality_cycle_attempts': {}, 'quality_cycle_discovery_sweeps': 0, 'quality_repair_active': bool(repair_queue), 'retry_count': 0, 'quality_blocked': False, 'feedback': decision.get('feedback', '') or '请依据已记录的质量证据，仅定向修复未通过章节。', 'course_quality_report': report, 'batch_results': fresh_quality['batch_results'], 'quality_cycle': fresh_quality['quality_cycle'], 'quality_cycle_id': fresh_quality['quality_cycle_id'], 'quality_cycle_iteration': fresh_quality['quality_cycle_iteration'], 'quality_repair_round': repair_round, 'quality_repair_round_results': [], 'quality_override': False})
        elif decision['action'] == 'APPROVE' and unresolved:
            patch['quality_override'] = True
        return patch

    def route_course_quality(state: CourseAgentState) -> str:
        if state.get('approval') == 'STOP':
            return 'stop'
        if state.get('approval') == 'REVISE' and state.get('quality_repair_active'):
            return 'repair'
        return 'release'

    return SimpleNamespace(prepare_course_quality_review=prepare_course_quality_review, course_quality_review=course_quality_review, route_course_quality=route_course_quality)
