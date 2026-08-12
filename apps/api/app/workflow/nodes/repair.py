from __future__ import annotations
import hashlib
from types import SimpleNamespace
from typing import Any
from langgraph.types import interrupt
from app.workflow.node_context import WorkflowContext
from app.db import utcnow
from app.workflow.quality_cycle import chapter_repair_sweep_tasks, detect_quality_regressions, merge_repair_queue, merge_same_cycle_discoveries, refund_legacy_semantic_rollback_attempts
from app.workflow.repair_tasks import create_or_refresh_task, list_repair_tasks, normalize_quality_issue, record_attempt, refresh_evidence, transition_task
from app.workflow.repository import append_event
from app.workflow.services.batch_planning import (
    _batch_display_label,
    _batch_repair_completion_route,
    _contract_codes_requiring_llm,
    _latest_batch_results,
    _normalize_reference_node,
    _repair_issue_is_resolved,
)
from app.workflow.services.context_packs import _context_pack, _effective_char_count
from app.workflow.services.course_quality import (
    _batch_contract_repair_entries,
    _contract_repair_entries,
    _full_course_validation_after_build,
    _normalize_lesson_intro,
    _relocate_external_links_to_references,
    _repair_queue_for_scope,
    _repair_queue_patch,
    _replace_batch_integration,
)
from app.workflow.services.quality_integration import (
    _integration_repair_entries,
    _persist_latest_batch_quality_results,
    _refresh_quality_integration,
    _repair_agents_for_chapter,
    _revalidate_batch_integrations,
    _replace_quality_chapter_result,
)
from app.workflow.services.workspace_contract import (
    _close_unclosed_markdown_fence,
    _redact_private_paths,
    _remove_missing_local_image,
)
from app.workflow.services.artifact_commits import (
    commit_chapter_candidate,
    reject_chapter_candidate,
    verify_chapter_candidate,
)
from app.workflow.services.repair_commits import commit_deterministic_repair
from app.workflow.services.repair_findings import separate_repair_findings, split_post_verification_findings
from app.workflow.services.repair_rounds import merge_round_discoveries, upsert_round_chapter_result
from app.workflow.state import CourseAgentState
def create_repair_nodes(context: WorkflowContext, *, global_change_patch) -> SimpleNamespace:
    run_id = context.run_id
    provider = context.provider
    settings = context.settings
    workflow_context = context
    _global_change_patch = global_change_patch
    def repair_open_chapters(state: CourseAgentState) -> dict[str, Any]:
        """Repair one chapter sweep of known issues, never a production batch."""
        repair_scope = 'batch' if state.get('repair_scope') == 'batch' else 'course'
        queue = _repair_queue_for_scope(state)
        active_batch = next((item for item in state.get('batches', []) if item.get('id') == state.get('batch_repair_batch_id')), None) if repair_scope == 'batch' else None
        scope_chapter_numbers = list((active_batch or {}).get('chapter_numbers') or [])
        cycle_attempts = {str(key): int(value) for key, value in (state.get('quality_cycle_attempts') or {}).items()}
        discovery_sweeps = int(state.get('quality_cycle_discovery_sweeps', 0))
        max_discovery_sweeps = settings.quality_cycle_max_discovery_sweeps
        discovery_budget_exhausted = False
        def defer_discovery_budget(task_ids: list[str], origin: str) -> None:
            nonlocal discovery_budget_exhausted
            if not task_ids:
                return
            discovery_budget_exhausted = True
            verification = {'outcome': 'human_decision_required', 'reason': f'当前质量循环已完成 {max_discovery_sweeps} 次新增问题回灌；该问题保留给人工确认或下一轮明确发起的质量闭环。', 'origin': origin, 'verified_at': utcnow()}
            for task_id in task_ids:
                transition_task(task_id, 'human_decision_required', verification=verification)
            append_event(run_id, 'quality.repair.same_cycle.discovery_budget_exhausted', 'quality', f'新增问题回灌已达 {max_discovery_sweeps} 次上限；{len(task_ids)} 个问题转人工确认，不再自动续环', {'origin': origin, 'task_ids': task_ids, 'max_discovery_sweeps': max_discovery_sweeps})
        previous_refunds = list(state.get('quality_refunded_legacy_tasks') or [])
        cycle_attempts, refunded_legacy_tasks = refund_legacy_semantic_rollback_attempts(cycle_attempts, list_repair_tasks(run_id), already_refunded=previous_refunds)
        newly_refunded = [task_id for task_id in refunded_legacy_tasks if task_id not in previous_refunds]
        if newly_refunded:
            append_event(run_id, 'quality.repair.migration.semantic_rollback_refunded', 'quality', f'已退还 {len(newly_refunded)} 次由旧语义回滚规则误消耗的定向尝试', {'task_ids': newly_refunded})
        queue, _, resumed_deferred = merge_repair_queue(queue, [], attempts=cycle_attempts, max_attempts=2)
        if resumed_deferred:
            append_event(run_id, 'quality.repair.resume.exhausted', 'quality', f'恢复检查点时有 {len(resumed_deferred)} 个问题已达到定向尝试上限，转人工确认', {'task_ids': resumed_deferred})
        if not queue:
            return {**_repair_queue_patch(repair_scope, []), 'quality_blocked': False, 'quality_cycle_attempts': cycle_attempts, 'quality_refunded_legacy_tasks': refunded_legacy_tasks}
        item = queue.pop(0)
        chapter_number = int(item['chapter'])
        raw_issues = [str(value) for value in item.get('issues', [])]
        contract_diagnostics = list(item.get('contract_diagnostics', []))
        task_ids = [str(value) for value in item.get('task_ids', []) if str(value)]
        repair_round = int(state.get('quality_repair_round', 1))
        repair_agents = [str(value) for value in item.get('repair_agents', [])]
        course_root = settings.courses_root / state['course_slug']
        latest_results = _latest_batch_results(state)
        chapter_result = next((chapter for batch in latest_results for chapter in batch.get('chapters', []) if chapter.get('chapter') == chapter_number), {})
        relative = str(item.get('path') or chapter_result.get('path', ''))
        target = course_root / relative if relative else None
        if not target or not target.exists():
            raise FileNotFoundError(f'第 {chapter_number} 章正文不存在，无法定向修复')
        markdown = target.read_text(encoding='utf-8')
        original_markdown = markdown
        before_contract = workflow_context.execute_tool('course.source_contract', caller='workflow.repair', course_slug=state['course_slug'], chapter_numbers=[chapter_number])
        issues, advisory_issues, operation_incidents, task_ids = separate_repair_findings(
            raw_issues=raw_issues,
            task_ids=task_ids,
            effective_chars=int(chapter_result.get('effective_chars') or 0) or None,
            effective_char_min=int(chapter_result.get('effective_char_min') or 0) or None,
            accept_advisory=lambda task_id: transition_task(task_id, 'advisory_accepted', verification={
                'outcome': 'advisory',
                'reason': '该 Finding 不阻塞课程交付，保留为后续可优化项。',
                'verified_at': utcnow(),
            }),
            record_incident=lambda issue: append_event(run_id, 'operation.incident', 'generation', f'第 {chapter_number} 章：运行故障不进入章节修复队列', {
                'chapter': chapter_number,
                'issue': issue,
                'origin': 'legacy_repair_queue',
            }),
        )
        if not issues:
            updated_chapter = {
                **chapter_result,
                'issues': [],
                'advisory_issues': advisory_issues,
                'operation_incidents': operation_incidents,
                'passed': True,
            }
            updated_results = _replace_quality_chapter_result(
                state.get('batch_results', []), chapter_number, updated_chapter
            )
            _persist_latest_batch_quality_results(course_root, updated_results)
            return {
                'batch_results': updated_results,
                **_repair_queue_patch(repair_scope, queue),
                'quality_blocked': False,
                'quality_cycle_attempts': cycle_attempts,
                'quality_refunded_legacy_tasks': refunded_legacy_tasks,
                'repair_scope': repair_scope,
                'batch_repair_batch_id': None if repair_scope == 'batch' and not queue else state.get('batch_repair_batch_id'),
            }
        normalized_task_ids: list[str] = []
        for issue in issues:
            normalized = create_or_refresh_task(normalize_quality_issue(course_slug=state['course_slug'], run_id=run_id, batch_id=str(item.get('batch', {}).get('id') or '') or None, chapter=chapter_number, issue=issue, path=relative, markdown=markdown))
            normalized_task_ids.append(normalized['id'])
        if normalized_task_ids:
            for old_task_id in task_ids:
                if old_task_id not in normalized_task_ids:
                    transition_task(old_task_id, 'stale_evidence', verification={'outcome': 'stale_evidence', 'reason': '已由包含审校原文证据的新 RepairTask 替代。'})
            task_ids = list(dict.fromkeys(normalized_task_ids))
        active_task_ids: list[str] = []
        task_issue_by_id: dict[str, str] = {}
        for task_id in task_ids:
            task = refresh_evidence(task_id, markdown)
            if task.get('status') == 'stale_evidence':
                append_event(run_id, 'quality.repair.task.stale_evidence', 'quality', f'第 {chapter_number} 章：RepairTask 的原始证据已过期，不再重复修复', {'task_id': task_id, 'chapter': chapter_number})
                continue
            active_task_ids.append(task_id)
            task_issue_by_id[task_id] = str(task.get('issue') or '')
        if task_ids and (not active_task_ids):
            return {**_repair_queue_patch(repair_scope, queue), 'quality_cycle_attempts': cycle_attempts, 'quality_refunded_legacy_tasks': refunded_legacy_tasks, 'active_repair_task_id': None, 'repair_scope': repair_scope}
        chapter_plan = next((chapter for module in state.get('blueprint', {}).get('modules', []) for chapter in module.get('chapters', []) if chapter.get('number') == chapter_number), {'number': chapter_number, 'title': chapter_result.get('title', '待修复章节')})
        module = next((module for module in state.get('blueprint', {}).get('modules', []) if any((chapter.get('number') == chapter_number for chapter in module.get('chapters', [])))), {'title': '课程质量闭环', 'goal': '修复已记录质量问题', 'chapters': []})
        context = _context_pack(state, module, chapter_plan, state.get('continuity_ledger', []), state.get('feedback', ''))
        context['quality_review_evidence'] = issues
        context['repair_agents'] = item.get('repair_agents', [])
        append_event(run_id, 'quality.repair.chapter.started', 'quality', f'第 {chapter_number} 章：集中修复 {len(active_task_ids)} 个已知问题（后续剩余 {len(queue)} 章）', {'chapter': chapter_number, 'issues': issues, 'repair_agents': repair_agents, 'repair_round': repair_round})
        for task_id in active_task_ids:
            record_attempt(task_id, 'planned', plan={'scope': 'chapter_local', 'strategy': repair_agents or ['deterministic_first_then_local_revision'], 'issues': [task_issue_by_id.get(task_id, '质量问题')]})
            transition_task(task_id, 'planned')
        append_event(run_id, 'recovery.supervisor.plan', 'quality', f'异常恢复 Agent：第 {chapter_number} 章已完成诊断，将按记录证据执行最小修复并重新验证', {'chapter': chapter_number, 'repair_round': repair_round, 'issues': issues, 'strategy': repair_agents, 'mode': 'deterministic_first_then_chapter_local_llm'})
        operations: list[str] = []
        forced_remaining_issues: list[str] = []
        handled_contract_codes: set[str] = set()
        for diagnostic in contract_diagnostics:
            code = str(diagnostic.get('code') or '')
            if code != 'REFERENCE_SECTION_MISSING':
                continue
            candidates = list(diagnostic.get('candidates') or [])
            decision = workflow_context.timed_quality_operation('reference_role_classification', f'第 {chapter_number} 章：正在识别参考资料区块的语义角色', chapter=chapter_number, repair_round=repair_round, operation=lambda diagnostic=diagnostic, candidates=candidates: workflow_context.invoke_agent('reviewer.agent', 'classify_reference_section', diagnostic, candidates, context))
            append_event(run_id, 'quality.repair.reference_role.classified', 'quality', f'第 {chapter_number} 章：参考资料区块识别为 {decision.role}（置信度 {decision.confidence:.2f}）', {'chapter': chapter_number, 'decision': decision.model_dump(mode='json')})
            if decision.role == 'references' and decision.node_id and diagnostic.get('source_hash'):
                markdown, reference_changed = _normalize_reference_node(markdown, decision.node_id)
                if reference_changed:
                    handled_contract_codes.add(code)
                    operations.append('参考文献 AST 节点确定性规范化')
                append_event(run_id, 'quality.repair.reference_heading.normalized', 'quality', f'第 {chapter_number} 章：仅将 Agent 选中的标题节点规范为“参考文献”', {'chapter': chapter_number, 'node_id': decision.node_id, 'changed': reference_changed})
        if any(('参考文献' in issue or '外部链接' in issue for issue in issues)):
            markdown, links_changed = _relocate_external_links_to_references(markdown)
            if links_changed:
                handled_contract_codes.add('EXTERNAL_LINK_BEFORE_REFERENCES')
                operations.append('参考文献前外部链接确定性迁移')
                append_event(run_id, 'quality.repair.deterministic_link_fix.completed', 'quality', f'第 {chapter_number} 章：已把正文 URL 迁入参考文献并保留原位置说明', {'chapter': chapter_number, 'repair_round': repair_round})
        if any(('章首必须且只能包含' in issue or 'INTRO_NON_CANONICAL' in issue for issue in issues)):
            markdown, intro_changed = _normalize_lesson_intro(markdown)
            if intro_changed:
                handled_contract_codes.add('INTRO_NON_CANONICAL')
                operations.append('章首结构确定性修复')
                append_event(run_id, 'quality.repair.deterministic_intro_fix.completed', 'quality', f'第 {chapter_number} 章：已修复预计学习时间与一句话总结格式', {'chapter': chapter_number, 'repair_round': repair_round})
        if any(('代码围栏未闭合' in issue for issue in issues)):
            markdown, fence_changed = _close_unclosed_markdown_fence(markdown)
            if fence_changed:
                operations.append('Markdown 代码围栏确定性修复')
                append_event(run_id, 'quality.repair.deterministic_fence_fix.completed', 'quality', f'第 {chapter_number} 章：已闭合缺失的 Markdown 代码围栏', {'chapter': chapter_number, 'repair_round': repair_round})
        for issue in issues:
            if '本地链接目标不存在' not in issue:
                continue
            markdown, image_changed = _remove_missing_local_image(markdown, issue)
            if image_changed:
                operations.append('缺失本地图片引用确定性修复')
                append_event(run_id, 'quality.repair.deterministic_asset_fix.completed', 'quality', f'第 {chapter_number} 章：已移除无法解析的本地图片引用并保留图示说明', {'chapter': chapter_number, 'repair_round': repair_round})
        if any(('本机私有路径' in issue for issue in issues)):
            markdown, paths_changed = _redact_private_paths(markdown)
            if paths_changed:
                operations.append('本机私有路径确定性清理')
                append_event(run_id, 'quality.repair.deterministic_private_path_fix.completed', 'quality', f'第 {chapter_number} 章：已移除学生可见内容中的本机私有路径', {'chapter': chapter_number, 'repair_round': repair_round})
        unresolved_contract_codes = _contract_codes_requiring_llm(contract_diagnostics, handled=handled_contract_codes)
        needs_enrichment = any(('有效字符' in issue for issue in issues))
        needs_semantic_revision = any((marker in issue for issue in issues for marker in ('[blocker]', '[major]', '[minor]', '语义', '事实', '连续性')))
        needs_diagnostic_revision = any(('确定性构建或校验未通过' in issue for issue in issues)) or bool(unresolved_contract_codes)
        needs_humanizer = any(('Humanizer' in issue for issue in issues)) or (isinstance(chapter_result.get('humanizer_score'), (int, float)) and chapter_result['humanizer_score'] < 45)
        repair_tasks_by_id = {str(candidate.get('id')): candidate for candidate in list_repair_tasks(run_id)}
        context['active_repair_tasks'] = [{'id': task_id, 'issue': task_issue_by_id.get(task_id, '质量问题'), 'evidence': repair_tasks_by_id.get(task_id, {}).get('evidence', {}), 'success_criteria': repair_tasks_by_id.get(task_id, {}).get('success_criteria', [])} for task_id in active_task_ids]
        deterministic_commit = commit_deterministic_repair(
            course_slug=state['course_slug'],
            relative_path=relative,
            original_markdown=original_markdown,
            repaired_markdown=markdown,
            reason=f'批次定向修复第 {repair_round} 轮：第 {chapter_number} 章确定性修复',
            run_id=run_id,
            operations=operations,
            source_contract=lambda: workflow_context.execute_tool(
                'course.source_contract',
                caller='workflow.repair',
                course_slug=state['course_slug'],
                chapter_numbers=[chapter_number],
            ),
        )
        if deterministic_commit:
            original_markdown = str(deterministic_commit['content'])
            append_event(
                run_id,
                'quality.repair.deterministic_committed',
                'quality',
                f'第 {chapter_number} 章：确定性修复已先行提交，后续模型调用失败也不会回滚该结果',
                {
                    'chapter': chapter_number,
                    'candidate_id': deterministic_commit['candidate_id'],
                    'source_contract_passed': deterministic_commit['source_contract_passed'],
                    'operations': operations,
                },
            )
        sweep_tasks = chapter_repair_sweep_tasks({'issues': issues, 'task_ids': task_ids}, active_task_ids=active_task_ids)
        for sweep_task in sweep_tasks:
            task_id = sweep_task['task_id']
            task_issue = sweep_task['issue']
            task_requires_llm = any((marker in task_issue for marker in ('[blocker]', '[Blocker]', '[major]', '[Major]', '[minor]', '[Minor]', '语义', '事实', '连续性', '确定性构建或校验未通过'))) or any((f'[{code}]' in task_issue for code in unresolved_contract_codes))
            if not task_requires_llm:
                continue
            task = repair_tasks_by_id.get(task_id, {'id': task_id, 'issue': task_issue})
            task_context = {**context, 'quality_review_evidence': [task_issue]}
            plan = workflow_context.timed_quality_operation('repair_planning', f'第 {chapter_number} 章：RepairTask 正在规划最小修复范围', chapter=chapter_number, repair_round=repair_round, operation=lambda task=task, task_context=task_context: workflow_context.invoke_agent('repair.agent', 'plan_repair', task, markdown, task_context))
            append_event(run_id, 'quality.repair.task.planned', 'quality', f"第 {chapter_number} 章：已规划 {plan.scope} 级修复，能力：{'、'.join(plan.selected_capabilities)}", {'task_id': task_id, 'issue': task_issue, 'plan': plan.model_dump(mode='json')})
            if plan.scope == 'chapter' or 'chapter_rewrite' in plan.selected_capabilities:
                markdown = workflow_context.timed_quality_operation('revising', f'第 {chapter_number} 章：升级修复 Agent 正在进行受控重构', chapter=chapter_number, repair_round=repair_round, operation=lambda task_context=task_context, task_issue=task_issue: workflow_context.invoke_agent('repair.agent', 'revise_chapter', markdown, {**task_context, 'instruction': task_issue}))
                operations.append('升级修复 Agent')
                continue
            patch_output = workflow_context.timed_quality_operation('repair_patching', f'第 {chapter_number} 章：RepairTask 正在应用最小补丁', chapter=chapter_number, repair_round=repair_round, operation=lambda task=task, task_context=task_context, plan=plan: workflow_context.invoke_agent('repair.agent', 'apply_repair_patch', task, markdown, task_context, plan))
            applied = 0
            for patch in patch_output.patches:
                if patch.original in markdown:
                    markdown = markdown.replace(patch.original, patch.replacement, 1)
                    applied += 1
            used_section_fallback = False
            if not applied:
                rejection = {'outcome': 'patch_anchor_mismatch', 'reason': '模型补丁锚点未命中，已升级到纯 LLM 目标小节重写。', 'task_id': task_id}
                record_attempt(task_id, 'patch_rejected', verification=rejection)
                transition_task(task_id, 'section_rewrite', verification=rejection)
                append_event(run_id, 'quality.repair.task.patch_escalated', 'quality', f'第 {chapter_number} 章：锚点补丁未命中，正在执行小节级 LLM 兜底', rejection)
                source_hash = hashlib.sha256(markdown.encode('utf-8')).hexdigest()
                try:
                    rewritten = workflow_context.timed_quality_operation('section_rewrite', f'第 {chapter_number} 章：纯 LLM 兜底正在重写目标小节', chapter=chapter_number, repair_round=repair_round, operation=lambda task=task, task_context=task_context, source_hash=source_hash: workflow_context.invoke_agent('repair.agent', 'rewrite_section', task, markdown, task_context, expected_hash=source_hash))
                    if rewritten.original_section not in markdown:
                        raise ValueError('小节重写锚点未命中当前章节正文')
                    markdown = markdown.replace(rewritten.original_section, rewritten.replacement_section, 1)
                    applied = 1
                    used_section_fallback = True
                    operations.append('纯 LLM 目标小节重写兜底')
                except Exception as error:
                    reason = f'小节重写兜底失败：{error}'
                    forced_remaining_issues.append(reason)
                    record_attempt(task_id, 'section_rewrite_failed', verification={'outcome': 'unresolved', 'reason': reason})
                    transition_task(task_id, 'human_decision_required' if repair_round >= 3 else 'unresolved', verification={'outcome': 'unresolved', 'reason': reason})
                    append_event(run_id, 'quality.repair.task.section_rewrite_failed', 'quality', f'第 {chapter_number} 章：小节兜底未成功，已记录并继续处理本章其他问题', {'task_id': task_id, 'reason': reason})
            if applied:
                operations.append('RepairTask 分级修复' if used_section_fallback else 'RepairTask 最小补丁')
            append_event(run_id, 'quality.repair.task.patched', 'quality', f'第 {chapter_number} 章：已应用 {applied} 个锚点内补丁', {'task_id': task_id, 'issue': task_issue, 'patches': applied})
        if needs_enrichment:
            markdown = workflow_context.timed_quality_operation('enriching', f'第 {chapter_number} 章：内容丰富化 Agent 正在补齐缺失教学层', chapter=chapter_number, repair_round=repair_round, operation=lambda: workflow_context.invoke_agent('repair.agent', 'enrich_chapter', markdown, context, issues))
            operations.append('内容丰富化 Agent')
        if (needs_semantic_revision or needs_diagnostic_revision) and (not active_task_ids):
            markdown = workflow_context.timed_quality_operation('revising', f'第 {chapter_number} 章：异常恢复 Agent 正在依据诊断定向修复', chapter=chapter_number, repair_round=repair_round, operation=lambda: workflow_context.invoke_agent('repair.agent', 'revise_chapter', markdown, {**context, 'instruction': '；'.join(issues)}))
            operations.append('异常恢复 / 教学语义修订 Agent')
        should_run_unified_gates = needs_humanizer or needs_enrichment or needs_semantic_revision or needs_diagnostic_revision
        if should_run_unified_gates:
            append_event(run_id, 'quality.repair.chapter.patch_sweep.completed', 'quality', f'第 {chapter_number} 章：全部已知补丁已处理，开始统一质量复验', {'chapter': chapter_number, 'repair_round': repair_round, 'task_count': len(active_task_ids), 'operations': operations})
        if should_run_unified_gates:
            humanized = workflow_context.timed_quality_operation('humanizing', f'第 {chapter_number} 章：Humanizer 闸门复核', chapter=chapter_number, repair_round=repair_round, operation=lambda: workflow_context.invoke_agent('reviewer.agent', 'humanize', markdown))
            markdown = humanized.revised_markdown
            humanizer_score = humanized.score
            operations.append('Humanizer 闸门')
        else:
            humanizer_score = chapter_result.get('humanizer_score')
            append_event(run_id, 'quality.repair.gate_reused', 'quality', f'第 {chapter_number} 章：本轮仅修改确定性结构，沿用已通过的 Humanizer 与语义结果', {'chapter': chapter_number, 'repair_round': repair_round})
        effective_chars = _effective_char_count(markdown)
        if needs_enrichment or needs_semantic_revision or needs_diagnostic_revision:
            review_output = workflow_context.timed_quality_operation('semantic_review', f'第 {chapter_number} 章：教学语义与事实审校复核', chapter=chapter_number, repair_round=repair_round, operation=lambda: workflow_context.invoke_agent('reviewer.agent', 'semantic_review', markdown, context))
            semantic_review = review_output.model_dump(mode='json')
            operations.append('教学语义与事实审校')
        else: semantic_review = dict(chapter_result.get('semantic_review') or {})
        markdown, final_intro_changed = _normalize_lesson_intro(markdown); operations += ['最终章首结构规范化'] if final_intro_changed else []
        effective_minimum = int(state['request'].get('effective_char_min', 12000))
        remaining_issues: list[str] = list(forced_remaining_issues)
        if isinstance(humanizer_score, (int, float)) and humanizer_score < 45:
            remaining_issues.append(f'Humanizer {humanizer_score}/50，低于 45')
        if effective_chars < effective_minimum:
            remaining_issues.append(f'有效字符 {effective_chars}，低于规格 {effective_minimum}')
        semantic_decision = semantic_review.get('decision')
        repair_verification_by_id = {str(value.get('task_id') or ''): value for value in semantic_review.get('repair_verifications', [])}
        if semantic_decision not in {None, 'ready'}:
            remaining_issues.extend(semantic_review.get('issues') or [f'语义结论为 {semantic_decision}'])
        remaining_issues, advisory_remaining, operation_incidents = split_post_verification_findings(
            remaining_issues,
            effective_chars=effective_chars,
            effective_char_min=effective_minimum,
        )
        for incident in operation_incidents:
            append_event(run_id, 'operation.incident', 'quality', f'第 {chapter_number} 章：运行故障不进入章节修复队列', {'chapter': chapter_number, 'issue': incident, 'origin': 'quality_reverification'})
        markdown = markdown.rstrip() + '\n'
        candidate = commit_chapter_candidate(
            course_slug=state['course_slug'], relative_path=relative, content=markdown,
            expected_hash=hashlib.sha256(original_markdown.encode('utf-8')).hexdigest(),
            reason=f'整课质量闭环第 {repair_round} 轮：第 {chapter_number} 章定向修复',
            run_id=run_id,
        )
        chapter_contract = workflow_context.execute_tool('course.source_contract', caller='workflow.repair', course_slug=state['course_slug'], chapter_numbers=[chapter_number])
        for diagnostic in chapter_contract.get('diagnostics') or []:
            remaining_issues.append(f"[{diagnostic.get('code')}] {diagnostic.get('actual') or '当前结构'}；期望：{diagnostic.get('expected') or '满足课程结构契约'}")
        regressions = detect_quality_regressions(before={'effective_chars': chapter_result.get('effective_chars'), 'effective_char_min': chapter_result.get('effective_char_min', effective_minimum), 'humanizer_score': chapter_result.get('humanizer_score'), 'semantic_decision': (chapter_result.get('semantic_review') or {}).get('decision'), 'contract_codes': [str(value.get('code') or '') for value in before_contract.get('diagnostics') or []]}, after={'effective_chars': effective_chars, 'effective_char_min': effective_minimum, 'humanizer_score': humanizer_score, 'semantic_decision': semantic_decision, 'contract_codes': [str(value.get('code') or '') for value in chapter_contract.get('diagnostics') or []]})
        if regressions:
            reject_chapter_candidate(candidate['id'], {
                'outcome': 'rejected', 'reason': '非回归门发现新失败',
                'regressions': regressions,
            })
            rollback = commit_chapter_candidate(
                course_slug=state['course_slug'], relative_path=relative,
                content=original_markdown,
                expected_hash=hashlib.sha256(markdown.encode('utf-8')).hexdigest(),
                reason=f'非回归保护回滚：第 {chapter_number} 章定向修复引入新失败',
                run_id=run_id,
            )
            verify_chapter_candidate(rollback['id'], {
                'outcome': 'rollback_restored', 'regressions': regressions,
            })
            markdown = original_markdown
            humanizer_score = chapter_result.get('humanizer_score')
            effective_chars = int(chapter_result.get('effective_chars') or _effective_char_count(markdown))
            semantic_review = dict(chapter_result.get('semantic_review') or {})
            semantic_decision = semantic_review.get('decision')
            chapter_contract = before_contract
            remaining_issues = list(dict.fromkeys([*issues, '本次候选修复已回滚；非回归门发现：' + '；'.join(regressions)]))
            operations.append('非回归事务回滚')
            append_event(run_id, 'quality.repair.regression_rolled_back', 'quality', f'第 {chapter_number} 章：候选修复引入新失败，已原子恢复修复前正文', {'chapter': chapter_number, 'repair_round': repair_round, 'regressions': regressions})
        updated_chapter = {**chapter_result, 'humanizer_score': humanizer_score, 'effective_chars': effective_chars, 'effective_char_min': effective_minimum, 'semantic_review': semantic_review, 'issues': remaining_issues, 'advisory_issues': advisory_remaining, 'operation_incidents': operation_incidents, 'passed': not remaining_issues, 'deferred': False}
        updated_results = _replace_quality_chapter_result(state.get('batch_results', []), chapter_number, updated_chapter)
        _persist_latest_batch_quality_results(course_root, updated_results)
        for task_id in active_task_ids:
            cycle_attempts[task_id] = cycle_attempts.get(task_id, 0) + 1
        discovered_from_review: list[dict[str, Any]] = []
        for issue in remaining_issues:
            if issue.startswith('本次候选修复已回滚'):
                continue
            task = create_or_refresh_task(normalize_quality_issue(course_slug=state['course_slug'], run_id=run_id, batch_id=str(item.get('batch', {}).get('id') or '') or None, chapter=chapter_number, issue=issue, path=relative, markdown=markdown))
            discovered_from_review.append({'chapter': chapter_number, 'title': chapter_plan.get('title', chapter_result.get('title', '')), 'path': relative, 'issues': [issue], 'repair_agents': _repair_agents_for_chapter({**updated_chapter, 'issues': [issue]}), 'batch': item.get('batch', {}), 'task_ids': [task['id']]})
        seen_chapters = {int(result.get('chapter') or 0) for result in state.get('quality_repair_round_results', [])} | {chapter_number}
        queue, review_added, review_deferred, deferred_review, discovery_sweeps, review_budget_exhausted = merge_round_discoveries(queue, discovered_from_review, attempts=cycle_attempts, seen_chapters=seen_chapters, discovery_sweeps=discovery_sweeps, max_discovery_sweeps=max_discovery_sweeps)
        if deferred_review:
            append_event(run_id, 'quality.repair.next_round.deferred', 'quality', f'第 {chapter_number} 章复验发现 {len(deferred_review)} 个新问题，已登记到下一轮候选，不在本轮重复修复', {'chapters': [entry.get('chapter') for entry in deferred_review]})
        if review_budget_exhausted:
            defer_discovery_budget(review_deferred, 'chapter_review')
        cycle_new_issue_count = len(review_added)
        if review_added:
            append_event(run_id, 'quality.repair.same_cycle.review_discovered', 'quality', f'第 {chapter_number} 章统一复验发现 {len(review_added)} 个新问题，已聚合为本轮下一次 Repair Sweep', {'chapter': chapter_number, 'repair_round': repair_round, 'task_ids': review_added})
        if review_deferred and (not review_budget_exhausted):
            append_event(run_id, 'quality.repair.same_cycle.exhausted', 'quality', f'第 {chapter_number} 章有 {len(review_deferred)} 个问题已完成两次定向尝试，转人工确认', {'chapter': chapter_number, 'repair_round': repair_round, 'task_ids': review_deferred})
        build: dict[str, Any] = {'succeeded': False, 'stdout': '', 'stderr': '尚未进入构建门', 'exit_code': None}
        validation: dict[str, Any] = {'succeeded': False, 'stdout': '', 'stderr': '尚未进入产物门', 'exit_code': None}
        if not queue:
            full_source_scan = workflow_context.timed_quality_operation('source_contract', '本批次队列暂时清空：正在重新扫描当前批次 Markdown 结构并吸收新问题' if repair_scope == 'batch' else '本轮队列暂时清空：正在重新扫描全部 Markdown 结构并吸收新问题', repair_round=repair_round, operation=lambda: workflow_context.execute_tool('course.source_contract', caller='workflow.repair', course_slug=state['course_slug'], **{'chapter_numbers': scope_chapter_numbers} if scope_chapter_numbers else {}))
            all_current_chapters = [chapter for result in _latest_batch_results({**state, 'batch_results': updated_results}) for chapter in result.get('chapters', []) if not scope_chapter_numbers or int(chapter.get('chapter') or 0) in scope_chapter_numbers]
            discovered = _batch_contract_repair_entries(full_source_scan, active_batch or {}, all_current_chapters) if repair_scope == 'batch' else _contract_repair_entries(full_source_scan, all_current_chapters)
            if discovered:
                batch_by_chapter = {int(chapter.get('chapter')): result.get('batch', {}) for result in _latest_batch_results({**state, 'batch_results': updated_results}) for chapter in result.get('chapters', []) if chapter.get('chapter')}
                grounded_discovered = []
                for entry in discovered:
                    entry_tasks = []
                    entry_markdown = (course_root / str(entry.get('path') or '')).read_text(encoding='utf-8')
                    for issue in entry.get('issues', []):
                        task = create_or_refresh_task(normalize_quality_issue(course_slug=state['course_slug'], run_id=run_id, batch_id=str(batch_by_chapter.get(int(entry['chapter']), {}).get('id') or '') or None, chapter=int(entry['chapter']), issue=str(issue), path=str(entry.get('path') or ''), markdown=entry_markdown))
                        entry_tasks.append(task['id'])
                    grounded_discovered.append({**entry, 'batch': batch_by_chapter.get(int(entry['chapter']), {}), 'task_ids': entry_tasks})
                queue, source_added, source_deferred, deferred_source, discovery_sweeps, source_budget_exhausted = merge_round_discoveries(queue, grounded_discovered, attempts=cycle_attempts, seen_chapters=seen_chapters, discovery_sweeps=discovery_sweeps, max_discovery_sweeps=max_discovery_sweeps)
                if deferred_source:
                    append_event(run_id, 'quality.repair.next_round.deferred', 'quality', f'结构复扫发现 {len(deferred_source)} 个已处理章节的问题，已登记到下一轮候选', {'chapters': [entry.get('chapter') for entry in deferred_source]})
                if source_budget_exhausted:
                    defer_discovery_budget(source_deferred, 'source_contract')
                if source_added:
                    cycle_new_issue_count += len(source_added)
                    append_event(run_id, 'quality.repair.same_cycle.discovered', 'quality', f'本轮复扫发现 {len(source_added)} 个结构问题，已加入当前修复队列', {'repair_round': repair_round, 'task_ids': source_added})
                if source_deferred and (not source_budget_exhausted):
                    append_event(run_id, 'quality.repair.same_cycle.exhausted', 'quality', f'本轮有 {len(source_deferred)} 个结构问题已达到两次定向尝试上限', {'repair_round': repair_round, 'task_ids': source_deferred})
            elif full_source_scan.get('succeeded'):
                build = workflow_context.timed_quality_operation('course_build', '源文件门通过：正在构建当前批次修订的课程产物' if repair_scope == 'batch' else '源文件门通过：正在构建当前修订的课程产物', repair_round=repair_round, operation=lambda: workflow_context.execute_tool('course.build', caller='workflow.repair', course_slug=state['course_slug'], **{'chapter_numbers': scope_chapter_numbers} if scope_chapter_numbers else {}))
                validation = workflow_context.timed_quality_operation('course_validation', '构建完成：正在验证当前批次 build revision 的课程产物' if repair_scope == 'batch' else '构建完成：正在验证当前 build revision 的课程产物', repair_round=repair_round, operation=lambda: workflow_context.execute_tool('course.validate', caller='workflow.repair', course_slug=state['course_slug'], chapter_numbers=scope_chapter_numbers) if repair_scope == 'batch' and build.get('succeeded') else {'succeeded': False, 'stdout': '', 'stderr': '批次构建失败，未运行批次确定性检查'} if repair_scope == 'batch' else _full_course_validation_after_build(state['course_slug'], build, validate_tool=lambda: workflow_context.execute_tool('course.validate', caller='workflow.repair', course_slug=state['course_slug'])))
                updated_results = _replace_batch_integration(updated_results, str((active_batch or {}).get('id') or ''), build, validation) if repair_scope == 'batch' else _refresh_quality_integration(updated_results, build, validation)
                artifact_entries = _integration_repair_entries({'chapters': all_current_chapters, 'build': build, 'validation': validation})
                if artifact_entries:
                    grounded_artifacts = []
                    for entry in artifact_entries:
                        entry_markdown = (course_root / str(entry.get('path') or '')).read_text(encoding='utf-8')
                        entry_tasks = []
                        for issue in entry.get('issues', []):
                            task = create_or_refresh_task(normalize_quality_issue(course_slug=state['course_slug'], run_id=run_id, batch_id=str((active_batch or {}).get('id') or '') or None if repair_scope == 'batch' else None, chapter=int(entry['chapter']), issue=str(issue), path=str(entry.get('path') or ''), markdown=entry_markdown))
                            entry_tasks.append(task['id'])
                        grounded_artifacts.append({**entry, 'batch': active_batch if repair_scope == 'batch' else entry.get('batch', {}), 'task_ids': entry_tasks})
                    queue, artifact_added, artifact_deferred, deferred_artifacts, discovery_sweeps, artifact_budget_exhausted = merge_round_discoveries(queue, grounded_artifacts, attempts=cycle_attempts, seen_chapters=seen_chapters, discovery_sweeps=discovery_sweeps, max_discovery_sweeps=max_discovery_sweeps)
                    if deferred_artifacts:
                        append_event(run_id, 'quality.repair.next_round.deferred', 'quality', f'构建/产物门发现 {len(deferred_artifacts)} 个已处理章节的问题，已登记到下一轮候选', {'chapters': [entry.get('chapter') for entry in deferred_artifacts]})
                    if artifact_budget_exhausted:
                        defer_discovery_budget(artifact_deferred, 'build_or_validation')
                    if artifact_added:
                        cycle_new_issue_count += len(artifact_added)
                        append_event(run_id, 'quality.repair.same_cycle.artifact_discovered', 'quality', f'构建/产物门发现 {len(artifact_added)} 个新问题，已加入当前修复队列', {'repair_round': repair_round, 'task_ids': artifact_added})
                _persist_latest_batch_quality_results(course_root, updated_results)
        round_results = upsert_round_chapter_result(state.get('quality_repair_round_results', []), {'chapter': chapter_number, 'title': chapter_plan.get('title', chapter_result.get('title', '')), 'issues_before': issues, 'operations': operations, 'remaining_issues': remaining_issues, 'passed': not remaining_issues})
        history = list(state.get('quality_repair_history', []))
        if not queue:
            round_summary = {'round': repair_round, 'chapters': round_results, 'repaired_count': sum((1 for result in round_results if result['passed'])), 'remaining_count': sum((1 for result in round_results if not result['passed'])), 'build_succeeded': bool(build.get('succeeded')), 'validation_succeeded': bool(validation.get('succeeded'))}
            history.append(round_summary)
            append_event(run_id, 'quality.repair.round.completed', 'quality', f"{('当前批次' if repair_scope == 'batch' else '整课')}定向修复第 {repair_round} 轮完成：{round_summary['repaired_count']} 章本轮通过，{round_summary['remaining_count']} 章仍有章节级问题", round_summary)
        append_event(run_id, 'quality.repair.chapter.completed', 'quality', f"{('批次' if repair_scope == 'batch' else '整课')}修复队列：第 {chapter_number} 章修复完成，{('仍有问题' if remaining_issues else '章节质量门通过')}", {'chapter': chapter_number, 'remaining_issues': remaining_issues, 'remaining_queue': len(queue), 'repair_round': repair_round, 'operations': operations})
        append_event(run_id, 'recovery.supervisor.result', 'quality', f"异常恢复 Agent：第 {chapter_number} 章已完成本轮修复，{('仍保留待人工审核项' if remaining_issues else '对应质量门已通过')}", {'chapter': chapter_number, 'repair_round': repair_round, 'operations': operations, 'remaining_issues': remaining_issues})
        verification = {'outcome': 'verified' if not remaining_issues else 'unresolved', 'diagnostic_code': str(contract_diagnostics[0].get('code')) if len(contract_diagnostics) == 1 else 'CHAPTER_QUALITY_GATES', 'source_revision': chapter_contract.get('source_revision'), 'verified_at': utcnow(), 'effective_chars': effective_chars, 'humanizer_score': humanizer_score, 'semantic_decision': semantic_decision, 'remaining_issues': remaining_issues}
        if not regressions:
            verify_chapter_candidate(candidate['id'], verification)
        current_contract_codes = {str(value.get('code') or '') for value in chapter_contract.get('diagnostics') or []}
        for task_id in active_task_ids:
            targeted_verification = repair_verification_by_id.get(task_id)
            task_resolved = (bool(targeted_verification.get('resolved')) if targeted_verification is not None else _repair_issue_is_resolved(task_issue_by_id.get(task_id, ''), contract_codes=current_contract_codes, remaining_issues=remaining_issues, humanizer_score=humanizer_score, effective_chars=effective_chars, effective_minimum=effective_minimum, semantic_decision=semantic_decision)) and (not regressions)
            task_verification = {**verification, 'outcome': 'verified' if task_resolved else 'unresolved', 'target_issue': task_issue_by_id.get(task_id, ''), 'targeted_semantic_verification': targeted_verification}
            record_attempt(task_id, 'verified', verification=task_verification)
            transition_task(task_id, 'fixed_verified' if task_resolved else 'human_decision_required' if cycle_attempts.get(task_id, 0) >= 2 else 'unresolved', verification=task_verification)
        course_integration = None
        if not queue and repair_scope == 'course':
            course_integration = {'passed': bool(build.get('succeeded')) and bool(validation.get('succeeded')), 'build': build, 'validation': validation, 'label': '整课构建与确定性检查'}
        cycle_state = {'cycle_id': str(state.get('quality_cycle_id') or f'{run_id}:quality:{repair_round}'), 'iteration': int(state.get('quality_cycle_iteration', 0)) + 1, 'queue_size': len(queue), 'new_issue_count': cycle_new_issue_count, 'discovery_sweeps': discovery_sweeps, 'max_discovery_sweeps': max_discovery_sweeps, 'current_chapter': chapter_number, 'escalation_level': 'section_rewrite' if '纯 LLM 目标小节重写兜底' in operations else 'deterministic', 'converged': not queue and bool(build.get('succeeded')) and bool(validation.get('succeeded'))}
        _persist_latest_batch_quality_results(course_root, updated_results, repair_tasks=list_repair_tasks(run_id), course_integration=course_integration, source_contract={'passed': bool(chapter_contract.get('succeeded')), 'diagnostics': chapter_contract.get('diagnostics') or [], 'revision': chapter_contract.get('source_revision')}, build={'passed': bool(build.get('succeeded')), 'revision': build.get('build_revision')}, artifact_validation={'passed': bool(validation.get('succeeded')) if build.get('succeeded') else None}, quality_cycle=cycle_state)
        return {'batch_results': updated_results, **_repair_queue_patch(repair_scope, queue), 'quality_cycle_attempts': cycle_attempts, 'quality_cycle_discovery_sweeps': discovery_sweeps, 'quality_refunded_legacy_tasks': refunded_legacy_tasks, 'quality_cycle': cycle_state, 'quality_cycle_id': cycle_state['cycle_id'], 'quality_cycle_iteration': cycle_state['iteration'], 'quality_blocked': discovery_budget_exhausted or (bool(queue) or not (bool(build.get('succeeded')) and bool(validation.get('succeeded'))) if repair_scope == 'batch' and (not queue) else bool(remaining_issues)), 'current_batch_index': state.get('current_batch_index', 0) + 1 if repair_scope == 'batch' and (not queue) and bool(build.get('succeeded')) and bool(validation.get('succeeded')) else state.get('current_batch_index', 0), 'feedback': state.get('feedback', ''), 'quality_repair_round_results': [] if not queue else round_results, 'quality_repair_history': history, 'active_repair_task_id': active_task_ids[-1] if active_task_ids else None, 'repair_scope': repair_scope, 'batch_repair_batch_id': None if repair_scope == 'batch' and (not queue) else state.get('batch_repair_batch_id')}
    def route_quality_repair(state: CourseAgentState) -> str:
        queue = _repair_queue_for_scope(state)
        if queue:
            return 'next'
        if state.get('repair_scope') == 'batch':
            if state.get('quality_blocked'):
                return 'manual'
            return _batch_repair_completion_route(state)
        return 'course_quality'
    def request_batch_review(state: CourseAgentState) -> dict[str, Any]:
        """Ask for help only after automatic, evidence-led repair is exhausted."""
        result = state['batch_results'][-1]
        repairing_course_quality = bool(state.get('quality_repair_active'))
        if not repairing_course_quality and state['current_batch_index'] >= len(state['batches']):
            return {'approval': 'APPROVE'}
        decision = interrupt({'type': 'BATCH_REVIEW_REQUIRED', 'step': 'generation', 'title': f"{_batch_display_label(result['batch'])} 需要人工建议", 'output': result, 'actions': ['REVISE', 'STOP'] if repairing_course_quality else ['REVISE', 'APPROVE', 'STOP']})
        patch = {'feedback': decision.get('feedback', '').strip(), 'approval': decision['action']} if repairing_course_quality else _global_change_patch(state, decision, 'generation')
        if decision['action'] == 'REVISE':
            patch['retry_count'] = 0
        elif decision['action'] == 'APPROVE':
            patch['current_batch_index'] = state['current_batch_index'] + 1
            patch['retry_count'] = 0
        return patch

    return SimpleNamespace(repair_open_chapters=repair_open_chapters, route_quality_repair=route_quality_repair, request_batch_review=request_batch_review)
