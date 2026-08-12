import json
import inspect
from types import SimpleNamespace

from app.agents.definitions import AGENT_DEFINITIONS, get_agent_definition
from app.agents.context import (
    _ground_repair_verifications,
    _planning_request,
    _semantic_review_context,
    _teaching_skill_packet,
)
from app.agents.course_runtime import CourseAgentRuntime
from app.provider import (
    CodexGatewayResponsesModel,
    CodexGatewayModelTransport,
    DeepSeekModelTransport,
    GatewayMalformedResponseError,
    GatewayNoFinalTextError,
    _codex_gateway_service_tier,
    _read_codex_gateway_config,
    _response_text,
    _with_reasoning_effort,
)
from app.config import Settings
from app.schemas import (
    BlueprintOutput,
    HumanizerPatchOutput,
    HumanizerPatchOutput,
    MissionOutput,
    ResearchCurationOutput,
    ResearchPlanOutput,
    WorkspaceConsistencyOutput,
    WorkspaceRevisionOutput,
    ReferenceSectionDecision,
    SectionRewriteOutput,
    WorkspacePatch,
)


class RunnableStub:
    def __init__(self, result):
        self.result = result
        self.prompt = ""

    def invoke(self, prompt):
        self.prompt = prompt
        return self.result


class ModelStub:
    def __init__(self):
        self.method = None
        self.runnable = RunnableStub(
            MissionOutput(
                mission_markdown="# 任务定义",
                assumptions=[],
            )
        )

    def with_structured_output(self, schema, *, method):
        assert schema is MissionOutput
        self.method = method
        return self.runnable


class EmptyFallbackModel:
    def __init__(self):
        self.fallback_prompts: list[str] = []
        self.responses = ["", '{"mission_markdown":"# 重试成功","assumptions":[]}']

    def with_structured_output(self, schema, *, method):
        del schema, method
        class FailingRunnable:
            def invoke(self, prompt):
                del prompt
                raise ValueError("invalid json")

        return FailingRunnable()

    def invoke(self, prompt):
        self.fallback_prompts.append(prompt)
        return type("Response", (), {"content": self.responses.pop(0)})()


class MissingFinalTextFallbackModel:
    def __init__(self):
        self.attempts = 0

    def invoke(self, prompt):
        del prompt
        self.attempts += 1
        if self.attempts < 3:
            raise RuntimeError(
                "LLM Gateway 未返回可用文本内容（response_status=incomplete；"
                "output_blocks=reasoning:completed）"
            )
        return type(
            "Response",
            (),
            {"content": '{"mission_markdown":"# 第三次成功","assumptions":[]}'},
        )()


class WorkspaceRevisionFallbackModel:
    def __init__(self):
        self.prompt = ""
        self.bind_calls = []

    def bind(self, **kwargs):
        self.bind_calls.append(kwargs)
        return self

    def invoke(self, prompt):
        self.prompt = prompt
        return type(
            "Response",
            (),
            {
                "content": json.dumps(
                    {
                        "change_summary": "课程增加 3D Graph 章节。",
                        "patches": [
                            {
                                "path": "MISSION.md",
                                "original": "课程共 8 章。",
                                "replacement": "课程共 9 章。",
                                "reason": "纳入 3D Graph 进阶内容",
                            }
                        ],
                        "preferred_chapter_count": 9,
                        "source_policy": None,
                        "downstream_impacts": ["课程蓝图"],
                    },
                    ensure_ascii=False,
                )
            },
        )()


class LongWritingModel:
    def __init__(self):
        self.bind_calls = []
        self.prompts = []

    def bind(self, **kwargs):
        self.bind_calls.append(kwargs)
        return self

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return type("Response", (), {"content": "# 第 1 章\n\n正文"})()


def test_deepseek_structured_output_uses_json_mode_without_tool_choice():
    provider = DeepSeekModelTransport.__new__(DeepSeekModelTransport)
    provider.model = ModelStub()

    result = provider.invoke_structured(MissionOutput, "生成任务定义")

    assert result.mission_markdown == "# 任务定义"
    assert provider.model.method == "json_mode"
    assert '"properties"' in provider.model.runnable.prompt
    assert "不要使用 Markdown 代码围栏" in provider.model.runnable.prompt


