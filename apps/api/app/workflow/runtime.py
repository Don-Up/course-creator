from __future__ import annotations

import asyncio
from contextlib import AbstractContextManager
from datetime import datetime
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

# "Refresh" is implemented by replaying from the latest checkpoint with no
# resume write, so the node's interrupt re-fires with a fresh payload instead
# of consuming a stale resume value.

from app.config import get_settings
from app.agents.runtime import create_course_agent
from app.workflow.graph import build_course_graph, build_review_graph
from app.workflow.command_repository import renew_command_lease
from app.workflow.repository import append_event, get_run_record, update_run
from app.workflow.execution_context import current_execution


def _continuation_config(graph, config: dict[str, Any]) -> dict[str, Any]:
    """Retry a failed LangGraph task from the checkpoint that scheduled it.

    LangGraph persists a task error in the newest checkpoint. Invoking that
    checkpoint with ``None`` does not rerun the failed task and can return an
    empty result, which must never be interpreted as successful completion.
    """
    snapshot = graph.get_state(config)
    failed_tasks = [
        task for task in getattr(snapshot, "tasks", ()) if getattr(task, "error", None)
    ]
    if not failed_tasks:
        return config
    failed_names = {task.name for task in failed_tasks}
    history = iter(graph.get_state_history(config, limit=8))
    next(history, None)
    for previous in history:
        scheduled = {task.name for task in getattr(previous, "tasks", ())}
        if failed_names & scheduled:
            return previous.config
    raise RuntimeError(
        f"未找到失败节点 {', '.join(sorted(failed_names))} 的可恢复检查点"
    )


def _require_terminal_graph_state(graph, config: dict[str, Any]) -> None:
    """Reject an empty invoke result while the persisted graph still has work."""
    snapshot = graph.get_state(config)
    pending = tuple(getattr(snapshot, "next", ()) or ())
    if not pending:
        return
    failed = [
        task.name
        for task in getattr(snapshot, "tasks", ())
        if getattr(task, "error", None)
    ]
    detail = ", ".join(failed or pending)
    raise RuntimeError(f"工作流仍有未完成节点，不能标记 Run 完成：{detail}")


