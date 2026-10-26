"""Application configuration.

`Settings` is the single source of truth for every path and LLM knob used by
the project: later phases derive their directories from the path properties
defined here, so the field names and defaults below are a contract.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict


PROVIDER_PREFERENCE_FILENAME = "provider-settings.json"
PROVIDER_PREFERENCE_KEYS = ("provider", "model", "deepseek_api_key", "llm_base_url")


class Settings(BaseSettings):
    """Runtime configuration, overridable through the environment or `.env`."""

    model_config = SettingsConfigDict(env_file=(".env", "apps/api/.env"), extra="ignore")

    # --- provider / model -------------------------------------------------
    llm_provider: str = "codex_gateway"
    llm_model: str = "llm-gateway--kimi-k3"
    deepseek_api_key: str = ""
    llm_base_url: str = ""
    codex_gateway_config_path: str = "~/.codex/config.toml"
    codex_gateway_reasoning_effort: str = "medium"
    codex_gateway_service_tier: str = "standard"

    # --- timeouts ---------------------------------------------------------
    llm_timeout_seconds: int = 90
    llm_call_hard_timeout_seconds: int = 210
    llm_long_content_hard_timeout_seconds: int = 600
    llm_humanizer_hard_timeout_seconds: int = 720
    llm_semantic_review_hard_timeout_seconds: int = 360
    llm_continuity_hard_timeout_seconds: int = 180

    # --- output tokens ----------------------------------------------------
    llm_max_output_tokens: int = 32768
    llm_chapter_max_output_tokens: int = 32768
    llm_mission_max_output_tokens: int = 32768
    llm_blueprint_max_output_tokens: int = 32768
    llm_research_max_output_tokens: int = 32768
    llm_workspace_audit_max_output_tokens: int = 32768
    llm_presentation_max_output_tokens: int = 32768
    llm_semantic_review_max_output_tokens: int = 32768
    llm_continuity_max_output_tokens: int = 32768

    # --- retries / attempts -----------------------------------------------
    llm_structured_output_retry_count: int = 2
    chapter_quality_max_attempts: int = 2
    quality_cycle_max_discovery_sweeps: int = 2
    chapter_writer_max_attempts: int = 3

    # --- runtime ----------------------------------------------------------
    course_agent_max_concurrent_runs: int = 1
    worker_poll_interval_seconds: float = 1.0
    worker_lease_seconds: int = 45

    # --- paths ------------------------------------------------------------
    # These stay properties (not fields) so no `.env` variable can move them
    # and every later phase derives its directories from the same root.
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
        return self.data_root / PROVIDER_PREFERENCE_FILENAME


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()


def _default_preferences(settings: Settings) -> dict[str, Any]:
    return {
        "provider": settings.llm_provider,
        "model": settings.llm_model,
        "deepseek_api_key": settings.deepseek_api_key,
        "llm_base_url": settings.llm_base_url,
    }


def _read_stored_preferences(path: Path) -> dict[str, Any]:
    """Read the stored preferences; an unreadable or malformed file yields `{}`."""
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        # A file that cannot even be decoded is not parseable JSON either.
        return {}
    try:
        stored = json.loads(raw)
    except ValueError:
        return {}
    if not isinstance(stored, dict):
        return {}
    return stored


def get_provider_preferences(settings: Settings | None = None) -> dict[str, Any]:
    """Return the effective provider preferences, falling back to the defaults."""
    if settings is None:
        settings = get_settings()
    defaults = _default_preferences(settings)
    path = settings.provider_preferences_path
    if not path.exists():
        return defaults
    stored = _read_stored_preferences(path)
    return {**defaults, **{key: value for key, value in stored.items() if value is not None}}


def save_provider_preferences(
    payload: dict[str, Any],
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Persist the provider preferences locally and return the merged result.

    The file holds the DeepSeek API key, so it stays local (`.course-agent/` is
    git-ignored) and is written through a temporary file that is then moved
    into place atomically.  `os.chmod(0o600)` restricts the file to its owner
    on POSIX; on Windows it can only clear the read-only flag, so the
    directory ACL still governs who may read it.
    """
    if settings is None:
        settings = get_settings()
    path = settings.provider_preferences_path
    stored = _read_stored_preferences(path)
    merged: dict[str, Any] = {
        **_default_preferences(settings),
        **{
            key: value
            for key, value in stored.items()
            if key in PROVIDER_PREFERENCE_KEYS and value is not None
        },
    }
    for key, value in payload.items():
        if key not in PROVIDER_PREFERENCE_KEYS:
            continue
        if value is None:
            continue
        if key == "deepseek_api_key" and not str(value).strip():
            # An empty input means "keep the stored key", never "erase it".
            continue
        merged[key] = value

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    # Owner-only on POSIX; on Windows `os.chmod` can only clear the read-only
    # flag, so the directory ACL still decides who can read the key.
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)
    return merged
