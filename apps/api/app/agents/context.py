from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

def _clip_text(value: object, limit: int) -> str:
    """Keep non-writing model calls proportional to the decision they make."""
    text = str(value or "")
    return text if len(text) <= limit else text[:limit] + "\n[其余内容已省略]"


_CORE_WORKSPACE_LIMIT = 65536
_LARGE_WORKSPACE_LIMIT = 48000
_NOTES_WORKSPACE_LIMIT = 32000


def _ground_semantic_issues(markdown: str, issues: list[str]) -> list[str]:
    """Keep only review findings backed by a literal excerpt from the chapter.

    A semantic model can otherwise re-report a problem that a prior targeted
    edit has already removed.  Evidence is intentionally strict: a queued
    finding needs a quoted, non-trivial substring from the Markdown itself.
    """
    grounded: list[str] = []
    pattern = re.compile(r"证据\s*[：:]\s*[『“\"]([^』”\"\n]{6,})[』”\"]")
    for issue in issues:
        match = pattern.search(issue)
        if match and match.group(1).strip() in markdown:
            grounded.append(issue)
    return grounded


def _ground_repair_verifications(
    markdown: str,
    tasks: list[dict[str, Any]],
    verifications: list[Any],
) -> dict[str, dict[str, Any]]:
    """Bind targeted semantic verification to literal post-repair evidence.

    For absence/gap findings the original quote is normally the exercise or
    claim that exposed the gap. Its continued presence cannot prove that the
    newly added scaffold is missing, so a resolved verdict must cite different
    text from the candidate revision.
    """
    task_by_id = {str(task.get("id") or ""): task for task in tasks}
    grounded: dict[str, dict[str, Any]] = {}
    for value in verifications:
        item = value.model_dump(mode="json") if hasattr(value, "model_dump") else dict(value)
        task_id = str(item.get("task_id") or "")
        task = task_by_id.get(task_id)
        if not task:
            continue
        excerpt = str(item.get("evidence_excerpt") or "").strip()
        trigger = str((task.get("evidence") or {}).get("quoted_source") or "").strip()
        evidence_is_grounded = len(excerpt) >= 6 and excerpt in markdown
        resolved = bool(item.get("resolved")) and evidence_is_grounded and excerpt != trigger
        grounded[task_id] = {
            **item,
            "resolved": resolved,
            "evidence_grounded": evidence_is_grounded,
        }
    return grounded


def _semantic_review_context(context: dict) -> dict:
    """Project a Context Pack into the facts a chapter reviewer really needs.

    The writer needs the full Workspace and selected teaching templates. A
    reviewer does not: sending all of it together with a long chapter made a
    compact JSON verdict unnecessarily slow through compatible gateways.
    """
    course = context.get("course_context", {})
    request = course.get("request", {}) if isinstance(course, dict) else {}
    workspace = course.get("workspace", {}) if isinstance(course, dict) else {}
    module = context.get("module_context", {})
    return {
        "course_title": course.get("title", "") if isinstance(course, dict) else "",
        "audience": request.get("audience", request.get("core_audience", "")),
        "learning_goals": request.get("learning_goals", request.get("goals", "")),
        "effective_char_min": request.get("effective_char_min", 12000),
        "chapter": context.get("chapter", {}),
        "module": {
            "title": module.get("title", "") if isinstance(module, dict) else "",
            "goal": module.get("goal", "") if isinstance(module, dict) else "",
        },
        "neighbors": context.get("neighbor_context", {}),
        "continuity": context.get("continuity_ledger", [])[-4:],
        # Keep primary source metadata for fact checking without pulling in
        # every historical workspace document.
        "approved_resources": _clip_text(
            workspace.get("RESOURCES.md", workspace.get("resources", ""))
            if isinstance(workspace, dict)
            else "",
            12000,
        ),
        "feedback": _clip_text(context.get("feedback", ""), 3000),
        "active_repair_tasks": context.get("active_repair_tasks", []),
    }