def test_reference_role_classifier_accepts_only_supplied_ast_node_ids():
    provider = CourseAgentRuntime.__new__(CourseAgentRuntime)
    provider.settings = Settings()
    provider._structured = lambda *args, **kwargs: ReferenceSectionDecision(
        role="references",
        node_id="heading:80",
        confidence=0.94,
        reason="位于章末且区块内容为来源链接。",
        recommended_action="canonicalize_heading",
    )
    candidates = [{
        "node_id": "heading:80", "depth": 2, "title": "本章资料来源", "line": 80,
        "relative_position": 0.9, "child_kinds": ["list"], "external_link_count": 3,
        "excerpt": "官方文档",
    }]
    decision = provider.classify_reference_section({}, candidates, {})
    assert decision.node_id == "heading:80"
    assert decision.confidence == 0.94

    provider._structured = lambda *args, **kwargs: ReferenceSectionDecision(
        role="references", node_id="heading:999", confidence=0.8,
        reason="错误节点", recommended_action="canonicalize_heading",
    )
    import pytest
    with pytest.raises(ValueError, match="候选"):
        provider.classify_reference_section({}, candidates, {})


def test_section_rewrite_fallback_is_bound_to_task_hash_and_existing_section():
    provider = CourseAgentRuntime.__new__(CourseAgentRuntime)
    provider.settings = Settings()
    provider._structured = lambda *args, **kwargs: SectionRewriteOutput(
        task_id="task-1",
        expected_hash="a" * 64,
        original_section="## 旧区块\n\n内容",
        replacement_section="## 参考文献\n\n内容",
        reason="规范结构",
    )
    result = provider.rewrite_section(
        {"id": "task-1"}, "## 旧区块\n\n内容", {}, expected_hash="a" * 64
    )
    assert result.replacement_section.startswith("## 参考文献")


def test_resolved_gap_requires_new_grounded_evidence_not_the_original_trigger():
    markdown = (
        "编写一个查询脚本，搜索最相似的 5 个分块。\n\n"
        "```python\nresults = table.search(query_vec).limit(5).to_list()\n```"
    )
    tasks = [{
        "id": "task-1",
        "evidence": {"quoted_source": "编写一个查询脚本，搜索最相似的 5 个分块。"},
    }]

    grounded = _ground_repair_verifications(
        markdown,
        tasks,
        [{
            "task_id": "task-1",
            "resolved": True,
            "evidence_excerpt": "table.search(query_vec).limit(5).to_list()",
            "reason": "已经提供最小调用示例。",
        }],
    )
    trigger_only = _ground_repair_verifications(
        markdown,
        tasks,
        [{
            "task_id": "task-1",
            "resolved": True,
            "evidence_excerpt": "编写一个查询脚本，搜索最相似的 5 个分块。",
            "reason": "误把练习要求当成解决证据。",
        }],
    )

    assert grounded["task-1"]["resolved"] is True
    assert trigger_only["task-1"]["resolved"] is False


def test_structured_output_retries_an_empty_fallback_response():
    provider = DeepSeekModelTransport.__new__(DeepSeekModelTransport)
    provider.model = EmptyFallbackModel()
    provider.settings = Settings(llm_structured_output_retry_count=1)

    result = provider.invoke_structured(MissionOutput, "生成任务定义")

    assert result.mission_markdown == "# 重试成功"
    assert len(provider.model.fallback_prompts) == 2
    assert "上一轮没有返回可解析的 JSON" in provider.model.fallback_prompts[1]


def test_structured_output_retries_missing_gateway_final_text_before_succeeding():
    provider = DeepSeekModelTransport.__new__(DeepSeekModelTransport)
    provider.model = MissingFinalTextFallbackModel()
    provider.settings = Settings(llm_structured_output_retry_count=2)

    result = provider.invoke_structured(MissionOutput, "生成任务定义")

    assert result.mission_markdown == "# 第三次成功"
    assert provider.model.attempts == 3


def test_workspace_revision_uses_existing_workspace_instead_of_full_course_rewrite():
    transport = DeepSeekModelTransport.__new__(DeepSeekModelTransport)
    transport.model = WorkspaceRevisionFallbackModel()
    transport.settings = Settings(llm_structured_output_retry_count=0)
    provider = CourseAgentRuntime(transport)

    result = provider.revise_workspace(
        {
            "feedback": "增加 3D Graph 章节",
            "workspace": {"MISSION.md": "课程共 8 章。", "NOTES.md": "# 笔记"},
        }
    )

    assert isinstance(result, WorkspaceRevisionOutput)
    assert result.preferred_chapter_count == 9
    assert result.patches[0].path == "MISSION.md"
    assert "增加 3D Graph 章节" in transport.model.prompt
    assert "完整课程原始需求" not in transport.model.prompt
    assert {"max_tokens": 32768} in transport.model.bind_calls


