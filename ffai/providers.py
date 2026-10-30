"""Built-in OpenAI-compatible provider presets.

Endpoint and suggested-model values follow the providers' current API
documentation. Models remain editable because availability varies by account and
region.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProviderPreset:
    id: str
    name: str
    base_url: str | None
    default_model: str | None
    docs_url: str | None = None
    api_key_url: str | None = None
    note: str | None = None
    name_zh: str | None = None
    note_zh: str | None = None


PROVIDERS: tuple[ProviderPreset, ...] = (
    ProviderPreset(
        id="openai",
        name="OpenAI",
        base_url="https://api.openai.com/v1",
        default_model="gpt-5.4-mini",
        docs_url="https://developers.openai.com/api/docs/models/gpt-5.4-mini",
        api_key_url="https://platform.openai.com/api-keys",
    ),
    ProviderPreset(
        id="openrouter",
        name="OpenRouter",
        base_url="https://openrouter.ai/api/v1",
        default_model="openai/gpt-5.4-mini",
        docs_url="https://openrouter.ai/docs/quickstart",
        api_key_url="https://openrouter.ai/keys",
        note="Model IDs are vendor-prefixed, for example openai/gpt-5.4-mini.",
        note_zh="模型 ID 带供应商前缀，例如 openai/gpt-5.4-mini。",
    ),
    ProviderPreset(
        id="deepseek",
        name="DeepSeek",
        base_url="https://api.deepseek.com",
        default_model="deepseek-flash",
        docs_url="https://api-docs.deepseek.com/",
        api_key_url="https://platform.deepseek.com/api_keys",
    ),
    ProviderPreset(
        id="glm",
        name="GLM (Zhipu)",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        default_model="glm-5.3",
        docs_url="https://docs.bigmodel.cn/cn/guide/models/text/glm-5.3",
        api_key_url="https://bigmodel.cn/usercenter/proj-mgmt/apikeys",
        note="Uses Zhipu's OpenAI Chat Completions-compatible endpoint.",
        note_zh="使用智谱的 OpenAI Chat Completions 兼容端点。",
    ),
    ProviderPreset(
        id="kimi",
        name="Kimi (Moonshot)",
        base_url="https://api.moonshot.cn/v1",
        default_model="kimi-k3.1-pro",
        docs_url="https://platform.kimi.com/docs/get-api-key",
        api_key_url="https://platform.kimi.com/console/api-keys",
    ),
    ProviderPreset(
        id="qwen",
        name="Qwen (DashScope)",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        default_model="qwen3.8-flash",
        docs_url="https://www.alibabacloud.com/help/zh/model-studio/base-url",
        api_key_url="https://modelstudio.console.alibabacloud.com/",
        note=(
            "China-region endpoint. Use your region's compatible-mode URL and a "
            "matching regional API key."
        ),
        note_zh="此为中国区端点。其他区域请使用对应区域的 compatible-mode URL 和 API Key。",
    ),
)

CUSTOM_PROVIDER = ProviderPreset(
    id="custom",
    name="Custom (OpenAI-compatible)",
    base_url=None,
    default_model=None,
    note="Any OpenAI-compatible endpoint that accepts a bearer API key.",
    name_zh="自定义（OpenAI 兼容）",
    note_zh="支持任何接受 Bearer API Key 的 OpenAI 兼容端点。",
)

PROVIDER_CHOICES: tuple[ProviderPreset, ...] = (*PROVIDERS, CUSTOM_PROVIDER)

_BY_ID = {provider.id: provider for provider in PROVIDER_CHOICES}


def get_provider(provider_id: str) -> ProviderPreset:
    try:
        return _BY_ID[provider_id]
    except KeyError as exc:
        raise KeyError(f"Unknown provider preset: {provider_id}") from exc


def identify_provider(base_url: str | None) -> ProviderPreset | None:
    """Return the preset matching *base_url*, or ``None`` for a custom endpoint."""

    if base_url is None:
        return get_provider("openai")
    normalized = base_url.rstrip("/")
    for provider in PROVIDERS:
        if provider.base_url and provider.base_url.rstrip("/") == normalized:
            return provider
    return None


def provider_name_for(base_url: str | None) -> str:
    provider = identify_provider(base_url)
    return provider.name if provider is not None else CUSTOM_PROVIDER.name
