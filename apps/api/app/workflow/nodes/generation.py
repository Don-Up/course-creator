from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from app.workflow.node_context import WorkflowContext
from app.workflow.quality_cycle import merge_repair_queue
from app.workflow.repair_tasks import create_or_refresh_task, list_repair_tasks, normalize_quality_issue, split_quality_issues
from app.workflow.repository import append_event
from app.workflow.services.batch_planning import _batch_display_label, _generation_cursor_exhausted, _plain_title
from app.workflow.services.context_packs import (
    _chapter_resume_stage,
    _context_pack,
    _deferred_chapter_quality_result,
    _effective_char_count,
    _effective_content_deficit,
    _retry_initial_chapter_write,
)
from app.workflow.services.course_quality import _batch_contract_repair_entries, _normalize_lesson_intro
from app.workflow.services.quality_integration import _persist_latest_batch_quality_results
from app.workflow.services.workspace_contract import _load_chapter_progress, _save_chapter_progress, _write_json
from app.workflow.services.artifact_commits import commit_chapter_candidate, verify_chapter_candidate
from app.workflow.state import CourseAgentState


def _register_generated_chapter(
    lessons: dict[int, dict[str, Any]],
    *,
    chapter: dict[str, Any],
    module_title: str,
    title: str,
    relative_path: str,
) -> None:
    """Record a persisted Markdown source independently from quality status."""
    lessons[int(chapter["number"])] = {
        "number": int(chapter["number"]),
        "module": module_title,
        "title": title,
        "time": "按正文展开",
        "summary": chapter["learning_outcome"],
        "status": "available",
        "href": f"lessons/{Path(relative_path).stem}.html",
        "markdown": relative_path,
    }


