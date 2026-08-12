import base64
import json
from types import SimpleNamespace

import pytest

from app import course_service
from app.courses import common, tools
from app.course_service import (
    get_course_asset,
    get_chapter,
    get_course,
    list_courses,
    get_workspace_file,
    list_workspace_files,
    append_workspace_resource_note,
    apply_workspace_patch_plan,
    update_workspace_file,
    upload_workspace_resource,
    run_course_tool,
    publish_course,
)


def test_all_existing_courses_are_discoverable():
    courses = list_courses()
    slugs = {course["slug"] for course in courses}
    assert {
        "fbs-fullstack-landing",
        "harness-engineering",
        "high-quality-ai-code-review",
        "java-web-backend-from-beginner-to-advanced",
        "langchain-langgraph-from-beginner-to-advanced",
        "rag-from-beginner-to-expert",
    }.issubset(slugs)


def test_quality_snapshot_keeps_chapter_batch_and_course_status_separate(tmp_path):
    snapshot = course_service.write_course_quality_snapshot(
        tmp_path,
        [
            {
                "batch": {"id": "m1-01-02"},
                "quality_gates": {"stage_3_batch_integration": {"passed": True}},
                "chapters": [
                    {"chapter": 1, "path": "lessons/01.md", "effective_chars": 10100, "effective_char_min": 10000, "humanizer_score": 46, "semantic_review": {"decision": "ready"}, "passed": True},
                    {"chapter": 2, "path": "lessons/02.md", "effective_chars": 9800, "effective_char_min": 10000, "humanizer_score": 46, "semantic_review": {"decision": "ready"}, "passed": False},
                ],
            }
        ],
        repair_tasks=[{"chapter": 2, "status": "unresolved"}],
        course_integration={"passed": False},
    )

    assert snapshot["chapters"][0]["chapter_passed"] is True
    assert snapshot["chapters"][0]["batch_integration_passed"] is True
    assert snapshot["chapters"][0]["course_integration_passed"] is False
    assert snapshot["chapters"][1]["repair_status"] == "unresolved"
    assert (tmp_path / "quality" / "course-quality-snapshot.json").exists()


def test_quality_snapshot_uses_only_the_latest_result_for_a_retried_batch(tmp_path):
    snapshot = course_service.write_course_quality_snapshot(
        tmp_path,
        [
            {
                "batch": {"id": "m1-01-01"},
                "quality_gates": {"stage_3_batch_integration": {"passed": False}},
                "chapters": [
                    {"chapter": 1, "effective_chars": 4100, "effective_char_min": 10000, "passed": False},
                ],
            },
            {
                "batch": {"id": "m1-01-01"},
                "quality_gates": {"stage_3_batch_integration": {"passed": True}},
                "chapters": [
                    {"chapter": 1, "effective_chars": 10200, "effective_char_min": 10000, "passed": True},
                ],
            },
        ],
    )

    assert len(snapshot["chapters"]) == 1
    assert snapshot["chapters"][0]["effective_chars"] == 10200
    assert snapshot["chapters"][0]["batch_integration_passed"] is True


def test_quality_snapshot_keeps_an_open_repair_visible_when_another_task_closed(tmp_path):
    snapshot = course_service.write_course_quality_snapshot(
        tmp_path,
        [{"batch": {"id": "m1-01-01"}, "chapters": [{"chapter": 1, "passed": True}]}],
        repair_tasks=[
            {"chapter": 1, "status": "fixed_verified"},
            {"chapter": 1, "status": "unresolved"},
        ],
    )

    assert snapshot["chapters"][0]["repair_status"] == "unresolved"


