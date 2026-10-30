"""Environment-backed configuration for the OpenAI-compatible client."""

from __future__ import annotations

import contextlib
import os
import re
import tempfile
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import find_dotenv, load_dotenv
from pydantic import BaseModel, ConfigDict, SecretStr, field_validator

from ffai.errors import ConfigError

API_KEY_ENV = "OPENAI_API_KEY"
BASE_URL_ENV = "OPENAI_BASE_URL"
MODEL_ENV = "OPENAI_MODEL"

_ENV_ASSIGNMENT = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")

# Values shipped in .env.example are placeholders, not configuration.
_PLACEHOLDER_API_KEYS = {
    "sk-your-key-here",
    "sk-your-deepseek-key",
    "your-api-key",
    "your-key-here",
}


class LLMConfig(BaseModel):
    """Validated settings required to make an LLM request."""

    model_config = ConfigDict(frozen=True)

    api_key: SecretStr
    model: str
    base_url: str | None = None


class Settings(BaseModel):
    """Process configuration.

    A complete LLM configuration is required before the interactive REPL
    starts. ``Settings.load`` remains lenient so startup can distinguish a
    missing configuration from invalid values and launch the setup wizard.
    """

    model_config = ConfigDict(frozen=True)

    api_key: SecretStr | None = None
    base_url: str | None = None
    model: str | None = None

    @field_validator("api_key", mode="before")
    @classmethod
    def _clean_api_key(cls, value: object) -> object:
        if isinstance(value, str):
            _reject_env_control_characters(value, API_KEY_ENV)
            value = value.strip()
            if value.lower() in _PLACEHOLDER_API_KEYS or value.lower().startswith("sk-your-"):
                return None
            return SecretStr(value) if value else None
        return value

    @field_validator("base_url", mode="before")
    @classmethod
    def _clean_base_url(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("OPENAI_BASE_URL must be a string")
        _reject_env_control_characters(value, BASE_URL_ENV)
        value = value.strip().rstrip("/")
        if not value:
            return None
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("OPENAI_BASE_URL must be an absolute http(s) URL")
        if parsed.username or parsed.password:
            raise ValueError("OPENAI_BASE_URL must not contain credentials")
        return value

    @field_validator("model", mode="before")
    @classmethod
    def _clean_model(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("OPENAI_MODEL must be a string")
        _reject_env_control_characters(value, MODEL_ENV)
        value = value.strip()
        return value or None

    @classmethod
    def load(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        load_env_file: bool = True,
    ) -> Settings:
        """Load settings from ``.env`` and the process environment.

        An explicit *env* mapping bypasses dotenv loading, which keeps tests
        independent of the developer's environment.
        """

        if env is None:
            if load_env_file:
                dotenv_path = find_dotenv(usecwd=True)
                if dotenv_path:
                    load_dotenv(dotenv_path=Path(dotenv_path), override=False)
            source: Mapping[str, str] = os.environ
        else:
            source = env

        try:
            return cls(
                api_key=source.get(API_KEY_ENV),
                base_url=source.get(BASE_URL_ENV),
                model=source.get(MODEL_ENV),
            )
        except ValueError as exc:
            raise ConfigError(f"Invalid API configuration: {exc}") from exc

    @property
    def llm_configured(self) -> bool:
        return self.api_key is not None and self.model is not None

    def require_llm(self) -> LLMConfig:
        missing = []
        if self.api_key is None:
            missing.append(API_KEY_ENV)
        if self.model is None:
            missing.append(MODEL_ENV)
        if missing:
            raise ConfigError(
                "API configuration is required. Missing "
                + " and ".join(missing)
                + ". Run the setup wizard or set the environment variables."
            )
        return LLMConfig(
            api_key=self.api_key,
            model=self.model,
            base_url=self.base_url,
        )


def env_file_path() -> Path:
    """Return the configuration file written by the REPL setup wizard."""

    return Path.cwd() / ".env"


def save_llm_settings(settings: Settings, *, env_path: Path | None = None) -> Path:
    """Atomically persist LLM settings to an owner-only ``.env`` file.

    Existing unrelated entries and comments are preserved. A missing base URL
    removes any previously configured ``OPENAI_BASE_URL`` entry.
    """

    llm = settings.require_llm()
    target = (env_path or env_file_path()).expanduser()
    if not target.is_absolute():
        target = Path.cwd() / target
    try:
        parent = target.parent.resolve(strict=True)
    except OSError as exc:
        raise ConfigError(f"Configuration directory does not exist: {target.parent}") from exc
    target = parent / target.name

    updates = {
        API_KEY_ENV: llm.api_key.get_secret_value(),
        MODEL_ENV: llm.model,
    }
    removals: set[str] = set()
    if llm.base_url:
        updates[BASE_URL_ENV] = llm.base_url
    else:
        removals.add(BASE_URL_ENV)

    try:
        existing = target.read_text(encoding="utf-8") if target.exists() else ""
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigError(f"Could not read configuration file {target}: {exc}") from exc

    content = _rewrite_env(existing, updates, removals)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=parent,
            prefix=".env.",
            delete=False,
        ) as temp_file:
            temp_file.write(content)
            temp_file.flush()
            os.fsync(temp_file.fileno())
            temp_path = Path(temp_file.name)
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, target)
        temp_path = None
        os.chmod(target, 0o600)
    except OSError as exc:
        raise ConfigError(f"Could not write configuration file {target}: {exc}") from exc
    finally:
        if temp_path is not None:
            # The write error is already being reported; a leftover temp file
            # is owner-only and cannot expose the credentials.
            with contextlib.suppress(OSError):
                temp_path.unlink(missing_ok=True)

    return target


def _reject_env_control_characters(value: str, variable: str) -> None:
    if any(char in value for char in ("\x00", "\n", "\r")):
        raise ValueError(f"{variable} must not contain control characters")


def _rewrite_env(existing: str, updates: dict[str, str], removals: set[str]) -> str:
    lines = existing.splitlines(keepends=True)
    output: list[str] = []
    written: set[str] = set()

    for line in lines:
        match = _ENV_ASSIGNMENT.match(line)
        key = match.group(1) if match else None
        if key in removals:
            continue
        if key in updates:
            if key not in written:
                output.append(f"{key}={_quote_env_value(updates[key])}\n")
                written.add(key)
            continue
        output.append(line)

    if output and not output[-1].endswith(("\n", "\r")):
        output[-1] += "\n"
    for key, value in updates.items():
        if key not in written:
            output.append(f"{key}={_quote_env_value(value)}\n")
    return "".join(output)


def _quote_env_value(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"