def create_generation_nodes(context: WorkflowContext) -> SimpleNamespace:
    run_id = context.run_id
    provider = context.provider
    settings = context.settings
    workflow_context = context

    def generate_batch(state: CourseAgentState) -> dict[str, Any]:
        if _generation_cursor_exhausted(state):
            latest = _latest_batch_results(state)
            return {'quality_blocked': any((not result.get('passed') for result in latest)), 'repair_scope': 'course', 'batch_repair_active': False, 'batch_repair_queue': [], 'batch_repair_batch_id': None}
        index = state['current_batch_index']
        batch = state['batches'][index]
        module = state['blueprint']['modules'][batch['module_index']]
        course_root = settings.courses_root / state['course_slug']
        metadata_path = course_root / 'course.json'
        metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
        existing = {item['number']: item for item in metadata.get('lessons', [])}
        previous_batch = next((item for item in reversed(state.get('batch_results', [])) if item.get('batch', {}).get('id') == batch['id']), None)
        previous_chapters = {item.get('chapter'): item for item in (previous_batch or {}).get('chapters', [])}
        passed_chapters = {number for number, item in previous_chapters.items() if item.get('passed')}
        ledger = [item for item in state.get('continuity_ledger', []) if not (item.get('module') == module['title'] and item.get('chapter') in batch['chapter_numbers'] and (item.get('chapter') not in passed_chapters))]
        batch_outputs = []
        effective_minimum = int(state['request'].get('effective_char_min', 12000))
        if provider.name == 'fake':
            effective_minimum = min(effective_minimum, 100)
        context_root = course_root / 'workspace' / 'context-packs' / batch['id']
        append_event(run_id, 'generation.batch.started', 'generation', f"{_batch_display_label(batch)} 开始处理：{len(batch['chapter_numbers'])} 个章节", {'batch': batch['id'], 'retry_round': state.get('retry_count', 0) + 1, 'reused_chapters': sorted(passed_chapters)})
        for chapter in module['chapters']:
            if chapter['number'] not in batch['chapter_numbers']:
                continue
            title = _plain_title(chapter['title'])
            previous_result = previous_chapters.get(chapter['number'], {})
            if chapter['number'] in passed_chapters:
                append_event(run_id, 'generation.chapter.reused', 'generation', f"第 {chapter['number']} 章：已有正文和质量门均通过，本轮直接复用", {'chapter': chapter['number'], 'batch': batch['id']})
                batch_outputs.append({**previous_result, 'reused': True})
                continue
            context = _context_pack(state, module, chapter, ledger, state.get('feedback', ''))
            context_path = context_root / f"chapter-{chapter['number']:02d}.json"
            _write_json(context_path, context)
            append_event(run_id, 'generation.chapter.context_ready', 'generation', f"第 {chapter['number']} 章：Context Pack 已组装，准备生成正文", {'chapter': chapter['number'], 'context_pack': str(context_path.relative_to(course_root))})
            attempts: list[dict[str, Any]] = []
            feedback = context.get('feedback', '')
            humanized = None
            humanizer_score: int | None = None
            review = None
            effective_chars = 0
            attempt_completed = False
            filename = f"{chapter['number']:02d}-{re.sub('[^a-z0-9]+', '-', title.lower()).strip('-') or 'chapter'}.md"
            relative = f'lessons/{filename}'
            target = course_root / relative
            latest_candidate_id: str | None = None

            def save_candidate(value: str, reason: str) -> None:
                nonlocal latest_candidate_id
                expected_hash = hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None
                candidate = commit_chapter_candidate(
                    course_slug=state['course_slug'], relative_path=relative,
                    content=value.rstrip() + '\n', expected_hash=expected_hash,
                    reason=reason, run_id=run_id,
                )
                latest_candidate_id = candidate['id']

            previous_markdown: str | None = target.read_text(encoding='utf-8') if target.exists() else None
            persisted_progress = _load_chapter_progress(course_root, batch['id'], chapter['number'])
            resume_state = previous_result or persisted_progress
            resume_stage = _chapter_resume_stage(resume_state, previous_markdown)
            markdown = previous_markdown or ''
            previous_issues: list[str] = list(previous_result.get('issues', []))
            writer_call_attempts = 0
            for attempt in range(1, settings.chapter_quality_max_attempts + 1):
                attempt_completed = False
                attempt_context = {**context, 'feedback': feedback, 'attempt': attempt}
                append_event(run_id, 'generation.chapter.writing', 'generation', (f"第 {chapter['number']} 章：正在生成正文" if previous_markdown is None else f"第 {chapter['number']} 章：正在定向优化已有正文") + f'（章节内第 {attempt}/{settings.chapter_quality_max_attempts} 轮）', {'chapter': chapter['number'], 'attempt': attempt, 'mode': 'generate' if previous_markdown is None else 'targeted_repair'})
                try:
                    if previous_markdown is None:

                        def write_initial_body(call_attempt: int) -> str:
                            nonlocal writer_call_attempts
                            writer_call_attempts = call_attempt
                            return workflow_context.timed_generation_operation('generation.chapter.writing', f"第 {chapter['number']} 章：正文生成调用（{call_attempt}/{settings.chapter_writer_max_attempts}）", chapter=chapter['number'], attempt=call_attempt, operation=lambda: workflow_context.invoke_agent('writer.agent', 'generate_chapter', attempt_context))
                        markdown = _retry_initial_chapter_write(write_initial_body, max_attempts=settings.chapter_writer_max_attempts, on_retry=lambda failed_attempt, exc: append_event(run_id, 'generation.chapter.write_retrying', 'generation', f"第 {chapter['number']} 章：正文生成调用 {failed_attempt}/{settings.chapter_writer_max_attempts} 失败，准备重试", {'chapter': chapter['number'], 'writer_call_attempt': failed_attempt, 'writer_call_max_attempts': settings.chapter_writer_max_attempts, 'error': str(exc)[:500]}))
                    elif resume_stage in {'enriching', 'humanizing', 'semantic_review'}:
                        markdown = previous_markdown
                    elif any(('有效字符' in issue for issue in previous_issues)):
                        markdown = previous_markdown
                    else:
                        markdown = workflow_context.timed_generation_operation('generation.chapter.revising', f"第 {chapter['number']} 章：依据质量证据定向修订（第 {attempt}/{settings.chapter_quality_max_attempts} 轮）", chapter=chapter['number'], attempt=attempt, operation=lambda: workflow_context.invoke_agent('writer.agent', 'revise_chapter', previous_markdown, {**attempt_context, 'instruction': feedback}))
                except Exception as exc:
                    attempts.append({'attempt': attempt, 'writer_call_attempts': writer_call_attempts or 1, 'issues': [f'正文生成失败：{str(exc)[:500]}'], 'failed_stage': 'writing'})
                    break
                normalized_heading = f"# 第 {chapter['number']} 章 {title}"
                if re.search('^#\\s+.+$', markdown, flags=re.MULTILINE):
                    markdown = re.sub('^#\\s+.+$', normalized_heading, markdown, count=1, flags=re.MULTILINE)
                else:
                    markdown = normalized_heading + '\n\n' + markdown
                save_candidate(markdown, f"第 {chapter['number']} 章正文候选生成")
                effective_chars, deficit = _effective_content_deficit(markdown, effective_minimum)
                if deficit:
                    enrichment_issue = f'当前有效字符 {effective_chars}，低于规格 {effective_minimum}，还需补充至少 {deficit} 个自然语言教学字符；代码块、Mermaid、命令、表格语法与重复总结不计入。'
                    append_event(run_id, 'generation.chapter.volume_preflight', 'generation', f"第 {chapter['number']} 章：有效内容不足 {deficit} 字，先执行内容丰富化，暂不运行 Humanizer", {'chapter': chapter['number'], 'attempt': attempt, 'effective_chars': effective_chars, 'effective_char_min': effective_minimum, 'deficit': deficit})
                    try:
                        markdown = workflow_context.timed_generation_operation('generation.chapter.enriching', f"第 {chapter['number']} 章：内容丰富化（第 {attempt}/{settings.chapter_quality_max_attempts} 轮）", chapter=chapter['number'], attempt=attempt, operation=lambda: workflow_context.invoke_agent('writer.agent', 'enrich_chapter', markdown, attempt_context, [enrichment_issue]))
                    except Exception as exc:
                        attempts.append({'attempt': attempt, 'issues': [f'内容丰富化失败：{str(exc)[:500]}'], 'failed_stage': 'enriching'})
                        break
                    normalized_heading = f"# 第 {chapter['number']} 章 {title}"
                    if re.search('^#\\s+.+$', markdown, flags=re.MULTILINE):
                        markdown = re.sub('^#\\s+.+$', normalized_heading, markdown, count=1, flags=re.MULTILINE)
                    else:
                        markdown = normalized_heading + '\n\n' + markdown
                    save_candidate(markdown, f"第 {chapter['number']} 章内容丰富化候选")
                    effective_chars, deficit = _effective_content_deficit(markdown, effective_minimum)
                    if deficit:
                        attempts.append({'attempt': attempt, 'effective_chars': effective_chars, 'issues': [f'有效字符 {effective_chars}，低于规格 {effective_minimum}；仍缺 {deficit} 字有效教学内容'], 'failed_stage': 'enriching'})
                        previous_markdown = markdown
                        previous_issues = attempts[-1]['issues']
                        feedback = previous_issues[0]
                        if attempt < settings.chapter_quality_max_attempts:
                            continue
                        break
                _save_chapter_progress(course_root, batch['id'], chapter['number'], {'body_generated': True, 'pending_stage': 'humanizing', 'path': relative, 'effective_chars': _effective_char_count(markdown), 'writer_call_attempts': writer_call_attempts})
                append_event(run_id, 'generation.chapter.humanizing', 'generation', f"第 {chapter['number']} 章：正在执行 Humanizer 闸门", {'chapter': chapter['number'], 'attempt': attempt})
                if resume_stage == 'semantic_review':
                    humanizer_score = int(resume_state.get('humanizer_score') or persisted_progress.get('humanizer_score') or 0)
                    effective_chars = _effective_char_count(markdown)
                else:
                    try:
                        humanized = workflow_context.timed_generation_operation('generation.chapter.humanizing', f"第 {chapter['number']} 章：Humanizer 闸门（第 {attempt}/{settings.chapter_quality_max_attempts} 轮）", chapter=chapter['number'], attempt=attempt, operation=lambda: workflow_context.invoke_agent('reviewer.agent', 'humanize', markdown))
                    except Exception as exc:
                        attempts.append({'attempt': attempt, 'issues': [f'Humanizer 失败：{str(exc)[:500]}'], 'failed_stage': 'humanizing'})
                        break
                    markdown = humanized.revised_markdown
                    previous_markdown = markdown
                    humanizer_score = humanized.score
                    effective_chars = _effective_char_count(markdown)
                    save_candidate(markdown, f"第 {chapter['number']} 章 Humanizer 候选")
                    _save_chapter_progress(course_root, batch['id'], chapter['number'], {'body_generated': True, 'pending_stage': 'semantic_review', 'path': relative, 'effective_chars': effective_chars, 'humanizer_score': humanizer_score})
                markdown, intro_changed = _normalize_lesson_intro(markdown)
                if intro_changed:
                    previous_markdown = markdown
                    save_candidate(markdown, f"第 {chapter['number']} 章章首结构候选")
                append_event(run_id, 'generation.chapter.semantic_review', 'generation', f"第 {chapter['number']} 章：正在进行教学语义与事实审校", {'chapter': chapter['number'], 'attempt': attempt})
                try:
                    review = workflow_context.timed_generation_operation('generation.chapter.semantic_review', f"第 {chapter['number']} 章：教学语义与事实审校（第 {attempt}/{settings.chapter_quality_max_attempts} 轮）", chapter=chapter['number'], attempt=attempt, operation=lambda: workflow_context.invoke_agent('reviewer.agent', 'semantic_review', markdown, attempt_context))
                except Exception as exc:
                    attempts.append({'attempt': attempt, 'issues': [f'语义审校失败：{str(exc)[:500]}'], 'failed_stage': 'semantic_review'})
                    break
                issues = []
                if humanizer_score < 45:
                    issues.append(f'Humanizer {humanizer_score}/50，低于 45')
                if effective_chars < effective_minimum:
                    issues.append(f'有效字符 {effective_chars}，低于规格 {effective_minimum}')
                if review.decision != 'ready':
                    issues.extend(review.issues or [f'语义结论为 {review.decision}'])
                attempts.append({'attempt': attempt, 'humanizer_score': humanizer_score, 'effective_chars': effective_chars, 'semantic_decision': review.decision, 'quality_gates': {'stage_1_language_and_volume': {'passed': humanizer_score >= 45 and effective_chars >= effective_minimum, 'humanizer_score': humanizer_score, 'effective_chars': effective_chars, 'effective_char_min': effective_minimum}, 'stage_2_semantic_review': {'passed': review.decision == 'ready', 'decision': review.decision, 'issues': review.issues}}, 'issues': issues, 'writer_markdown': markdown, 'humanizer_output': humanized.model_dump(mode='json') if humanized is not None else {'resumed_from_progress': True, 'score': humanizer_score}, 'semantic_review': review.model_dump(mode='json')})
                attempt_completed = True
                if not issues:
                    append_event(run_id, 'generation.chapter.gates_passed', 'generation', f"第 {chapter['number']} 章：章节级质量门通过", {'chapter': chapter['number'], 'attempt': attempt})
                    break
                append_event(run_id, 'generation.chapter.retrying', 'generation', f"第 {chapter['number']} 章：发现 {len(issues)} 项问题，正在定向返工", {'chapter': chapter['number'], 'attempt': attempt, 'issues': issues[:6]})
                feedback = '上一轮未通过质量门。请在原有结构中定向修复这些问题，不在文末凑字数：' + '；'.join(issues[:12])
                previous_issues = issues
            if not attempt_completed or humanizer_score is None or review is None:
                issues = attempts[-1].get('issues', ['章节未完成'])
                if markdown:
                    save_candidate(markdown, f"第 {chapter['number']} 章未完成候选")
                    _register_generated_chapter(
                        existing,
                        chapter=chapter,
                        module_title=module['title'],
                        title=title,
                        relative_path=relative,
                    )
                append_event(run_id, 'generation.chapter.deferred', 'generation', f"第 {chapter['number']} 章：已记录待处理问题，继续生成后续章节", {'chapter': chapter['number'], 'issues': issues})
                failure_stage = str(attempts[-1].get('failed_stage') or 'writing')
                batch_outputs.append(_deferred_chapter_quality_result(chapter=chapter['number'], title=title, path=relative, markdown=markdown, effective_char_min=effective_minimum, failure_stage=failure_stage, issue=issues[0], attempts=attempts))
                continue
            if latest_candidate_id is None:
                save_candidate(markdown, f"第 {chapter['number']} 章正文候选")
            _register_generated_chapter(
                existing,
                chapter=chapter,
                module_title=module['title'],
                title=title,
                relative_path=relative,
            )
            append_event(run_id, 'generation.chapter.continuity', 'generation', f"第 {chapter['number']} 章：正在提取跨章连续性账本", {'chapter': chapter['number']})
            continuity_issue = ''
            try:
                continuity = workflow_context.timed_generation_operation('generation.chapter.continuity', f"第 {chapter['number']} 章：提取跨章连续性账本", chapter=chapter['number'], operation=lambda: workflow_context.invoke_agent('reviewer.agent', 'extract_continuity', markdown, context))
                continuity_data = continuity.model_dump(mode='json')
            except Exception as exc:
                continuity_issue = f'连续性账本提取失败：{str(exc)[:500]}'
                continuity_data = {'summary': '待人工补充连续性账本', 'open_loops': [continuity_issue]}
                append_event(run_id, 'generation.chapter.deferred', 'generation', f"第 {chapter['number']} 章：连续性问题已记录，继续后续章节", {'chapter': chapter['number'], 'issues': [continuity_issue]})
            ledger.append({'chapter': chapter['number'], 'module': module['title'], **continuity_data})
            passed = humanizer_score >= 45 and effective_chars >= effective_minimum and (review.decision == 'ready') and (not continuity_issue)
            if passed and latest_candidate_id:
                verify_chapter_candidate(latest_candidate_id, {
                    'gate': 'chapter_generation', 'humanizer_score': humanizer_score,
                    'effective_chars': effective_chars, 'semantic_decision': review.decision,
                    'continuity_complete': not continuity_issue,
                })
            batch_outputs.append({'chapter': chapter['number'], 'title': title, 'humanizer_score': humanizer_score, 'effective_chars': effective_chars, 'effective_char_min': effective_minimum, 'semantic_review': review.model_dump(mode='json'), 'path': relative, 'context_pack': str(context_path.relative_to(course_root)), 'attempts': attempts, 'continuity_output': continuity_data, 'passed': passed, 'deferred': bool(continuity_issue), 'issues': [*attempts[-1].get('issues', []), *([continuity_issue] if continuity_issue else [])]})
            _save_chapter_progress(course_root, batch['id'], chapter['number'], {'body_generated': True, 'pending_stage': 'completed' if not continuity_issue else 'continuity', 'path': relative, 'effective_chars': effective_chars, 'humanizer_score': humanizer_score, 'semantic_review': review.model_dump(mode='json')})
        metadata['title'] = state['blueprint']['course_title']
        metadata['status'] = 'generating'
        metadata['lessons'] = [existing[number] for number in sorted(existing)]
        metadata['modules'] = [{'title': item['title'], 'goal': item['goal'], 'chapterNumbers': [chapter['number'] for chapter in item['chapters']]} for item in state['blueprint']['modules']]
        _write_json(metadata_path, metadata)
        _write_json(course_root / 'workspace' / 'continuity-ledger.agent.json', {'entries': ledger})
        batch_source_contract = workflow_context.timed_generation_operation('generation.batch.source_contract', f'{_batch_display_label(batch)}：预检 Markdown 结构契约', operation=lambda: workflow_context.execute_tool('course.source_contract', caller='workflow.generation', course_slug=state['course_slug'], chapter_numbers=batch['chapter_numbers']))
        contract_entries = _batch_contract_repair_entries(batch_source_contract, batch, batch_outputs)
        batch_repair_entries: list[dict[str, Any]] = []
        for entry in contract_entries:
            relative_path = str(entry.get('path') or '')
            source = course_root / relative_path
            markdown = source.read_text(encoding='utf-8') if source.exists() else ''
            task_ids: list[str] = []
            for issue in entry.get('issues', []):
                task = create_or_refresh_task(normalize_quality_issue(course_slug=state['course_slug'], run_id=run_id, batch_id=str(batch['id']), chapter=int(entry['chapter']), issue=str(issue), path=relative_path, markdown=markdown))
                task_ids.append(task['id'])
            batch_repair_entries.append({**entry, 'task_ids': task_ids})
            for chapter_output in batch_outputs:
                if int(chapter_output.get('chapter') or 0) == int(entry['chapter']):
                    chapter_output['issues'] = list(dict.fromkeys([*chapter_output.get('issues', []), *entry.get('issues', [])]))
                    chapter_output['passed'] = False
                    chapter_output['repair_task_ids'] = list(dict.fromkeys([*chapter_output.get('repair_task_ids', []), *task_ids]))
        batch_repair_queue, _, _ = merge_repair_queue([], batch_repair_entries, attempts={}, max_attempts=2)
        if batch_repair_queue:
            append_event(run_id, 'generation.batch.structure_repair_queued', 'generation', f"{_batch_display_label(batch)}：结构预检发现 {sum((len(item.get('issues', [])) for item in batch_repair_queue))} 个问题，进入定向修复，不重复生成正文", {'batch': batch['id'], 'chapters': [item['chapter'] for item in batch_repair_queue]})
        append_event(run_id, 'generation.batch.building', 'generation', f'{_batch_display_label(batch)}：正在构建课程产物并执行确定性检查', {'batch': batch['id']})
        build = workflow_context.timed_generation_operation('generation.batch.build', f'{_batch_display_label(batch)}：构建课程产物', operation=lambda: workflow_context.execute_tool('course.build', caller='workflow.generation', course_slug=state['course_slug'], chapter_numbers=batch['chapter_numbers'])) if not batch_repair_queue else {'succeeded': False, 'exit_code': None, 'stdout': '', 'stderr': '结构预检未通过，已进入章节定向修复；暂不执行构建。'}
        validation = workflow_context.timed_generation_operation('generation.batch.validation', f'{_batch_display_label(batch)}：确定性检查', operation=lambda: workflow_context.execute_tool('course.validate', caller='workflow.generation', course_slug=state['course_slug'], chapter_numbers=batch['chapter_numbers'])) if build['succeeded'] else {'succeeded': False, 'exit_code': None, 'stdout': '', 'stderr': '构建失败，未运行确定性检查'}
        result = {'batch': batch, 'chapters': batch_outputs, 'source_contract': batch_source_contract, 'build': build, 'validation': validation, 'quality_gates': {'stage_1_chapter_language_and_volume': {'passed': all((item['humanizer_score'] >= 45 and item['effective_chars'] >= item['effective_char_min'] for item in batch_outputs)), 'label': '章节语言与有效内容门'}, 'stage_2_semantic_review': {'passed': all((item['semantic_review']['decision'] == 'ready' for item in batch_outputs)), 'label': '教学语义与事实审校门'}, 'stage_3_batch_integration': {'passed': build['succeeded'] and validation['succeeded'], 'label': '批次构建与确定性集成门'}}}
        result['passed'] = all((item['passed'] for item in batch_outputs)) and build['succeeded'] and validation['succeeded']
        batch_task_ids: list[str] = []
        for chapter_output in batch_outputs:
            chapter_issues = list(chapter_output.get('issues', []))
            if chapter_output.get('effective_chars', 0) < chapter_output.get('effective_char_min', 0):
                chapter_issues.append(f"有效字符 {chapter_output.get('effective_chars', 0)}，低于规格 {chapter_output.get('effective_char_min', 0)}")
            if chapter_output.get('humanizer_score', 50) < 45:
                chapter_issues.append(f"Humanizer {chapter_output.get('humanizer_score')}/50，低于 45")
            chapter_issues.extend(chapter_output.get('semantic_review', {}).get('issues', []))
            relative_path = str(chapter_output.get('path') or '')
            target = course_root / relative_path
            markdown = target.read_text(encoding='utf-8') if target.exists() else ''
            repairable_issues, advisory_issues, operation_incidents = split_quality_issues(
                list(dict.fromkeys((str(value) for value in chapter_issues if str(value).strip()))),
                effective_chars=int(chapter_output.get('effective_chars') or 0) or None,
                effective_char_min=int(chapter_output.get('effective_char_min') or 0) or None,
            )
            chapter_output['issues'] = repairable_issues
            chapter_output['advisory_issues'] = advisory_issues
            chapter_output['operation_incidents'] = operation_incidents
            for incident in operation_incidents:
                append_event(run_id, 'operation.incident', 'generation', f"第 {chapter_output.get('chapter')} 章：运行故障不进入章节修复队列", {'chapter': chapter_output.get('chapter'), 'issue': incident, 'origin': 'generation'})
            task_ids: list[str] = []
            for issue in repairable_issues:
                task = create_or_refresh_task(normalize_quality_issue(course_slug=state['course_slug'], run_id=run_id, batch_id=str(batch['id']), chapter=int(chapter_output.get('chapter') or 0) or None, issue=issue, path=relative_path, markdown=markdown))
                task_ids.append(task['id'])
                batch_task_ids.append(task['id'])
            if not repairable_issues and (
                not chapter_output.get('deferred') or chapter_output.get('body_generated')
            ):
                chapter_output['passed'] = True
            chapter_output['repair_task_ids'] = task_ids
        result['repair_task_ids'] = batch_task_ids
        result['passed'] = all((item['passed'] for item in batch_outputs)) and build['succeeded'] and validation['succeeded']
        persisted_results = [*state.get('batch_results', []), result]
        _persist_latest_batch_quality_results(course_root, persisted_results, repair_tasks=list_repair_tasks(run_id))
        append_event(run_id, 'generation.batch.quality_recorded', 'generation', f"{_batch_display_label(batch)}：质量结果已记录，{('通过' if result['passed'] else '将进入自动返工')}", {'batch': batch['id'], 'passed': result['passed']})
        automatic_retry_count = 0 if result['passed'] else state.get('retry_count', 0) + 1
        retry_feedback = '；'.join([*[issue for chapter_result in batch_outputs for issue in chapter_result.get('semantic_review', {}).get('issues', [])], *[str(issue) for entry in contract_entries for issue in entry.get('issues', [])]])
        if not result['passed']:
            retry_feedback = '上一批次质量门未通过。请仅重写受影响章节，保留已通过部分；优先修复以下证据：' + (retry_feedback or '请核对 Humanizer、有效内容、构建和确定性检查报告。')
        quality_repair_queue = list(state.get('quality_repair_queue', []))
        quality_repair_active = bool(state.get('quality_repair_active'))
        if result['passed'] and quality_repair_active:
            remaining_queue = [item for item in quality_repair_queue if item != index]
            next_batch_index = remaining_queue[0] if remaining_queue else index
        else:
            remaining_queue = quality_repair_queue
            next_batch_index = index + 1 if result['passed'] else index
        return {'continuity_ledger': ledger, 'batch_results': persisted_results, 'quality_blocked': not result['passed'], 'current_batch_index': next_batch_index, 'retry_count': automatic_retry_count, 'feedback': retry_feedback, 'quality_repair_queue': remaining_queue, 'batch_repair_queue': batch_repair_queue, 'batch_repair_active': bool(batch_repair_queue), 'batch_repair_batch_id': str(batch['id']) if batch_repair_queue else None, 'repair_scope': 'batch' if batch_repair_queue else 'course', 'quality_cycle_discovery_sweeps': 0 if batch_repair_queue else state.get('quality_cycle_discovery_sweeps', 0), 'quality_repair_active': quality_repair_active}

    def route_generated_batch(state: CourseAgentState) -> str:
        if state.get('batch_repair_queue'):
            return 'repair'
        if state.get('quality_blocked'):
            return 'manual'
        if state.get('quality_repair_active'):
            return 'complete' if not state.get('quality_repair_queue') else 'next'
        return 'complete' if state['current_batch_index'] >= len(state['batches']) else 'next'

    return SimpleNamespace(generate_batch=generate_batch, route_generated_batch=route_generated_batch)
