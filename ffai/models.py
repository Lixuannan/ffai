"""Pydantic models for conversion tasks and LLM decisions.

The language model never receives or produces a shell command. It may only
produce a :class:`ToolPatch`; the patch is validated here and applied to the
locally owned task state. Each supported external tool owns its own task model
and patch model, and a patch always targets exactly one tool.
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

ToolName = Literal["ffmpeg", "pandoc"]

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

# Pandoc format names are single tokens such as ``gfm``, ``markdown_strict``
# or ``docx``. The pattern is deliberately permissive about the exact name so
# newer Pandoc formats keep working; Pandoc itself reports unknown formats.
FormatName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=32,
        pattern=r"^[A-Za-z][A-Za-z0-9_+-]*$",
    ),
]

# Metadata is passed as one ``-M key=value`` argv pair. Only the key is
# constrained; the value is an opaque argv token that never reaches a shell.
MetadataEntry = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=3,
        max_length=2_048,
        pattern=r"^[A-Za-z][A-Za-z0-9_.-]*=.+$",
    ),
]

# Filesystem inputs to Pandoc (templates, bibliographies, resources). They are
# validated against the filesystem by the Pandoc command builder; the model
# only carries the path as one argv token.
PathValue = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=4_096),
]

PDF_ENGINES: tuple[str, ...] = (
    "pdflatex",
    "xelatex",
    "lualatex",
    "latexmk",
    "tectonic",
    "typst",
    "context",
    "wkhtmltopdf",
    "weasyprint",
    "prince",
    "pdfroff",
)

HIGHLIGHT_STYLES: tuple[str, ...] = (
    "pygments",
    "tango",
    "espresso",
    "zenburn",
    "kate",
    "monochrome",
    "breezedark",
    "haddock",
)


def _reject_nul(value: str, field_name: str) -> str:
    if "\x00" in value:
        raise ValueError(f"{field_name} must not contain NUL characters")
    return value


def _reject_control_characters(value: str, field_name: str) -> str:
    _reject_nul(value, field_name)
    if "\n" in value or "\r" in value:
        raise ValueError(f"{field_name} must not contain newlines")
    return value


def _validate_choice(value: str | None, allowed: tuple[str, ...], field_name: str) -> str | None:
    if value is not None and value not in allowed:
        raise ValueError(f"{field_name} must be one of: {', '.join(allowed)}")
    return value


class TaskBase(BaseModel):
    """Fields shared by every external conversion tool.

    ``inputs`` and ``output`` are owned by the REPL commands and are never
    writable through a model patch.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    inputs: list[str] = Field(default_factory=list)
    output: str | None = None
    description: Description = "New conversion task"


class FFmpegTask(TaskBase):
    """Canonical, local representation of one FFmpeg operation."""

    description: Description = "New FFmpeg task"

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
            _reject_control_characters(value, "extra option")
        return values

    @field_validator("filter_complex")
    @classmethod
    def _validate_filter_complex(cls, value: str | None) -> str | None:
        if value is not None:
            _reject_nul(value, "filter_complex")
        return value


class PandocTask(TaskBase):
    """Canonical, local representation of one Pandoc conversion."""

    description: Description = "New pandoc task"

    from_format: FormatName | None = None
    to_format: FormatName | None = None
    standalone: bool = False
    toc: bool = False
    toc_depth: int | None = Field(default=None, ge=1, le=6)
    number_sections: bool = False
    shift_heading_level_by: int | None = Field(default=None, ge=-10, le=10)
    metadata: list[MetadataEntry] = Field(default_factory=list)
    template: PathValue | None = None
    reference_doc: PathValue | None = None
    pdf_engine: str | None = None
    highlight_style: str | None = None
    embed_resources: bool = False
    citeproc: bool = False
    bibliography: list[PathValue] = Field(default_factory=list)
    csl: PathValue | None = None
    resource_path: list[PathValue] = Field(default_factory=list)
    extra_options: list[ExtraOption] = Field(default_factory=list)

    @field_validator("metadata", "bibliography", "resource_path", "extra_options")
    @classmethod
    def _validate_string_lists(cls, values: list[str]) -> list[str]:
        for value in values:
            _reject_control_characters(value, "Pandoc list value")
        return values

    @field_validator("template", "reference_doc", "csl")
    @classmethod
    def _validate_path_values(cls, value: str | None) -> str | None:
        if value is not None:
            _reject_control_characters(value, "Pandoc path")
        return value

    @field_validator("pdf_engine")
    @classmethod
    def _validate_pdf_engine(cls, value: str | None) -> str | None:
        return _validate_choice(value, PDF_ENGINES, "pdf_engine")

    @field_validator("highlight_style")
    @classmethod
    def _validate_highlight_style(cls, value: str | None) -> str | None:
        return _validate_choice(value, HIGHLIGHT_STYLES, "highlight_style")