def _workspace_projection(workspace: object, limits: dict[str, int]) -> dict[str, str]:
    if not isinstance(workspace, dict):
        return {}
    return {
        name: _clip_text(workspace.get(name, ""), limit)
        for name, limit in limits.items()
        if workspace.get(name)
    }


def _planning_request(request: dict, *, include_resources: bool = False) -> dict:
    """Remove unrelated workspace history from small planning decisions."""
    projected = {key: value for key, value in request.items() if key != "workspace"}
    workspace_limits = {
        "COURSE-GENERATION-SPEC.md": _CORE_WORKSPACE_LIMIT,
        "NOTES.md": _NOTES_WORKSPACE_LIMIT,
    }
    if include_resources:
        workspace_limits["RESOURCES.md"] = _LARGE_WORKSPACE_LIMIT
    workspace = _workspace_projection(request.get("workspace"), workspace_limits)
    if workspace:
        projected["workspace"] = workspace
    return projected


def _audit_workspace_projection(workspace: dict) -> dict:
    """Keep contract facts, not an unbounded archive, in the audit prompt."""
    limits = {
        "MISSION.md": _CORE_WORKSPACE_LIMIT,
        "COURSE-BLUEPRINT.md": _CORE_WORKSPACE_LIMIT,
        "COURSE-GENERATION-SPEC.md": _CORE_WORKSPACE_LIMIT,
        "blueprint.agent.json": _CORE_WORKSPACE_LIMIT,
        "generation-plan.agent.json": _LARGE_WORKSPACE_LIMIT,
        "research.agent.json": _LARGE_WORKSPACE_LIMIT,
    }
    result = _workspace_projection(workspace, limits)
    if isinstance(workspace.get("course.json"), dict):
        result["course.json"] = json.dumps(workspace["course.json"], ensure_ascii=False)
    return result


_SKILL_ROOT = Path(__file__).resolve().parents[4] / ".agents" / "skills"
_TEACH_ROOT = _SKILL_ROOT / "teach-generator"


@lru_cache(maxsize=32)
def _skill_text(relative_path: str) -> str:
    """Read the canonical teaching asset instead of maintaining a second copy."""
    path = _TEACH_ROOT / relative_path
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


_PEDAGOGY_ASSETS = {
    "opening_closing": (
        "课程开篇、模块过渡与总结",
        "references/writing-guide-opening-closing.md",
        "templates/opening-closing-structure.md",
        None,
        "简洁专业型",
    ),
    "environment": (
        "环境安装与工具准备",
        "references/writing-guide-environment.md",
        "templates/environment-structure.md",
        "templates/environment-writing-example.md",
        "耐心教练型 + 实践带练型",
    ),
    "language": (
        "语言基础与标准库",
        "references/writing-guide-language.md",
        "templates/language-structure.md",
        "templates/language-writing-example.md",
        "耐心教练型",
    ),
    "framework": (
        "单一框架或工具介绍、应用及进阶",
        "references/writing-guide-framework.md",
        "templates/framework-structure.md",
        "templates/framework-structure-example.md",
        "耐心教练型 + 实践带练型",
    ),
    "mechanism": (
        "原理机制、协议、架构与故障诊断",
        "references/writing-guide-mechanism-diagnostics.md",
        "templates/mechanism-diagnostics-structure.md",
        "templates/mechanism-diagnostics-structure-example.md",
        "严谨技术型",
    ),
    "integrated_practice": (
        "综合应用实践与项目交付",
        "references/writing-guide-integrated-practice.md",
        "templates/integrated-practice-structure.md",
        None,
        "实践带练型",
    ),
}


