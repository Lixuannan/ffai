"""Cross-module integration tests for the two-tool conversion session.

These tests exercise the real boundaries that matter to the feature: a model
decision JSON is parsed, applied to session state, rendered by the tool
registry into argv, and executed through the generic executor. They do not
mock the modules under test.
"""

from __future__ import annotations

import json
import shutil
from io import StringIO
from pathlib import Path

import pytest
from pydantic import ValidationError
from rich.console import Console

from ffai.errors import CommandBuildError, ExecutionError
from ffai.executor import execute_tool
from ffai.llm import parse_decision
from ffai.models import PandocPatch, ToolPatch
from ffai.state import SessionState
from ffai.tools import get_tool


@pytest.fixture
def markdown_file(tmp_path: Path) -> Path:
    path = tmp_path / "report.md"
    path.write_text("# Report\n\nSome text.\n", encoding="utf-8")
    return path


@pytest.fixture
def media_file(tmp_path: Path) -> Path:
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"placeholder")
    return path


def test_pandoc_decision_becomes_pandoc_argv(markdown_file: Path, tmp_path: Path) -> None:
    state = SessionState()
    state.add_inputs((str(markdown_file),))
    state.set_output(str(tmp_path / "report.docx"))
    assert state.tool == "pandoc"

    decision = parse_decision(
        json.dumps(
            {
                "intent": "apply",
                "patch": {
                    "pandoc": {
                        "to_format": "docx",
                        "toc": True,
                        "standalone": True,
                        "metadata": ["title=Report"],
                    }
                },
                "explanation": "Building a Word document with a table of contents.",
                "question": None,
            }
        )
    )
    assert decision.intent == "apply"
    state.apply_patch(decision.patch)

    command = get_tool(state.tool).builder(state.task)

    assert command[0] == "pandoc"
    assert command[command.index("--standalone")] == "--standalone"
    assert command[command.index("--toc")] == "--toc"
    assert command[command.index("-M") + 1] == "title=Report"
    assert command[command.index("-o") + 1] == str((tmp_path / "report.docx").resolve())
    assert command[-1] == str(markdown_file.resolve())
    assert "-f" not in command


def test_ffmpeg_decision_still_builds_ffmpeg_argv(media_file: Path, tmp_path: Path) -> None:
    state = SessionState()
    state.add_inputs((str(media_file),))
    state.set_output(str(tmp_path / "out.mp4"))

    decision = parse_decision(
        json.dumps(
            {
                "intent": "apply",
                "patch": {
                    "ffmpeg": {
                        "video_filters": ["scale=1280:720"],
                        "video_codec": "libx264",
                        "crf": 23,
                    }
                },
                "explanation": "Scaling and re-encoding.",
                "question": None,
            }
        )
    )
    state.apply_patch(decision.patch)
    command = get_tool(state.tool).builder(state.task)

    assert command[0] == "ffmpeg"
    assert command[command.index("-vf") + 1] == "scale=1280:720"
    assert command[-1] == str((tmp_path / "out.mp4").resolve())


def test_tool_switch_preserves_both_tasks(
    markdown_file: Path, media_file: Path, tmp_path: Path
) -> None:
    state = SessionState()
    state.add_inputs((str(media_file),))
    state.set_output(str(tmp_path / "out.mp4"))
    state.apply_patch(ToolPatch(ffmpeg=parse_decision(
        json.dumps(
            {
                "intent": "apply",
                "patch": {"ffmpeg": {"crf": 18}},
                "explanation": "Higher quality.",
                "question": None,
            }
        )
    ).patch.ffmpeg))

    state.select_tool("pandoc")
    state.add_inputs((str(markdown_file),))
    state.set_output(str(tmp_path / "report.docx"))
    state.apply_patch(ToolPatch(pandoc=PandocPatch(to_format="docx")))

    assert state.tool == "pandoc"
    assert state.pandoc_task.inputs == [str(markdown_file.resolve())]
    assert state.ffmpeg_task.inputs == [str(media_file.resolve())]
    assert state.ffmpeg_task.crf == 18

    state.select_tool("ffmpeg")
    assert state.llm_context()["tool"] == "ffmpeg"
    assert state.llm_context()["crf"] == 18
    assert get_tool("ffmpeg").builder(state.task)[-1] == str((tmp_path / "out.mp4").resolve())


def test_switch_decision_with_empty_payload_changes_only_the_tool(
    media_file: Path, tmp_path: Path
) -> None:
    state = SessionState()
    state.add_inputs((str(media_file),))
    state.set_output(str(tmp_path / "out.mp4"))

    decision = parse_decision(
        json.dumps(
            {
                "intent": "apply",
                "patch": {"pandoc": {}},
                "explanation": "Switching to document conversion.",
                "question": None,
            }
        )
    )
    changes = state.apply_patch(decision.patch)

    assert state.tool == "pandoc"
    assert [change.field for change in changes] == ["tool"]
    assert state.ffmpeg_task.inputs == [str(media_file.resolve())]


def test_pandoc_builder_rejects_program_options(markdown_file: Path, tmp_path: Path) -> None:
    state = SessionState()
    state.add_inputs((str(markdown_file),))
    state.set_output(str(tmp_path / "report.html"))
    state.apply_patch(
        ToolPatch(pandoc=PandocPatch(extra_options=["--filter", "evil-program"]))
    )

    with pytest.raises(CommandBuildError, match="Unsupported extra option"):
        get_tool("pandoc").builder(state.task)


def test_pandoc_engine_choice_is_validated_at_the_model_boundary() -> None:
    with pytest.raises(ValidationError, match="pdf_engine"):
        PandocPatch(pdf_engine="sh")


@pytest.mark.skipif(shutil.which("pandoc") is not None, reason="Pandoc is installed")
def test_missing_pandoc_is_reported_clearly(markdown_file: Path, tmp_path: Path) -> None:
    state = SessionState()
    state.add_inputs((str(markdown_file),))
    state.set_output(str(tmp_path / "report.html"))
    command = get_tool("pandoc").builder(state.task)

    console = Console(file=StringIO(), force_terminal=False)
    with pytest.raises(ExecutionError, match="Pandoc was not found on PATH"):
        execute_tool(
            command,
            expected_output=state.task.output or "",
            console=console,
            tool_label="Pandoc",
            show_progress=False,
        )
