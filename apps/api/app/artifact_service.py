from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.course_service import get_course


def _read_text(path: Path) -> str | None:
    return path.read_text(encoding="utf-8") if path.exists() else None


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _artifact(
    run: dict[str, Any],
    step: str,
    title: str,
    conclusion: str,
    highlights: list[str],
    raw_output: dict[str, Any],
    metrics: dict[str, str | int | float | bool] | None = None,
    issues: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": f"recovered-{run['id']}-{step}",
        "run_id": run["id"],
        "step": step,
        "node": "historical_recovery",
        "title": title,
        "source": "recovered",
        "presentation": {
            "headline": title,
            "conclusion": conclusion,
            "highlights": highlights,
            "metrics": metrics or {},
            "issues": issues or [],
            "next_action": "可展开查看从本地文件恢复的原始信息。",
        },
        "raw_output": raw_output,
        "created_at": run["updated_at"],
    }


def _recover_course_artifacts(run: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        course = get_course(run["course_slug"])
    except FileNotFoundError:
        return []
    root = get_settings().courses_root / run["course_slug"]
    mission = _read_text(root / "workspace" / "MISSION.md")
    blueprint = _read_text(root / "workspace" / "COURSE-BLUEPRINT.md")
    generation_plan = _read_json(root / "workspace" / "generation-plan.agent.json")
    continuity = _read_json(root / "workspace" / "continuity-ledger.agent.json")
    quality_files = (
        [
            str(path.relative_to(root))
            for path in sorted((root / "quality").glob("*"))
            if path.is_file()
        ]
        if (root / "quality").exists()
        else []
    )
    artifacts = [
        _artifact(
            run,
            "intake",
            "课程基础信息",
            "已从 course.json 和课程目录恢复课程输入。",
            [
                f"课程：{course['title']}",
                f"章节：{course['chapter_count']}",
                f"状态：{course['status']}",
            ],
            {
                "title": course["title"],
                "description": course["description"],
                "status": course["status"],
                "duration": course["duration"],
            },
            {"章节数": course["chapter_count"]},
        ),
    ]
    if mission:
        artifacts.append(
            _artifact(
                run,
                "mission",
                "现有任务定义",
                "原始模型响应没有留存；以下内容从 MISSION.md 恢复。",
                ["任务定义文件仍在本地 workspace 中。"],
                {
                    "path": "workspace/MISSION.md",
                    "content": mission,
                },
            )
        )
    else:
        artifacts.append(
            _artifact(
                run,
                "mission",
                "未找到历史任务定义",
                "这门课程没有可恢复的 MISSION.md，早期模型响应也未保存。",
                ["课程正文仍可继续 Review，但无法还原当时的任务定义生成过程。"],
                {"available": False, "expected_path": "workspace/MISSION.md"},
                issues=["历史任务定义不可恢复"],
            )
        )
    if blueprint:
        artifacts.append(
            _artifact(
                run,
                "blueprint",
                "现有课程蓝图",
                "原始模型响应没有留存；以下内容从 COURSE-BLUEPRINT.md 恢复。",
                ["模块、章节与学习成果仍可完整查看。"],
                {
                    "path": "workspace/COURSE-BLUEPRINT.md",
                    "content": blueprint,
                },
            )
        )
    else:
        artifacts.append(
            _artifact(
                run,
                "blueprint",
                "未找到历史课程蓝图",
                "这门课程没有可恢复的 COURSE-BLUEPRINT.md。",
                ["现有章节目录可以作为结构索引，但不等同于原始蓝图。"],
                {
                    "available": False,
                    "expected_path": "workspace/COURSE-BLUEPRINT.md",
                },
                issues=["历史蓝图不可恢复"],
            )
        )
    if generation_plan:
        artifacts.append(
            _artifact(
                run,
                "batch_plan",
                "历史生成批次",
                "已找到 Agent 生成计划。",
                [
                    f"批次数：{len(generation_plan.get('batches', []))}",
                    generation_plan.get("strategy", ""),
                ],
                generation_plan,
                {"批次数": len(generation_plan.get("batches", []))},
            )
        )
    else:
        artifacts.append(
            _artifact(
                run,
                "batch_plan",
                "未找到历史批次计划",
                "该课程不是由当前 Agent 的批次节点生成，或早期生成计划没有留存。",
                ["后续新建和重生成课程会保存每个批次及其 Context Pack。"],
                {
                    "available": False,
                    "expected_path": "workspace/generation-plan.agent.json",
                },
                issues=["原始批次划分不可恢复"],
            )
        )
    lessons = [
        {
            "number": lesson.get("number"),
            "title": lesson.get("title"),
            "path": lesson.get("markdown"),
        }
        for lesson in course["lessons"]
    ]
    artifacts.append(
        _artifact(
            run,
            "generation",
            "现有 Markdown 章节",
            "章节正文仍保存在本地；这里展示产物索引，不复制整章正文。",
            [f"已找到 {len(lessons)} 个 Markdown 章节。"],
            {
                "lessons": lessons,
                "continuity_ledger": continuity,
            },
            {"Markdown 章节": len(lessons)},
        )
    )
    quality_raw: dict[str, Any] = {"quality_files": quality_files}
    if (
        run.get("current_step") == "quality"
        and (run.get("interrupt_payload") or {}).get("output") is not None
    ):
        quality_raw["current_review"] = run["interrupt_payload"]["output"]
    artifacts.append(
        _artifact(
            run,
            "quality",
            "课程质量记录",
            "质量报告仍在本地；当前 Review 的完整结构化输出也会保留。",
            [f"已找到 {len(quality_files)} 份质量相关文件。"],
            quality_raw,
            {"质量文件": len(quality_files)},
        )
    )
    artifacts.append(
        _artifact(
            run,
            "release",
            "当前交付状态",
            f"课程当前状态为 {course['status']}。",
            [
                "课程首页存在" if (root / "index.html").exists() else "课程首页尚未生成",
                f"交付章节：{course['chapter_count']}",
            ],
            {
                "status": course["status"],
                "index_html": (root / "index.html").exists(),
                "chapter_count": course["chapter_count"],
            },
        )
    )
    return artifacts


def _submitted_intake_artifact(run: dict[str, Any]) -> dict[str, Any]:
    request = run.get("request", {})
    return {
        "id": f"submitted-{run['id']}-intake",
        "run_id": run["id"],
        "step": "intake",
        "node": "course_create",
        "title": "本次课程需求",
        "source": "submitted",
        "presentation": {
            "headline": "课程需求已提交",
            "conclusion": "这些信息来自本次新建课程表单，不是从历史课程文件恢复。",
            "highlights": [
                f"课程：{request.get('title', run['course_slug'])}",
                f"核心受众：{request.get('audience', '未填写')}",
                f"学习目标：{request.get('goals', '未填写')}",
                f"内容范围：{request.get('scope', '未填写')}",
            ],
            "metrics": {
                "期望章节数": request.get("preferred_chapter_count", ""),
                "单章有效字符下限": request.get("effective_char_min", ""),
            },
            "issues": [],
            "next_action": "继续查看本次 Run 后续节点的生成结果。",
        },
        "raw_output": request,
        "created_at": run.get("created_at", run["updated_at"]),
    }


def _derive_missing_creation_artifacts(run: dict[str, Any], existing_steps: set[str]) -> list[dict[str, Any]]:
    """Expose durable outputs for older creation runs that predate artifacts.

    These are not historical-course recovery records: the files belong to the
    same creation Run.  The distinction matters because a completed workflow
    must remain reviewable even if an early process version did not persist a
    node artifact at the moment it was produced.
    """
    root = get_settings().courses_root / run["course_slug"]
    sources = {
        "mission": ("任务定义（本次 Run 的持久化产物）", root / "workspace" / "MISSION.md"),
        "blueprint": ("课程蓝图（本次 Run 的持久化产物）", root / "workspace" / "COURSE-BLUEPRINT.md"),
        "batch_plan": ("生成批次（本次 Run 的持久化产物）", root / "workspace" / "generation-plan.agent.json"),
        "quality": ("质量闭环（本次 Run 的持久化产物）", root / "quality" / "agent-batch-m1-01-03.json"),
    }
    artifacts: list[dict[str, Any]] = []
    for step, (title, path) in sources.items():
        if step in existing_steps or not path.exists():
            continue
        try:
            raw: dict[str, Any] = (
                json.loads(path.read_text(encoding="utf-8"))
                if path.suffix == ".json"
                else {"path": str(path.relative_to(root)), "content": path.read_text(encoding="utf-8")}
            )
        except (OSError, json.JSONDecodeError):
            continue
        artifacts.append(
            _artifact(
                run,
                step,
                title,
                "该节点的原始 artifact 未在早期版本中落库；以下内容由同一次 Run 的持久化 Workspace 产物推导。",
                [f"文件：{path.relative_to(root)}", "可展开查看完整内容与原始结构。"],
                raw,
                {"状态": "可追溯"},
            )
        )
        artifacts[-1]["source"] = "run_workspace"
        artifacts[-1]["id"] = f"run-workspace-{run['id']}-{step}"
    return artifacts


def attach_artifact_presentations(run: dict[str, Any]) -> dict[str, Any]:
    artifacts = list(run.get("artifacts", []))
    existing_steps = {artifact["step"] for artifact in artifacts}
    # 新建课程的节点产物必须只来自本次 Run。历史恢复只服务于对既有课程
    # 发起的 Review / 重生成，避免刚创建出的 course.json 被误称为“恢复”。
    request = run.get("request", {})
    workflow_scope = request.get("workflow_scope")
    if not workflow_scope:
        legacy_scope = request.get("scope")
        workflow_scope = (
            legacy_scope
            if legacy_scope in {"new_course", "review_course", "regenerate_course"}
            else "new_course"
        )
    if workflow_scope == "new_course":
        if "intake" not in existing_steps:
            artifacts.append(_submitted_intake_artifact(run))
        # Do not fabricate future-node outputs for a newly created course.
        # Once the run has genuinely reached production / quality / release,
        # older runs that missed artifact persistence may expose their own
        # durable workspace files as traceable outputs.
        if run.get("current_step") in {"generation", "quality", "release"} or run.get("status") == "COMPLETED":
            artifacts.extend(_derive_missing_creation_artifacts(run, existing_steps))
    else:
        for recovered in _recover_course_artifacts(run):
            if recovered["step"] not in existing_steps:
                artifacts.append(recovered)
    artifacts.sort(key=lambda item: (item["created_at"], item["id"]))
    run["artifacts"] = artifacts
    by_step: dict[str, list[dict[str, Any]]] = {}
    for artifact in artifacts:
        by_step.setdefault(artifact["step"], []).append(artifact)
    for step in run["workflow_steps"]:
        step["artifacts"] = by_step.get(step["id"], [])
    return run