def test_snapshot_separates_content_source_build_and_artifact_gates(tmp_path):
    snapshot = course_service.write_course_quality_snapshot(
        tmp_path,
        [{"batch": {"id": "m1-01-01"}, "chapters": [{"chapter": 1, "passed": True}]}],
        source_contract={"passed": False, "diagnostics": [{"code": "REFERENCE_SECTION_MISSING"}]},
        build={"passed": False},
        artifact_validation={"passed": None},
        quality_cycle={"cycle_id": "cycle-1", "iteration": 3, "queue_size": 1, "new_issue_count": 1},
    )
    assert snapshot["chapters"][0]["chapter_passed"] is True
    assert snapshot["source_contract_gate"]["passed"] is False
    assert snapshot["build_gate"]["passed"] is False
    assert snapshot["artifact_gate"]["passed"] is None
    assert snapshot["quality_cycle"]["iteration"] == 3


def test_course_json_variants_are_normalized():
    java = get_course("java-web-backend-from-beginner-to-advanced")
    rag = get_course("rag-from-beginner-to-expert")
    langgraph = get_course("langchain-langgraph-from-beginner-to-advanced")
    assert java["chapter_count"] == 36
    assert rag["chapter_count"] >= 7
    assert langgraph["chapter_count"] == 15


def test_publish_course_persists_metadata_and_catalog_entry(tmp_path, monkeypatch):
    courses_root = tmp_path / "courses"
    root = courses_root / "test-course"
    (root / "lessons").mkdir(parents=True)
    (root / "course.json").write_text(
        json.dumps(
            {
                "slug": "test-course",
                "title": "测试课程",
                "description": "课程简介",
                "duration": "4 小时",
                "status": "ready-for-release",
                "lessons": [{"number": 1, "markdown": "lessons/01.md"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (root / "lessons" / "01.md").write_text("# 第 1 章 测试\n", encoding="utf-8")
    (courses_root / "catalog.json").write_text(
        json.dumps({"schemaVersion": 1, "courses": []}), encoding="utf-8"
    )
    monkeypatch.setattr(
        common,
        "get_settings",
        lambda: SimpleNamespace(courses_root=courses_root),
    )

    published = publish_course("test-course", workflow_run_id="run-123")
    metadata = json.loads((root / "course.json").read_text(encoding="utf-8"))
    catalog = json.loads((courses_root / "catalog.json").read_text(encoding="utf-8"))

    assert published["status"] == "published"
    assert metadata["status"] == "published"
    assert metadata["publication"]["workflow_run_id"] == "run-123"
    assert metadata["published_at"]
    assert catalog["courses"] == [{
        "slug": "test-course",
        "title": "测试课程",
        "description": "课程简介",
        "href": "./test-course/index.html",
        "chapters": 1,
        "duration": "4 小时",
        "status": "published",
    }]


def test_chapter_can_be_read_by_number():
    chapter = get_chapter("harness-engineering", "1")
    assert chapter["title"]
    assert chapter["content"].startswith("#")
    assert len(chapter["content_hash"]) == 64


def test_course_asset_is_limited_to_the_course_assets_directory(tmp_path, monkeypatch):
    courses_root = tmp_path / "courses"
    root = courses_root / "test-course"
    screenshot = root / "assets" / "screenshots" / "overview.png"
    screenshot.parent.mkdir(parents=True)
    screenshot.write_bytes(b"png")
    monkeypatch.setattr(
        common,
        "get_settings",
        lambda: SimpleNamespace(courses_root=courses_root),
    )

    assert get_course_asset("test-course", "screenshots/overview.png") == screenshot
    with pytest.raises(ValueError):
        get_course_asset("test-course", "../course.json")
    with pytest.raises(FileNotFoundError):
        get_course_asset("test-course", "screenshots/missing.png")


def test_workspace_files_can_be_reviewed_edited_and_extended(tmp_path, monkeypatch):
    courses_root = tmp_path / "courses"
    root = courses_root / "test-course"
    workspace = root / "workspace"
    workspace.mkdir(parents=True)
    (root / "course.json").write_text(
        json.dumps({"title": "测试课程", "lessons": []}), encoding="utf-8"
    )
    (workspace / "RESOURCES.md").write_text("# 资源\n", encoding="utf-8")
    monkeypatch.setattr(
        common,
        "get_settings",
        lambda: SimpleNamespace(courses_root=courses_root),
    )

    files = list_workspace_files("test-course")
    assert [item["path"] for item in files] == ["RESOURCES.md"]
    current = get_workspace_file("test-course", "RESOURCES.md")
    saved = update_workspace_file(
        "test-course",
        "RESOURCES.md",
        "# 资源\n\n已修改。\n",
        current["content_hash"],
    )
    assert "已修改" in saved["content"]
    uploaded = upload_workspace_resource(
        "test-course",
        "guide.pdf",
        base64.b64encode(b"fake-pdf").decode(),
        "application/pdf",
    )
    assert uploaded["path"] == "resources/guide.pdf"
    assert "guide.pdf" in (workspace / "RESOURCES.md").read_text(encoding="utf-8")


def test_workspace_rejects_path_traversal(tmp_path, monkeypatch):
    courses_root = tmp_path / "courses"
    (courses_root / "test-course" / "workspace").mkdir(parents=True)
    monkeypatch.setattr(
        common,
        "get_settings",
        lambda: SimpleNamespace(courses_root=courses_root),
    )
    with pytest.raises(ValueError):
        get_workspace_file("test-course", "../course.json")


def test_missing_resources_file_is_created_for_existing_workspace(tmp_path, monkeypatch):
    courses_root = tmp_path / "courses"
    (courses_root / "test-course" / "workspace").mkdir(parents=True)
    monkeypatch.setattr(
        common,
        "get_settings",
        lambda: SimpleNamespace(courses_root=courses_root),
    )

    resource_file = get_workspace_file("test-course", "RESOURCES.md")
    assert resource_file["content"].startswith("# 课程资源\n\n## 来源政策")
    assert (courses_root / "test-course" / "workspace" / "RESOURCES.md").is_file()


def test_resource_note_is_appended_without_rewriting_existing_sources(tmp_path, monkeypatch):
    courses_root = tmp_path / "courses"
    workspace = courses_root / "test-course" / "workspace"
    workspace.mkdir(parents=True)
    (workspace / "RESOURCES.md").write_text("# 课程资源\n\n- 原有资料\n", encoding="utf-8")
    monkeypatch.setattr(
        common,
        "get_settings",
        lambda: SimpleNamespace(courses_root=courses_root),
    )

    saved = append_workspace_resource_note("test-course", "- 新增资料")
    assert "原有资料" in saved["content"]
    assert saved["content"].rstrip().endswith("- 新增资料")


def test_workspace_patch_plan_updates_only_matching_files_and_keeps_one_snapshot_batch(tmp_path, monkeypatch):
    courses_root = tmp_path / "courses"
    workspace = courses_root / "test-course" / "workspace"
    workspace.mkdir(parents=True)
    (workspace / "MISSION.md").write_text("# MISSION\n\n课程共 8 章。\n", encoding="utf-8")
    (workspace / "COURSE-GENERATION-SPEC.md").write_text("期望章节数：8\n", encoding="utf-8")
    (workspace / "RESOURCES.md").write_text("# 资源\n\n- 用户资料\n", encoding="utf-8")
    (workspace / "NOTES.md").write_text("# 课程迭代笔记\n", encoding="utf-8")
    monkeypatch.setattr(
        common,
        "get_settings",
        lambda: SimpleNamespace(courses_root=courses_root),
    )

    result = apply_workspace_patch_plan(
        "test-course",
        [
            {"path": "MISSION.md", "original": "课程共 8 章。", "replacement": "课程共 9 章。"},
            {"path": "COURSE-GENERATION-SPEC.md", "original": "期望章节数：8", "replacement": "期望章节数：9"},
            {"path": "RESOURCES.md", "original": "- 用户资料", "replacement": "- 用户资料\n- 3D Graph 插件资料"},
            {"path": "NOTES.md", "original": "# 课程迭代笔记\n", "replacement": "# 课程迭代笔记\n\n- 新增 3D Graph 要求\n"},
        ],
        reason="新增 3D Graph 内容",
    )

    assert result["changed_files"] == [
        "MISSION.md",
        "COURSE-GENERATION-SPEC.md",
        "RESOURCES.md",
        "NOTES.md",
    ]
    assert "课程共 9 章" in (workspace / "MISSION.md").read_text(encoding="utf-8")
    assert "用户资料" in (workspace / "RESOURCES.md").read_text(encoding="utf-8")
    snapshots = list((workspace / ".agent-history").iterdir())
    assert len(snapshots) == 1
    assert (snapshots[0] / "MISSION.md").is_file()
    assert (snapshots[0] / "NOTES.md").is_file()


def test_workspace_patch_plan_rejects_non_unique_or_destructive_resource_patch(tmp_path, monkeypatch):
    courses_root = tmp_path / "courses"
    workspace = courses_root / "test-course" / "workspace"
    workspace.mkdir(parents=True)
    (workspace / "MISSION.md").write_text("旧内容\n旧内容\n", encoding="utf-8")
    (workspace / "RESOURCES.md").write_text("- 用户资料\n", encoding="utf-8")
    monkeypatch.setattr(
        common,
        "get_settings",
        lambda: SimpleNamespace(courses_root=courses_root),
    )

    with pytest.raises(RuntimeError, match="唯一命中"):
        apply_workspace_patch_plan(
            "test-course", [{"path": "MISSION.md", "original": "旧内容", "replacement": "新内容"}], reason="测试"
        )
    with pytest.raises(RuntimeError, match="不得删除"):
        apply_workspace_patch_plan(
            "test-course", [{"path": "RESOURCES.md", "original": "- 用户资料", "replacement": "- 新资料"}], reason="测试"
        )


def test_batch_course_tools_only_target_the_requested_chapters(tmp_path, monkeypatch):
    courses_root = tmp_path / "courses"
    course_root = courses_root / "test-course"
    (course_root / "lessons").mkdir(parents=True)
    (course_root / "course.json").write_text(
        json.dumps(
            {
                "lessons": [
                    {"number": 1, "markdown": "lessons/01.md"},
                    {"number": 2, "markdown": "lessons/02.md"},
                    {"number": 3, "markdown": "lessons/03.md"},
                ]
            }
        ),
        encoding="utf-8",
    )
    commands = []
    monkeypatch.setattr(
        common,
        "get_settings",
        lambda: SimpleNamespace(courses_root=courses_root, repo_root=tmp_path),
    )
    monkeypatch.setattr(
        tools.subprocess,
        "run",
        lambda command, **_: commands.append(command)
        or SimpleNamespace(returncode=0, stdout="ok", stderr=""),
    )

    run_course_tool("test-course", "build", chapter_numbers=[2, 3])
    run_course_tool("test-course", "validate", chapter_numbers=[2, 3])

    assert commands[0] == [
        "node", "scripts/build-static-course.mjs", "test-course", "--chapters", "2,3"
    ]
    assert commands[1][-5:] == [
        "--include", "lessons/02.md", "--include", "lessons/03.md", "--no-write"
    ]


def test_source_contract_is_a_separate_phase_and_does_not_scan_stale_html(tmp_path, monkeypatch):
    courses_root = tmp_path / "courses"
    course_root = courses_root / "test-course"
    course_root.mkdir(parents=True)
    monkeypatch.setattr(
        common, "get_settings",
        lambda: SimpleNamespace(courses_root=courses_root, repo_root=tmp_path),
    )
    monkeypatch.setattr(
        tools,
        "scan_course_contract",
        lambda slug, lesson_paths=None: SimpleNamespace(
            model_dump=lambda **_: {
                "diagnostics": [{"code": "INTRO_NON_CANONICAL", "path": "lessons/01.md"}],
                "lessons": [{"path": "lessons/01.md", "hash": "rev"}],
            }
        ),
    )
    monkeypatch.setattr(
        tools.subprocess, "run",
        lambda *args, **kwargs: pytest.fail("source_contract 不应调用 HTML Validator"),
    )

    result = run_course_tool("test-course", "source_contract")

    assert result["succeeded"] is False
    assert result["diagnostics"][0]["code"] == "INTRO_NON_CANONICAL"
    assert result["source_revision"] == "rev"
