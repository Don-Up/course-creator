from __future__ import annotations

import json
from pathlib import Path

from app.courses.catalog import get_course
from app.courses.common import _safe_course_root
from app.courses.workspace import _default_resources_markdown
from app.schemas import CourseCreate

def create_course_scaffold(request: CourseCreate) -> dict[str, Any]:
    root = _safe_course_root(request.slug)
    if root.exists():
        raise FileExistsError(request.slug)
    for path in (
        root / "workspace" / "learning-records",
        root / "lessons",
        root / "reference",
        root / "markdown",
        root / "assets",
        root / "quality",
    ):
        path.mkdir(parents=True, exist_ok=True)
    (root / "workspace" / "NOTES.md").write_text(
        "# 课程迭代笔记\n\n本课程由课程生成 Agent 创建，当前处于引导模式。\n",
        encoding="utf-8",
    )
    (root / "workspace" / "RESOURCES.md").write_text(
        _default_resources_markdown().replace(
            "待课程任务定义确认后写入。", request.source_policy
        ),
        encoding="utf-8",
    )
    (root / "workspace" / "COURSE-GENERATION-SPEC.md").write_text(
        (
            "# 课程生成规格\n\n"
            f"- 交付格式：{request.delivery}\n"
            f"- 期望章节数：{request.preferred_chapter_count}（供蓝图规划参考）\n"
            f"- 单章有效字符数下限：{request.effective_char_min}\n"
            "- 运行模式：本地单用户、引导模式\n"
            "- 质量门：逐章 Humanizer、构建、确定性检查、语义审校、人工确认\n"
            "- 自动返工上限：同类问题连续三轮后转人工\n"
        ),
        encoding="utf-8",
    )
    (root / "reference" / "glossary.md").write_text(
        "# 术语表\n\n| 术语 | 定义 |\n| --- | --- |\n",
        encoding="utf-8",
    )
    (root / "course.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "slug": request.slug,
                "title": request.title,
                "description": request.goals,
                "duration": "待蓝图确认",
                "status": "preparing",
                "audience": request.audience,
                "lessons": [],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return get_course(request.slug)
