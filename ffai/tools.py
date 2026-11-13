"""Registry of external conversion tools and extension-based routing.

Each supported tool exposes one task model, one patch model, and one argv
builder. The registry is the single place that maps a tool name to its
capabilities so the REPL, the prompt, and the session state stay tool-agnostic.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ffai import command_builder, pandoc_builder
from ffai.models import (
    FFMPEG_DISPLAY_FIELDS,
    PANDOC_DISPLAY_FIELDS,
    FFmpegPatch,
    FFmpegTask,
    PandocPatch,
    PandocTask,
    TaskBase,
    ToolName,
)

# Media container/codec extensions routed to FFmpeg.
MEDIA_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".3g2",
        ".3gp",
        ".aac",
        ".aif",
        ".aiff",
        ".alac",
        ".ape",
        ".avi",
        ".avif",
        ".bmp",
        ".flac",
        ".flv",
        ".gif",
        ".jpeg",
        ".jpg",
        ".m2ts",
        ".m4a",
        ".m4v",
        ".mkv",
        ".mov",
        ".mp3",
        ".mp4",
        ".mpeg",
        ".mpg",
        ".mts",
        ".oga",
        ".ogg",
        ".ogv",
        ".opus",
        ".png",
        ".tif",
        ".tiff",
        ".ts",
        ".vob",
        ".wav",
        ".webm",
        ".webp",
        ".wma",
        ".wmv",
    }
)

# Document extensions routed to Pandoc.
DOCUMENT_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".adoc",
        ".asciidoc",
        ".docx",
        ".epub",
        ".htm",
        ".html",
        ".ipynb",
        ".latex",
        ".markdown",
        ".md",
        ".mediawiki",
        ".odt",
        ".opml",
        ".org",
        ".pptx",
        ".rst",
        ".rtf",
        ".tex",
        ".text",
        ".textile",
        ".txt",
    }
)


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """Everything the application needs to know about one external tool."""

    name: ToolName
    binary: str
    label: str
    task_type: type[TaskBase]
    patch_type: type[FFmpegPatch] | type[PandocPatch]
    display_fields: tuple[str, ...]
    default_description: str
    supports_progress: bool
    builder: Callable[[Any], list[str]]


TOOL_SPECS: dict[ToolName, ToolSpec] = {
    "ffmpeg": ToolSpec(
        name="ffmpeg",
        binary="ffmpeg",
        label="FFmpeg",
        task_type=FFmpegTask,
        patch_type=FFmpegPatch,
        display_fields=FFMPEG_DISPLAY_FIELDS,
        default_description="New FFmpeg task",
        supports_progress=True,
        builder=command_builder.build_command,
    ),
    "pandoc": ToolSpec(
        name="pandoc",
        binary="pandoc",
        label="Pandoc",
        task_type=PandocTask,
        patch_type=PandocPatch,
        display_fields=PANDOC_DISPLAY_FIELDS,
        default_description="New pandoc task",
        supports_progress=False,
        builder=pandoc_builder.build_command,
    ),
}

TOOL_NAMES: tuple[ToolName, ...] = tuple(TOOL_SPECS)

_EXTENSION_TOOL: dict[str, ToolName] = {
    **{extension: "ffmpeg" for extension in MEDIA_EXTENSIONS},
    **{extension: "pandoc" for extension in DOCUMENT_EXTENSIONS},
}


def get_tool(name: ToolName) -> ToolSpec:
    return TOOL_SPECS[name]


def detect_tool(paths: Sequence[str]) -> ToolName | None:
    """Infer the conversion tool from the extension of *paths*.

    Returns ``None`` when the extensions are unknown or point at different
    tools, in which case the caller keeps the currently selected tool.
    """

    detected = {
        _EXTENSION_TOOL[Path(path).suffix.lower()]
        for path in paths
        if Path(path).suffix.lower() in _EXTENSION_TOOL
    }
    return detected.pop() if len(detected) == 1 else None


def tool_available(name: ToolName) -> bool:
    return shutil.which(TOOL_SPECS[name].binary) is not None


def available_tools() -> tuple[ToolName, ...]:
    return tuple(name for name in TOOL_NAMES if tool_available(name))


def missing_tools() -> tuple[ToolName, ...]:
    return tuple(name for name in TOOL_NAMES if not tool_available(name))
