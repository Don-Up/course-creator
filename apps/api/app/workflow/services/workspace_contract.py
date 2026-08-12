from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.workflow.state import CourseAgentState
from app.workflow.services.batch_planning import _make_batches


def _close_unclosed_markdown_fence(markdown: str) -> tuple[str, bool]:
    fences = [
        index
        for index, line in enumerate(markdown.splitlines())
        if re.match(r"^\s*```", line)
    ]
    if len(fences) % 2 == 0:
        return markdown, False
    reference_index = markdown.find("\n## 参考文献")
    insert_at = reference_index if reference_index >= 0 else len(markdown)
    normalized = markdown[:insert_at].rstrip() + "\n```\n\n" + markdown[insert_at:].lstrip("\n")
    return normalized, True


def _remove_missing_local_image(markdown: str, issue: str) -> tuple[str, bool]:
    match = re.search(r"本地链接目标不存在:\s*([^\s]+)", issue)
    if not match:
        return markdown, False
    target = re.escape(match.group(1).strip())
    normalized = re.sub(
        rf"!\[([^\]]*)\]\({target}\)",
        lambda image: f"> 图示说明：{image.group(1).strip() or '相关操作结果'}。",
        markdown,
    )
    return normalized, normalized != markdown


def _redact_private_paths(markdown: str) -> tuple[str, bool]:
    """Remove machine-specific home directories from student-visible text."""
    normalized = re.sub(
        r"/(?:Users|home)/[A-Za-z0-9._-]+/",
        "<项目根目录>/",
        markdown,
    )
    normalized = re.sub(
        r"[A-Z]:\\Users\\[A-Za-z0-9._-]+\\",
        r"<项目根目录>\\",
        normalized,
    )
    return normalized, normalized != markdown


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _chapter_progress_path(course_root: Path, batch_id: str, chapter: int) -> Path:
    return course_root / "quality" / f"agent-chapter-{batch_id}-{chapter:02d}.progress.json"


def _save_chapter_progress(
    course_root: Path, batch_id: str, chapter: int, progress: dict[str, Any]
) -> None:
    _write_json(_chapter_progress_path(course_root, batch_id, chapter), progress)


def _load_chapter_progress(course_root: Path, batch_id: str, chapter: int) -> dict[str, Any]:
    path = _chapter_progress_path(course_root, batch_id, chapter)
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _read_workspace_context(
    course_root: Path,
    limits: dict[str, int] | None = None,
) -> dict[str, str]:
    limits = limits or {
        # Core contract files must remain complete across a task-definition
        # revision. A presentation summary is bounded separately and must
        # never become the source of truth for these files.
        "MISSION.md": 65536,
        "COURSE-GENERATION-SPEC.md": 65536,
        "COURSE-BLUEPRINT.md": 65536,
        "RESOURCES.md": 48000,
        "NOTES.md": 32000,
    }
    context: dict[str, str] = {}
    for name, limit in limits.items():
        path = course_root / "workspace" / name
        if path.exists():
            content = path.read_text(encoding="utf-8")
            context[name] = (
                content
                if len(content) <= limit
                else content[:limit] + "\n[其余内容已截断]"
            )
    return context


_RESEARCH_START = "<!-- agent-research:start -->"
_RESEARCH_END = "<!-- agent-research:end -->"


def _research_markdown(research: dict[str, Any]) -> str:
    lines = [
        _RESEARCH_START,
        "## 自动检索记录",
        "",
        f"- 本轮来源政策：{research.get('policy', '未记录')}。",
        "- 检索覆盖：核心概念、框架/API、标准或论文、项目实践，以及需要时的安全与部署边界。",
        "- 使用方式：资料仅支撑其对应的事实、API 或实践；未核验社区资料不能作为关键事实的唯一依据。",
        "",
        "### 本轮检索计划",
        "",
    ]
    rationale = research.get("search_rationale")
    if rationale:
        lines.append(f"- 检索理由：{rationale}")
    queries = research.get("queries", [])
    if queries:
        lines.extend(f"- 检索词：`{query}`" for query in queries)
    if not rationale and not queries:
        lines.append("- 未执行公开检索。")
    lines.extend(["", "### 已核验可用资料", ""])
    if research.get("skipped"):
        lines.extend([f"- {research['reason']}", ""])
    elif research.get("sources"):
        for source in research["sources"]:
            lines.extend(
                [
                    f"- [{source['title']}]({source['url']})（{source['source_type']}）：{source['reason']}",
                ]
            )
        lines.append("")
    else:
        lines.extend(
            [
                "- 本轮公开检索未获得满足来源政策的可用资料。生成节点不得把未核验内容伪装成参考资料；请补充内部资源或在人工审核时确认。",
                "",
            ]
        )
    if research.get("notes"):
        lines.append("### 检索备注")
        lines.append("")
        lines.extend(f"- {note}" for note in research["notes"])
        lines.append("")
    lines.append(_RESEARCH_END)
    return "\n".join(lines)


def _write_research_to_resources(course_root: Path, research: dict[str, Any]) -> None:
    path = course_root / "workspace" / "RESOURCES.md"
    current = path.read_text(encoding="utf-8") if path.exists() else "# 课程资源\n\n"
    pattern = re.compile(
        rf"\n?{re.escape(_RESEARCH_START)}[\s\S]*?{re.escape(_RESEARCH_END)}\n?",
    )
    current = pattern.sub("\n", current).rstrip() + "\n\n"
    path.write_text(current + _research_markdown(research).rstrip() + "\n", encoding="utf-8")


