from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

import pytest

from app.config import (
    Settings,
    get_provider_preferences,
    get_settings,
    save_provider_preferences,
)


@pytest.fixture
def preferences_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point `provider_preferences_path` at a temp file.

    The patch is applied to the *class*: `property` is a data descriptor, so a
    class-level replacement is the only way an instance actually sees the temp
    path.  Patching the instance would silently keep writing into the repo's
    real `.course-agent/`.
    """
    path = tmp_path / "provider-settings.json"
    monkeypatch.setattr(Settings, "provider_preferences_path", path)
    return path


def test_settings_paths_derive_from_repo_root():
    settings = Settings(_env_file=None)

    assert settings.repo_root == Path(__file__).resolve().parents[3]
    assert settings.courses_root == settings.repo_root / "courses"
    assert settings.data_root == settings.repo_root / ".course-agent"
    assert settings.data_root.name == ".course-agent"
    assert settings.database_path.parent == settings.data_root
    assert settings.checkpoint_path.parent == settings.data_root
    assert settings.provider_preferences_path == settings.data_root / "provider-settings.json"


def test_settings_defaults_are_safe(monkeypatch: pytest.MonkeyPatch):
    # `_env_file=None` only shields the `.env` *file*; an exported shell variable
    # would still win over the default, so both mechanisms are needed.
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("WORKER_LEASE_SECONDS", raising=False)

    settings = Settings(_env_file=None)

    assert settings.llm_provider == "codex_gateway"
    assert settings.llm_model == "llm-gateway--kimi-k3"
    assert settings.llm_timeout_seconds == 90
    assert settings.worker_lease_seconds == 45


def test_get_settings_returns_a_cached_instance():
    assert get_settings() is get_settings()


def test_provider_preferences_round_trip(preferences_path: Path):
    settings = Settings(_env_file=None)

    saved = save_provider_preferences(
        {
            "provider": "deepseek",
            "model": "deepseek-chat",
            "deepseek_api_key": "test-key",
            "not_allowed": "dropped",
        },
        settings,
    )

    assert "not_allowed" not in saved
    assert preferences_path.exists()
    assert not preferences_path.with_suffix(".tmp").exists()
    assert get_provider_preferences(settings) == saved


def test_provider_preferences_never_erase_key(preferences_path: Path):
    settings = Settings(_env_file=None)
    save_provider_preferences(
        {
            "provider": "deepseek",
            "model": "deepseek-chat",
            "deepseek_api_key": "test-key",
        },
        settings,
    )

    save_provider_preferences(
        {
            "provider": "deepseek",
            "model": "deepseek-chat",
            "deepseek_api_key": "",
        },
        settings,
    )

    stored = json.loads(preferences_path.read_text(encoding="utf-8"))
    assert stored["deepseek_api_key"] == "test-key"
    assert get_provider_preferences(settings)["deepseek_api_key"] == "test-key"


def test_provider_preferences_fall_back_on_corrupt_file(preferences_path: Path):
    settings = Settings(_env_file=None)
    preferences_path.write_text("{ not json", encoding="utf-8")

    result = get_provider_preferences(settings)

    assert result["provider"] == settings.llm_provider
    assert result["model"] == settings.llm_model

    preferences_path.write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")

    result = get_provider_preferences(settings)

    assert result["provider"] == settings.llm_provider
    assert result["model"] == settings.llm_model

    # A file whose bytes are not valid UTF-8 cannot be parsed as JSON either.
    preferences_path.write_bytes(b"\xff\xfe not utf-8")

    result = get_provider_preferences(settings)

    assert result["provider"] == settings.llm_provider
    assert result["model"] == settings.llm_model


def test_provider_preferences_missing_file_returns_defaults(preferences_path: Path):
    settings = Settings(_env_file=None)

    assert not preferences_path.exists()

    result = get_provider_preferences(settings)

    assert result["provider"] == settings.llm_provider
    assert result["model"] == settings.llm_model


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Windows os.chmod only toggles the read-only flag, not POSIX mode bits",
)
def test_provider_preferences_file_is_written_with_restrictive_permissions(
    preferences_path: Path,
):
    settings = Settings(_env_file=None)

    save_provider_preferences(
        {"provider": "deepseek", "model": "deepseek-chat"},
        settings,
    )

    assert stat.S_IMODE(preferences_path.stat().st_mode) == 0o600
