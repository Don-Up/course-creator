from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

from app.course_service import run_course_tool
from app.workflow.state import CourseAgentState
from app.workflow.services.batch_planning import _quality_gates_for_result


def _diagnose_course_tool_failure(evidence: str, path: str) -> tuple[str, str]:
    """Convert raw tool stderr into an actionable, bounded repair directive.

    Raw Node/Python stacks are retained as evidence, but never become the
    learner-facing or operator-facing task description.  Known contracts are
    repaired deterministically; everything else is delegated to a focused
    chapter-repair Agent rather than re-generating an entire course.
    """
    compact = " ".join(evidence.split())
    if "泄露学生不可见信息" in compact:
        excerpt = compact.split("泄露学生不可见信息:", 1)[-1].strip()[:600]
        return (
            f"{path}：学生可见内容触发披露边界检查；证据：『{excerpt}』。"
            "仅核对该命中语境：生产侧资料来源须移除，正常的学习者操作对话应保留。",
            "构建异常修复 Agent（披露语境定向修订）",
        )
    if "学生内容暴露本机私有路径" in compact:
        return (
            f"{path}：学生页面包含本机私有路径；将替换为与读者环境无关的相对路径或说明文字。",
            "构建异常修复 Agent（私有路径披露规则）",
        )
    if "参考文献" in compact and "外部链接" in compact:
        return (
            f"{path}：参考文献之前存在外部链接；将把链接保留为文本说明，并仅在“参考文献”章节保留 URL。",
            "构建异常修复 Agent（参考文献链接规则）",
        )
    if "章首必须且只能包含" in compact:
        return (
            f"{path}：章首格式不符合发布契约；将规范为“预计学习时间”和“一句话总结”两行。",
            "构建异常修复 Agent（章首结构规则）",
        )
    if "代码围栏" in compact and ("未闭合" in compact or "闭合" in compact):
        return (
            f"{path}：Markdown 代码围栏未闭合；将补齐围栏并重新验证。",
            "构建异常修复 Agent（Markdown 结构规则）",
        )
    if "本地链接目标不存在" in compact:
        return (
            f"{path}：引用了不存在的本地资源；将移除失效引用并保留必要文字说明。",
            "构建异常修复 Agent（本地资源规则）",
        )
    return (
        f"{path}：确定性构建或校验未通过；需要根据已保留的原始诊断进行章节级定向修复。",
        "构建异常修复 Agent（基于诊断的章节级修订）",
    )


