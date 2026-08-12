import json
from types import SimpleNamespace

from app.workflow.services import context_packs, course_quality, quality_integration
from app.workflow.nodes import repair
from app.workflow.nodes.generation import _register_generated_chapter
from app.workflow.runtime import _continuation_config, _require_terminal_graph_state
from langgraph.checkpoint.memory import MemorySaver
from langgraph.errors import GraphInterrupt

from app.agents.context import _ground_semantic_issues
from app.agents.runtime import create_course_agent
from app.provider import GatewayNoFinalTextError
from app.schemas import BlueprintOutput, ChapterPlan, ModulePlan
from app.workflow.assembly.course_graph import build_course_graph
from app.workflow.services.batch_planning import (
    _batch_repair_completion_route,
    _blueprint_markdown,
    _contract_codes_requiring_llm,
    _generation_cursor_exhausted,
    _make_batches,
    _normalize_reference_node,
    _repair_issue_is_resolved,
)
from app.workflow.services.context_packs import (
    _chapter_resume_stage,
    _deferred_chapter_quality_result,
    _effective_char_count,
    _effective_content_deficit,
    _presentation_projection,
    _projected,
    _relevant_ledger,
    _retry_initial_chapter_write,
    _sync_requested_chapter_count,
)
from app.workflow.services.course_quality import (
    _batch_contract_repair_entries,
    _diagnose_course_tool_failure,
    _full_course_validation_after_build,
    _normalize_lesson_intro,
    _quality_review_can_auto_complete,
    _refresh_quality_review_state,
    _relocate_external_links_to_references,
    _repair_queue_for_scope,
)
from app.workflow.services.quality_integration import (
    _integration_repair_entries,
    _persist_latest_batch_quality_results,
    _refresh_quality_integration,
    _revalidate_batch_integrations,
)
from app.workflow.services.workspace_contract import (
    _close_unclosed_markdown_fence,
    _load_chapter_progress,
    _save_chapter_progress,
    _redact_private_paths,
    _reconciliation_route,
    _workspace_revision_route,
    _sync_workspace_contract,
    _workspace_contract_snapshot,
    _write_research_to_resources,
    _read_workspace_context,
)


def sample_blueprint() -> dict:
    return BlueprintOutput(
        course_title="测试课程",
        modules=[
            ModulePlan(
                title="基础模块",
                goal="建立基础",
                narrative="连续推进",
                chapters=[
                    ChapterPlan(
                        number=index,
                        title=f"第 {index} 章 主题 {index}",
                        learning_outcome=f"成果 {index}",
                    )
                    for index in range(1, 6)
                ],
            )
        ],
    ).model_dump(mode="json")


def test_batches_follow_module_and_size_limit():
    batches = _make_batches(sample_blueprint(), max_size=4)
    assert [batch["chapter_numbers"] for batch in batches] == [[1, 2, 3, 4], [5]]
    assert [batch["ordinal"] for batch in batches] == [1, 2]
    assert batches[1]["display_label"] == "批次 2 · 第 5–5 章"
    assert batches[1]["id"] == "m2-05-05"


def test_deferred_chapter_is_registered_as_a_markdown_source():
    lessons = {}
    chapter = {"number": 3, "learning_outcome": "理解 ReAct 与 Plan-Execute"}

    _register_generated_chapter(
        lessons,
        chapter=chapter,
        module_title="单 Agent 架构",
        title="ReAct / Plan-Execute",
        relative_path="lessons/03-react-plan-execute.md",
    )

    assert lessons[3] == {
        "number": 3,
        "module": "单 Agent 架构",
        "title": "ReAct / Plan-Execute",
        "time": "按正文展开",
        "summary": "理解 ReAct 与 Plan-Execute",
        "status": "available",
        "href": "lessons/03-react-plan-execute.html",
        "markdown": "lessons/03-react-plan-execute.md",
    }


def test_continuation_rewinds_to_the_checkpoint_before_the_failed_task():
    current = SimpleNamespace(
        tasks=[SimpleNamespace(name="repair_batch_chapters", error=RuntimeError("gateway failed"))],
    )
    retry = SimpleNamespace(
        config={"configurable": {"thread_id": "run-1", "checkpoint_id": "before-error"}},
        next=("repair_batch_chapters",),
        tasks=[SimpleNamespace(name="repair_batch_chapters", error=None)],
    )
    graph = SimpleNamespace(
        get_state=lambda _config: current,
        get_state_history=lambda _config, limit: iter([current, retry]),
    )

    assert _continuation_config(graph, {"configurable": {"thread_id": "run-1"}}) == retry.config