def _blueprint_chapter_count(blueprint: dict[str, Any]) -> int:
    return sum(len(module.get("chapters", [])) for module in blueprint.get("modules", []))


def _sync_workspace_contract(course_root: Path, blueprint: dict[str, Any]) -> dict[str, Any]:
    """Keep all derived planning files aligned with the approved blueprint."""
    chapter_count = _blueprint_chapter_count(blueprint)
    changed: list[str] = []
    spec_path = course_root / "workspace" / "COURSE-GENERATION-SPEC.md"
    spec = spec_path.read_text(encoding="utf-8") if spec_path.exists() else "# 课程生成规格\n\n"
    expected_line = f"- 期望章节数：{chapter_count}（以课程蓝图为准）"
    if re.search(r"^- 期望章节数：.*$", spec, flags=re.MULTILINE):
        synced_spec = re.sub(r"^- 期望章节数：.*$", expected_line, spec, flags=re.MULTILINE)
    else:
        synced_spec = spec.rstrip() + "\n" + expected_line + "\n"
    if synced_spec != spec:
        spec_path.write_text(synced_spec, encoding="utf-8")
        changed.append("workspace/COURSE-GENERATION-SPEC.md")

    metadata_path = course_root / "course.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    modules = [
        {
            "title": module["title"],
            "goal": module["goal"],
            "chapterNumbers": [chapter["number"] for chapter in module["chapters"]],
        }
        for module in blueprint["modules"]
    ]
    metadata_changed = (
        metadata.get("title") != blueprint["course_title"]
        or metadata.get("planned_chapter_count") != chapter_count
        or metadata.get("modules") != modules
    )
    metadata.update(
        {
            "title": blueprint["course_title"],
            "planned_chapter_count": chapter_count,
            "modules": modules,
        }
    )
    if metadata_changed:
        _write_json(metadata_path, metadata)
        changed.append("course.json")

    plan_path = course_root / "workspace" / "generation-plan.agent.json"
    if plan_path.exists():
        plan = {
            "batches": _make_batches(blueprint),
            "strategy": "依赖优先：批次默认顺序执行，每批最多 4 章",
            "execution": {
                "batch_mode": "sequential",
                "chapter_mode": "sequential_by_default",
                "max_parallel_chapters": 1,
                "rule": "当前按章节顺序执行；后续只有蓝图明确无前后依赖时才可提高并行度。",
            },
        }
        _write_json(plan_path, plan)
        changed.append("workspace/generation-plan.agent.json")
    return {"chapter_count": chapter_count, "synced_files": changed}


def _workspace_contract_snapshot(course_root: Path) -> dict[str, Any]:
    names = (
        "MISSION.md",
        "COURSE-BLUEPRINT.md",
        "COURSE-GENERATION-SPEC.md",
        "blueprint.agent.json",
        "generation-plan.agent.json",
        "research.agent.json",
    )
    snapshot: dict[str, Any] = {}
    for name in names:
        path = course_root / "workspace" / name
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        # This snapshot is the input to cross-file consistency decisions.
        # Keep the complete core contract instead of silently losing tail
        # requirements such as success criteria.
        snapshot[name] = content[:65536]
    metadata_path = course_root / "course.json"
    if metadata_path.exists():
        snapshot["course.json"] = json.loads(metadata_path.read_text(encoding="utf-8"))
    return snapshot


def _effective_source_policy(request: dict[str, Any], changes: list[dict[str, Any]]) -> str:
    change_text = "\n".join(str(item.get("request", "")) for item in changes)
    if "仅限使用内部提供材料" in change_text:
        return "仅限使用内部提供材料"
    if any(term in change_text for term in ("允许使用社区", "社区资源", "社区教程")):
        return "允许使用用户资料、社区优质资料与公开官方资料"
    return str(request.get("source_policy", "允许使用用户资料与公开官方资料"))


def _reconciliation_route(state: CourseAgentState, *, default: str = "audit") -> str:
    """Route a Workspace patch to the smallest stale downstream stage.

    A changed Workspace file is not by itself a reason to rebuild the
    course.  The patch Agent declares semantic impacts; without one, a
    consistency repair (for example correcting a stale chapter count in a
    MISSION delivery line) is verified directly against the current facts.
    """
    revision = state.get("workspace_revision") or {}
    impacts = "\n".join(
        str(value) for value in revision.get("downstream_impacts", [])
    )
    if any(marker in impacts for marker in ("资料", "来源", "检索", "引用范围")):
        return "research"
    if any(marker in impacts for marker in ("蓝图", "模块", "章节", "学习路径", "课程结构")):
        return "blueprint"
    return default


def _has_recorded_research(state: CourseAgentState, course_root: Path) -> bool:
    """Return whether this course already passed the research stage.

    A mission revision can run before the first `research_sources` node.  The
    state then has no `research` value and the durable workspace report does
    not exist.  Treating a blueprint-related patch as sufficient reason to
    skip research leaves the writer with only user-provided links.
    """
    if isinstance(state.get("research"), dict):
        return True
    return (course_root / "workspace" / "research.agent.json").is_file()


def _workspace_revision_route(state: CourseAgentState, course_root: Path) -> str:
    """Route a mission revision while preserving the research-before-blueprint invariant."""
    if not _has_recorded_research(state, course_root):
        return "research"
    return _reconciliation_route(state, default="blueprint")