def _normalize_lesson_intro(markdown: str) -> tuple[str, bool]:
    """Repair the deterministic two-line public lesson header contract."""
    lines = markdown.splitlines()
    title_index = next(
        (index for index, line in enumerate(lines) if line.startswith("# ")),
        None,
    )
    if title_index is None:
        return markdown, False
    cursor = title_index + 1
    while cursor < len(lines) and not lines[cursor].strip():
        cursor += 1
    intro_start = cursor
    intro: list[str] = []
    while cursor < len(lines) and lines[cursor].lstrip().startswith(">"):
        intro.append(re.sub(r"^\s*>\s?", "", lines[cursor]).strip())
        cursor += 1
    inline_time = (
        re.match(
            r"^\*\*(?:预计)?学习时间\s*[：:]\s*([^*]+?)\*\*\s*(.+)$",
            intro[0],
        )
        if len(intro) == 1
        else None
    )
    if inline_time:
        body_cursor = cursor
        while body_cursor < len(lines) and not lines[body_cursor].strip():
            body_cursor += 1
        normalized = "\n".join(
            [
                *lines[:intro_start],
                f"> 预计学习时间：{inline_time.group(1).strip()}  ",
                f"> 一句话总结：{inline_time.group(2).strip()}",
                "",
                *lines[body_cursor:],
            ]
        )
        if markdown.endswith("\n"):
            normalized += "\n"
        return normalized, normalized != markdown
    if not intro:
        # Older or manually edited lessons often have the two metadata lines
        # as ordinary paragraphs. The renderer requires block quotes, so the
        # previous normalizer silently did nothing and every later repair
        # round rediscovered the same root violation.
        plain_candidates: list[tuple[int, str]] = []
        plain_cursor = title_index + 1
        while plain_cursor < len(lines) and len(plain_candidates) < 8:
            line = lines[plain_cursor].strip()
            if line == "---" or line.startswith("## "):
                break
            if line:
                plain_candidates.append((plain_cursor, line))
            plain_cursor += 1
        time_item = next(
            (
                (index, re.sub(r"^(?:\*\*)?(?:预计)?学习时间(?:\*\*)?\s*[：:]\s*", "", line).strip())
                for index, line in plain_candidates
                if re.match(r"^(?:\*\*)?(?:预计)?学习时间(?:\*\*)?\s*[：:]", line)
            ),
            None,
        )
        summary_item = next(
            (
                (index, re.sub(r"^(?:\*\*)?一句话总结(?:\*\*)?\s*[：:]\s*", "", line).strip())
                for index, line in plain_candidates
                if re.match(r"^(?:\*\*)?一句话总结(?:\*\*)?\s*[：:]", line)
            ),
            None,
        )
        if not time_item or not summary_item:
            return markdown, False
        last_intro_index = max(time_item[0], summary_item[0])
        body_cursor = last_intro_index + 1
        while body_cursor < len(lines) and not lines[body_cursor].strip():
            body_cursor += 1
        normalized = "\n".join(
            [
                *lines[: title_index + 1],
                "",
                f"> 预计学习时间：{time_item[1]}  ",
                f"> 一句话总结：{summary_item[1]}",
                "",
                *lines[body_cursor:],
            ]
        )
        if markdown.endswith("\n"):
            normalized += "\n"
        return normalized, normalized != markdown
    time = next(
        (
            re.sub(r"^(?:\*\*)?(?:预计)?学习时间(?:\*\*)?\s*[：:]\s*", "", line)
            for line in intro
            if re.match(r"^(?:\*\*)?(?:预计)?学习时间", line)
        ),
        "",
    ).strip()
    summary = next(
        (
            re.sub(r"^(?:\*\*)?一句话总结(?:\*\*)?\s*[：:]\s*", "", line)
            for line in intro
            if re.match(r"^(?:\*\*)?一句话总结", line)
        ),
        "",
    ).strip()
    if not time or not summary:
        return markdown, False
    # Keep extra opening notes, but move them out of the two-line public
    # header contract instead of silently deleting useful learner guidance.
    extra_intro = [
        line
        for line in intro
        if not re.match(r"^(?:\*\*)?(?:预计)?学习时间", line)
        and not re.match(r"^(?:\*\*)?一句话总结", line)
    ]
    # Keep the conventional Markdown hard break between the two metadata
    # lines.  Besides rendering more cleanly, this makes the normalizer
    # idempotent for a header that already satisfies the renderer contract.
    replacement = [f"> 预计学习时间：{time}  ", f"> 一句话总结：{summary}"]
    body_prefix = [*extra_intro, ""] if extra_intro else []
    # Consume original separator blank lines before restoring exactly one.
    # Without this, a valid header is textually rewritten on every repair.
    body_cursor = cursor
    while body_cursor < len(lines) and not lines[body_cursor].strip():
        body_cursor += 1
    updated = [*lines[:intro_start], *replacement, "", *body_prefix, *lines[body_cursor:]]
    normalized = "\n".join(updated)
    if markdown.endswith("\n"):
        normalized += "\n"
    return normalized, normalized != markdown


