from __future__ import annotations

import json

import pytest

from ffai.errors import LLMError
from ffai.llm import extract_json_object, parse_decision
from ffai.prompt import SYSTEM_PROMPT, build_user_prompt


def test_extracts_json_from_code_fence_and_preface() -> None:
    text = (
        'Here is the result:\n```json\n{"intent": "noop", "patch": {}, "explanation": "hi"}\n```\n'
    )
    assert json.loads(extract_json_object(text)) == {
        "intent": "noop",
        "patch": {},
        "explanation": "hi",
    }


def test_extract_ignores_braces_inside_strings() -> None:
    text = '{"intent":"noop","patch":{},"explanation":"use {braces} here"}'
    assert json.loads(extract_json_object(text))["explanation"] == "use {braces} here"


def test_extract_rejects_incomplete_json() -> None:
    with pytest.raises(LLMError, match="incomplete"):
        extract_json_object('{"intent": "noop"')


def test_full_system_prompt_has_allowlist_substituted() -> None:
    assert "__ALLOWED_EXTRA_OPTIONS__" not in SYSTEM_PROMPT
    assert "-movflags" in SYSTEM_PROMPT
    assert "never write or execute shell commands" in SYSTEM_PROMPT.lower()


def test_parse_valid_apply_decision() -> None:
    decision = parse_decision(
        json.dumps(
            {
                "intent": "apply",
                "patch": {"video_codec": "libx265", "crf": 23, "description": "H.265"},
                "explanation": "Using H.265 at CRF 23.",
                "question": None,
            }
        )
    )
    assert decision.intent == "apply"
    assert decision.patch.model_fields_set == {"video_codec", "crf", "description"}
    assert decision.patch.crf == 23


def test_parse_rejects_unknown_patch_fields() -> None:
    with pytest.raises(LLMError, match="invalid task decision"):
        parse_decision(
            json.dumps(
                {
                    "intent": "apply",
                    "patch": {"shell_command": "rm -rf /"},
                    "explanation": "bad",
                }
            )
        )


def test_clarify_requires_question_and_empty_patch() -> None:
    with pytest.raises(LLMError, match="requires a question"):
        parse_decision(
            json.dumps(
                {
                    "intent": "clarify",
                    "patch": {},
                    "explanation": "Ambiguous",
                    "question": None,
                }
            )
        )

    with pytest.raises(LLMError, match="must not include task changes"):
        parse_decision(
            json.dumps(
                {
                    "intent": "clarify",
                    "patch": {"crf": 20},
                    "explanation": "Ambiguous",
                    "question": "Which codec?",
                }
            )
        )


def test_noop_rejects_task_changes() -> None:
    with pytest.raises(LLMError, match="must not include task changes"):
        parse_decision(
            json.dumps(
                {
                    "intent": "noop",
                    "patch": {"crf": 20},
                    "explanation": "No change",
                    "question": None,
                }
            )
        )


def test_user_prompt_delimits_state_and_request() -> None:
    prompt = build_user_prompt({"inputs": ["a.mp4"], "output": None}, "make it smaller")
    assert "<current_task>" in prompt
    assert '"inputs": [' in prompt
    assert "<user_request>" in prompt
    assert "make it smaller" in prompt


class _FakeCompletions:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        from types import SimpleNamespace

        self.calls.append(kwargs)
        content = self.responses.pop(0)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def _fake_client(responses: list[str]) -> tuple[object, _FakeCompletions]:
    from types import SimpleNamespace

    completions = _FakeCompletions(responses)
    return SimpleNamespace(chat=SimpleNamespace(completions=completions)), completions


def test_llm_client_analyzes_state_with_json_mode() -> None:
    from pydantic import SecretStr

    from ffai.config import LLMConfig
    from ffai.llm import LLMClient

    client, completions = _fake_client(
        [
            json.dumps(
                {
                    "intent": "apply",
                    "patch": {"video_codec": "libx265"},
                    "explanation": "Using H.265.",
                    "question": None,
                }
            )
        ]
    )
    llm = LLMClient(
        LLMConfig(api_key=SecretStr("sk-test"), model="test-model"),
        client=client,
    )
    decision = llm.analyze(
        {"inputs": ["/tmp/input.mp4"], "output": "/tmp/out.mp4"},
        "use h265",
    )

    assert decision.patch.video_codec == "libx265"
    assert len(completions.calls) == 1
    call = completions.calls[0]
    assert call["response_format"] == {"type": "json_object"}
    assert call["model"] == "test-model"
    messages = call["messages"]
    assert isinstance(messages, list)
    assert "use h265" in messages[1]["content"]


def test_llm_client_repairs_one_invalid_response() -> None:
    from pydantic import SecretStr

    from ffai.config import LLMConfig
    from ffai.llm import LLMClient

    valid = json.dumps(
        {
            "intent": "noop",
            "patch": {},
            "explanation": "No change needed.",
            "question": None,
        }
    )
    client, completions = _fake_client(["not JSON at all", valid])
    llm = LLMClient(
        LLMConfig(api_key=SecretStr("sk-test"), model="test-model"),
        client=client,
    )

    decision = llm.analyze({"inputs": [], "output": None}, "hello")
    assert decision.intent == "noop"
    assert len(completions.calls) == 2
    repair_messages = completions.calls[1]["messages"]
    assert "failed validation" in repair_messages[-1]["content"]
