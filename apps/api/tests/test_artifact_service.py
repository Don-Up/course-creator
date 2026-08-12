from app.artifact_service import attach_artifact_presentations
from app.workflow.definitions import WORKFLOW_STEPS
from app.workflow.services.context_packs import _presentation_projection


def test_historical_course_artifacts_are_recovered_from_local_files():
    run = {
        "id": "historical-run",
        "course_slug": "harness-engineering",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "created_at": "2026-01-01T00:00:00+00:00",
        "current_step": "quality",
        "interrupt_payload": None,
        "artifacts": [],
        "workflow_steps": [{**step, "status": "completed"} for step in WORKFLOW_STEPS],
        "request": {"workflow_scope": "review_course"},
    }
    enriched = attach_artifact_presentations(run)
    by_step = {step["id"]: step["artifacts"] for step in enriched["workflow_steps"]}
    assert by_step["mission"][0]["source"] == "recovered"
    assert "MISSION.md" in by_step["mission"][0]["raw_output"]["path"]
    assert by_step["generation"][0]["presentation"]["metrics"]["Markdown 章节"] == 13


def test_new_course_run_never_synthesizes_recovered_artifacts():
    run = {
        "id": "new-run",
        "course_slug": "harness-engineering",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "current_step": "mission",
        "interrupt_payload": None,
        "request": {
            "workflow_scope": "new_course",
            "scope": "这是用户填写的课程内容范围",
        },
        "artifacts": [],
        "workflow_steps": [{**step, "status": "pending"} for step in WORKFLOW_STEPS],
    }
    enriched = attach_artifact_presentations(run)
    assert len(enriched["artifacts"]) == 1
    assert enriched["artifacts"][0]["source"] == "submitted"
    assert "不是从历史课程文件恢复" in enriched["artifacts"][0]["presentation"]["conclusion"]
    assert enriched["workflow_steps"][0]["artifacts"][0]["step"] == "intake"


def test_new_course_quality_artifacts_stay_on_quality_step():
    run = {
        "id": "new-run",
        "course_slug": "harness-engineering",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "current_step": "quality",
        "interrupt_payload": None,
        "request": {"workflow_scope": "new_course"},
        "artifacts": [
            {
                "id": "quality-artifact",
                "run_id": "new-run",
                "step": "quality",
                "node": "repair_open_chapters",
                "title": "整课质量闭环定向修复",
                "source": "model",
                "presentation": {"headline": "修复完成"},
                "raw_output": {},
                "created_at": "2026-01-01T00:01:00+00:00",
            }
        ],
        "workflow_steps": [{**step, "status": "completed"} for step in WORKFLOW_STEPS],
    }
    enriched = attach_artifact_presentations(run)
    by_step = {step["id"]: step["artifacts"] for step in enriched["workflow_steps"]}
    assert [artifact["id"] for artifact in by_step["quality"]] == ["quality-artifact"]
    assert not any(
        artifact["id"] == "quality-artifact"
        for artifact in by_step["generation"]
    )


def test_presentation_projection_keeps_raw_output_out_of_summary_prompt():
    value = {"markdown": "课" * 2000, "items": list(range(20))}
    projected = _presentation_projection(value)
    assert len(projected["markdown"]) < 1400
    assert "完整原始产物已持久化" in projected["markdown"]
    assert len(projected["items"]) == 13


def test_presentation_projection_marks_clipped_content_as_summary_only():
    projected = _presentation_projection({"mission_markdown": "课" * 1400})

    assert projected["__presentation_projection__"] is True
    assert "不能据此判断原始产物是否完整" in projected["mission_markdown"]