def test_runtime_rejects_a_non_terminal_graph_as_completed():
    graph = SimpleNamespace(
        get_state=lambda _config: SimpleNamespace(
            next=("repair_batch_chapters",),
            tasks=[SimpleNamespace(name="repair_batch_chapters", error=RuntimeError("gateway failed"))],
        ),
    )

    try:
        _require_terminal_graph_state(graph, {"configurable": {"thread_id": "run-1"}})
    except RuntimeError as exc:
        assert "repair_batch_chapters" in str(exc)
    else:
        raise AssertionError("expected incomplete graph state to prevent completion")


def test_batch_contract_repair_entries_are_limited_to_the_current_batch():
    batch = {"id": "m2-04-05", "chapter_numbers": [4, 5]}
    chapters = [
        {"chapter": 4, "title": "当前批次", "path": "lessons/04-current.md"},
        {"chapter": 5, "title": "当前批次", "path": "lessons/05-current.md"},
        {"chapter": 6, "title": "下一批次", "path": "lessons/06-next.md"},
    ]
    source_contract = {
        "diagnostics": [
            {"path": "lessons/04-current.md", "code": "INTRO_NON_CANONICAL", "actual": "旧章首"},
            {"path": "lessons/06-next.md", "code": "REFERENCE_SECTION_MISSING", "actual": "缺参考文献"},
        ],
        "report": {"lessons": []},
    }

    entries = _batch_contract_repair_entries(source_contract, batch, chapters)

    assert [entry["chapter"] for entry in entries] == [4]
    assert entries[0]["batch"] == batch
    assert "INTRO_NON_CANONICAL" in entries[0]["issues"][0]


def test_batch_repair_scope_never_reads_the_course_quality_queue():
    state = {
        "repair_scope": "batch",
        "batch_repair_queue": [{"chapter": 4}],
        "quality_cycle_queue": [{"chapter": 1}],
    }

    assert _repair_queue_for_scope(state) == [{"chapter": 4}]


def test_final_batch_repair_routes_to_course_quality_instead_of_nonexistent_next_batch():
    state = {
        "current_batch_index": 1,
        "batches": [{"id": "m1-01-03"}],
    }

    assert _batch_repair_completion_route(state) == "course_quality"
    assert _generation_cursor_exhausted(state) is True


