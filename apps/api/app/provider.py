from __future__ import annotations

import json
import queue
import re
import threading
from typing import Any, TypeVar

import httpx
from langchain_deepseek import ChatDeepSeek
from pydantic import BaseModel

from app.config import Settings, get_provider_preferences, get_settings
from app.providers.gateway import (
    CodexGatewayResponsesModel, GatewayMalformedResponseError, GatewayNoFinalTextError, _codex_gateway_service_tier,
    _read_codex_gateway_config, _response_text, _with_reasoning_effort, codex_gateway_available,
    codex_gateway_model, list_codex_gateway_models,
)
from app.providers.protocols import ModelTransport
from app.observability.context import set_invocation_metrics
from app.observability.contracts import InvocationMetrics

OutputT = TypeVar("OutputT", bound=BaseModel)


class DeepSeekModelTransport:
    name = "deepseek"

    def __init__(self, settings: Settings, model_name: str | None = None) -> None:
        preferences = get_provider_preferences(settings)
        api_key = str(preferences.get("deepseek_api_key") or settings.deepseek_api_key)
        if not api_key:
            raise RuntimeError("尚未配置 DEEPSEEK_API_KEY")
        self.settings = settings
        kwargs = {
            "model": model_name or settings.llm_model,
            "api_key": api_key,
            "timeout": settings.llm_timeout_seconds,
            "max_retries": 0,
            "temperature": 0.2,
            "max_tokens": settings.llm_max_output_tokens,
        }
        api_base = str(preferences.get("llm_base_url") or settings.llm_base_url)
        if api_base:
            kwargs["api_base"] = api_base
        self.model = ChatDeepSeek(**kwargs)

    def _invoke_with_hard_timeout(self, operation: str, callback, *, timeout_seconds: int | None = None):
        result_queue: queue.Queue[tuple[bool, object]] = queue.Queue(maxsize=1)
        def run() -> None:
            try:
                result_queue.put((True, callback()))
            except BaseException as exc:
                result_queue.put((False, exc))
        if timeout_seconds is None:
            timeout_seconds = getattr(
                getattr(self, "settings", None),
                "llm_call_hard_timeout_seconds",
                get_settings().llm_call_hard_timeout_seconds,
            )
        worker = threading.Thread(target=run, daemon=True, name=f"course-agent-{operation}")
        worker.start()
        worker.join(timeout_seconds)
        if worker.is_alive():
            raise TimeoutError(f"模型调用“{operation}”超过 {timeout_seconds} 秒未返回；已停止等待并保留 LangGraph 检查点，可稍后继续生成。")
        succeeded, value = result_queue.get_nowait()
        if not succeeded:
            raise value  # type: ignore[misc]
        return value

    def invoke_text(
        self,
        operation: str,
        prompt: str,
        *,
        hard_timeout_seconds: int | None = None,
        max_output_tokens: int | None = None,
        reasoning_effort: str | None = None,
        transport_timeout_seconds: int | None = None,
    ) -> str:
        if transport_timeout_seconds is None and hard_timeout_seconds is not None:
            transport_timeout_seconds = hard_timeout_seconds
        model = self.model
        bind = getattr(model, "bind", None)
        if max_output_tokens is not None and callable(bind):
            model = bind(max_tokens=max_output_tokens)
        model = _with_reasoning_effort(model, reasoning_effort)
        if transport_timeout_seconds is not None and isinstance(model, CodexGatewayResponsesModel):
            model = model.bind(timeout_seconds=transport_timeout_seconds)
        response = self._invoke_with_hard_timeout(
            operation,
            lambda: model.invoke(prompt),
            timeout_seconds=hard_timeout_seconds,
        )
        set_invocation_metrics(self._metrics(response))
        return str(response.content or "")

    def invoke_structured(self, schema: type[OutputT], prompt: str, *, hard_timeout_seconds: int | None = None, max_output_tokens: int | None = None, reasoning_effort: str | None = None, transport_timeout_seconds: int | None = None) -> OutputT:
        if transport_timeout_seconds is None and hard_timeout_seconds is not None:
            transport_timeout_seconds = hard_timeout_seconds
        schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False, indent=2)
        structured_prompt = prompt + "\n\n请只返回一个符合下列 JSON Schema 的 JSON 对象，不要使用 Markdown 代码围栏，也不要添加 JSON 之外的解释：\n" + schema_json
        model = self.model
        bind = getattr(model, "bind", None)
        if max_output_tokens is not None and callable(bind):
            model = bind(max_tokens=max_output_tokens)
        model = _with_reasoning_effort(model, reasoning_effort)
        if transport_timeout_seconds is not None and isinstance(model, CodexGatewayResponsesModel):
            model = model.bind(timeout_seconds=transport_timeout_seconds)
        structured_output = getattr(model, "with_structured_output", None)
        try:
            if not callable(structured_output):
                raise ValueError("当前模型不支持 json mode；使用 JSON 文本回退")
            result = self._invoke_with_hard_timeout(schema.__name__, lambda: structured_output(schema, method="json_mode").invoke(structured_prompt), timeout_seconds=hard_timeout_seconds)
            set_invocation_metrics(self._metrics(result))
            return result
        except Exception as exc:
            signals = ("response_format", "json mode", "json_object", "invalid json", "validation error", "parsing", "不支持 json mode")
            if not any(signal in str(exc).lower() for signal in signals):
                raise
            last_error = ""
            for retry_index in range(self.settings.llm_structured_output_retry_count + 1):
                retry_note = "\n\n上一轮没有返回可解析的 JSON。请立即只返回完整 JSON 对象，字段必须齐全，不能为空，不要解释。" if retry_index else ""
                attempt_model = model.bind(reasoning_effort="low") if retry_index >= 2 and isinstance(model, CodexGatewayResponsesModel) else model
                try:
                    response = self._invoke_with_hard_timeout(f"{schema.__name__}-fallback", lambda: attempt_model.invoke(structured_prompt + retry_note), timeout_seconds=hard_timeout_seconds)
                except Exception as invoke_exc:
                    if "未返回可用文本内容" not in str(invoke_exc) and "incomplete" not in str(invoke_exc).lower():
                        raise
                    last_error = str(invoke_exc)[:500]
                    continue
                content = str(response.content or "").strip()
                fenced = re.fullmatch(r"```(?:json)?\s*([\s\S]*?)\s*```", content, flags=re.IGNORECASE)
                if fenced:
                    content = fenced.group(1).strip()
                if not content:
                    last_error = "模型返回空内容"
                    continue
                try:
                    set_invocation_metrics(self._metrics(response))
                    return schema.model_validate_json(content)
                except Exception as parse_exc:
                    last_error = str(parse_exc)[:500]
            raise RuntimeError(f"模型调用“{schema.__name__}”连续返回空或无效 JSON；已重试 {self.settings.llm_structured_output_retry_count} 次。" + (f"最后错误：{last_error}" if last_error else ""))

    def _metrics(self, response: Any) -> InvocationMetrics:
        metadata = getattr(response, "usage_metadata", None) or getattr(response, "response_metadata", None) or {}
        usage = metadata.get("token_usage", metadata.get("usage", metadata)) if isinstance(metadata, dict) else {}
        input_tokens = usage.get("input_tokens", usage.get("prompt_tokens")) if isinstance(usage, dict) else None
        output_tokens = usage.get("output_tokens", usage.get("completion_tokens")) if isinstance(usage, dict) else None
        total_tokens = usage.get("total_tokens") if isinstance(usage, dict) else None
        configured_model = getattr(getattr(self, "settings", None), "llm_model", "unknown")
        return InvocationMetrics(provider=self.name, model=str(getattr(getattr(self, "model", None), "model", None) or getattr(getattr(self, "model", None), "model_name", None) or configured_model), input_tokens=int(input_tokens) if isinstance(input_tokens, (int, float)) else None, output_tokens=int(output_tokens) if isinstance(output_tokens, (int, float)) else None, total_tokens=int(total_tokens) if isinstance(total_tokens, (int, float)) else None, response_status=str(metadata.get("response_status")) if isinstance(metadata, dict) and metadata.get("response_status") else None)


