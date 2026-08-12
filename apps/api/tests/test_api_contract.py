import inspect

from app.main import _attach_resumable_creation_run, create_course, resolve_approval, start_run
from app.workflow.definitions import REVIEW_WORKFLOW_STEPS, WORKFLOW_STEPS


def test_workflow_mutation_endpoints_run_on_the_event_loop():
    assert inspect.iscoroutinefunction(create_course)
    assert inspect.iscoroutinefunction(start_run)
    assert inspect.iscoroutinefunction(resolve_approval)


def test_legacy_creation_run_remains_resumable_while_course_is_generating():
    course = {"slug": "legacy-course", "status": "generating"}
    runs = [
        {
            "id": "review-run",
            "status": "WAITING_APPROVAL",
            "current_step": "quality",
            "request": {"workflow_scope": "review_course"},
        },
        {
            "id": "creation-run",
            "status": "WAITING_APPROVAL",
            "current_step": "quality",
            "request": {
                "slug": "legacy-course",
                "audience": "初学者",
                "goals": "完成课程",
                "scope": "课程范围",
                "delivery": "Markdown + HTML",
            },
        },
    ]

    result = _attach_resumable_creation_run(course, runs)

    assert result["resumable_run_id"] == "creation-run"
    assert result["resumable_run_step"] == "generation"


def test_creation_workflow_has_batch_gates_and_a_separate_course_quality_closure():
    step_ids = [step["id"] for step in WORKFLOW_STEPS]

    assert step_ids == [
        "intake",
        "mission",
        "blueprint",
        "batch_plan",
        "generation",
        "quality",
        "release",
    ]
    assert "三阶段质量门" in next(
        step["description"] for step in WORKFLOW_STEPS if step["id"] == "generation"
    )
    assert "quality" in step_ids
    assert "quality" in [step["id"] for step in REVIEW_WORKFLOW_STEPS]