class WorkflowRuntime:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.checkpointer_context: AbstractContextManager | None = None
        self.checkpointer = None
        self.graphs: dict[str, Any] = {}
        self.semaphore = asyncio.Semaphore(self.settings.course_agent_max_concurrent_runs)
        self.tasks: set[asyncio.Task] = set()

    async def start(self) -> None:
        self.settings.data_root.mkdir(parents=True, exist_ok=True)
        self.checkpointer_context = SqliteSaver.from_conn_string(
            str(self.settings.checkpoint_path)
        )
        self.checkpointer = self.checkpointer_context.__enter__()

    async def stop(self) -> None:
        if self.tasks:
            _, pending = await asyncio.wait(self.tasks, timeout=10)
            for task in pending:
                task.cancel()
        if self.checkpointer_context:
            self.checkpointer_context.__exit__(None, None, None)

    def submit_start(
        self,
        run_id: str,
        course_slug: str,
        scope: str,
        request: dict[str, Any],
        provider_name: str,
    ) -> None:
        task = asyncio.create_task(
            self._execute(
                run_id,
                course_slug,
                scope,
                request,
                provider_name,
                command=None,
            )
        )
        self._track(task)

    def submit_resume(
        self,
        run_id: str,
        course_slug: str,
        scope: str,
        request: dict[str, Any],
        provider_name: str,
        payload: dict[str, Any],
    ) -> None:
        task = asyncio.create_task(
            self._execute(
                run_id,
                course_slug,
                scope,
                request,
                provider_name,
                command=Command(resume=payload),
            )
        )
        self._track(task)

    def submit_continue(
        self,
        run_id: str,
        course_slug: str,
        scope: str,
        request: dict[str, Any],
        provider_name: str,
    ) -> None:
        """Resume unfinished work without recreating its original input state."""
        task = asyncio.create_task(
            self._execute(
                run_id,
                course_slug,
                scope,
                request,
                provider_name,
                command=None,
                continue_from_checkpoint=True,
            )
        )
        self._track(task)

    def _track(self, task: asyncio.Task) -> None:
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    def _graph_for(
        self,
        run_id: str,
        scope: str,
        provider_name: str,
        model_name: str | None,
    ):
        if run_id not in self.graphs:
            provider = create_course_agent(provider_name, model_name)
            if scope == "new_course":
                graph = build_course_graph(run_id, provider, self.checkpointer)
            else:
                graph = build_review_graph(run_id, provider, self.checkpointer)
            self.graphs[run_id] = graph
        return self.graphs[run_id]

    async def _execute(
        self,
        run_id: str,
        course_slug: str,
        scope: str,
        request: dict[str, Any],
        provider_name: str,
        command: Command | None,
        continue_from_checkpoint: bool = False,
    ) -> None:
        async with self.semaphore:
            try:
                graph = self._graph_for(
                    run_id,
                    scope,
                    provider_name,
                    request.get("model"),
                )
                config = {
                    "configurable": {"thread_id": run_id},
                    "recursion_limit": 80,
                }
                graph_input: Any = (
                    (None if command is None else command)
                    if continue_from_checkpoint
                    else command
                    or {
                        "run_id": run_id,
                        "course_slug": course_slug,
                        "scope": scope,
                        "request": request,
                    }
                )
                if continue_from_checkpoint and command is None:
                    config = _continuation_config(graph, config)
                update_run(
                    run_id,
                    status="RUNNING",
                    clear_interrupt=True,
                    clear_error=True,
                )
                result = await self._invoke_with_heartbeat(
                    run_id,
                    graph,
                    graph_input,
                    config,
                )
                latest_config = {"configurable": {"thread_id": run_id}}
                interrupt_value = self._extract_interrupt(graph, result, latest_config)
                if interrupt_value:
                    step = interrupt_value.get("step", "intake")
                    update_run(
                        run_id,
                        status="WAITING_APPROVAL",
                        step=step,
                        interrupt_type=interrupt_value.get("type", "APPROVAL"),
                        interrupt_payload=interrupt_value,
                    )
                    append_event(
                        run_id,
                        "approval.requested",
                        step,
                        interrupt_value.get("title", "等待用户确认"),
                    )
                    return
                _require_terminal_graph_state(graph, latest_config)
                final_status = result.get("final_status", "COMPLETED")
                status = "STOPPED" if final_status == "STOPPED" else "COMPLETED"
                update_run(run_id, status=status, step="release", clear_interrupt=True)
                append_event(
                    run_id,
                    "run.completed",
                    "release",
                    f"Run 已结束：{final_status}",
                )
            except Exception as exc:
                update_run(
                    run_id,
                    status="FAILED",
                    error_message=str(exc)[:2000],
                    clear_interrupt=True,
                )
                append_event(
                    run_id,
                    "run.failed",
                    "intake",
                    "课程工作流执行失败",
                    {"error": str(exc)[:2000]},
                )

    async def _invoke_with_heartbeat(self, run_id: str, graph, graph_input: Any, config: dict):
        """Keep the local UI informed while a blocking model/tool call is in flight."""
        invoke_task = asyncio.create_task(
            asyncio.to_thread(graph.invoke, graph_input, config)
        )
        while not invoke_task.done():
            try:
                await asyncio.wait_for(asyncio.shield(invoke_task), timeout=15)
            except asyncio.TimeoutError:
                run = get_run_record(run_id) or {}
                step = run.get("current_step", "intake")
                progress = next(
                    (
                        event
                        for event in reversed(run.get("events", []))
                        if event.get("event_type") != "run.heartbeat"
                    ),
                    None,
                )
                detail = progress.get("message") if progress else "正在准备当前节点"
                elapsed_note = ""
                overrun_note = ""
                if progress and progress.get("created_at"):
                    try:
                        started_at = datetime.fromisoformat(progress["created_at"])
                        seconds = max(0, int((datetime.now(started_at.tzinfo) - started_at).total_seconds()))
                        elapsed_note = f"，已等待 {seconds // 60} 分 {seconds % 60} 秒"
                        if seconds >= self.settings.llm_call_hard_timeout_seconds:
                            overrun_note = (
                                "；已超过普通调用时限，当前可能在处理整章内容，"
                                "仍会在阶段级硬上限前继续等待"
                            )
                    except (TypeError, ValueError):
                        pass
                append_event(
                    run_id,
                    "run.heartbeat",
                    step,
                    f"{detail}；正在等待模型或工具返回{elapsed_note}{overrun_note}",
                )
                execution = current_execution.get()
                if execution:
                    renew_command_lease(
                        execution.command_id, execution.worker_id, execution.lease_seconds
                    )
        return await invoke_task

    @staticmethod
    def _extract_interrupt(graph, result, config) -> dict[str, Any] | None:
        interrupts = result.get("__interrupt__", ()) if isinstance(result, dict) else ()
        if interrupts:
            item = interrupts[0]
            return item.value if hasattr(item, "value") else dict(item)
        snapshot = graph.get_state(config)
        snapshot_interrupts = getattr(snapshot, "interrupts", ())
        if snapshot_interrupts:
            item = snapshot_interrupts[0]
            return item.value if hasattr(item, "value") else dict(item)
        return None
