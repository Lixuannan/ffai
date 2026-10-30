from __future__ import annotations

import shutil
from io import StringIO
from pathlib import Path

import pytest
from rich.console import Console

from ffai.errors import ExecutionError
from ffai.executor import execute_ffmpeg, parse_progress_seconds
from ffai.utils import scrubbed_environment


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
    console = Console(file=StringIO(), force_terminal=False)
    with pytest.raises(ExecutionError, match="not found on PATH"):
        execute_ffmpeg(
            ["ffai-definitely-not-an-executable"],
            expected_output=str(tmp_path / "out.mp4"),
            console=console,
        )


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg is not installed")
def test_real_ffmpeg_run_creates_the_output_file(tmp_path: Path) -> None:
    output = tmp_path / "generated.mp4"
    console = Console(file=StringIO(), force_terminal=False)
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
        console=console,
        total_duration=0.3,
    )

    assert result.succeeded
    assert result.interrupted is False
    assert result.exit_code == 0
    assert output.is_file()
    assert output.stat().st_size > 0
    assert b"ftyp" in output.read_bytes()[:32]
