from __future__ import annotations

import pytest

from ffai.providers import (
    CUSTOM_PROVIDER,
    PROVIDER_CHOICES,
    PROVIDERS,
    get_provider,
    identify_provider,
    provider_name_for,
)


def test_provider_ids_are_unique_and_include_required_presets() -> None:
    ids = [provider.id for provider in PROVIDER_CHOICES]
    assert len(ids) == len(set(ids))
    assert {"openai", "openrouter", "deepseek", "glm", "kimi", "qwen", "custom"} <= set(ids)
    assert CUSTOM_PROVIDER in PROVIDER_CHOICES


@pytest.mark.parametrize(
    ("provider_id", "base_url", "model"),
    [
        ("openai", "https://api.openai.com/v1", "gpt-5.4-mini"),
        ("openrouter", "https://openrouter.ai/api/v1", "openai/gpt-5.4-mini"),
        ("deepseek", "https://api.deepseek.com", "deepseek-flash"),
        ("glm", "https://open.bigmodel.cn/api/paas/v4", "glm-5.3"),
        ("kimi", "https://api.moonshot.cn/v1", "kimi-k3.1-pro"),
        (
            "qwen",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "qwen3.8-flash",
        ),
    ],
)
def test_presets_have_expected_endpoint_and_default_model(
    provider_id: str, base_url: str, model: str
) -> None:
    preset = get_provider(provider_id)
    assert preset.base_url == base_url
    assert preset.default_model == model
    assert preset.docs_url


@pytest.mark.parametrize("provider", PROVIDERS)
def test_provider_presets_are_https(provider) -> None:
    assert provider.base_url is not None
    assert provider.base_url.startswith("https://")


def test_identify_provider_normalizes_trailing_slash() -> None:
    assert identify_provider("https://api.deepseek.com/") == get_provider("deepseek")
    assert identify_provider("https://openrouter.ai/api/v1/") == get_provider("openrouter")


def test_missing_base_url_identifies_openai() -> None:
    assert identify_provider(None) == get_provider("openai")
    assert provider_name_for(None) == "OpenAI"


def test_unknown_endpoint_is_custom() -> None:
    assert identify_provider("https://example.test/v1") is None
    assert provider_name_for("https://example.test/v1") == CUSTOM_PROVIDER.name


def test_get_unknown_provider_raises() -> None:
    with pytest.raises(KeyError, match="Unknown provider"):
        get_provider("does-not-exist")
