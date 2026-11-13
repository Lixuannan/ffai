from __future__ import annotations

from pathlib import Path

from ffai.models import FFmpegTask, PandocTask
from ffai.tools import (
    DOCUMENT_EXTENSIONS,
    MEDIA_EXTENSIONS,
    TOOL_NAMES,
    TOOL_SPECS,
    detect_tool,
    get_tool,
    tool_available,
)


def test_registry_covers_every_supported_tool() -> None:
    assert TOOL_NAMES == ("ffmpeg", "pandoc")
    ffmpeg = get_tool("ffmpeg")
    pandoc = get_tool("pandoc")
    assert ffmpeg.task_type is FFmpegTask
    assert pandoc.task_type is PandocTask
    assert ffmpeg.binary == "ffmpeg"
    assert pandoc.binary == "pandoc"
    assert ffmpeg.supports_progress is True
    assert pandoc.supports_progress is False
    assert TOOL_SPECS["ffmpeg"].label == "FFmpeg"
    assert TOOL_SPECS["pandoc"].label == "Pandoc"


def test_registry_builders_are_callable() -> None:
    assert callable(TOOL_SPECS["ffmpeg"].builder)
    assert callable(TOOL_SPECS["pandoc"].builder)


def test_detects_tool_from_extension(tmp_path: Path) -> None:
    assert detect_tool(["clip.mp4"]) == "ffmpeg"
    assert detect_tool(["clip.MOV"]) == "ffmpeg"
    assert detect_tool(["frame.png"]) == "ffmpeg"
    assert detect_tool(["notes.md"]) == "pandoc"
    assert detect_tool(["notes.txt"]) == "pandoc"
    assert detect_tool(["report.docx"]) == "pandoc"
    assert detect_tool(["archive.zip"]) is None


def test_detection_is_ambiguous_across_tools(tmp_path: Path) -> None:
    assert detect_tool(["clip.mp4", "notes.md"]) is None
    assert detect_tool([]) is None


def test_detection_ignores_unknown_extensions() -> None:
    assert detect_tool(["archive.zip"]) is None
    assert detect_tool(["clip.mp4", "archive.zip"]) == "ffmpeg"


def test_extension_sets_are_disjoint() -> None:
    assert not MEDIA_EXTENSIONS & DOCUMENT_EXTENSIONS
    assert all(extension.startswith(".") for extension in MEDIA_EXTENSIONS | DOCUMENT_EXTENSIONS)


def test_tool_available_matches_path_lookup() -> None:
    import shutil

    for name in TOOL_NAMES:
        assert tool_available(name) is (shutil.which(TOOL_SPECS[name].binary) is not None)
