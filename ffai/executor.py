"""Safe subprocess execution with live progress and interrupt handling."""

from __future__ import annotations

import contextlib
import os
import re
import shutil
import signal
import subprocess
import time
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)

from ffai.errors import ExecutionError
from ffai.utils import scrubbed_environment

_TIME_PATTERN = re.compile(r"\btime=(\d+):(\d{2}):(\d{2}(?:\.\d+)?)")
_TAIL_LINES = 30


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    exit_code: int | None
    interrupted: bool
    elapsed_seconds: float
    stderr_tail: str
    output_path: str

    @property
    def succeeded(self) -> bool:
        return not self.interrupted and self.exit_code == 0


def parse_progress_seconds(line: str) -> float | None:
    """Parse FFmpeg's ``time=HH:MM:SS.xx`` stats field."""

    match = _TIME_PATTERN.search(line)
    if match is None:
        return None
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def execute_ffmpeg(
    args: Sequence[str],
    *,
    expected_output: str,
    console: Console,
    total_duration: float | None = None,
) -> ExecutionResult:
    """Run a prebuilt argv list and report the real process outcome.

    FFmpeg's stderr is consumed continuously so the pipe cannot deadlock, while
    stats lines drive a Rich progress bar. Ctrl+C terminates the whole child
    process group and is reported separately from a normal non-zero exit.
    """

    if not args:
        raise ExecutionError("No command to execute")
    if shutil.which(args[0]) is None:
        raise ExecutionError(f"{args[0]} was not found on PATH. Install FFmpeg and try again.")

    popen_kwargs: dict[str, object] = {}
    if os.name == "posix":
        # Keep the child in its own process group so cancellation can reliably
        # reach FFmpeg without leaving orphaned workers.
        popen_kwargs["start_new_session"] = True

    try:
        process = subprocess.Popen(
            list(args),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=scrubbed_environment(),
            **popen_kwargs,
        )
    except OSError as exc:
        raise ExecutionError(f"Could not start FFmpeg: {exc}") from exc

    assert process.stderr is not None
    started = time.monotonic()
    interrupted = False
    tail: deque[str] = deque(maxlen=200)
    duration = total_duration if total_duration and total_duration > 0 else None

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    )

    try:
        with progress:
            task_id = progress.add_task("Encoding with FFmpeg", total=duration)
            try:
                for raw_line in process.stderr:
                    line = raw_line.strip()
                    if line:
                        tail.append(line)
                    seconds = parse_progress_seconds(raw_line)
                    if seconds is not None:
                        if duration is not None:
                            progress.update(
                                task_id,
                                completed=min(seconds, duration),
                            )
                        else:
                            progress.update(task_id, advance=0)
            except KeyboardInterrupt:
                interrupted = True
                _terminate_process(process)
    finally:
        if process.poll() is None:
            _terminate_process(process)
        # The pipe is already closed when process teardown raced with EOF;
        # there is nothing left to release.
        with contextlib.suppress(OSError):
            process.stderr.close()
        return_code = process.poll()
        if return_code is None:
            try:
                return_code = process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                return_code = None
        elapsed = time.monotonic() - started

    result = ExecutionResult(
        exit_code=return_code,
        interrupted=interrupted,
        elapsed_seconds=elapsed,
        stderr_tail="\n".join(tail),
        output_path=expected_output,
    )

    if result.succeeded:
        output = Path(expected_output)
        if not output.is_file():
            raise ExecutionError(
                "FFmpeg exited successfully but did not create the output file.\n"
                + (result.stderr_tail or "No FFmpeg diagnostics were produced.")
            )
        try:
            empty = output.stat().st_size == 0
        except OSError as exc:
            raise ExecutionError(f"Could not inspect the output file: {exc}") from exc
        if empty:
            raise ExecutionError("FFmpeg exited successfully but the output file is empty.")

    return result


def _terminate_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return

    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            # The child exited between poll() and the signal; it is already gone.
            return
    else:
        process.terminate()

    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                return
        else:
            process.kill()
        process.wait()
