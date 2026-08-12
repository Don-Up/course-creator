from __future__ import annotations

import json
import tomllib
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx

from app.config import Settings, get_settings

def _read_codex_gateway_config(settings: Settings) -> dict[str, str]:
    """Read only the transport details from the user's existing Codex setup."""
    path = Path(settings.codex_gateway_config_path).expanduser()
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"未找到 Codex 配置文件：{path}") from exc
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise RuntimeError("无法读取 Codex Gateway 配置") from exc
    provider = raw.get("model_providers", {}).get("custom", {})
    if not isinstance(provider, dict):
        provider = {}
    base_url = str(provider.get("base_url") or "").rstrip("/")
    token = str(provider.get("experimental_bearer_token") or "")
    if not base_url or not token:
        raise RuntimeError("当前 Codex 配置未提供可用的 LLM Gateway 凭据")
    return {
        "base_url": base_url,
        "token": token,
        "model": str(raw.get("model") or settings.llm_model),
    }


def codex_gateway_available(settings: Settings | None = None) -> bool:
    try:
        _read_codex_gateway_config(settings or get_settings())
    except RuntimeError:
        return False
    return True


def codex_gateway_model(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    try:
        return _read_codex_gateway_config(settings)["model"]
    except RuntimeError:
        return settings.llm_model


def list_codex_gateway_models(settings: Settings | None = None) -> list[str]:
    """Offer the current Codex model plus locally cached Gateway models."""
    settings = settings or get_settings()
    models = [codex_gateway_model(settings)]
    catalog_path = Path(settings.codex_gateway_config_path).expanduser().with_name(
        "ais-switch-model-catalog.json"
    )
    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return models
    entries = catalog if isinstance(catalog, list) else catalog.get("models", []) if isinstance(catalog, dict) else []
    for entry in entries:
        if isinstance(entry, dict):
            slug = str(entry.get("slug") or entry.get("id") or "")
            if slug.startswith("llm-gateway--") and slug not in models:
                models.append(slug)
    return models


def _codex_gateway_service_tier(settings: Settings, model: str) -> str | None:
    """Return a requested tier only when the local Gateway catalog supports it.

    The AIS Switch catalog is the capability source for `llm-gateway--*`
    models. Sending an unsupported tier makes the proxy reject the complete
    Responses request before it reaches the model.
    """
    requested = settings.codex_gateway_service_tier.strip()
    if not requested:
        return None
    catalog_path = Path(settings.codex_gateway_config_path).expanduser().with_name(
        "ais-switch-model-catalog.json"
    )
    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        # Preserve the explicit user setting when the local capability catalog
        # is unavailable; the request-level fallback below remains in place.
        return requested
    entries = catalog if isinstance(catalog, list) else catalog.get("models", []) if isinstance(catalog, dict) else []
    for entry in entries:
        if isinstance(entry, dict) and str(entry.get("slug") or entry.get("id") or "") == model:
            tiers = entry.get("service_tiers")
            return requested if isinstance(tiers, list) and requested in tiers else None
    return requested


def _response_text(payload: dict[str, Any]) -> str:
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct
    parts: list[str] = []
    for item in payload.get("output", []) if isinstance(payload.get("output"), list) else []:
        # Gateway Responses include a separate reasoning item before the final
        # assistant message. Reasoning text must never be prepended to a JSON
        # structured result, otherwise Pydantic sees invalid JSON.
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for content in item.get("content", []) if isinstance(item.get("content"), list) else []:
            if not isinstance(content, dict):
                continue
            if content.get("type") not in {"output_text", "text"}:
                continue
            text = content.get("text")
            if isinstance(text, dict):
                text = text.get("value")
            if isinstance(text, str):
                parts.append(text)
    return "".join(parts).strip()


def _gateway_response_diagnostics(payload: dict[str, Any]) -> dict[str, Any]:
    """Project a Responses payload into safe, user-visible call evidence."""
    blocks: list[dict[str, Any]] = []
    output = payload.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            entries = content if isinstance(content, list) else []
            text_length = 0
            content_types: list[str] = []
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                content_types.append(str(entry.get("type") or "unknown"))
                value = entry.get("text")
                if isinstance(value, dict):
                    value = value.get("value")
                if isinstance(value, str):
                    text_length += len(value)
            blocks.append(
                {
                    "type": str(item.get("type") or "unknown"),
                    "status": str(item.get("status") or "unknown"),
                    "content_types": content_types,
                    "text_length": text_length,
                }
            )
    incomplete = payload.get("incomplete_details")
    usage = payload.get("usage")
    safe_usage = (
        {
            key: value
            for key, value in usage.items()
            if key in {"input_tokens", "output_tokens", "total_tokens"}
            and isinstance(value, (int, float))
        }
        if isinstance(usage, dict)
        else {}
    )
    return {
        "response_status": str(payload.get("status") or "unknown"),
        "incomplete_reason": str(incomplete.get("reason") or "unknown")
        if isinstance(incomplete, dict)
        else None,
        "output_blocks": blocks,
        "usage": safe_usage,
    }


class GatewayNoFinalTextError(RuntimeError):
    """A successful HTTP response without a consumable final assistant message."""

    def __init__(self, diagnostics: dict[str, Any]) -> None:
        self.diagnostics = diagnostics
        blocks = ", ".join(
            f"{block['type']}:{block['status']}"
            for block in diagnostics.get("output_blocks", [])
            if isinstance(block, dict)
        )
        super().__init__(
            "LLM Gateway 未返回可用文本内容"
            f"（response_status={diagnostics.get('response_status')}；"
            f"incomplete_reason={diagnostics.get('incomplete_reason') or '无'}；"
            f"output_blocks={blocks or '无'}）"
        )


class GatewayMalformedResponseError(GatewayNoFinalTextError):
    """A successful HTTP response that is not a Responses JSON payload."""


class CodexGatewayResponsesModel:
    """Small LangChain-compatible adapter for Codex's local Responses Gateway."""

    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        model: str,
        timeout_seconds: int,
        max_output_tokens: int,
        reasoning_effort: str,
        service_tier: str | None,
    ) -> None:
        self.base_url = base_url
        self.token = token
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max_output_tokens
        self.reasoning_effort = reasoning_effort
        self.service_tier = service_tier

    def bind(
        self,
        *,
        max_tokens: int | None = None,
        reasoning_effort: str | None = None,
        timeout_seconds: int | None = None,
        **_: object,
    ) -> "CodexGatewayResponsesModel":
        return CodexGatewayResponsesModel(
            base_url=self.base_url,
            token=self.token,
            model=self.model,
            timeout_seconds=timeout_seconds or self.timeout_seconds,
            max_output_tokens=max_tokens or self.max_output_tokens,
            reasoning_effort=reasoning_effort or self.reasoning_effort,
            service_tier=self.service_tier,
        )

    def invoke(self, prompt: str) -> SimpleNamespace:
        body: dict[str, Any] = {
            "model": self.model,
            "input": prompt,
            "reasoning": {"effort": self.reasoning_effort},
            "max_output_tokens": self.max_output_tokens,
        }
        if self.service_tier:
            body["service_tier"] = self.service_tier
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        with httpx.Client(timeout=self.timeout_seconds) as client:
            for malformed_attempt in range(2):
                response = client.post(f"{self.base_url}/responses", headers=headers, json=body)
                # Some compatible gateways use the Codex term `default` instead
                # of `standard`. Preserve the requested standard setting first,
                # then retry once without it only for an unsupported-parameter 4xx.
                if response.status_code in {400, 422} and (
                    "service_tier" in response.text or "standard" in response.text
                ):
                    body.pop("service_tier", None)
                    response = client.post(f"{self.base_url}/responses", headers=headers, json=body)
                if response.is_error:
                    detail = response.text[:700].replace(self.token, "[redacted]")
                    raise RuntimeError(f"LLM Gateway 请求失败（HTTP {response.status_code}）：{detail}")
                try:
                    payload = response.json()
                    break
                except ValueError:
                    if malformed_attempt == 0:
                        continue
                    excerpt = response.text[:240].replace(self.token, "[redacted]")
                    raise GatewayMalformedResponseError(
                        {
                            "response_status": f"http_{response.status_code}_non_json",
                            "incomplete_reason": "invalid_json_payload",
                            "content_type": str(response.headers.get("content-type") or "unknown"),
                            "body_excerpt": excerpt,
                            "output_blocks": [],
                            "usage": {},
                        }
                    ) from None
        content = _response_text(payload) if isinstance(payload, dict) else ""
        if not content:
            diagnostics = _gateway_response_diagnostics(payload) if isinstance(payload, dict) else {
                "response_status": "invalid_payload",
                "incomplete_reason": None,
                "output_blocks": [],
                "usage": {},
            }
            # The caller records this safe usage even though the invocation
            # fails to yield consumable final text.
            from app.observability.context import set_invocation_metrics
            from app.observability.contracts import InvocationMetrics
            usage = diagnostics.get("usage") or {}
            set_invocation_metrics(InvocationMetrics(provider="codex_gateway", model=self.model, input_tokens=usage.get("input_tokens"), output_tokens=usage.get("output_tokens"), total_tokens=usage.get("total_tokens"), response_status=str(diagnostics.get("response_status") or "unknown")))
            raise GatewayNoFinalTextError(diagnostics)
        usage = payload.get("usage") if isinstance(payload, dict) else {}
        return SimpleNamespace(content=content, response_metadata={"usage": usage if isinstance(usage, dict) else {}, "response_status": str(payload.get("status") or "unknown")})


def _with_reasoning_effort(model: Any, effort: str | None) -> Any:
    """Override reasoning only for the Responses adapter that supports it."""
    if effort and isinstance(model, CodexGatewayResponsesModel):
        return model.bind(reasoning_effort=effort)
    return model
