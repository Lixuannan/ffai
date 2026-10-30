"""OpenAI-compatible LLM client and strict decision parsing."""

from __future__ import annotations

import json
from typing import Any

from openai import (
    APIConnectionError,
    APIStatusError,
    AuthenticationError,
    BadRequestError,
    OpenAI,
    OpenAIError,
)
from pydantic import ValidationError

from ffai.config import LLMConfig
from ffai.errors import LLMError
from ffai.models import LLMDecision
from ffai.prompt import SYSTEM_PROMPT, build_user_prompt


def extract_json_object(text: str) -> str:
    """Extract the first balanced JSON object from model output.

    Models occasionally wrap JSON in code fences or a short preface even when
    instructed not to. Braces inside JSON strings are ignored.
    """

    start = text.find("{")
    if start < 0:
        raise LLMError("The model did not return a JSON object")

    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    raise LLMError("The model returned an incomplete JSON object")


def parse_decision(text: str) -> LLMDecision:
    raw = extract_json_object(text)
    try:
        payload: Any = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LLMError(f"The model returned invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise LLMError("The model response must be a JSON object")
    try:
        return LLMDecision.model_validate(payload)
    except ValidationError as exc:
        errors = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        )
        raise LLMError(f"The model returned an invalid task decision: {errors}") from exc


class LLMClient:
    """Thin wrapper around an OpenAI-compatible chat-completions endpoint."""

    def __init__(self, config: LLMConfig, *, client: Any | None = None) -> None:
        self._config = config
        if client is None:
            try:
                client = OpenAI(
                    api_key=config.api_key.get_secret_value(),
                    base_url=config.base_url,
                    timeout=60.0,
                    max_retries=2,
                )
            except OpenAIError as exc:
                raise LLMError(f"Could not initialize the API client: {exc}") from exc
        self._client = client

    def analyze(self, state: dict[str, Any], request: str) -> LLMDecision:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(state, request)},
        ]
        json_mode = True
        try:
            raw = self._complete(messages, json_mode=True, allow_bad_request=True)
        except BadRequestError:
            # Some OpenAI-compatible servers do not implement JSON mode. The
            # prompt still demands JSON, and parse_decision validates it, so a
            # single fallback is safe.
            json_mode = False
            raw = self._complete(messages, json_mode=False)

        try:
            return parse_decision(raw)
        except LLMError as first_error:
            repair_messages = [
                *messages,
                {"role": "assistant", "content": raw[:8_000]},
                {
                    "role": "user",
                    "content": (
                        "Your previous response failed validation: "
                        f"{first_error}. Return exactly one corrected JSON object "
                        "matching the contract. Do not add commentary or markdown."
                    ),
                },
            ]
            repaired = self._complete(repair_messages, json_mode=json_mode)
            try:
                return parse_decision(repaired)
            except LLMError as second_error:
                raise LLMError(
                    f"The model response could not be validated after one repair attempt: "
                    f"{second_error}"
                ) from second_error

    def _complete(
        self,
        messages: list[dict[str, str]],
        *,
        json_mode: bool,
        allow_bad_request: bool = False,
    ) -> str:
        kwargs: dict[str, Any] = {
            "model": self._config.model,
            "messages": messages,
            "temperature": 0.1,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            response = self._client.chat.completions.create(**kwargs)
        except AuthenticationError as exc:
            raise LLMError(
                "API authentication failed. Check OPENAI_API_KEY and OPENAI_BASE_URL."
            ) from exc
        except BadRequestError as exc:
            if allow_bad_request:
                raise
            raise LLMError(
                "The API rejected the request (HTTP 400). Check OPENAI_MODEL and the endpoint."
            ) from exc
        except APIConnectionError as exc:
            raise LLMError(
                "Could not reach the API endpoint. Check OPENAI_BASE_URL and your network."
            ) from exc
        except APIStatusError as exc:
            raise LLMError(
                f"The API returned HTTP {exc.status_code}: {_short_api_message(exc)}"
            ) from exc
        except OpenAIError as exc:
            raise LLMError(f"The API request failed: {exc}") from exc

        try:
            content = response.choices[0].message.content
        except (AttributeError, IndexError) as exc:
            raise LLMError("The API returned an empty or malformed response") from exc
        if not isinstance(content, str) or not content.strip():
            raise LLMError("The model returned no content")
        return content


def _short_api_message(exc: APIStatusError) -> str:
    message = getattr(exc, "message", None) or str(exc)
    return message.strip()[:500]