def test_chapter_generation_uses_long_transport_and_output_profile():
    transport = DeepSeekModelTransport.__new__(DeepSeekModelTransport)
    transport.model = LongWritingModel()
    transport.settings = Settings(
        llm_long_content_hard_timeout_seconds=600,
        llm_chapter_max_output_tokens=32768,
    )

    provider = CourseAgentRuntime(transport)
    result = provider.generate_chapter({"chapter": {"number": 1}})

    assert result.startswith("# 第 1 章")
    assert {"max_tokens": 32768} in transport.model.bind_calls


def test_all_agent_output_budgets_default_to_the_safe_long_budget():
    settings = Settings()

    assert settings.llm_max_output_tokens == 32768
    assert settings.llm_chapter_max_output_tokens == 32768
    assert settings.llm_mission_max_output_tokens == 32768
    assert settings.llm_blueprint_max_output_tokens == 32768
    assert settings.llm_research_max_output_tokens == 32768
    assert settings.llm_workspace_audit_max_output_tokens == 32768
    assert settings.llm_presentation_max_output_tokens == 32768
    assert settings.llm_semantic_review_max_output_tokens == 32768
    assert settings.llm_continuity_max_output_tokens == 32768


def test_humanizer_uses_its_own_long_transport_and_safe_output_budget():
    provider = CourseAgentRuntime.__new__(CourseAgentRuntime)
    provider.settings = Settings(
        llm_humanizer_hard_timeout_seconds=720,
        llm_semantic_review_max_output_tokens=32768,
    )
    calls = []

    def structured(schema, prompt, **kwargs):
        calls.append((schema, kwargs))
        return HumanizerPatchOutput(score=50)

    provider._structured = structured
    provider.humanize("# 第 1 章\n\n正文")

    assert calls == [
        (
            HumanizerPatchOutput,
            {
                "hard_timeout_seconds": 720,
                "max_output_tokens": 32768,
                "transport_timeout_seconds": 720,
            },
        )
    ]


def test_reasoning_override_is_applied_only_to_codex_gateway_models():
    model = CodexGatewayResponsesModel(
        base_url="http://gateway/v1",
        token="never-log-this",
        model="llm-gateway--deepseek-v4-pro",
        timeout_seconds=12,
        max_output_tokens=3200,
        reasoning_effort="medium",
        service_tier=None,
    )

    assert _with_reasoning_effort(model, "low").reasoning_effort == "low"


def test_blueprint_planning_operations_use_the_long_running_profile():
    provider = CourseAgentRuntime.__new__(CourseAgentRuntime)
    provider.settings = Settings(
        llm_max_output_tokens=16384,
        llm_long_content_hard_timeout_seconds=600,
    )
    calls = []

    def structured(schema, prompt, **kwargs):
        calls.append((schema, kwargs))
        if schema is BlueprintOutput:
            return BlueprintOutput(course_title="测试课程", modules=[])
        if schema is ResearchPlanOutput:
            return ResearchPlanOutput()
        if schema is ResearchCurationOutput:
            return ResearchCurationOutput()
        if schema is WorkspaceConsistencyOutput:
            return WorkspaceConsistencyOutput(decision="pass")
        raise AssertionError(schema)

    provider._structured = structured
    provider.plan_research({"title": "测试课程"}, "# MISSION")
    provider.curate_research("允许公开资料", {"results": []})
    provider.create_blueprint({"title": "测试课程"}, "# MISSION")
    provider.audit_workspace_consistency("# MISSION", {}, {}, [])

    assert len(calls) == 4
    for _schema, kwargs in calls:
        assert kwargs["max_output_tokens"] == 16384
        assert kwargs["hard_timeout_seconds"] == 600
        assert kwargs["transport_timeout_seconds"] == 600
        assert "reasoning_effort" not in kwargs


