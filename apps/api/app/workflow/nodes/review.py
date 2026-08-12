from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from langgraph.types import interrupt
from app.course_service import get_chapter, get_course, update_chapter
from app.workflow.node_context import WorkflowContext
from app.workflow.services.workspace_contract import _read_workspace_context
from app.workflow.state import CourseAgentState


def create_review_nodes(context: WorkflowContext) -> SimpleNamespace:
    run_id = context.run_id
    provider = context.provider
    settings = context.settings
    workflow_context = context

    def inspect(state: CourseAgentState) -> dict[str, Any]:
        course = get_course(state['course_slug'])
        requested_keys = state['request'].get('chapter_keys', [])
        lessons = course['lessons']
        if requested_keys:
            selected = [item for item in lessons if str(item.get('number')) in requested_keys or item.get('code') in requested_keys or item.get('markdown') in requested_keys]
        else:
            selected = lessons
        course_root = settings.courses_root / state['course_slug']
        mission_path = course_root / 'workspace' / 'MISSION.md'
        mission = mission_path.read_text(encoding='utf-8') if mission_path.exists() else course['description']
        chapter_results = []
        regenerated = state['scope'] == 'regenerate_course'
        for position, lesson in enumerate(selected):
            key = str(lesson['number'])
            chapter = get_chapter(state['course_slug'], key)
            neighbor = {'previous': selected[position - 1].get('summary', '') if position > 0 else '', 'next': selected[position + 1].get('summary', '') if position + 1 < len(selected) else ''}
            context = {'course_context': {'title': course['title'], 'mission': mission, 'request': {'audience': course.get('audience', ''), 'effective_char_min': state['request'].get('effective_char_min', 12000)}, 'workspace': _read_workspace_context(course_root)}, 'chapter': {'number': chapter['number'], 'title': chapter['title'], 'summary': chapter['summary']}, 'neighbor_context': neighbor, 'instruction': state['request'].get('instruction', ''), 'scope': state['scope']}
            content = chapter['content']
            if regenerated:
                revised_by_model = workflow_context.invoke_agent('writer.agent', 'revise_chapter', content, context)
                humanized = workflow_context.invoke_agent('reviewer.agent', 'humanize', revised_by_model)
                content = humanized.revised_markdown
                saved = update_chapter(state['course_slug'], key, content, chapter['content_hash'], state['request'].get('instruction') or '课程 Agent 章节重生成')
            else:
                revised_by_model = None
                humanized = None
                saved = None
            semantic = workflow_context.invoke_agent('reviewer.agent', 'semantic_review', content, context)
            chapter_results.append({'chapter': chapter['number'], 'title': chapter['title'], 'path': chapter['path'], 'content_hash': saved['content_hash'] if saved else chapter['content_hash'], 'humanizer_score': humanized.score if humanized else None, 'semantic_review': semantic.model_dump(mode='json'), 'model_outputs': {'revised_markdown': revised_by_model, 'humanizer': humanized.model_dump(mode='json') if humanized else None, 'semantic_review': semantic.model_dump(mode='json')}})
        build = workflow_context.execute_tool('course.build', caller='workflow.review', course_slug=state['course_slug']) if regenerated else None
        validation = workflow_context.execute_tool('course.validate', caller='workflow.review', course_slug=state['course_slug'])
        return {'review_result': {'course': {'title': course['title'], 'chapter_count': course['chapter_count'], 'quality_report_count': course['quality_report_count']}, 'scope': state['scope'], 'validation': validation, 'build': build, 'chapters': chapter_results, 'selected_chapters': [str(item['number']) for item in selected], 'instruction': state['request'].get('instruction', '')}}

    def approve_review(state: CourseAgentState) -> dict[str, Any]:
        decision = interrupt({'type': 'COURSE_REVIEW_APPROVAL', 'step': 'quality', 'title': '确认章节重生成结果' if state['scope'] == 'regenerate_course' else '确认课程 Review 结果', 'output': state['review_result'], 'actions': ['APPROVE', 'STOP']})
        return {'approval': decision['action']}

    def finish(state: CourseAgentState) -> dict[str, Any]:
        return {'final_status': 'REGENERATION_COMPLETED' if state['scope'] == 'regenerate_course' else 'REVIEW_COMPLETED'}

    def stop(state: CourseAgentState) -> dict[str, Any]:
        return {'final_status': 'STOPPED'}

    return SimpleNamespace(inspect=inspect, approve_review=approve_review, finish=finish, stop=stop)
