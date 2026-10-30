"""Small, side-effect-light helpers shared by the CLI and executor."""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

_SECRET_ENV_NAME = re.compile(r"KEY|SECRET|TOKEN|PASSWORD|PASSWD|CREDENTIAL", re.IGNORECASE)


def format_command(args: Sequence[str]) -> str:
    """Render argv as a copy-pasteable shell command for display only."""

    return shlex.join(str(arg) for arg in args)


def scrubbed_environment(source: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return an environment without credentials for spawned media tools."""

    environment = os.environ if source is None else source
    return {name: value for name, value in environment.items() if not _SECRET_ENV_NAME.search(name)}


def probe_duration(path: str, timeout_seconds: float = 10.0) -> float | None:
    """Best-effort media duration used only to render a progress bar.

    The FFmpeg run itself is still reported from its real exit status. Missing
    ffprobe, malformed media, and timeouts therefore degrade to an unknown
    duration rather than masking or changing command execution.
    """

    if shutil.which("ffprobe") is None:
        return None
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(Path(path)),
    ]
    try:
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
            env=scrubbed_environment(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    try:
        duration = float(completed.stdout.strip().splitlines()[0])
    except (IndexError, ValueError):
        return None
    return duration if duration > 0 else None


def format_file_size(path: str) -> str | None:
    try:
        size = Path(path).stat().st_size
    except OSError:
        return None
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return None


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None
