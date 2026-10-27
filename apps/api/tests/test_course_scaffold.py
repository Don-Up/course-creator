"""Behaviour tests for the course scaffold.

`app/courses/scaffold.py` lays out the folder skeleton of a brand new
course and writes its `course.json`.  The tests therefore look at the real
files on disk: the folders have to exist, the metadata has to hold exactly
the eleven agreed keys, and a second attempt with the same slug has to be
refused without touching the course that is already there.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.courses.common import SLUG_PATTERN
from app.courses.scaffold import create_course_scaffold
from app.schemas import CourseCreate

EXPECTED_DIRECTORIES = (
    "lessons",
    "reference",
    "markdown",
    "assets",
    "quality",
    "workspace",
)

EXPECTED_COURSE_JSON_KEYS = frozenset(
    {
        "schemaVersion",
        "slug",
        "title",
        "description",
        "audience",
        "goals",
        "scope",
        "duration",
        "status",
        "preferred_chapter_count",
        "lessons",
    }
)


def build_request(**overrides: object) -> CourseCreate:
    """Build a valid intake request, with the given fields replaced.

    Args:
        overrides: The fields to replace, for example
            ``{"slug": "python_101"}`` for an illegal slug.

    Returns:
        A CourseCreate that is valid apart from the replaced fields.
    """
    payload: dict[str, object] = {
        "title": "Python 入门",
        "slug": "python-101",
        "audience": "有 Python 基础的学习者",
        "goals": "学会构建一个可恢复的 Agent",
        "scope": "从零到发布",
    }
    payload.update(overrides)
    return CourseCreate(**payload)


def test_scaffold_creates_the_expected_folder_skeleton(tmp_path: Path) -> None:
    """A fresh course holds the six top level folders and the records folder.

    Args:
        tmp_path: The empty directory pytest provides for this test.

    Returns:
        Nothing. The test fails when one of the folders is missing.
    """
    request = build_request()

    create_course_scaffold(request, tmp_path)

    course_root = tmp_path / request.slug
    for name in EXPECTED_DIRECTORIES:
        assert (course_root / name).is_dir()
    assert (course_root / "workspace" / "learning-records").is_dir()


def test_scaffold_creates_the_expected_starting_files(tmp_path: Path) -> None:
    """The three workspace files and the glossary exist with the agreed content.

    Args:
        tmp_path: The empty directory pytest provides for this test.

    Returns:
        Nothing. The test fails when a file is missing or its content differs.
    """
    request = build_request()

    create_course_scaffold(request, tmp_path)

    course_root = tmp_path / request.slug
    workspace = course_root / "workspace"
    assert (workspace / "NOTES.md").read_text(encoding="utf-8") == (
        "# 课程迭代笔记\n"
        "\n"
        "本课程由课程生成 Agent 创建，当前处于引导模式。\n"
    )
    assert (workspace / "RESOURCES.md").is_file()
    assert (workspace / "COURSE-GENERATION-SPEC.md").is_file()
    assert (course_root / "reference" / "glossary.md").read_text(encoding="utf-8") == (
        "# 术语表\n"
        "\n"
        "| 术语 | 定义 |\n"
        "| --- | --- |\n"
    )


def test_course_json_repeats_the_intake_values(tmp_path: Path) -> None:
    """course.json carries the intake values and the answer matches the file.

    Args:
        tmp_path: The empty directory pytest provides for this test.

    Returns:
        Nothing. The test fails when a value differs from the request.
    """
    request = build_request()

    metadata = create_course_scaffold(request, tmp_path)

    course_json = tmp_path / request.slug / "course.json"
    stored = json.loads(course_json.read_text(encoding="utf-8"))
    assert stored == metadata
    assert stored["slug"] == request.slug
    assert stored["title"] == request.title
    assert stored["audience"] == request.audience
    assert stored["goals"] == request.goals
    assert stored["scope"] == request.scope
    assert stored["status"] == "preparing"
    assert stored["description"] == request.goals
    assert stored["lessons"] == []


def test_course_json_has_exactly_the_eleven_agreed_keys(tmp_path: Path) -> None:
    """No key may be added or dropped, because later phases read this file.

    Args:
        tmp_path: The empty directory pytest provides for this test.

    Returns:
        Nothing. The test fails when the key set differs from the agreement.
    """
    request = build_request()

    create_course_scaffold(request, tmp_path)

    course_json = tmp_path / request.slug / "course.json"
    stored = json.loads(course_json.read_text(encoding="utf-8"))
    assert set(stored) == EXPECTED_COURSE_JSON_KEYS


def test_workspace_files_quote_the_request_values(tmp_path: Path) -> None:
    """The source policy and the generation limits reach the written files.

    Args:
        tmp_path: The empty directory pytest provides for this test.

    Returns:
        Nothing. The test fails when a value is missing from a file.
    """
    request = build_request(
        source_policy="只使用公开官方资料",
        delivery="Markdown",
        preferred_chapter_count=8,
        effective_char_min=20000,
    )

    create_course_scaffold(request, tmp_path)

    workspace = tmp_path / request.slug / "workspace"
    resources = (workspace / "RESOURCES.md").read_text(encoding="utf-8")
    spec = (workspace / "COURSE-GENERATION-SPEC.md").read_text(encoding="utf-8")
    assert request.source_policy in resources
    assert "- 交付格式：Markdown" in spec
    assert "- 期望章节数：8（供蓝图规划参考）" in spec
    assert "- 单章有效字符数下限：20000" in spec


def test_duplicate_slug_is_refused_and_keeps_the_old_course(tmp_path: Path) -> None:
    """A second course with the same slug raises and changes nothing.

    Args:
        tmp_path: The empty directory pytest provides for this test.

    Returns:
        Nothing. The test fails when the old course was overwritten.
    """
    request = build_request()
    create_course_scaffold(request, tmp_path)
    course_root = tmp_path / request.slug
    notes = course_root / "workspace" / "NOTES.md"
    record = course_root / "workspace" / "learning-records" / "manual.md"
    notes.write_text("# 手写笔记\n", encoding="utf-8")
    record.write_text("人工补充记录\n", encoding="utf-8")
    course_json = course_root / "course.json"
    before = course_json.read_text(encoding="utf-8")

    with pytest.raises(FileExistsError):
        create_course_scaffold(build_request(title="另一个标题"), tmp_path)

    assert notes.read_text(encoding="utf-8") == "# 手写笔记\n"
    assert record.read_text(encoding="utf-8") == "人工补充记录\n"
    assert course_json.read_text(encoding="utf-8") == before


def test_course_create_shares_the_slug_pattern_of_the_path_guard() -> None:
    """The API and the path guard have to agree on what a legal slug is.

    Args:
        Nothing.

    Returns:
        Nothing. The test fails when the two patterns differ.
    """
    pattern = CourseCreate.model_json_schema()["properties"]["slug"]["pattern"]

    assert pattern == SLUG_PATTERN.pattern


@pytest.mark.parametrize(
    "overrides",
    [
        {"title": "短"},
        {"audience": "短"},
        {"goals": "四个字符"},
        {"scope": "短"},
        {"preferred_chapter_count": 0},
        {"preferred_chapter_count": 61},
        {"effective_char_min": 999},
        {"effective_char_min": 50001},
        {"slug": "Python-101"},
        {"slug": "python_101"},
    ],
)
def test_course_create_rejects_impossible_values(overrides: dict[str, object]) -> None:
    """Every boundary of the intake contract is enforced by the model.

    Args:
        overrides: The field that has to be refused, for example
            ``{"title": "短"}``.

    Returns:
        Nothing. The test fails when the model accepts the value.
    """
    with pytest.raises(ValidationError):
        build_request(**overrides)


def test_course_create_keeps_the_agreed_defaults() -> None:
    """The intake defaults are the contract the creation wizard relies on.

    Args:
        Nothing.

    Returns:
        Nothing. The test fails when a default differs from the agreement.
    """
    request = build_request()

    assert request.source_policy == "允许使用用户资料与公开官方资料"
    assert request.delivery == "Markdown + HTML"
    assert request.preferred_chapter_count == 12
    assert request.effective_char_min == 12000
    assert request.token_budget_mtokens is None
    assert request.provider == "codex_gateway"
    assert request.model == "llm-gateway--kimi-k3"
