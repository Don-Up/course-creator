"""Independent local execution process for persisted course-agent commands."""
from __future__ import annotations

import asyncio
import os
import socket
import uuid
from typing import Any

from langgraph.types import Command

from app.config import get_settings
from app.workflow.execution_context import ExecutionContext, current_execution
from app.workflow.command_repository import claim_next_command, finish_command, is_command_cancel_requested
from app.workflow.repository import append_event, get_run_record, update_run
from app.workflow.runtime import WorkflowRuntime
from app.observability.context import TraceContext, trace_scope
from app.observability.tracing import finish_span, start_span


class CourseAgentWorker:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.worker_id = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
        self.runtime = WorkflowRuntime()
        self.running = True

    async def run_forever(self) -> None:
        await self.runtime.start()
        try:
            while self.running:
                command = claim_next_command(self.worker_id, self.settings.worker_lease_seconds)
                if not command:
                    await asyncio.sleep(self.settings.worker_poll_interval_seconds)
                    continue
                await self._execute(command)
        finally:
            await self.runtime.stop()

    async def _execute(self, command: dict[str, Any]) -> None:
        run_id = str(command["run_id"])
        kind = str(command["kind"])
        run = get_run_record(run_id)
        if not run:
            finish_command(command["id"], self.worker_id, "FAILED", error="Run 不存在")
            return
        if kind == "STOP":
            command_span = start_span(run_id, kind="command", name="STOP", parent_span_id=f"run:{run_id}", command_id=command["id"])
            update_run(run_id, status="STOPPED", clear_interrupt=True)
            append_event(run_id, "run.stopped", run.get("current_step", "intake"), "Worker 已确认停止 Run")
            finish_command(command["id"], self.worker_id, "SUCCEEDED")
            finish_span(command_span["id"], "CANCELLED")
            return
        payload = command.get("payload") or {}
        scope = run["request"].get("workflow_scope") or run["request"].get("scope") or "new_course"
        graph_command = None
        continue_from_checkpoint = kind == "CONTINUE"
        if kind == "RESUME":
            graph_command = Command(resume=payload)
        token = current_execution.set(
            ExecutionContext(command["id"], self.worker_id, self.settings.worker_lease_seconds)
        )
        command_span = start_span(run_id, kind="command", name=kind, parent_span_id=f"run:{run_id}", command_id=command["id"], attributes={"operation": kind})
        trace_manager = None
        try:
            trace_manager = trace_scope(TraceContext(trace_id=run_id, run_id=run_id, span_id=command_span["id"], parent_span_id=f"run:{run_id}", command_id=command["id"]))
            trace_manager.__enter__()
            await self.runtime._execute(run_id, run["course_slug"], scope, run["request"], run["provider"], graph_command, continue_from_checkpoint)
            current = get_run_record(run_id) or {}
            if is_command_cancel_requested(command["id"]):
                update_run(run_id, status="STOPPED", clear_interrupt=True)
                finish_command(command["id"], self.worker_id, "CANCELLED")
            elif current.get("status") == "WAITING_APPROVAL":
                finish_command(command["id"], self.worker_id, "WAITING_APPROVAL")
            elif current.get("status") == "FAILED":
                finish_command(command["id"], self.worker_id, "FAILED", error=current.get("error_message"))
            else:
                finish_command(command["id"], self.worker_id, "SUCCEEDED")
            finish_span(command_span["id"], "WAITING_APPROVAL" if current.get("status") == "WAITING_APPROVAL" else "SUCCEEDED")
        except Exception as exc:
            finish_command(command["id"], self.worker_id, "FAILED", error=str(exc))
            finish_span(command_span["id"], "FAILED", error=exc)
        finally:
            if trace_manager is not None:
                trace_manager.__exit__(None, None, None)
            current_execution.reset(token)


def run() -> None:
    asyncio.run(CourseAgentWorker().run_forever())


if __name__ == "__main__":
    run()