def _relocate_external_links_to_references(markdown: str) -> tuple[str, bool]:
    """Move URL evidence behind the already-canonical reference boundary.

    This parser handles Markdown link syntax only. It does not infer section
    semantics: the AST + Agent stage must have established ``## 参考文献``
    before this deterministic operation is allowed to run.
    """
    marker = "## 参考文献"
    reference_index = markdown.find(marker)
    if reference_index < 0:
        return markdown, False
    before = markdown[:reference_index]
    after = markdown[reference_index:]
    moved: list[tuple[str, str]] = []
    pattern = re.compile(r"(!?)\[([^\]]+)\]\((https?://[^)\s]+)(?:\s+[\"'][^\"']*[\"'])?\)")

    def replace(match: re.Match[str]) -> str:
        image, label, url = match.groups()
        moved.append((label.strip() or "外部资料", url))
        if image:
            return f"> 图示说明：{label.strip()}（外部图像地址见本章参考文献）"
        return f"{label.strip()}（见本章参考文献）"

    repaired_before = pattern.sub(replace, before)
    if not moved:
        return markdown, False
    additions = []
    seen_urls = set()
    for label, url in moved:
        if url in seen_urls or url in after:
            continue
        seen_urls.add(url)
        additions.append(f"- [{label}]({url})")
    if additions:
        heading_end = after.find("\n")
        if heading_end < 0:
            after = after + "\n\n" + "\n".join(additions) + "\n"
        else:
            after = after[:heading_end + 1] + "\n" + "\n".join(additions) + "\n" + after[heading_end + 1:]
    return repaired_before + after, True


