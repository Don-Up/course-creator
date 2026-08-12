from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.config import get_provider_preferences, get_settings, save_provider_preferences
from app.provider import codex_gateway_available, list_codex_gateway_models
from app.schemas import ProviderPreferencesUpdate
from app.workflow.definitions import WORKFLOW_STEPS
from app.workflow.snapshot import workflow_snapshot


router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health():
    settings = get_settings()
    preferences = get_provider_preferences(settings)
    provider = str(preferences.get("provider") or settings.llm_provider)
    model = str(preferences.get("model") or settings.llm_model)
    return {
        "status": "ok", "provider": provider, "model": model,
        "provider_configured": codex_gateway_available(settings) if provider == "codex_gateway" else bool(preferences.get("deepseek_api_key")),
        "deepseek_configured": bool(preferences.get("deepseek_api_key")),
        "codex_gateway_available": codex_gateway_available(settings),
        "codex_gateway_models": list_codex_gateway_models(settings),
        "reasoning_effort": settings.codex_gateway_reasoning_effort,
        "service_tier": settings.codex_gateway_service_tier,
        "storage": "sqlite", "mode": "local-guided",
    }


@router.put("/settings/provider")
def update_provider_preferences(payload: ProviderPreferencesUpdate):
    settings = get_settings()
    if payload.provider == "codex_gateway" and not codex_gateway_available(settings):
        raise HTTPException(400, "当前 Codex Gateway 不可用，请先检查 ~/.codex/config.toml")
    existing = get_provider_preferences(settings)
    if payload.provider == "deepseek" and not (payload.deepseek_api_key.strip() or str(existing.get("deepseek_api_key") or "").strip()):
        raise HTTPException(400, "切换到 DeepSeek 前请填写 API Key")
    saved = save_provider_preferences(payload.model_dump(), settings)
    return {"provider": saved["provider"], "model": saved["model"], "provider_configured": True}


@router.get("/workflow")
def workflow():
    # Keep the legacy keys while offering the actual executable topology to
    # clients that can render the two-level workbench map.
    return {"mode": "guided", "steps": WORKFLOW_STEPS, **workflow_snapshot()}