def test_codex_gateway_reads_transport_from_existing_codex_config(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text(
        'model = "llm-gateway--kimi-k3"\n[model_providers.custom]\n'
        'base_url = "http://127.0.0.1:15721/codex/v1"\n'
        'experimental_bearer_token = "local-token"\n',
        encoding="utf-8",
    )

    gateway = _read_codex_gateway_config(Settings(codex_gateway_config_path=str(config)))

    assert gateway["base_url"].endswith("/codex/v1")
    assert gateway["model"] == "llm-gateway--kimi-k3"
    assert gateway["token"] == "local-token"


def test_codex_gateway_requests_responses_with_requested_runtime_options(monkeypatch):
    calls = []

    class Response:
        status_code = 200
        is_error = False
        text = ""

        def json(self):
            return {"output_text": "gateway response"}

    class Client:
        def __init__(self, timeout):
            assert timeout == 12

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, *, headers, json):
            calls.append((url, headers, json))
            return Response()

    monkeypatch.setattr("app.provider.httpx.Client", Client)
    model = CodexGatewayResponsesModel(
        base_url="http://gateway/v1",
        token="never-log-this",
        model="llm-gateway--kimi-k3",
        timeout_seconds=12,
        max_output_tokens=3200,
        reasoning_effort="medium",
        service_tier="standard",
    )

    assert model.invoke("hello").content == "gateway response"
    assert calls[0][0] == "http://gateway/v1/responses"
    assert calls[0][2]["reasoning"] == {"effort": "medium"}
    assert calls[0][2]["service_tier"] == "standard"
    assert calls[0][2]["max_output_tokens"] == 3200
    assert "never-log-this" not in str(calls[0][0])


def test_codex_gateway_can_lower_reasoning_effort_for_a_recovery_attempt():
    model = CodexGatewayResponsesModel(
        base_url="http://gateway/v1",
        token="never-log-this",
        model="llm-gateway--deepseek-v4-pro",
        timeout_seconds=12,
        max_output_tokens=3200,
        reasoning_effort="medium",
        service_tier=None,
    )

    recovery_model = model.bind(reasoning_effort="low")

    assert recovery_model.reasoning_effort == "low"
    assert recovery_model.max_output_tokens == 3200

    long_running_model = model.bind(timeout_seconds=300)
    assert long_running_model.timeout_seconds == 300


def test_codex_gateway_omits_an_unsupported_service_tier(monkeypatch):
    calls = []

    class Response:
        status_code = 200
        is_error = False
        text = ""

        def json(self):
            return {"output_text": "gateway response"}

    class Client:
        def __init__(self, timeout):
            del timeout

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, *, headers, json):
            del url, headers
            calls.append(json)
            return Response()

    monkeypatch.setattr("app.provider.httpx.Client", Client)
    model = CodexGatewayResponsesModel(
        base_url="http://gateway/v1",
        token="never-log-this",
        model="llm-gateway--deepseek-v4-pro",
        timeout_seconds=12,
        max_output_tokens=3200,
        reasoning_effort="medium",
        service_tier=None,
    )

    assert model.invoke("hello").content == "gateway response"
    assert "service_tier" not in calls[0]


def test_codex_gateway_missing_final_text_exposes_safe_response_diagnostics(monkeypatch):
    class Response:
        status_code = 200
        is_error = False
        text = ""

        def json(self):
            return {
                "status": "incomplete",
                "incomplete_details": {"reason": "max_output_tokens"},
                "usage": {"input_tokens": 120, "output_tokens": 3200},
                "output": [
                    {
                        "type": "reasoning",
                        "status": "completed",
                        "content": [{"type": "reasoning_text", "text": "不保存此文本"}],
                    }
                ],
            }

    class Client:
        def __init__(self, timeout):
            del timeout

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, *, headers, json):
            del url, headers, json
            return Response()

    monkeypatch.setattr("app.provider.httpx.Client", Client)
    model = CodexGatewayResponsesModel(
        base_url="http://gateway/v1",
        token="never-log-this",
        model="llm-gateway--deepseek-v4-pro",
        timeout_seconds=12,
        max_output_tokens=3200,
        reasoning_effort="medium",
        service_tier=None,
    )

    try:
        model.invoke("hello")
    except GatewayNoFinalTextError as exc:
        assert exc.diagnostics["response_status"] == "incomplete"
        assert exc.diagnostics["incomplete_reason"] == "max_output_tokens"
        assert exc.diagnostics["output_blocks"] == [
            {"type": "reasoning", "status": "completed", "content_types": ["reasoning_text"], "text_length": 6}
        ]
        assert exc.diagnostics["usage"] == {"input_tokens": 120, "output_tokens": 3200}
    else:
        raise AssertionError("expected a GatewayNoFinalTextError")


