from __future__ import annotations

import shutil
import sys
from io import StringIO
from pathlib import Path

import pytest
from rich.console import Console

from ffai.errors import ExecutionError
from ffai.executor import execute_ffmpeg, execute_tool, parse_progress_seconds
from ffai.utils import scrubbed_environment


def _console() -> Console:
    return Console(file=StringIO(), force_terminal=False)


def test_parse_progress_timestamp() -> None:
    line = "frame=  120 fps= 60 q=28.0 size=     512kB time=00:00:02.50 bitrate=..."
    assert parse_progress_seconds(line) == 2.5
    assert parse_progress_seconds("time=N/A") is None
    assert parse_progress_seconds("no timing here") is None


def test_environment_scrubbing_removes_credentials() -> None:
    env = {
        "PATH": "/bin",
        "HOME": "/home/user",
        "OPENAI_API_KEY": "sk-secret",
        "AWS_SECRET_ACCESS_KEY": "secret",
        "GITHUB_TOKEN": "token",
        "DB_PASSWORD": "password",
    }
    scrubbed = scrubbed_environment(env)
    assert scrubbed == {"PATH": "/bin", "HOME": "/home/user"}


def test_missing_executable_is_reported(tmp_path: Path) -> None:
    with pytest.raises(ExecutionError, match="not found on PATH"):
        execute_ffmpeg(
            ["ffai-definitely-not-an-executable"],
            expected_output=str(tmp_path / "out.mp4"),
            console=_console(),
        )


def test_execute_tool_runs_a_generic_process(tmp_path: Path) -> None:
    output = tmp_path / "generated.txt"
    script = (
        "import sys; from pathlib import Path; "
        "Path(sys.argv[1]).write_text('hello', encoding='utf-8')"
    )

    result = execute_tool(
        [sys.executable, "-c", script, str(output)],
        expected_output=str(output),
        console=_console(),
        tool_label="TestTool",
        show_progress=False,
    )

    assert result.succeeded
    assert result.interrupted is False
    assert result.exit_code == 0
    assert result.output_path == str(output)
    assert output.read_text(encoding="utf-8") == "hello"


def test_execute_tool_reports_nonzero_exit_without_raising(tmp_path: Path) -> None:
    output = tmp_path / "out.txt"
    script = (
        "import sys; sys.stderr.write('boom happened\\n'); sys.stderr.flush(); "
        "raise SystemExit(3)"
    )

    result = execute_tool(
        [sys.executable, "-c", script],
        expected_output=str(output),
        console=_console(),
        tool_label="TestTool",
        show_progress=False,
    )

    assert result.succeeded is False
    assert result.interrupted is False
    assert result.exit_code == 3
    assert "boom happened" in result.stderr_tail
    assert not output.exists()


def test_execute_tool_missing_executable_names_the_tool(tmp_path: Path) -> None:
    with pytest.raises(ExecutionError, match="Pandoc was not found on PATH"):
        execute_tool(
            ["ffai-definitely-not-an-executable"],
            expected_output=str(tmp_path / "out.html"),
            console=_console(),
            tool_label="Pandoc",
            show_progress=False,
        )


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg is not installed")
def test_real_ffmpeg_run_creates_the_output_file(tmp_path: Path) -> None:
    output = tmp_path / "generated.mp4"
    result = execute_ffmpeg(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=64x64:r=10",
            "-t",
            "0.3",
            "-c:v",
            "mpeg4",
            "-pix_fmt",
            "yuv420p",
            str(output),
        ],
        expected_output=str(output),
        console=_console(),
        total_duration=0.3,
    )

    assert result.succeeded
    assert result.interrupted is False
    assert result.exit_code == 0
    assert output.is_file()
    assert output.stat().st_size > 0
    assert b"ftyp" in output.read_bytes()[:32]


@pytest.mark.skipif(shutil.which("pandoc") is None, reason="Pandoc is not installed")
def test_real_pandoc_run_creates_the_output_file(tmp_path: Path) -> None:
    markdown = tmp_path / "input.md"
    markdown.write_text("# Hello\n\nWorld.\n", encoding="utf-8")
    output = tmp_path / "output.html"

    result = execute_tool(
        ["pandoc", str(markdown), "-t", "html", "-o", str(output)],
        expected_output=str(output),
        console=_console(),
        tool_label="Pandoc",
        show_progress=False,
    )

    assert result.succeeded
    assert result.exit_code == 0
    assert output.is_file()
    assert output.stat().st_size > 0
    rendered = output.read_text(encoding="utf-8").lower()
    assert "<html" in rendered or "<h1" in rendered