def _infer_pedagogy(context: dict) -> str:
    """Use the chapter plan first; fall back to a conservative topic classifier."""
    chapter = context.get("chapter", {})
    explicit = str(chapter.get("pedagogy_type", "")).strip()
    if explicit in _PEDAGOGY_ASSETS:
        return explicit
    text = " ".join(
        str(value) for value in (chapter.get("title", ""), chapter.get("learning_outcome", ""))
    ).lower()
    if any(word in text for word in ("安装", "环境", "配置", "部署", "docker", "容器")):
        return "environment"
    if any(word in text for word in ("项目", "实战", "交付", "端到端", "综合")):
        return "integrated_practice"
    if any(word in text for word in ("原理", "机制", "架构", "协议", "诊断", "性能", "并发", "链路")):
        return "mechanism"
    if any(word in text for word in ("fastapi", "flask", "spring", "django", "框架", "路由", "api")):
        return "framework"
    if any(word in text for word in ("开篇", "导学", "过渡", "总结", "收束")):
        return "opening_closing"
    return "language"


def _teaching_skill_packet(context: dict, *, include_example: bool = True) -> str:
    """Inject the applicable guide, structure and calibration sample verbatim.

    This is deliberately selected per chapter. The Skill explicitly forbids
    concatenating every template into a single article, and doing so also
    dilutes the chapter's own learning path.
    """
    pedagogy = _infer_pedagogy(context)
    label, guide_path, structure_path, example_path, default_voice = _PEDAGOGY_ASSETS[pedagogy]
    chapter = context.get("chapter", {})
    voice = chapter.get("instructor_voice") or default_voice
    sections = [
        "# teach-generator 本章写作契约（必须执行）",
        f"- 正文主类型：{label}；基础讲师风格：{voice}。",
        "- 先根据章节学习成果、前置、连续性账本和可信来源设计本章自己的学习路径；再从下列模板中只取能服务该路径的模块。模板不是固定目录。",
        "- 不复制样例中的事实、代码、标题、链接、章节编号或段落数；完整样例只用于校准解释粒度、代码粒度、节奏和可观察证据。",
        "- 先完成主教学任务；只在需要时加入图、表、代码、反例或练习。每个新术语、操作和代码符号都必须与目标受众的前置匹配。",
        "- 学生正文不得出现工作区、Skill、Agent、质检、用户资料、内部文件、评分或生成过程。",
        "\n## 当前正文类型的写法指引（原文）\n" + _skill_text(guide_path),
        "\n## 当前正文类型的结构模板（原文）\n" + _skill_text(structure_path),
    ]
    if include_example and example_path:
        sections.append("\n## 当前正文类型的完整写法模板（原文，仅用于校准）\n" + _skill_text(example_path))
    return "\n".join(sections)


_HUMANIZER_PROTOCOL = """
# humanizer-zh 编辑闸门（必须逐项执行）
这是技术课程编辑，不是禁词替换。先保留事实、数字、限定条件、术语、链接、Markdown
结构、所有代码块和命令的语义，再定向改写散文部分。

逐段扫描并修复：夸大意义/遗产/趋势；媒体知名度堆砌；句尾肤浅分词分析；宣传或广告式
语言；模糊归因；"挑战与未来展望"式空段；高频 AI 词（此外、至关重要、深入探讨、
彰显、赋能等）；回避“是/有”的绕句；否定式排比；强凑三段式；同义词循环；虚假范围；
装饰性破折号；过量粗体；粗体内联标题清单；表情符号；聊天协作痕迹；知识截止免责声明；
谄媚语气；填充短语；过度限定；通用积极结尾。

技术教学的“真人感”来自具体对象、可观察结果、明确条件、长短句交错和可信的老师语气，
不是虚构个人经历、情绪或权威。不要为了去 AI 味删除必要的定义、步骤、反例、验收或
严谨限定。输出前逐项复核：代码围栏、URL、术语标记、数字、命令、引用均未改变。

按五维度各 0-10 打分：直接性、节奏、信任度、真实性、精炼度。只有总分至少 45/50，
且没有改变事实、代码或引用，才能给出高分。issues 必须说明实际模式和位置/片段。
""".strip()