class CodexGatewayModelTransport(DeepSeekModelTransport):
    name = "codex_gateway"

    def __init__(self, settings: Settings, model_name: str | None = None) -> None:
        self.settings = settings
        gateway = _read_codex_gateway_config(settings)
        selected_model = model_name or settings.llm_model or gateway["model"]
        self.model = CodexGatewayResponsesModel(
            base_url=gateway["base_url"], token=gateway["token"], model=selected_model,
            timeout_seconds=settings.llm_timeout_seconds, max_output_tokens=settings.llm_max_output_tokens,
            reasoning_effort=settings.codex_gateway_reasoning_effort,
            service_tier=_codex_gateway_service_tier(settings, selected_model),
        )


def create_model_transport(
    name: str | None = None,
    model_name: str | None = None,
) -> ModelTransport:
    settings = get_settings()
    preferences = get_provider_preferences(settings)
    provider = (name or preferences.get("provider") or settings.llm_provider).lower()
    if provider == "deepseek":
        return DeepSeekModelTransport(settings, model_name=model_name)
    if provider == "codex_gateway":
        return CodexGatewayModelTransport(settings, model_name=model_name)
    raise ValueError(f"暂不支持 Provider: {provider}")


def create_provider(name: str | None = None, model_name: str | None = None):
    """Deprecated compatibility facade returning a teaching Agent runtime."""

    from app.agents.runtime import create_course_agent

    return create_course_agent(name, model_name)


# Older integrations imported these classes directly. Keep the names during
# the migration; new code should use create_model_transport/create_course_agent.
DeepSeekProvider = DeepSeekModelTransport
CodexGatewayProvider = CodexGatewayModelTransport
