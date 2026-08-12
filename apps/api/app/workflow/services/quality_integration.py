from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

from app.config import get_settings
from app.course_service import run_course_tool, write_course_quality_snapshot
from app.workflow.state import CourseAgentState
from app.workflow.services.batch_planning import _quality_gates_for_result
from app.workflow.services.context_packs import _effective_char_count
from app.workflow.services.course_quality import _diagnose_course_tool_failure
from app.workflow.services.workspace_contract import _write_json


def _repair_agents_for_chapter(chapter: dict[str, Any]) -> list[str]:
    """Map recorded gate evidence to bounded, chapter-local repair tools."""
    issues = [str(item) for item in chapter.get("issues", [])]
    semantic = chapter.get("semantic_review") or {}
    agents: list[str] = []
    if (
        chapter.get("effective_chars", 0) > 0
        and chapter.get("effective_chars", 0) < chapter.get("effective_char_min", 0)
    ) or any(
        "有效字符" in issue for issue in issues
    ):
        agents.append("内容丰富化 Agent（补齐缺失教学层）")
    if (
        isinstance(chapter.get("humanizer_score"), (int, float))
        and chapter["humanizer_score"] < 45
    ) or any("Humanizer" in issue for issue in issues):
        agents.append("Humanizer Agent（定点语言修订）")
    if semantic.get("decision") not in {None, "ready"} or any(
        marker in issue
        for issue in issues
        for marker in ("[blocker]", "[major]", "[minor]", "语义", "事实")
    ):
        agents.append("教学语义与事实修订 Agent")
    if any("连续性" in issue for issue in issues):
        agents.append("连续性账本 Agent")
    return agents or ["确定性构建 / 格式修复工具"]


def _replace_quality_chapter_result(
    batch_results: list[dict[str, Any]],
    chapter_number: int,
    updated_chapter: dict[str, Any],
) -> list[dict[str, Any]]:
    """Replace one chapter only in the latest result of the owning batch."""
    updated = [dict(item) for item in batch_results]
    for index in range(len(updated) - 1, -1, -1):
        chapters = list(updated[index].get("chapters", []))
        if not any(chapter.get("chapter") == chapter_number for chapter in chapters):
            continue
        updated[index] = {
            **updated[index],
            "chapters": [
                updated_chapter if chapter.get("chapter") == chapter_number else chapter
                for chapter in chapters
            ],
        }
        break
    return updated


def _refresh_quality_integration(
    batch_results: list[dict[str, Any]],
    build: dict[str, Any],
    validation: dict[str, Any],
) -> list[dict[str, Any]]:
    """Attach whole-course evidence without overwriting autonomous batch gates."""
    latest_indexes: dict[str, int] = {}
    for index, result in enumerate(batch_results):
        batch_id = result.get("batch", {}).get("id")
        if batch_id:
            latest_indexes[batch_id] = index
    refreshed = [dict(item) for item in batch_results]
    for index in latest_indexes.values():
        result = refreshed[index]
        refreshed[index] = {
            **result,
            "course_build": build,
            "course_validation": validation,
            "course_integration": {
                "passed": bool(build.get("succeeded")) and bool(validation.get("succeeded")),
                "label": "整课构建与确定性检查（仅整课质量闭环使用）",
            },
        }
    return refreshed