class FFmpegPatch(BaseModel):
    """Incremental changes to an FFmpeg task.

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


class PandocPatch(BaseModel):
    """Incremental changes to a Pandoc task.

    ``None`` clears a field; omitted fields are unchanged. Boolean fields use
    ``false`` to turn an option off, and an explicit ``null`` also turns it off.
    """

    model_config = ConfigDict(extra="forbid")

    from_format: FormatName | None = None
    to_format: FormatName | None = None
    standalone: bool | None = None
    toc: bool | None = None
    toc_depth: int | None = Field(default=None, ge=1, le=6)
    number_sections: bool | None = None
    shift_heading_level_by: int | None = Field(default=None, ge=-10, le=10)
    metadata: list[MetadataEntry] | None = None
    template: PathValue | None = None
    reference_doc: PathValue | None = None
    pdf_engine: str | None = None
    highlight_style: str | None = None
    embed_resources: bool | None = None
    citeproc: bool | None = None
    bibliography: list[PathValue] | None = None
    csl: PathValue | None = None
    resource_path: list[PathValue] | None = None
    extra_options: list[ExtraOption] | None = None
    description: Description | None = None

    @field_validator("metadata", "bibliography", "resource_path", "extra_options")
    @classmethod
    def _validate_lists(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return values
        for value in values:
            if "\x00" in value or "\n" in value or "\r" in value:
                raise ValueError("Pandoc list values must not contain NUL or newlines")
        return values

    @field_validator("template", "reference_doc", "csl", "description")
    @classmethod
    def _validate_text(cls, value: str | None) -> str | None:
        if value is not None:
            _reject_nul(value, "field")
        return value

    @field_validator("pdf_engine")
    @classmethod
    def _validate_pdf_engine(cls, value: str | None) -> str | None:
        return _validate_choice(value, PDF_ENGINES, "pdf_engine")

    @field_validator("highlight_style")
    @classmethod
    def _validate_highlight_style(cls, value: str | None) -> str | None:
        return _validate_choice(value, HIGHLIGHT_STYLES, "highlight_style")


_TOOL_PATCH_FIELDS: tuple[ToolName, ...] = ("ffmpeg", "pandoc")


class ToolPatch(BaseModel):
    """A patch that targets exactly one tool.

    The JSON shape is ``{"ffmpeg": { ... }}`` or ``{"pandoc": { ... }}``. An
    empty object (``{}``) means "no task changes" and is only valid for the
    clarify/noop intents. A tool key with an empty payload selects that tool
    without changing any of its fields.
    """

    model_config = ConfigDict(extra="forbid")

    ffmpeg: FFmpegPatch | None = None
    pandoc: PandocPatch | None = None

    @model_validator(mode="after")
    def _exactly_one_tool(self) -> ToolPatch:
        present = [name for name in _TOOL_PATCH_FIELDS if getattr(self, name) is not None]
        if len(present) > 1:
            raise ValueError("a patch must target exactly one tool, not several")
        return self

    @property
    def tool(self) -> ToolName | None:
        for name in _TOOL_PATCH_FIELDS:
            if getattr(self, name) is not None:
                return name
        return None

    @property
    def fields(self) -> FFmpegPatch | PandocPatch | None:
        tool = self.tool
        return None if tool is None else getattr(self, tool)


class LLMDecision(BaseModel):
    """The only thing the language model is allowed to return."""

    model_config = ConfigDict(extra="forbid")

    intent: Literal["apply", "clarify", "noop"]
    patch: ToolPatch = Field(default_factory=ToolPatch)
    explanation: Annotated[str, StringConstraints(min_length=1, max_length=4_000)]
    question: Annotated[str, StringConstraints(min_length=1, max_length=2_000)] | None = None

    @model_validator(mode="after")
    def _validate_decision(self) -> LLMDecision:
        if self.intent in {"clarify", "noop"} and self.patch.model_fields_set:
            raise ValueError(f"intent '{self.intent}' must not include task changes")
        if self.intent == "apply" and self.patch.tool is None:
            raise ValueError("intent 'apply' requires a patch for exactly one tool")
        if self.intent == "clarify" and self.question is None:
            raise ValueError("intent 'clarify' requires a question")
        return self


# Fields shown by the REPL and used for change summaries. Keeping the order
# here gives panels and diffs a stable presentation.
FFMPEG_DISPLAY_FIELDS: tuple[str, ...] = (
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

PANDOC_DISPLAY_FIELDS: tuple[str, ...] = (
    "from_format",
    "to_format",
    "standalone",
    "toc",
    "toc_depth",
    "number_sections",
    "shift_heading_level_by",
    "metadata",
    "template",
    "reference_doc",
    "pdf_engine",
    "highlight_style",
    "embed_resources",
    "citeproc",
    "bibliography",
    "csl",
    "resource_path",
    "extra_options",
    "description",
)

# Backward-compatible name for the FFmpeg field presentation order.
TASK_DISPLAY_FIELDS = FFMPEG_DISPLAY_FIELDS