def _full_course_validation_after_build(
    course_slug: str,
    build: dict[str, Any],
    *,
    validate_tool: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Validate only fresh build output, never stale generated HTML.

    If rendering stops at the first Markdown error, existing ``lessons/*.html``
    files describe a previous revision. Scanning them creates a cascade of
    false local-link RepairTasks. The build error itself is the sole valid
    deterministic evidence until the root source is repaired and a fresh
    course build completes.
    """
    if not build.get("succeeded"):
        return {
            "succeeded": False,
            "exit_code": build.get("exit_code"),
            "stdout": "",
            "stderr": "整课构建未通过，未执行整课确定性检查；请先修复构建诊断。",
            "scope": {"scope": "course"},
        }
    return validate_tool() if validate_tool else run_course_tool(course_slug, "validate")


def _quality_review_can_auto_complete(report: dict[str, Any]) -> bool:
    """A clean all-course review is a workflow transition, not a new pause."""
    scan = report.get("deterministic_scan") or {}
    return (
        not report.get("unresolved")
        and not report.get("course_issues")
        and bool(scan.get("succeeded"))
    )


def _refresh_quality_review_state(
    refresh: Callable[[CourseAgentState], dict[str, Any]],
    state: CourseAgentState,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Keep a fresh Review report coupled to the state facts it summarizes."""
    fresh = refresh(state)
    report = fresh.get("course_quality_report")
    if not isinstance(report, dict):
        raise RuntimeError("整课质量刷新未返回 course_quality_report")
    return fresh, report


def _contract_repair_entries(
    contract_result: dict[str, Any], chapters: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Attach stable AST diagnostics to the chapter that owns each source."""
    chapter_by_path = {
        str(chapter.get("path") or ""): chapter
        for chapter in chapters
        if chapter.get("path")
    }
    lesson_hashes = {
        str(lesson.get("path") or ""): str(lesson.get("hash") or "")
        for lesson in (contract_result.get("report") or {}).get("lessons", [])
    }
    grouped: dict[int, dict[str, Any]] = {}
    for diagnostic in contract_result.get("diagnostics") or []:
        path = str(diagnostic.get("path") or "")
        chapter = chapter_by_path.get(path)
        if not chapter:
            continue
        number = int(chapter.get("chapter") or 0)
        if not number:
            continue
        code = str(diagnostic.get("code") or "COURSE_STRUCTURE_ERROR")
        evidence = {
            **diagnostic,
            "source_hash": lesson_hashes.get(path, ""),
        }
        entry = grouped.setdefault(number, {
            "chapter": number,
            "title": chapter.get("title", ""),
            "path": path,
            "issues": [],
            "repair_agents": [],
            "contract_diagnostics": [],
        })
        entry["issues"].append(
            f"[{code}] {diagnostic.get('actual') or '当前结构'}；期望：{diagnostic.get('expected') or '满足课程结构契约'}"
        )
        entry["contract_diagnostics"].append(evidence)
        capability = str(diagnostic.get("repair_capability") or "structure_contract")
        entry["repair_agents"].append(f"结构契约修复 Agent（{capability}）")
    return list(grouped.values())


def _batch_contract_repair_entries(
    contract_result: dict[str, Any],
    batch: dict[str, Any],
    chapters: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return structural repairs owned by one production batch only.

    ``source_contract`` is intentionally run before a batch build.  A build
    can fail because one Markdown node violates the publishing contract; that
    evidence belongs in the same chapter-local repair sweep, never in another
    batch and never in a blind whole-batch regeneration retry.
    """
    chapter_numbers = {int(value) for value in batch.get("chapter_numbers", [])}
    entries = _contract_repair_entries(contract_result, chapters)
    return [
        {**entry, "batch": batch}
        for entry in entries
        if int(entry.get("chapter") or 0) in chapter_numbers
    ]


def _repair_queue_for_scope(state: CourseAgentState) -> list[dict[str, Any]]:
    """Select the checkpointed queue without crossing batch/course scope."""
    if state.get("repair_scope") == "batch":
        return list(state.get("batch_repair_queue") or [])
    return list(
        state.get("quality_cycle_queue")
        if state.get("quality_cycle_queue") is not None
        else state.get("quality_repair_queue", [])
    )


def _repair_queue_patch(scope: str, queue: list[dict[str, Any]]) -> dict[str, Any]:
    """Persist queue ownership explicitly for interruption-safe resumption."""
    if scope == "batch":
        return {
            "batch_repair_queue": queue,
            "batch_repair_active": bool(queue),
            "quality_repair_active": False,
        }
    return {
        "quality_cycle_queue": queue,
        "quality_repair_queue": queue,
        "quality_repair_active": bool(queue),
    }


def _replace_batch_integration(
    batch_results: list[dict[str, Any]],
    batch_id: str,
    build: dict[str, Any],
    validation: dict[str, Any],
) -> list[dict[str, Any]]:
    """Refresh only the owning batch's deterministic integration evidence."""
    updated = [dict(item) for item in batch_results]
    for index in range(len(updated) - 1, -1, -1):
        result = updated[index]
        if result.get("batch", {}).get("id") != batch_id:
            continue
        chapters = list(result.get("chapters", []))
        updated[index] = {
            **result,
            "build": build,
            "validation": validation,
            "quality_gates": _quality_gates_for_result(chapters, build, validation),
            "passed": all(chapter.get("passed") for chapter in chapters)
            and bool(build.get("succeeded"))
            and bool(validation.get("succeeded")),
        }
        break
    return updated


def _lesson_header_repair_entries(
    course_root: Path,
    chapters: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Find every invalid two-line lesson header before the renderer fails."""
    chapter_by_number = {int(item.get("chapter")): item for item in chapters if item.get("chapter")}
    entries: list[dict[str, Any]] = []
    for path in sorted((course_root / "lessons").glob("*.md")):
        match = re.match(r"(\d+)-", path.name)
        if not match:
            continue
        number = int(match.group(1))
        lines = path.read_text(encoding="utf-8").splitlines()
        title_index = next((index for index, line in enumerate(lines) if line.startswith("# ")), None)
        if title_index is None:
            continue
        cursor = title_index + 1
        while cursor < len(lines) and not lines[cursor].strip():
            cursor += 1
        intro: list[str] = []
        while cursor < len(lines) and lines[cursor].lstrip().startswith(">"):
            intro.append(re.sub(r"^\s*>\s?", "", lines[cursor]).strip())
            cursor += 1
        valid = (
            len(intro) == 2
            and any(line.startswith("预计学习时间：") for line in intro)
            and any(line.startswith("一句话总结：") for line in intro)
        )
        if valid:
            continue
        source = chapter_by_number.get(number, {})
        entries.append(
            {
                "chapter": number,
                "title": source.get("title", f"第 {number} 章"),
                "path": source.get("path", f"lessons/{path.name}"),
                "issues": ["章首必须且只能包含预计学习时间和一句话总结"],
                "repair_agents": ["结构 / 链接确定性修复工具"],
            }
        )
    return entries