def test_codex_gateway_retries_a_non_json_success_response_with_safe_diagnostics(monkeypatch):
    responses = [
        SimpleNamespace(
            status_code=200,
            is_error=False,
            text="<html>temporary upstream page</html>",
            headers={"content-type": "text/html"},
            json=lambda: (_ for _ in ()).throw(ValueError("not json")),
        ),
        SimpleNamespace(
            status_code=200,
            is_error=False,
            text="",
            headers={"content-type": "application/json"},
            json=lambda: {"output_text": "recovered"},
        ),
    ]
    calls = []

    class Client:
        def __init__(self, timeout):
            del timeout

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, *, headers, json):
            del url, headers, json
            calls.append("post")
            return responses.pop(0)

    monkeypatch.setattr("app.provider.httpx.Client", Client)
    model = CodexGatewayResponsesModel(
        base_url="http://gateway/v1",
        token="never-log-this",
        model="llm-gateway--deepseek-v4-pro",
        timeout_seconds=12,
        max_output_tokens=3200,
        reasoning_effort="medium",
        service_tier=None,
    )

    assert model.invoke("hello").content == "recovered"
    assert len(calls) == 2


def test_codex_gateway_non_json_response_has_http_diagnostics(monkeypatch):
    response = SimpleNamespace(
        status_code=200,
        is_error=False,
        text="<html>temporary upstream page</html>",
        headers={"content-type": "text/html"},
        json=lambda: (_ for _ in ()).throw(ValueError("not json")),
    )

    class Client:
        def __init__(self, timeout):
            del timeout

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, *, headers, json):
            del url, headers, json
            return response

    monkeypatch.setattr("app.provider.httpx.Client", Client)
    model = CodexGatewayResponsesModel(
        base_url="http://gateway/v1",
        token="never-log-this",
        model="llm-gateway--deepseek-v4-pro",
        timeout_seconds=12,
        max_output_tokens=3200,
        reasoning_effort="medium",
        service_tier=None,
    )

    try:
        model.invoke("hello")
    except GatewayMalformedResponseError as exc:
        assert exc.diagnostics["response_status"] == "http_200_non_json"
        assert exc.diagnostics["content_type"] == "text/html"
        assert exc.diagnostics["body_excerpt"] == "<html>temporary upstream page</html>"
    else:
        raise AssertionError("expected a GatewayMalformedResponseError")


def test_codex_gateway_disables_a_tier_not_supported_by_selected_model(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text("model = 'llm-gateway--deepseek-v4-pro'", encoding="utf-8")
    (tmp_path / "ais-switch-model-catalog.json").write_text(
        '[{"slug":"llm-gateway--deepseek-v4-pro","service_tiers":[]}]',
        encoding="utf-8",
    )

    tier = _codex_gateway_service_tier(
        Settings(
            codex_gateway_config_path=str(config),
            codex_gateway_service_tier="standard",
        ),
        "llm-gateway--deepseek-v4-pro",
    )

    assert tier is None


def test_codex_gateway_response_text_excludes_reasoning_blocks():
    content = _response_text(
        {
            "output": [
                {
                    "type": "reasoning",
                    "content": [
                        {"type": "reasoning_text", "text": "不应进入最终输出"}
                    ],
                },
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": '{"mission_markdown":"# 任务"}'}
                    ],
                },
            ]
        }
    )

    assert content == '{"mission_markdown":"# 任务"}'


def test_codex_gateway_structured_output_uses_plain_json_fallback():
    provider = CodexGatewayModelTransport.__new__(CodexGatewayModelTransport)
    provider.settings = Settings(llm_structured_output_retry_count=0)
    provider.model = type(
        "GatewayModel",
        (),
        {"invoke": lambda self, prompt: type("Response", (), {"content": '{"mission_markdown":"# 任务","assumptions":[]}'})()},
    )()

    result = provider.invoke_structured(MissionOutput, "生成任务定义")

    assert result.mission_markdown == "# 任务"


