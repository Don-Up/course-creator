from __future__ import annotations

import asyncio
import json
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.artifact_service import attach_artifact_presentations
from app.schemas import ApprovalResolve, RunContinue
from app.workflow.command_repository import enqueue_command, request_run_stop
from app.workflow.repository import append_event, get_run_record, list_run_records
from app.observability.budget import get_budget_projection
from app.observability.tracing import get_trace_projection


router = APIRouter(prefix="/api/runs", tags=["runs"])


def build_router() -> APIRouter:
    @router.get("")
    def runs(course_slug: Annotated[str | None, Query()] = None):
        return {"items": list_run_records(course_slug)}

    @router.get("/{run_id}")
    def run_detail(run_id: str):
        run = get_run_record(run_id)
        if not run:
            raise HTTPException(404, "Run 不存在")
        return attach_artifact_presentations(run)

    @router.get("/{run_id}/budget")
    def run_budget(run_id: str):
        if not get_run_record(run_id):
            raise HTTPException(404, "Run 不存在")
        return get_budget_projection(run_id)

    @router.get("/{run_id}/trace")
    def run_trace(run_id: str):
        if not get_run_record(run_id):
            raise HTTPException(404, "Run 不存在")
        return get_trace_projection(run_id)

    @router.post("/{run_id}/resolve", status_code=202)
    async def resolve_approval(run_id: str, payload: ApprovalResolve):
        run = get_run_record(run_id)
        if not run:
            raise HTTPException(404, "Run 不存在")
        if run["status"] != "WAITING_APPROVAL":
            raise HTTPException(409, "当前 Run 不在等待确认状态")
        if run["current_step"] == "release" and payload.action == "APPROVE" and not _has_release_review(run):
            raise HTTPException(409, "整课总结尚未生成，请先重新生成整课总结")
        append_event(run_id, "approval.resolved", run["current_step"], f"用户选择 {payload.action}", {"feedback": payload.feedback})
        command, duplicate = enqueue_command(run_id, "RESUME", payload.model_dump(mode="json"))
        return {"run_id": run_id, "status": "QUEUED", "command_id": command["id"], "duplicate": duplicate}

    @router.post("/{run_id}/continue", status_code=202)
    async def continue_run(run_id: str, payload: RunContinue):
        run = get_run_record(run_id)
        if not run:
            raise HTTPException(404, "Run 不存在")
        scope = run["request"].get("workflow_scope") or "new_course"
        if run["status"] == "WAITING_APPROVAL":
            summary_regeneration = run["current_step"] == "release"
            append_event(run_id, "run.continued", run["current_step"], "重新生成整课总结" if summary_regeneration else "继续自动处理当前批次", {"feedback": payload.feedback} if not summary_regeneration else None)
            command, duplicate = enqueue_command(
                run_id, "RESUME",
                {"action": "REGENERATE_SUMMARY", "feedback": payload.feedback} if summary_regeneration else {"action": "REVISE", "feedback": payload.feedback},
            )
            return {"run_id": run_id, "status": "QUEUED", "command_id": command["id"], "duplicate": duplicate}
        if run["status"] != "FAILED":
            raise HTTPException(409, "只有失败或等待人工建议的 Run 可以继续")
        append_event(run_id, "run.continued", run["current_step"], "从最近检查点继续执行")
        command, duplicate = enqueue_command(run_id, "CONTINUE")
        return {"run_id": run_id, "status": "QUEUED", "command_id": command["id"], "duplicate": duplicate}

    @router.post("/{run_id}/stop", status_code=202)
    async def stop_run(run_id: str):
        if not get_run_record(run_id):
            raise HTTPException(404, "Run 不存在")
        request_run_stop(run_id)
        command, duplicate = enqueue_command(run_id, "STOP")
        return {"run_id": run_id, "status": "STOPPING", "command_id": command["id"], "duplicate": duplicate}

    @router.get("/{run_id}/stream")
    async def stream_run(run_id: str):
        if not get_run_record(run_id):
            raise HTTPException(404, "Run 不存在")

        async def generate():
            last_seq, last_status = 0, ""
            while True:
                run = get_run_record(run_id)
                if not run:
                    break
                for event in [item for item in run["events"] if item["seq"] > last_seq]:
                    last_seq = event["seq"]
                    yield f"id: {last_seq}\nevent: run_event\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                if run["status"] != last_status:
                    last_status = run["status"]
                    snapshot = {"status": last_status, "step": run["current_step"]}
                    yield f"event: snapshot\ndata: {json.dumps(snapshot, ensure_ascii=False)}\n\n"
                if run["status"] in {"COMPLETED", "FAILED", "STOPPED"}:
                    break
                await asyncio.sleep(1)

        return StreamingResponse(generate(), media_type="text/event-stream")

    globals().update(resolve_approval=resolve_approval, continue_run=continue_run, stop_run=stop_run, stream_run=stream_run)
    return router


def _workflow_scope(run: dict) -> str:
    scope = run["request"].get("workflow_scope")
    if scope:
        return scope
    return run["request"].get("scope") if run["request"].get("scope") in {"new_course", "review_course", "regenerate_course"} else "new_course"


def _has_release_review(run: dict) -> bool:
    payload = run.get("interrupt_payload")
    return isinstance(payload, dict) and isinstance(payload.get("output"), dict) and bool(payload["output"].get("release_review"))
