"""Creation of the course folder skeleton.

A new course starts as a folder under the courses root: six top level
folders for the material the later phases produce, a workspace for the
notes of the agent, and a `course.json` that tells the later phases what
the course is about.  The skeleton is written once, when the user submits
the intake form, so every later phase can rely on the same layout.

The courses root is passed in explicitly instead of read from the settings
singleton, for the same reason as `app.courses.common`: the caller decides
where the courses live.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.courses.common import SLUG_PATTERN, _safe_course_root, _write_json_atomic
from app.schemas import CourseCreate

COURSE_DIRECTORIES = (
    "lessons",
    "reference",
    "markdown",
    "assets",
    "quality",
    "workspace",
)

WORKSPACE_DIRECTORIES = ("learning-records",)

NOTES_MD = (
    "# 课程迭代笔记\n"
    "\n"
    "本课程由课程生成 Agent 创建，当前处于引导模式。\n"
)

RESOURCES_MD_TEMPLATE = (
    "# 课程资源\n"
    "\n"
    "## 来源政策\n"
    "\n"
    "{source_policy}\n"
    "\n"
    "## 检索范围与使用边界\n"
    "\n"
    "- Agent 会围绕课程核心概念、所用框架或工具的当前 API、相关标准或论文、"
    "项目实践与部署/安全边界检索资料。\n"
    "- 每一条资料都必须说明其支撑的教学内容；关键事实、API 用法和规范不得只依赖"
    "未核验的社区文章。\n"
    "- 资料是否可用以来源政策为准：只有政策允许时，才将社区教程作为补充阅读。\n"
    "\n"
    "## Agent 检索与核验\n"
    "\n"
    "任务定义确认后，Agent 会在这里写入检索计划、经筛选的资料和仍需人工补充的缺口。\n"
    "\n"
    "## 用户补充资源\n"
    "\n"
    "可在此登记链接、课程资料说明或上传附件的使用目的。\n"
)

COURSE_GENERATION_SPEC_MD_TEMPLATE = (
    "# 课程生成规格\n"
    "\n"
    "- 交付格式：{delivery}\n"
    "- 期望章节数：{preferred_chapter_count}（供蓝图规划参考）\n"
    "- 单章有效字符数下限：{effective_char_min}\n"
    "- 运行模式：本地单用户、引导模式\n"
    "- 质量门：逐章 Humanizer、构建、确定性检查、语义审校、人工确认\n"
    "- 自动返工上限：同类问题连续三轮后转人工\n"
)

GLOSSARY_MD = (
    "# 术语表\n"
    "\n"
    "| 术语 | 定义 |\n"
    "| --- | --- |\n"
)


def _course_metadata(request: CourseCreate) -> dict[str, Any]:
    """Return the eleven keys that course.json has to contain.

    Args:
        request: The intake form the user submitted, for example a
            CourseCreate with the title "Python 入门".

    Returns:
        The metadata of a course that has not been generated yet: the
        intake values, an empty lesson list, the duration "待蓝图确认"
        and the status "preparing".
    """
    return {
        "schemaVersion": 1,
        "slug": request.slug,
        "title": request.title,
        "description": request.goals,
        "audience": request.audience,
        "goals": request.goals,
        "scope": request.scope,
        "duration": "待蓝图确认",
        "status": "preparing",
        "preferred_chapter_count": request.preferred_chapter_count,
        "lessons": [],
    }


def _write_starting_files(course_root: Path, request: CourseCreate) -> None:
    """Write the four files a fresh course starts with.

    Args:
        course_root: The folder of the new course, for example
            courses/python-101/.
        request: The intake form the user submitted, for example a
            CourseCreate with the source policy "只使用公开官方资料".

    Returns:
        Nothing. The four files exist once the call returns.
    """
    workspace = course_root / "workspace"
    (workspace / "NOTES.md").write_text(NOTES_MD, encoding="utf-8")
    (workspace / "RESOURCES.md").write_text(
        RESOURCES_MD_TEMPLATE.format(source_policy=request.source_policy),
        encoding="utf-8",
    )
    (workspace / "COURSE-GENERATION-SPEC.md").write_text(
        COURSE_GENERATION_SPEC_MD_TEMPLATE.format(
            delivery=request.delivery,
            preferred_chapter_count=request.preferred_chapter_count,
            effective_char_min=request.effective_char_min,
        ),
        encoding="utf-8",
    )
    glossary = course_root / "reference" / "glossary.md"
    glossary.write_text(GLOSSARY_MD, encoding="utf-8")


def create_course_scaffold(request: CourseCreate, courses_root: Path) -> dict[str, Any]:
    """Create the folder skeleton and course.json of a brand new course.

    Args:
        request: The intake form the user submitted, for example a
            CourseCreate with the slug "python-101".
        courses_root: The directory that holds every course folder,
            for example courses/.

    Returns:
        The metadata that was written to course.json, so the caller can
        answer with the same values without reading the file again.
        Raises ValueError("课程 slug 不合法") when the slug does not match
        the shared pattern, and FileExistsError when the course folder is
        already there: an existing course is never overwritten.
    """
    if not SLUG_PATTERN.fullmatch(request.slug):
        raise ValueError("课程 slug 不合法")

    course_root = _safe_course_root(request.slug, courses_root)
    if course_root.exists():
        raise FileExistsError(f"课程已存在：{request.slug}")

    course_root.mkdir(parents=True)
    for name in COURSE_DIRECTORIES:
        (course_root / name).mkdir()
    for name in WORKSPACE_DIRECTORIES:
        (course_root / "workspace" / name).mkdir()

    _write_starting_files(course_root, request)

    metadata = _course_metadata(request)
    _write_json_atomic(course_root / "course.json", metadata)
    return metadata