def test_workspace_context_keeps_complete_core_contract_at_64k(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    mission = "成功标准：" + "甲" * 20000 + "完整结尾"
    (workspace / "MISSION.md").write_text(mission, encoding="utf-8")

    context = _read_workspace_context(tmp_path)

    assert context["MISSION.md"].endswith("完整结尾")
    assert "其余内容已截断" not in context["MISSION.md"]


def test_workspace_contract_snapshot_keeps_complete_core_contract_at_64k(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    mission = "成功标准：" + "甲" * 20000 + "完整结尾"
    (workspace / "MISSION.md").write_text(mission, encoding="utf-8")

    snapshot = _workspace_contract_snapshot(tmp_path)

    assert snapshot["MISSION.md"].endswith("完整结尾")


def test_external_links_are_relocated_without_losing_image_or_source_evidence():
    markdown = (
        "# 标题\n\n"
        "> 预计学习时间：30 分钟  \n"
        "> 一句话总结：完成。\n\n"
        "## 正文\n\n"
        "![架构截图](https://example.com/image.png)\n\n"
        "阅读[官方说明](https://example.com/docs)。\n\n"
        "## 参考文献\n\n"
        "- 已有来源\n"
    )
    repaired, changed = _relocate_external_links_to_references(markdown)
    assert changed is True
    assert "https://" not in repaired.split("## 参考文献", 1)[0]
    assert "图示说明：架构截图" in repaired
    assert "[架构截图](https://example.com/image.png)" in repaired.split("## 参考文献", 1)[1]
    assert "[官方说明](https://example.com/docs)" in repaired.split("## 参考文献", 1)[1]


def test_persisted_batch_quality_also_refreshes_the_course_snapshot(tmp_path, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        quality_integration,
        "write_course_quality_snapshot",
        lambda root, results, **kwargs: captured.update(
            root=root, results=results, kwargs=kwargs
        ),
    )
    results = [{
        "batch": {"id": "m1-01-01"},
        "chapters": [{"chapter": 1, "passed": True}],
        "build": {"succeeded": True},
        "validation": {"succeeded": True},
    }]

    _persist_latest_batch_quality_results(
        tmp_path,
        results,
        repair_tasks=[{"chapter": 1, "status": "fixed_verified"}],
        course_integration={"passed": True},
    )

    assert captured["root"] == tmp_path
    assert captured["results"] == results
    assert captured["kwargs"]["repair_tasks"][0]["status"] == "fixed_verified"
    assert captured["kwargs"]["course_integration"] == {"passed": True}


def test_diagnostic_supervisor_translates_raw_build_stack_to_a_safe_fix():
    issue, strategy = _diagnose_course_tool_failure(
        'Error: courses/demo/lessons/10-chapter.md 在"参考文献"之前包含外部链接',
        "lessons/10-chapter.md",
    )
    assert "参考文献之前存在外部链接" in issue
    assert "参考文献链接规则" in strategy


def test_diagnostic_supervisor_keeps_disclosure_evidence_for_targeted_revision():
    issue, strategy = _diagnose_course_tool_failure(
        'lessons/02-skill.md 泄露学生不可见信息: 你提供（第 250 行：“请确认你提供的是 git log 输出”）',
        "lessons/02-skill.md",
    )

    assert "披露边界检查" in issue
    assert "证据：" in issue
    assert "披露语境" in strategy


def test_blueprint_markdown_records_continuity():
    markdown = _blueprint_markdown(sample_blueprint())
    assert "# 测试课程：课程蓝图" in markdown
    assert "模块 1：基础模块" in markdown
    assert "学习成果：成果 1" in markdown


def test_effective_char_count_ignores_markdown_and_code_blocks():
    markdown = "# 标题\n\n正文内容。\n\n```python\nprint('不计入')\n```\n"
    assert _effective_char_count(markdown) == len("标题正文内容。")


def test_lesson_intro_normalizer_repairs_legacy_plain_text_metadata():
    markdown = (
        "# 第 1 章 测试\n\n"
        "预计学习时间：60 分钟\n\n"
        "一句话总结：这是一句完整总结。\n\n"
        "---\n\n正文\n"
    )

    normalized, changed = _normalize_lesson_intro(markdown)

    assert changed is True
    assert "> 预计学习时间：60 分钟  \n> 一句话总结：这是一句完整总结。" in normalized
    assert _normalize_lesson_intro(normalized) == (normalized, False)


def test_lesson_intro_normalizer_recovers_summary_from_humanized_inline_quote():
    markdown = (
        "# 第 1 章 范式转移\n\n"
        "> **预计学习时间：90 分钟** 本章建立 AI Agent 的认知坐标。\n\n"
        "## 正文\n\n内容。\n"
    )

    normalized, changed = _normalize_lesson_intro(markdown)

    assert changed is True
    assert "> 预计学习时间：90 分钟  \n> 一句话总结：本章建立 AI Agent 的认知坐标。" in normalized


def test_course_validation_does_not_scan_stale_html_after_build_failure(monkeypatch):
    calls = []
    monkeypatch.setattr(
        course_quality,
        "run_course_tool",
        lambda _slug, action, **_kwargs: calls.append(action) or {"succeeded": True},
    )

    validation = _full_course_validation_after_build(
        "test-course", {"succeeded": False, "stderr": "章首格式错误"}
    )

    assert calls == []
    assert validation["succeeded"] is False
    assert "未执行整课确定性检查" in validation["stderr"]


def test_clean_course_quality_review_can_continue_to_release_without_another_approval():
    assert _quality_review_can_auto_complete(
        {"unresolved": [], "deterministic_scan": {"succeeded": True}}
    ) is True
    assert _quality_review_can_auto_complete(
        {"unresolved": [{"chapters": [{"chapter": 1}]}], "deterministic_scan": {"succeeded": True}}
    ) is False


def test_quality_revision_refresh_keeps_report_and_state_payload_together():
    fresh, report = _refresh_quality_review_state(
        lambda _state: {
            "course_quality_report": {"unresolved": []},
            "batch_results": [{"batch": {"id": "m1"}}],
            "quality_cycle": {"cycle_id": "cycle-1"},
            "quality_cycle_id": "cycle-1",
            "quality_cycle_iteration": 3,
        },
        {"course_quality_report": {"unresolved": [{"chapter": 1}]}},
    )

    assert report == {"unresolved": []}
    assert fresh["batch_results"][0]["batch"]["id"] == "m1"
    assert _quality_review_can_auto_complete(
        {"unresolved": [], "deterministic_scan": {"succeeded": False}}
    ) is False
    assert _quality_review_can_auto_complete(
        {
            "unresolved": [],
            "course_issues": [{"path": "index.html", "issue": "发布产物失败"}],
            "deterministic_scan": {"succeeded": True},
        }
    ) is False


def test_deterministic_contract_repairs_do_not_trigger_unrelated_llm_rewrites():
    diagnostics = [
        {"code": "INTRO_NON_CANONICAL"},
        {"code": "REFERENCE_SECTION_MISSING"},
        {"code": "EXTERNAL_LINK_BEFORE_REFERENCES"},
    ]
    assert _contract_codes_requiring_llm(diagnostics, handled={
        "INTRO_NON_CANONICAL",
        "REFERENCE_SECTION_MISSING",
        "EXTERNAL_LINK_BEFORE_REFERENCES",
    }) == []
    assert _contract_codes_requiring_llm(
        [{"code": "TITLE_MISSING"}], handled=set()
    ) == ["TITLE_MISSING"]


def test_agent_selected_reference_node_is_normalized_in_memory_without_guessing_title_words():
    markdown = "# 标题\n\n正文\n\n**本章使用的资料来源**：\n\n- [来源](https://example.com)\n"
    offset = markdown.index("**本章使用的资料来源**")

    normalized, changed = _normalize_reference_node(markdown, f"paragraph:{offset}")

    assert changed is True
    assert "## 参考文献\n\n- [来源]" in normalized


def test_repair_node_imports_the_agent_selected_reference_normalizer():
    markdown = "# 标题\n\n**本章参考文献**：\n"
    offset = markdown.index("**本章参考文献**")

    normalized, changed = repair._normalize_reference_node(
        markdown, f"heading:{offset}"
    )

    assert changed is True
    assert "## 参考文献" in normalized


def test_original_structure_task_closes_even_when_semantic_review_finds_a_different_issue():
    assert _repair_issue_is_resolved(
        "[EXTERNAL_LINK_BEFORE_REFERENCES] 2 个外链需要迁移",
        contract_codes=set(),
        remaining_issues=["[minor] 缺少查询示例"],
        humanizer_score=48,
        effective_chars=12000,
        effective_minimum=10000,
        semantic_decision="manual_review",
    ) is True

    assert _repair_issue_is_resolved(
        "[minor] 缺少查询示例",
        contract_codes=set(),
        remaining_issues=["[minor] 路径转义错误"],
        humanizer_score=48,
        effective_chars=12000,
        effective_minimum=10000,
        semantic_decision="manual_review",
    ) is True


def test_relevant_ledger_keeps_module_context_and_recent_cross_module_bridge():
    ledger = [
        {"module": "前置", "chapter": 1},
        {"module": "前置", "chapter": 2},
        {"module": "当前", "chapter": 3},
        {"module": "当前", "chapter": 4},
    ]
    selected = _relevant_ledger(ledger, "当前")
    assert [item["chapter"] for item in selected] == [1, 2, 3, 4]


def test_research_sources_are_written_without_overwriting_user_resources(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    resources = workspace / "RESOURCES.md"
    resources.write_text("# 课程资源\n\n- 用户提供资料\n", encoding="utf-8")
    research = {
        "sources": [
            {
                "title": "官方文档",
                "url": "https://docs.example.com",
                "reason": "解释核心概念。",
                "source_type": "official",
            }
        ],
        "notes": [],
    }
    _write_research_to_resources(tmp_path, research)
    content = resources.read_text(encoding="utf-8")
    assert "用户提供资料" in content
    assert "https://docs.example.com" in content


def test_workspace_contract_sync_uses_blueprint_as_the_single_chapter_count(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "COURSE-GENERATION-SPEC.md").write_text(
        "# 课程生成规格\n\n- 期望章节数：8（供蓝图规划参考）\n",
        encoding="utf-8",
    )
    (tmp_path / "course.json").write_text('{"title": "旧标题", "lessons": []}', encoding="utf-8")
    (workspace / "generation-plan.agent.json").write_text('{"batches": []}', encoding="utf-8")
    blueprint = sample_blueprint()

    result = _sync_workspace_contract(tmp_path, blueprint)

    assert result["chapter_count"] == 5
    assert "期望章节数：5（以课程蓝图为准）" in (
        workspace / "COURSE-GENERATION-SPEC.md"
    ).read_text(encoding="utf-8")
    assert '"planned_chapter_count": 5' in (tmp_path / "course.json").read_text(encoding="utf-8")
    assert len(json.loads((workspace / "generation-plan.agent.json").read_text())["batches"]) == 2


def test_global_chapter_request_updates_spec_before_the_new_blueprint_is_ready(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "COURSE-GENERATION-SPEC.md").write_text(
        "# 课程生成规格\n\n- 期望章节数：8（供蓝图规划参考）\n",
        encoding="utf-8",
    )
    (tmp_path / "course.json").write_text("{}", encoding="utf-8")

    count = _sync_requested_chapter_count(
        tmp_path,
        [{"step": "blueprint", "request": "当前课程要求的是10章，请保持一致"}],
    )

    assert count == 10
    assert "期望章节数：10" in (workspace / "COURSE-GENERATION-SPEC.md").read_text(encoding="utf-8")


def test_workspace_reconciliation_reaudits_for_mission_only_patch():
    assert _reconciliation_route(
        {
            "workspace_revision": {
                "patches": [{"path": "MISSION.md"}],
                "downstream_impacts": [],
            }
        }
    ) == "audit"


def test_initial_chapter_writer_retries_transport_failures_before_deferring():
    calls = []
    retries = []

    def write(call_attempt):
        calls.append(call_attempt)
        if call_attempt == 1:
            raise TimeoutError("timed out")
        return "# 第 1 章\n\n正文"

    result = _retry_initial_chapter_write(
        write,
        max_attempts=3,
        on_retry=lambda failed_attempt, exc: retries.append(
            (failed_attempt, str(exc))
        ),
    )

    assert result == "# 第 1 章\n\n正文"
    assert calls == [1, 2]
    assert retries == [(1, "timed out")]


def test_humanizer_timeout_preserves_generated_body_metrics_and_resume_stage():
    markdown = "# 第 1 章\n\n" + "正文内容" * 3000
    deferred = _deferred_chapter_quality_result(
        chapter=1,
        title="测试章节",
        path="lessons/01-test.md",
        markdown=markdown,
        effective_char_min=10000,
        failure_stage="humanizing",
        issue="Humanizer 失败：timed out",
        attempts=[{"attempt": 1, "failed_stage": "humanizing"}],
    )

    assert deferred["body_generated"] is True
    assert deferred["effective_chars"] > 10000
    assert deferred["pending_stage"] == "humanizing"
    assert deferred["semantic_review"]["decision"] == "pending"
    assert _chapter_resume_stage(deferred, markdown) == "humanizing"


def test_effective_content_deficit_excludes_mermaid_before_humanizer():
    markdown = "正文讲解" * 1000 + "\n```mermaid\n" + "graph TD; A-->B;\n" * 1000 + "```\n"

    effective_chars, deficit = _effective_content_deficit(markdown, 10000)

    assert effective_chars < 10000
    assert deficit == 10000 - effective_chars


def test_effective_char_count_does_not_treat_inline_fence_example_as_a_code_block():
    markdown = (
        "正文中可以写内联示例：` ``` `，这仍是正常教学文本。\n\n"
        "```python\nprint('代码不计入')\n```\n\n"
        "后续正文也必须继续计入有效字符。"
    )

    assert _effective_char_count(markdown) == len(
        "正文中可以写内联示例：，这仍是正常教学文本。后续正文也必须继续计入有效字符。"
    )


def test_chapter_progress_persists_humanizer_resume_state(tmp_path):
    _save_chapter_progress(
        tmp_path,
        "m1-01-01",
        1,
        {"body_generated": True, "pending_stage": "humanizing", "effective_chars": 12230},
    )

    assert _load_chapter_progress(tmp_path, "m1-01-01", 1) == {
        "body_generated": True,
        "pending_stage": "humanizing",
        "effective_chars": 12230,
    }


def test_workspace_reconciliation_researches_only_for_source_change():
    assert _reconciliation_route(
        {"workspace_revision": {"downstream_impacts": ["资料来源与引用范围"]}}
    ) == "research"


def test_workspace_reconciliation_rebuilds_blueprint_for_course_structure_change():
    assert _reconciliation_route(
        {"workspace_revision": {"downstream_impacts": ["课程蓝图与章节结构"]}}
    ) == "blueprint"


def test_workspace_revision_requires_initial_research_before_rebuilding_blueprint(tmp_path):
    state = {"workspace_revision": {"downstream_impacts": ["课程蓝图与章节结构"]}}

    assert _workspace_revision_route(state, tmp_path) == "research"


def test_workspace_revision_skips_research_only_after_a_durable_research_record(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "research.agent.json").write_text("{}", encoding="utf-8")
    state = {"workspace_revision": {"downstream_impacts": ["课程蓝图与章节结构"]}}

    assert _workspace_revision_route(state, tmp_path) == "blueprint"


def test_global_reconciliation_routes_mission_only_repair_directly_back_to_audit():
    graph = build_course_graph(
        "test-global-reconciliation-audit-route",
        create_course_agent("fake", None),
        MemorySaver(),
    ).get_graph()
    targets = {
        edge.data: edge.target
        for edge in graph.edges
        if edge.source == "reconcile_global_requirements" and edge.conditional
    }

    assert targets["audit"] == "verify_workspace_contract"
    assert targets["research"] == "research_sources"
    assert targets["blueprint"] == "draft_blueprint"


def test_mission_revision_does_not_research_when_its_patch_only_changes_the_blueprint():
    graph = build_course_graph(
        "test-mission-revision-minimal-route",
        create_course_agent("fake", None),
        MemorySaver(),
    ).get_graph()
    targets = {
        edge.data: edge.target
        for edge in graph.edges
        if edge.source == "revise_workspace" and edge.conditional
    }

    assert targets["blueprint"] == "draft_blueprint"
    assert targets["research"] == "research_sources"
    assert targets["audit"] == "verify_workspace_contract"


def test_course_graph_compiles_with_autonomous_batch_loop():
    graph = build_course_graph(
        "test-autonomous-batch-loop",
        create_course_agent("fake", None),
        MemorySaver(),
    )

    assert graph is not None


def test_mission_revision_routes_to_incremental_workspace_node():
    graph = build_course_graph(
        "test-mission-revision-route",
        create_course_agent("fake", None),
        MemorySaver(),
    ).get_graph()
    conditional_edges = {
        edge.data: edge.target
        for edge in graph.edges
        if edge.source == "approve_mission" and edge.conditional
    }

    assert conditional_edges["revise"] == "revise_workspace"


def test_projected_node_records_gateway_diagnostics_before_reraising(monkeypatch):
    events = []
    artifacts = []
    monkeypatch.setattr(context_packs, "update_run", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        context_packs,
        "append_event",
        lambda run_id, event_type, step, message, payload=None: events.append(
            (run_id, event_type, step, message, payload)
        ),
    )
    monkeypatch.setattr(
        context_packs,
        "record_run_artifact",
        lambda *args, **kwargs: artifacts.append((args, kwargs)),
    )

    def fail(_state):
        raise GatewayNoFinalTextError(
            {
                "response_status": "incomplete",
                "incomplete_reason": "max_output_tokens",
                "output_blocks": [{"type": "reasoning", "status": "completed"}],
                "usage": {"output_tokens": 3200},
            }
        )

    wrapped = _projected("run-1", "mission", "任务定义", fail, create_course_agent("fake", None))

    try:
        wrapped({})
    except GatewayNoFinalTextError:
        pass
    else:
        raise AssertionError("expected GatewayNoFinalTextError")

    assert events[-1][1:3] == ("node.failed", "mission")
    assert events[-1][4]["gateway"]["incomplete_reason"] == "max_output_tokens"
    assert artifacts[0][0][6] == "system"
    assert artifacts[0][0][4]["headline"] == "任务定义未完成"
    assert artifacts[0][0][5]["gateway"]["usage"] == {"output_tokens": 3200}


def test_projected_node_does_not_treat_langgraph_interrupt_as_a_model_failure(monkeypatch):
    events = []
    artifacts = []
    monkeypatch.setattr(context_packs, "update_run", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        context_packs,
        "append_event",
        lambda run_id, event_type, step, message, payload=None: events.append(event_type),
    )
    monkeypatch.setattr(
        context_packs,
        "record_run_artifact",
        lambda *args, **kwargs: artifacts.append(args),
    )

    def wait_for_approval(_state):
        raise GraphInterrupt([])

    wrapped = _projected("run-1", "quality", "整课质量闭环", wait_for_approval, create_course_agent("fake", None))

    try:
        wrapped({})
    except GraphInterrupt:
        pass
    else:
        raise AssertionError("expected GraphInterrupt")

    assert events == ["node.started"]
    assert artifacts == []


def test_batch_review_approve_routes_to_the_next_generation_batch():
    graph = build_course_graph(
        "test-batch-review-next-route",
        create_course_agent("fake", None),
        MemorySaver(),
    ).get_graph()

    conditional_edges = {
        edge.data: edge.target
        for edge in graph.edges
        if edge.source == "request_batch_review" and edge.conditional
    }

    assert conditional_edges["next"] == "generate_batch"
    # A skipped failed batch must still enter the all-course quality gate;
    # release is unavailable until that gate has no unresolved evidence.
    assert conditional_edges["complete"] == "prepare_course_quality_review"


def test_batch_structure_repair_stays_in_generation_before_the_next_batch():
    course_graph = build_course_graph(
        "test-batch-structure-repair-route",
        create_course_agent("fake", None),
        MemorySaver(),
    ).get_graph()
    generated_edges = {
        edge.data: edge.target
        for edge in course_graph.edges
        if edge.source == "generate_batch" and edge.conditional
    }
    batch_repair_edges = {
        edge.data: edge.target
        for edge in course_graph.edges
        if edge.source == "repair_batch_chapters" and edge.conditional
    }

    assert generated_edges["repair"] == "repair_batch_chapters"
    assert batch_repair_edges["next"] == "repair_batch_chapters"
    assert batch_repair_edges["batch_complete"] == "generate_batch"
    assert batch_repair_edges["manual"] == "request_batch_review"


def test_course_quality_repairs_remain_in_the_quality_subgraph():
    graph = build_course_graph(
        "test-course-quality-repair-subgraph",
        create_course_agent("fake", None),
        MemorySaver(),
    ).get_graph()

    quality_edges = {
        edge.data: edge.target
        for edge in graph.edges
        if edge.source == "course_quality_review" and edge.conditional
    }
    repair_edges = {
        edge.data: edge.target
        for edge in graph.edges
        if edge.source == "repair_open_chapters" and edge.conditional
    }

    assert quality_edges["repair"] == "repair_open_chapters"
    assert repair_edges["next"] == "repair_open_chapters"
    assert repair_edges["course_quality"] == "prepare_course_quality_review"


def test_release_summary_regeneration_reenters_only_the_release_summary_node():
    graph = build_course_graph(
        "test-release-summary-refresh",
        create_course_agent("fake", None),
        MemorySaver(),
    ).get_graph()
    release_edges = {
        edge.data: edge.target
        for edge in graph.edges
        if edge.source == "release_approval" and edge.conditional
    }

    assert release_edges["refresh"] == "prepare_release_review"
    assert release_edges["quality"] == "prepare_course_quality_review"


def test_lesson_intro_normalizer_repairs_learning_time_alias():
    markdown = (
        "# 第 2 章 流程控制\n\n"
        "> 学习时间：建议 3 小时  \n"
        "> 一句话总结：学习条件、循环与函数。\n\n"
        "## 一、正文\n"
    )
    normalized, changed = _normalize_lesson_intro(markdown)
    assert changed is True
    assert "> 预计学习时间：建议 3 小时" in normalized
    assert normalized.count("> 一句话总结：") == 1


def test_lesson_intro_normalizer_is_idempotent_for_renderer_contract():
    markdown = (
        "# 第 3 章 面向对象\n\n"
        "> 预计学习时间：5 小时  \n"
        "> 一句话总结：理解对象如何封装状态与行为。\n\n"
        "## 正文\n"
    )
    normalized, changed = _normalize_lesson_intro(markdown)
    assert normalized == markdown
    assert changed is False


def test_semantic_issues_require_literal_chapter_evidence():
    markdown = "# 测试\n\nCURRENT_YEAR = datetime.now().year\n"
    issues = [
        "[major] 年份测试问题 | 证据：『CURRENT_YEAR = datetime.now().year』 | 建议：检查边界。",
        "[major] 这是一条没有原文证据的历史问题。",
    ]
    assert _ground_semantic_issues(markdown, issues) == [issues[0]]


def test_unclosed_fence_is_closed_before_references():
    markdown = "# 章节\n\n```python\nprint('x')\n\n## 参考文献\n"
    normalized, changed = _close_unclosed_markdown_fence(markdown)
    assert changed is True
    assert "print('x')\n```\n\n## 参考文献" in normalized


def test_integration_repair_entries_ignore_warnings_but_map_generated_html_errors():
    result = {
        "chapters": [
            {"chapter": 3, "title": "第三章", "path": "lessons/03-chapter.md"},
        ],
        "build": {
            "stderr": "Error: courses/demo/lessons/02-chapter.md 章首格式错误",
        },
        "validation": {
            "stdout": "\n".join(
                [
                    "[ERROR] METADATA_TARGET_MISSING course.json:1 lessons/10.html 不存在",
                    "[WARNING] URL_NOT_IN_RESOURCES lessons/09-chapter.md:10 URL 未登记",
                    "[ERROR] MARKDOWN_UNCLOSED_FENCE lessons/03-chapter.md:20 Markdown 代码围栏未闭合",
                    "[ERROR] CONTENT_PRIVATE_PATH lessons/07-chapter.html:20 学生内容暴露本机私有路径",
                ]
            )
        },
    }
    entries = _integration_repair_entries(result)
    assert [entry["chapter"] for entry in entries] == [2, 3, 7]


def test_revalidating_batches_keeps_each_integration_gate_scoped(tmp_path, monkeypatch):
    from app.workflow import graph as workflow_graph

    course_root = tmp_path / "courses" / "demo"
    course_root.mkdir(parents=True)
    calls = []

    def scoped_tool(slug, action, *, chapter_numbers=None):
        calls.append((slug, action, tuple(chapter_numbers or [])))
        return {"succeeded": True, "stdout": "", "stderr": ""}

    monkeypatch.setattr(quality_integration, "run_course_tool", scoped_tool)
    monkeypatch.setattr(
        quality_integration,
        "get_settings",
        lambda: SimpleNamespace(courses_root=tmp_path / "courses"),
    )
    results = [
        {
            "batch": {"id": "m1-01-01", "chapter_numbers": [1]},
            "chapters": [{"chapter": 1, "passed": True, "path": "lessons/01.md"}],
            "build": {"succeeded": False},
            "validation": {"succeeded": False},
        },
        {
            "batch": {"id": "m2-02-02", "chapter_numbers": [2]},
            "chapters": [{"chapter": 2, "passed": True, "path": "lessons/02.md"}],
            "build": {"succeeded": False},
            "validation": {"succeeded": False},
        },
    ]

    refreshed = _revalidate_batch_integrations("demo", results)

    assert calls == [
        ("demo", "build", (1,)),
        ("demo", "validate", (1,)),
        ("demo", "build", (2,)),
        ("demo", "validate", (2,)),
    ]
    assert all(
        item["quality_gates"]["stage_3_batch_integration"]["passed"]
        for item in refreshed
    )


def test_course_wide_integration_evidence_does_not_replace_batch_gate_results():
    batch_result = {
        "batch": {"id": "m1-01-01", "chapter_numbers": [1]},
        "chapters": [{"chapter": 1, "passed": True}],
        "build": {"succeeded": True, "scope": {"chapter_numbers": [1]}},
        "validation": {"succeeded": True, "scope": {"chapter_numbers": [1]}},
        "quality_gates": {"stage_3_batch_integration": {"passed": True}},
        "passed": True,
    }

    refreshed = _refresh_quality_integration(
        [batch_result],
        {"succeeded": False, "stderr": "整课第 9 章构建失败"},
        {"succeeded": False, "stderr": "整课检查未通过"},
    )

    assert refreshed[0]["build"]["scope"] == {"chapter_numbers": [1]}
    assert refreshed[0]["quality_gates"]["stage_3_batch_integration"]["passed"] is True
    assert refreshed[0]["course_integration"]["passed"] is False


def test_private_path_repair_removes_home_directory_without_touching_api_routes():
    markdown = (
        "请在 /Users/alice/project/app 中运行命令。\n"
        "API 使用 GET /api/v1/users/ 获取当前用户。\n"
    )

    normalized, changed = _redact_private_paths(markdown)

    assert changed is True
    assert "/Users/alice/" not in normalized
    assert "<项目根目录>/project/app" in normalized
    assert "/api/v1/users/" in normalized
    windows, windows_changed = _redact_private_paths(r"C:\Users\alice\project\app.py")
    assert windows_changed is True
    assert windows == r"<项目根目录>\project\app.py"
