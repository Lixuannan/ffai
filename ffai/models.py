"""Pydantic models for FFmpeg tasks and LLM decisions.

The language model never receives or produces a shell command. It may only
produce a :class:`TaskPatch`; the patch is validated here and applied to the
locally owned task state.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

# Codec identifiers are flag values, not shell fragments. Restricting the
# first character also keeps a model-provided value from looking like an
# FFmpeg option.
CodecName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$",
    ),
]

Bitrate = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=16,
        pattern=r"^\d+(?:\.\d+)?[kKmMgG]?$",
    ),
]

Preset = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=48,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
    ),
]

FilterExpression = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=20_000),
]

StreamMap = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=256,
        pattern=r"^(?:\[[^\[\]\s,]+\]|\d+(?::[^:\s]+){0,4}\??)$",
    ),
]

ExtraOption = Annotated[
    str,
    StringConstraints(min_length=1, max_length=2_048),
]

Description = Annotated[str, StringConstraints(max_length=4_000)]


def _reject_nul(value: str, field_name: str) -> str:
    if "\x00" in value:
        raise ValueError(f"{field_name} must not contain NUL characters")
    return value


class FFmpegTask(BaseModel):
    """Canonical, local representation of one FFmpeg operation.

    ``inputs`` and ``output`` are owned by the REPL commands and are never
    writable through the model patch.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    inputs: list[str] = Field(default_factory=list)
    output: str | None = None
    video_filters: list[FilterExpression] = Field(default_factory=list)
    audio_filters: list[FilterExpression] = Field(default_factory=list)
    video_codec: CodecName | None = None
    audio_codec: CodecName | None = None
    video_bitrate: Bitrate | None = None
    audio_bitrate: Bitrate | None = None
    crf: int | None = Field(default=None, ge=0, le=63)
    preset: Preset | None = None
    extra_options: list[ExtraOption] = Field(default_factory=list)
    filter_complex: FilterExpression | None = None
    maps: list[StreamMap] = Field(default_factory=list)
    description: Description = "New FFmpeg task"

    @field_validator("video_filters", "audio_filters")
    @classmethod
    def _validate_filters(cls, values: list[str]) -> list[str]:
        for value in values:
            _reject_nul(value, "filter")
        return values

    @field_validator("extra_options")
    @classmethod
    def _validate_extra_options(cls, values: list[str]) -> list[str]:
        for value in values:
            _reject_nul(value, "extra option")
            if "\n" in value or "\r" in value:
                raise ValueError("extra options must not contain newlines")
        return values

    @field_validator("filter_complex")
    @classmethod
    def _validate_filter_complex(cls, value: str | None) -> str | None:
        if value is not None:
            _reject_nul(value, "filter_complex")
        return value


class TaskPatch(BaseModel):
    """Incremental changes to a task.

    Only fields present in the JSON payload are applied. ``model_fields_set``
    distinguishes "unchanged" from an explicit ``null``, which clears a value.
    """

    model_config = ConfigDict(extra="forbid")

    video_filters: list[FilterExpression] | None = None
    audio_filters: list[FilterExpression] | None = None
    video_codec: CodecName | None = None
    audio_codec: CodecName | None = None
    video_bitrate: Bitrate | None = None
    audio_bitrate: Bitrate | None = None
    crf: int | None = Field(default=None, ge=0, le=63)
    preset: Preset | None = None
    extra_options: list[ExtraOption] | None = None
    filter_complex: FilterExpression | None = None
    maps: list[StreamMap] | None = None
    description: Description | None = None

    @field_validator("video_filters", "audio_filters", "maps", "extra_options")
    @classmethod
    def _validate_lists(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return values
        for value in values:
            if "\x00" in value or "\n" in value or "\r" in value:
                raise ValueError("Task list values must not contain NUL or newlines")
        return values

    @field_validator("filter_complex", "description")
    @classmethod
    def _validate_text(cls, value: str | None) -> str | None:
        if value is not None:
            _reject_nul(value, "field")
        return value


class LLMDecision(BaseModel):
    """The only thing the language model is allowed to return."""

    model_config = ConfigDict(extra="forbid")

    intent: Literal["apply", "clarify", "noop"]
    patch: TaskPatch = Field(default_factory=TaskPatch)
    explanation: Annotated[str, StringConstraints(min_length=1, max_length=4_000)]
    question: Annotated[str, StringConstraints(min_length=1, max_length=2_000)] | None = None

    @model_validator(mode="after")
    def _validate_decision(self) -> LLMDecision:
        if self.intent in {"clarify", "noop"} and self.patch.model_fields_set:
            raise ValueError(f"intent '{self.intent}' must not include task changes")
        if self.intent == "clarify" and self.question is None:
            raise ValueError("intent 'clarify' requires a question")
        return self


# Fields shown by the REPL and used for change summaries. Keeping the order
# here gives panels and diffs a stable presentation.
TASK_DISPLAY_FIELDS: tuple[str, ...] = (
    "video_filters",
    "audio_filters",
    "filter_complex",
    "maps",
    "video_codec",
    "audio_codec",
    "crf",
    "preset",
    "video_bitrate",
    "audio_bitrate",
    "extra_options",
    "description",
)
