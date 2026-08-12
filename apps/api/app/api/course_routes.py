from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app.api.course_helpers import (
    attach_resumable_creation_run,
    find_resumable_creation_run,
    persist_primary_workflow_run,
)
from app.course_service import (
    append_workspace_resource_note,
    create_course_scaffold,
    get_chapter,
    get_course_asset,
    get_course,
    get_workspace_file,
    list_courses,
    list_workspace_files,
    run_course_tool,
    update_chapter,
    update_workspace_file,
    upload_workspace_resource,
)
from app.schemas import (
    ChapterUpdate, CourseCreate, RunStart, WorkspaceFileUpdate,
    WorkspaceResourceNote, WorkspaceResourceUpload,
)
from app.workflow.command_repository import enqueue_command
from app.workflow.repository import create_run_record, list_run_records, record_run_artifact


router = APIRouter(prefix="/api/courses", tags=["courses"])


def build_router() -> APIRouter:
    @router.get("")
    def courses():
        return {"items": [attach_resumable_creation_run(course, list_run_records(course["slug"])) for course in list_courses()]}

    @router.post("", status_code=201)
    async def create_course(payload: CourseCreate):
        try:
            course = create_course_scaffold(payload)
        except FileExistsError:
            raise HTTPException(409, "课程 slug 已存在") from None
        run_id = str(uuid.uuid4())
        request = {**payload.model_dump(mode="json"), "workflow_scope": "new_course"}
        budget_policy = (
            {"max_total_tokens": round(payload.token_budget_mtokens * 1_000_000)}
            if payload.token_budget_mtokens is not None
            else {}
        )
        create_run_record(run_id, payload.slug, "guided", payload.provider, payload.model, request, budget_policy=budget_policy)
        persist_primary_workflow_run(payload.slug, run_id)
        record_run_artifact(
            run_id, "intake", "course_create", "本次课程需求",
            {
                "headline": "课程需求已提交",
                "conclusion": "以下信息来自本次新建课程表单，并已写入新的本地课程工作区。",
                "highlights": [f"课程：{payload.title}", f"核心受众：{payload.audience}", f"目标：{payload.goals}", f"内容范围：{payload.scope}"],
                "metrics": {"期望章节数": payload.preferred_chapter_count, "单章有效字符下限": payload.effective_char_min, "Token 阈值": f"{payload.token_budget_mtokens:g} M" if payload.token_budget_mtokens is not None else "不限制"},
                "issues": [], "next_action": "Agent 正在根据本次输入生成课程任务定义。",
            }, request, source="submitted",
        )
        command, duplicate = enqueue_command(run_id, "START")
        return {"course": course, "run_id": run_id, "command_id": command["id"], "duplicate": duplicate}

    @router.get("/{slug}/workspace")
    def workspace_files(slug: str):
        try:
            return {"items": list_workspace_files(slug)}
        except FileNotFoundError:
            raise HTTPException(404, "课程不存在") from None

    @router.get("/{slug}/assets/{path:path}")
    def course_asset(slug: str, path: str):
        try:
            return FileResponse(get_course_asset(slug, path))
        except FileNotFoundError:
            raise HTTPException(404, "课程素材不存在") from None
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None

    @router.get("/{slug}/workspace/file")
    def workspace_file(slug: str, path: Annotated[str, Query()]):
        try:
            return get_workspace_file(slug, path)
        except FileNotFoundError:
            raise HTTPException(404, "Workspace 文件不存在") from None
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None

    @router.put("/{slug}/workspace/file")
    def save_workspace_file(slug: str, payload: WorkspaceFileUpdate, path: Annotated[str, Query()]):
        try:
            return update_workspace_file(slug, path, payload.content, payload.expected_hash)
        except FileNotFoundError:
            raise HTTPException(404, "Workspace 文件不存在") from None
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from None
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None

    @router.post("/{slug}/workspace/resources", status_code=201)
    def upload_resource(slug: str, payload: WorkspaceResourceUpload):
        try:
            return upload_workspace_resource(slug, payload.filename, payload.content_base64, payload.media_type)
        except FileNotFoundError:
            raise HTTPException(404, "课程不存在") from None
        except FileExistsError:
            raise HTTPException(409, "同名资源已经存在") from None
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None

    @router.post("/{slug}/workspace/resources/note")
    def append_resource_note(slug: str, payload: WorkspaceResourceNote):
        try:
            return append_workspace_resource_note(slug, payload.content)
        except FileNotFoundError:
            raise HTTPException(404, "课程不存在") from None
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None

    @router.get("/{slug}")
    def course_detail(slug: str):
        try:
            course = get_course(slug)
        except FileNotFoundError:
            raise HTTPException(404, "课程不存在") from None
        runs = list_run_records(slug)
        course["runs"] = runs
        return attach_resumable_creation_run(course, runs)

    @router.get("/{slug}/chapters/{key:path}")
    def chapter_detail(slug: str, key: str):
        try:
            return get_chapter(slug, key)
        except FileNotFoundError:
            raise HTTPException(404, "章节不存在") from None

    @router.put("/{slug}/chapters/{key:path}")
    def save_chapter(slug: str, key: str, payload: ChapterUpdate):
        try:
            chapter = update_chapter(slug, key, payload.content, payload.expected_hash, payload.reason)
            return {"chapter": chapter, "build": run_course_tool(slug, "build") if payload.rebuild else None}
        except FileNotFoundError:
            raise HTTPException(404, "章节不存在") from None
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from None
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None

    @router.post("/{slug}/tools/{action}")
    def course_tool(slug: str, action: str):
        try:
            return run_course_tool(slug, action)
        except FileNotFoundError:
            raise HTTPException(404, "课程不存在") from None
        except (ValueError, TimeoutError) as exc:
            raise HTTPException(400, str(exc)) from None

    @router.post("/{slug}/runs", status_code=202)
    async def start_run(slug: str, payload: RunStart):
        try:
            course = get_course(slug)
        except FileNotFoundError:
            raise HTTPException(404, "课程不存在") from None
        if find_resumable_creation_run(course, list_run_records(slug)) and payload.scope in {"review_course", "regenerate_course"}:
            raise HTTPException(409, "该课程仍在创建 Workflow 中，请先回到原 Workflow 完成剩余批次。")
        if payload.scope in {"review_course", "regenerate_course"} and not course["chapter_count"]:
            raise HTTPException(409, "课程尚未生成章节，请先回到创建 Workflow 完成蓝图与章节生成，再执行 Review 或重生成。")
        run_id = str(uuid.uuid4())
        request = {**payload.model_dump(mode="json"), "workflow_scope": payload.scope, "title": course["title"], "chapter_count": course["chapter_count"]}
        create_run_record(run_id, slug, "guided", payload.provider, payload.model, request)
        command, duplicate = enqueue_command(run_id, "START")
        return {"run_id": run_id, "command_id": command["id"], "duplicate": duplicate}

    globals().update(create_course=create_course, start_run=start_run)
    return router
