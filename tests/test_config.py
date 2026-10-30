from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest
from dotenv import dotenv_values

from ffai.config import Settings, save_llm_settings
from ffai.errors import ConfigError


def test_loads_all_values_from_env_mapping() -> None:
    settings = Settings.load(
        {
            "OPENAI_API_KEY": "sk-test",
            "OPENAI_BASE_URL": "https://api.deepseek.com/",
            "OPENAI_MODEL": "deepseek-chat",
        },
        load_env_file=False,
    )
    assert settings.api_key is not None
    assert settings.api_key.get_secret_value() == "sk-test"
    assert settings.base_url == "https://api.deepseek.com"
    assert settings.model == "deepseek-chat"
    assert settings.llm_configured


def test_missing_llm_configuration_is_detected() -> None:
    settings = Settings.load({}, load_env_file=False)
    assert not settings.llm_configured
    with pytest.raises(ConfigError, match="API configuration is required"):
        settings.require_llm()


def test_base_url_must_be_http_or_https() -> None:
    with pytest.raises(ConfigError, match="OPENAI_BASE_URL"):
        Settings.load(
            {
                "OPENAI_API_KEY": "sk-test",
                "OPENAI_MODEL": "gpt-4o-mini",
                "OPENAI_BASE_URL": "file:///tmp/api",
            },
            load_env_file=False,
        )


def test_secret_is_not_in_model_repr() -> None:
    settings = Settings.load(
        {"OPENAI_API_KEY": "sk-super-secret", "OPENAI_MODEL": "model"},
        load_env_file=False,
    )
    assert "sk-super-secret" not in repr(settings)


def test_save_llm_settings_preserves_comments_and_removes_stale_base_url(
    tmp_path: Path,
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "# keep this comment\nOTHER_SETTING=unchanged\nOPENAI_BASE_URL='https://old.example/v1'\n",
        encoding="utf-8",
    )
    settings = Settings.load(
        {
            "OPENAI_API_KEY": "sk-test",
            "OPENAI_MODEL": "deepseek-chat",
        },
        load_env_file=False,
    )

    saved = save_llm_settings(settings, env_path=env_path)

    assert saved == env_path
    content = env_path.read_text(encoding="utf-8")
    assert "# keep this comment" in content
    assert "OTHER_SETTING=unchanged" in content
    assert "OPENAI_BASE_URL" not in content
    values = dotenv_values(env_path)
    assert values["OPENAI_API_KEY"] == "sk-test"
    assert values["OPENAI_MODEL"] == "deepseek-chat"


def test_save_llm_settings_quotes_special_characters_and_uses_owner_only_mode(
    tmp_path: Path,
) -> None:
    env_path = tmp_path / ".env"
    settings = Settings.load(
        {
            "OPENAI_API_KEY": "sk-'quoted\\key",
            "OPENAI_BASE_URL": "https://api.deepseek.com",
            "OPENAI_MODEL": "deepseek-chat",
        },
        load_env_file=False,
    )

    save_llm_settings(settings, env_path=env_path)

    values = dotenv_values(env_path)
    assert values["OPENAI_API_KEY"] == "sk-'quoted\\key"
    assert values["OPENAI_BASE_URL"] == "https://api.deepseek.com"
    if os.name == "posix":
        assert stat.S_IMODE(env_path.stat().st_mode) == 0o600


def test_save_llm_settings_requires_complete_config(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="API configuration is required"):
        save_llm_settings(Settings.load({}, load_env_file=False), env_path=tmp_path / ".env")
    assert not (tmp_path / ".env").exists()


def test_example_placeholder_key_is_treated_as_unconfigured() -> None:
    settings = Settings.load(
        {
            "OPENAI_API_KEY": "sk-your-key-here",
            "OPENAI_MODEL": "gpt-4o-mini",
        },
        load_env_file=False,
    )
    assert not settings.llm_configured
    with pytest.raises(ConfigError, match="API configuration is required"):
        settings.require_llm()