def _revalidate_batch_integrations(
    course_slug: str,
    batch_results: list[dict[str, Any]],
    *,
    tool_runner: Callable[..., dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Refresh deterministic evidence one batch at a time.

    This is the compatibility path for checkpoints created before scoped batch
    gates existed.  It deliberately does not call LLM review agents again:
    their persisted chapter evidence remains intact, while build/validation
    and the effective-character metric are reconstructed from the current
    batch sources.
    """
    course_root = get_settings().courses_root / course_slug
    tool_runner = tool_runner or (lambda action, **kwargs: run_course_tool(course_slug, action, **kwargs))
    latest_indexes: dict[str, int] = {}
    for index, result in enumerate(batch_results):
        batch_id = result.get("batch", {}).get("id")
        if batch_id:
            latest_indexes[batch_id] = index
    refreshed = [dict(item) for item in batch_results]
    for index in latest_indexes.values():
        result = refreshed[index]
        batch = result.get("batch", {})
        numbers = [int(number) for number in batch.get("chapter_numbers", [])]
        if not numbers:
            continue
        try:
            build = tool_runner("build", chapter_numbers=numbers)
            validation = (
                tool_runner("validate", chapter_numbers=numbers)
                if build.get("succeeded")
                else {
                    "succeeded": False,
                    "stdout": "",
                    "stderr": "批次构建失败，未运行批次确定性检查",
                }
            )
        except Exception as error:
            build = {"succeeded": False, "stdout": "", "stderr": str(error)}
            validation = {
                "succeeded": False,
                "stdout": "",
                "stderr": "批次构建无法启动，未运行批次确定性检查",
            }
        chapters: list[dict[str, Any]] = []
        for chapter in result.get("chapters", []):
            current = dict(chapter)
            relative_path = current.get("path")
            source = course_root / str(relative_path) if relative_path else None
            if source and source.is_file():
                current["effective_chars"] = _effective_char_count(
                    source.read_text(encoding="utf-8")
                )
            chapters.append(current)
        refreshed[index] = {
            **result,
            "chapters": chapters,
            "build": build,
            "validation": validation,
            "quality_gates": _quality_gates_for_result(chapters, build, validation),
            "passed": (
                all(chapter.get("passed") for chapter in chapters)
                and bool(build.get("succeeded"))
                and bool(validation.get("succeeded"))
            ),
        }
    return refreshed


def _persist_latest_batch_quality_results(
    course_root: Path,
    batch_results: list[dict[str, Any]],
    *,
    repair_tasks: list[dict[str, Any]] | None = None,
    course_integration: dict[str, Any] | None = None,
    source_contract: dict[str, Any] | None = None,
    build: dict[str, Any] | None = None,
    artifact_validation: dict[str, Any] | None = None,
    quality_cycle: dict[str, Any] | None = None,
) -> None:
    """Keep durable batch reports aligned with the latest repair state.

    Batch quality JSON is also consumed outside the active LangGraph run.  A
    targeted repair must therefore update it instead of leaving a successful
    repair visible only in a checkpoint or a transient node artifact.
    """
    latest_by_id = {
        item.get("batch", {}).get("id"): item
        for item in batch_results
        if item.get("batch", {}).get("id")
    }
    for result in latest_by_id.values():
        batch = result.get("batch", {})
        batch_id = batch.get("id")
        if not batch_id:
            continue
        chapters = result.get("chapters", [])
        batch_build = result.get("build") or {}
        batch_validation = result.get("validation") or {}
        quality_gates = _quality_gates_for_result(chapters, batch_build, batch_validation)
        persisted = {
            **result,
            "quality_gates": quality_gates,
            "passed": all(item.get("passed") for item in chapters)
            and bool(batch_build.get("succeeded"))
            and bool(batch_validation.get("succeeded")),
        }
        _write_json(course_root / "quality" / f"agent-batch-{batch_id}.json", persisted)
    # The course article UI never derives its current state from the
    # append-only artifact timeline. Refresh its one facts snapshot in the
    # exact same write boundary as the durable per-batch reports.
    write_course_quality_snapshot(
        course_root,
        batch_results,
        repair_tasks=repair_tasks,
        course_integration=course_integration,
        source_contract=source_contract,
        build=build,
        artifact_validation=artifact_validation,
        quality_cycle=quality_cycle,
    )


def _integration_repair_entries(batch_result: dict[str, Any]) -> list[dict[str, Any]]:
    """Turn deterministic build evidence into chapter-local repair items."""
    build_result = batch_result.get("build") or {}
    validation_result = batch_result.get("validation") or {}
    build_diagnostics = "\n".join(
        str(build_result.get(key, "")) for key in ("stdout", "stderr")
    )
    validation_diagnostics = "\n".join(
        str(validation_result.get(key, "")) for key in ("stdout", "stderr")
    )
    # Validation aggregates every source error. Warnings remain non-blocking,
    # but an HTML error is still actionable because generated lesson HTML maps
    # one-to-one to its Markdown source. Ignoring it created a false “no
    # unresolved issues” state while the release check still failed.
    actionable_validation = "\n".join(
        line
        for line in validation_diagnostics.splitlines()
        if line.startswith("[ERROR]")
        and "lessons/" in line
        and (".md" in line or ".html" in line)
    )
    diagnostics = "\n".join(
        value for value in (build_diagnostics, actionable_validation) if value
    )
    chapter_numbers = {
        int(value)
        for value in re.findall(r"lessons/(\d+)-[^\s:`]+\.(?:md|html)", diagnostics)
    }
    chapters = {item.get("chapter"): item for item in batch_result.get("chapters", [])}
    entries = []
    for number in sorted(chapter_numbers):
        source = chapters.get(number, {})
        chapter_path = source.get("path", f"lessons/{number:02d}-chapter.md")
        chapter_lines = [
            line.strip()
            for line in diagnostics.splitlines()
            if chapter_path in line or f"lessons/{number:02d}-" in line
        ]
        evidence = "\n".join(chapter_lines) or diagnostics
        issue, strategy = _diagnose_course_tool_failure(evidence, chapter_path)
        entries.append(
            {
                "chapter": number,
                "title": source.get("title", f"第 {number} 章"),
                "path": chapter_path,
                "issues": [issue],
                "repair_agents": [strategy],
                "diagnostic_evidence": evidence[:1600],
            }
        )
    return entries