def test_humanizer_applies_only_exact_prose_patches_to_the_existing_markdown():
    provider = CourseAgentRuntime.__new__(CourseAgentRuntime)
    provider.settings = Settings()
    provider._structured = lambda schema, prompt, **kwargs: HumanizerPatchOutput(
        score=47,
        issues=["删去填充语"],
        patches=[
            {
                "original": "此外，我们将深入探讨这个关键概念。",
                "replacement": "下面具体说明这个概念。",
            },
            {"original": "不存在的原文", "replacement": "不会应用"},
        ],
    )

    result = provider.humanize(
        "# 标题\n\n此外，我们将深入探讨这个关键概念。\n\n```python\nprint('保持不变')\n```"
    )

    assert result.score == 47
    assert "下面具体说明这个概念。" in result.revised_markdown
    assert "print('保持不变')" in result.revised_markdown
    assert "1 个 Humanizer 补丁未命中原文，已跳过" in result.issues


def test_teaching_skill_packet_selects_language_assets_verbatim():
    packet = _teaching_skill_packet(
        {
            "chapter": {
                "title": "流程控制与函数",
                "learning_outcome": "理解条件、循环和函数。",
            }
        }
    )

    assert "语言基础与标准库类写法指引" in packet
    assert "语言基础与标准库类结构模板" in packet
    assert "完整写法模板" in packet
    assert "不要照搬本例的 Java 事实" in packet


def test_teaching_skill_packet_selects_fastapi_framework_assets():
    packet = _teaching_skill_packet(
        {
            "chapter": {
                "title": "FastAPI 入门：第一个 Web API",
                "learning_outcome": "完成一个最小 API 闭环。",
            }
        }
    )

    assert "单一框架或工具介绍、应用及进阶类写法指引" in packet
    assert "单一框架或工具介绍、应用及进阶类结构模板" in packet


def test_semantic_review_context_keeps_sources_but_drops_unneeded_workspace_files():
    result = _semantic_review_context(
        {
            "course_context": {
                "title": "Python Web",
                "request": {"audience": "零基础", "effective_char_min": 10000},
                "workspace": {
                    "RESOURCES.md": "官方文档\n" * 4000,
                    "NOTES.md": "不应进入语义审校上下文",
                    "COURSE-GENERATION-SPEC.md": "也不应原样进入",
                },
            },
            "chapter": {"number": 3, "title": "FastAPI"},
            "module_context": {"title": "Web 开发", "goal": "完成 API"},
            "continuity_ledger": [{"chapter": index} for index in range(8)],
        }
    )

    assert result["effective_char_min"] == 10000
    assert len(result["approved_resources"]) < 12100
    assert "NOTES.md" not in str(result)
    assert [item["chapter"] for item in result["continuity"]] == [4, 5, 6, 7]


def test_planning_context_excludes_resources_unless_the_stage_needs_them():
    request = {
        "title": "测试课程",
        "workspace": {
            "RESOURCES.md": "用户资料" * 10000,
            "COURSE-GENERATION-SPEC.md": "规格",
            "NOTES.md": "备注",
        },
    }

    mission_input = _planning_request(request)
    blueprint_input = _planning_request(request, include_resources=True)

    assert "RESOURCES.md" not in mission_input["workspace"]
    assert "RESOURCES.md" in blueprint_input["workspace"]
    assert len(blueprint_input["workspace"]["RESOURCES.md"]) < 48100


def test_workspace_patch_accepts_core_contract_excerpt_larger_than_legacy_limit():
    patch = WorkspacePatch(
        path="MISSION.md",
        original="甲" * 20000,
        replacement="乙" * 20000,
    )

    assert len(patch.replacement) == 20000


def test_teaching_agent_definitions_are_versioned_and_provider_independent():
    writer = get_agent_definition("writer.agent")

    assert writer.version == "v1"
    assert writer.context_policy_ref == "teaching_skill_packet.v1"
    assert writer.model_policy_ref == "writer.v1"
    assert set(AGENT_DEFINITIONS) == {
        "mission.agent",
        "research.agent",
        "blueprint.agent",
        "writer.agent",
        "reviewer.agent",
        "repair.agent",
        "presenter.agent",
    }


def test_model_transport_contains_no_teaching_prompt_or_quality_rule():
    source = inspect.getsource(DeepSeekModelTransport)

    assert "teach-generator" not in source
    assert "课程蓝图" not in source
    assert "Humanizer" not in source
    assert "RepairTask" not in source
