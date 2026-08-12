from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "apps/api/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Default to the local Codex Gateway. It reads the user's existing Codex
    # credentials at runtime, so this project never copies a Gateway token.
    llm_provider: str = "codex_gateway"
    llm_model: str = "llm-gateway--kimi-k3"
    deepseek_api_key: str = ""
    llm_base_url: str = ""
    codex_gateway_config_path: str = "~/.codex/config.toml"
    codex_gateway_reasoning_effort: str = "medium"
    codex_gateway_service_tier: str = "standard"
    llm_timeout_seconds: int = 90
    # The provider's HTTP timeout does not reliably bound every streaming or
    # retry path. This is a final local safeguard for one model operation.
    llm_call_hard_timeout_seconds: int = 210
    # Whole-chapter operations must read and return a long Markdown document.
    # Their deadline is intentionally longer than lightweight planning calls.
    llm_long_content_hard_timeout_seconds: int = 600
    llm_humanizer_hard_timeout_seconds: int = 720
    # Semantic review needs to read a chapter, but its verdict is compact. A
    # purpose-specific deadline prevents a stalled review from holding a whole
    # batch hostage indefinitely.
    llm_semantic_review_hard_timeout_seconds: int = 360
    llm_continuity_hard_timeout_seconds: int = 180
    # Gateway reasoning and final text share output capacity.  Use one safe
    # baseline across every Agent; individual prompt schemas still constrain
    # the returned shape rather than relying on a tiny token ceiling.
    llm_max_output_tokens: int = 32768
    # A chapter may require 10,000+ Chinese effective characters.  Gateway
    # reasoning and final text share this budget, so long-form writing needs
    # a larger ceiling than planning and structured review calls.
    llm_chapter_max_output_tokens: int = 32768
    llm_mission_max_output_tokens: int = 32768
    llm_blueprint_max_output_tokens: int = 32768
    llm_research_max_output_tokens: int = 32768
    llm_workspace_audit_max_output_tokens: int = 32768
    llm_presentation_max_output_tokens: int = 32768
    llm_semantic_review_max_output_tokens: int = 32768
    llm_continuity_max_output_tokens: int = 32768
    # A compatible gateway can occasionally acknowledge a JSON-mode request
    # with an empty body. Retry the compact structured response before a
    # chapter is deferred; long-form work is never repeated here.
    llm_structured_output_retry_count: int = 2
    chapter_quality_max_attempts: int = 2
    # A repair cycle may discover follow-up issues during revalidation. Limit
    # those re-entry sweeps separately from per-RepairTask retry attempts.
    quality_cycle_max_discovery_sweeps: int = 2
    # Retries before a chapter body exists are transport recovery attempts,
    # not quality-repair rounds.
    chapter_writer_max_attempts: int = 3
    course_agent_max_concurrent_runs: int = 1
    worker_poll_interval_seconds: float = 1.0
    worker_lease_seconds: int = 45

    @property
    def repo_root(self) -> Path:
        return Path(__file__).resolve().parents[3]

    @property
    def courses_root(self) -> Path:
        return self.repo_root / "courses"

    @property
    def data_root(self) -> Path:
        return self.repo_root / ".course-agent"

    @property
    def database_path(self) -> Path:
        return self.data_root / "agent.db"

    @property
    def checkpoint_path(self) -> Path:
        return self.data_root / "checkpoints.db"

    @property
    def provider_preferences_path(self) -> Path:
        return self.data_root / "provider-settings.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def get_provider_preferences(settings: Settings | None = None) -> dict[str, Any]:
    """Read local-only provider preferences without exposing secrets to runs.

    Environment variables remain a compatible fallback. The preference file is
    deliberately outside course workspaces and is never included in artifacts.
    """
    settings = settings or get_settings()
    defaults: dict[str, Any] = {
        "provider": settings.llm_provider,
        "model": settings.llm_model,
        "deepseek_api_key": settings.deepseek_api_key,
        "llm_base_url": settings.llm_base_url,
    }
    path = settings.provider_preferences_path
    if not path.exists():
        return defaults
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return defaults
    if not isinstance(stored, dict):
        return defaults
    return {**defaults, **{key: value for key, value in stored.items() if value is not None}}


def save_provider_preferences(payload: dict[str, Any], settings: Settings | None = None) -> dict[str, Any]:
    """Persist API credentials locally with restrictive file permissions."""
    settings = settings or get_settings()
    current = get_provider_preferences(settings)
    allowed = {"provider", "model", "deepseek_api_key", "llm_base_url"}
    updates = {key: value for key, value in payload.items() if key in allowed}
    # The API intentionally never returns a stored secret. A blank field in
    # the UI therefore means “keep the current key”, not “erase it”.
    if not str(updates.get("deepseek_api_key") or "").strip():
        updates.pop("deepseek_api_key", None)
    next_value = {**current, **updates}
    path = settings.provider_preferences_path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(next_value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)
    return next_value
