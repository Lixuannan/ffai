"""End-to-end pty tests for the interactive ffai REPL.

These tests drive the real ``python -m ffai`` process through a pseudo-terminal
so that readline/libedit line editing (history recall and TAB completion) is
exercised exactly as it is for an interactive user. They never contact an LLM:
the fake ``OPENAI_*`` environment is enough for startup and for the built-in
commands under test.
"""

from __future__ import annotations

import os
import re
import select
import struct
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

if sys.platform == "win32":
    pytest.skip("pty-based REPL tests require a POSIX pseudoterminal", allow_module_level=True)

pytest.importorskip("pty")
termios = pytest.importorskip("termios")
fcntl = pytest.importorskip("fcntl")

PROMPT_MARKER = b"ffai> "
STARTUP_TIMEOUT = 20.0
COMMAND_TIMEOUT = 20.0

_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def _configured_env() -> dict[str, str]:
    """Environment that lets the REPL start without prompting or network access."""
    env = os.environ.copy()
    for name in ("OPENAI_API_KEY", "OPENAI_MODEL", "OPENAI_BASE_URL"):
        env.pop(name, None)
    env["OPENAI_API_KEY"] = "sk-test-secret-value"
    env["OPENAI_MODEL"] = "test-model"
    env["OPENAI_BASE_URL"] = "https://api.openai.com/v1"
    env["FFAI_LANG"] = "en"
    env["NO_COLOR"] = "1"
    return env


@contextmanager
def _repl_pty() -> Iterator[tuple[subprocess.Popen[bytes], int]]:
    """Spawn ``python -m ffai`` on a wide pty and clean up afterwards."""
    master_fd, slave_fd = os.openpty()
    try:
        # A wide window keeps rich from hard-wrapping long tmp paths in command output.
        fcntl.ioctl(master_fd, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 400, 0, 0))
        process = subprocess.Popen(
            [sys.executable, "-m", "ffai"],
            cwd=ROOT,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            env=_configured_env(),
            close_fds=True,
        )
    except BaseException:
        os.close(slave_fd)
        os.close(master_fd)
        raise
    os.close(slave_fd)
    try:
        yield process, master_fd
    finally:
        # Close the master first: the resulting hangup/EOF lets a child that is
        # blocked on pty I/O exit instead of deadlocking the interpreter shutdown.
        os.close(master_fd)
        _reap_process(process)


def _reap_process(process: subprocess.Popen[bytes], timeout: float = 8.0) -> None:
    """Ensure the child is gone, escalating from wait to SIGTERM to SIGKILL."""
    deadline = time.monotonic() + timeout
    while process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.05)
    if process.poll() is None:
        process.terminate()
        deadline = time.monotonic() + 5.0
        while process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
    if process.poll() is None:
        process.kill()
    with suppress(subprocess.TimeoutExpired):
        process.wait(timeout=5)


def _send(master_fd: int, data: bytes) -> None:
    os.write(master_fd, data)


def _wait_for_exit(
    process: subprocess.Popen[bytes],
    master_fd: int,
    timeout: float,
) -> int:
    """Wait for *process* to finish while draining the pty master.

    libedit restores terminal attributes while shutting down and can block in
    ``tcsetattr`` if the pty output is not being read, so polling ``wait``
    without draining would deadlock. Returns the exit status.
    """
    deadline = time.monotonic() + timeout
    while process.poll() is None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AssertionError(f"ffai did not exit within {timeout:.0f}s")
        ready, _, _ = select.select([master_fd], [], [], min(remaining, 0.1))
        if not ready:
            continue
        try:
            chunk = os.read(master_fd, 65536)
        except OSError:
            break
        if not chunk:
            break
    return process.wait(timeout=5)


def _read_chunk(master_fd: int, timeout: float) -> bytes:
    """Read one chunk, or return ``b""`` when the timeout/quiet period elapses."""
    ready, _, _ = select.select([master_fd], [], [], timeout)
    if not ready:
        return b""
    try:
        return os.read(master_fd, 65536)
    except OSError:
        return b""


def _read_until(master_fd: int, marker: bytes, timeout: float) -> bytes:
    """Collect pty output until *marker* is seen, raising with the buffer otherwise."""
    deadline = time.monotonic() + timeout
    buffer = bytearray()
    while marker not in buffer:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AssertionError(
                f"timed out after {timeout:.1f}s waiting for {marker!r}; collected:\n"
                f"{bytes(buffer).decode('utf-8', 'replace')!r}"
            )
        chunk = _read_chunk(master_fd, min(remaining, 0.25))
        if not chunk:
            continue
        buffer.extend(chunk)
    return bytes(buffer)


def _drain(master_fd: int, quiet: float = 0.3, total: float = 2.0) -> bytes:
    """Read whatever the pty has produced, stopping after a short quiet period."""
    deadline = time.monotonic() + total
    buffer = bytearray()
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        chunk = _read_chunk(master_fd, min(quiet, remaining))
        if not chunk:
            break
        buffer.extend(chunk)
    return bytes(buffer)


def _plain(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _compact(text: str) -> str:
    """Drop all whitespace so a path wrapped across terminal lines still matches."""
    return "".join(text.split())


def _feed_until_prompt(master_fd: int) -> bytes:
    return _read_until(master_fd, PROMPT_MARKER, COMMAND_TIMEOUT)


def _exit_repl(master_fd: int, process: subprocess.Popen[bytes]) -> None:
    """Ask the REPL to quit and reap it while keeping the pty drained."""
    _send(master_fd, b"exit\r")
    _read_until(master_fd, b"Goodbye.", COMMAND_TIMEOUT)
    assert _wait_for_exit(process, master_fd, timeout=15.0) == 0


class _ScreenModel:
    """Tiny visible-terminal model: enough to reconstruct the prompt line.

    Tracks a line buffer per row and the cursor, honouring printable writes,
    carriage returns (column 0), backspaces (column - 1), line feeds (next row)
    and ignoring BEL and ANSI escape sequences.
    """

    def __init__(self) -> None:
        self._lines: list[list[str]] = [[]]
        self._row = 0
        self._col = 0

    @property
    def current_line(self) -> str:
        return "".join(self._lines[self._row])

    def feed(self, text: str) -> None:
        index = 0
        while index < len(text):
            char = text[index]
            if char == "\x1b":
                index = self._skip_escape(text, index)
                continue
            index += 1
            if char == "\x07":
                continue
            if char == "\b":
                self._col = max(0, self._col - 1)
            elif char == "\r":
                self._col = 0
            elif char == "\n":
                self._row += 1
                self._lines.append([])
                self._col = 0
            elif char == "\t":
                for _ in range(8 - (self._col % 8)):
                    self._write(" ")
            elif ord(char) >= 0x20 and char != "\x7f":
                self._write(char)

    def _write(self, char: str) -> None:
        line = self._lines[self._row]
        if self._col < len(line):
            line[self._col] = char
        else:
            line.extend(" " * (self._col - len(line)))
            line.append(char)
        self._col += 1

    @staticmethod
    def _skip_escape(text: str, start: int) -> int:
        if start + 1 >= len(text):
            return len(text)
        following = text[start + 1]
        if following == "[":
            index = start + 2
            while index < len(text):
                if 0x40 <= ord(text[index]) <= 0x7E:
                    return index + 1
                index += 1
            return len(text)
        if following == "]":
            index = start + 2
            while index < len(text):
                if text[index] == "\x07":
                    return index + 1
                if text[index] == "\x1b" and index + 1 < len(text) and text[index + 1] == "\\":
                    return index + 2
                index += 1
            return len(text)
        return start + 2


def test_prompt_survives_history_recall_and_backspace() -> None:
    """Recalling history and erasing it must not erase the ``ffai> `` prompt.

    readline can only protect the prompt when it is told about it; printing the
    prompt separately and calling ``input()`` with an empty prompt makes the up
    arrow redraw the recalled line over the prompt and backspace destroy it.
    """
    with _repl_pty() as (process, master_fd):
        output = _read_until(master_fd, PROMPT_MARKER, STARTUP_TIMEOUT)

        time.sleep(0.2)
        _send(master_fd, b"help\r")
        output += _feed_until_prompt(master_fd)

        time.sleep(0.2)
        _send(master_fd, b"\x1b[A")  # up arrow: recall the previous line
        time.sleep(0.2)
        _send(master_fd, b"\x7f" * 8)  # BACKSPACE: erase the recalled line
        time.sleep(0.5)
        output += _drain(master_fd, quiet=0.4)

        screen = _ScreenModel()
        screen.feed(output.decode("utf-8", "replace"))
        visible_line = screen.current_line.rstrip()
        tail = _plain(output.decode("utf-8", "replace"))[-2000:]
        assert visible_line == "ffai>", (
            "history recall + backspace erased the shell prompt; "
            f"last visible line was {visible_line!r}\n"
            f"--- last output ---\n{tail}"
        )

        _exit_repl(master_fd, process)


def test_tab_completes_paths_for_add_and_setoutput(tmp_path: Path) -> None:
    """TAB completes filenames for ``add`` and ``setoutput``, quoting spaces."""
    root = tmp_path.resolve()
    input_file = root / "input.mp4"
    output_file = root / "out.mp4"
    input_file.write_bytes(b"x")
    output_file.write_bytes(b"x")
    spaced_dir = root / "my media"
    spaced_dir.mkdir()
    clip_file = spaced_dir / "clip.mkv"
    clip_file.write_bytes(b"x")

    with _repl_pty() as (process, master_fd):
        output = _read_until(master_fd, PROMPT_MARKER, STARTUP_TIMEOUT)

        # add <partial absolute path> + TAB
        time.sleep(0.2)
        _send(master_fd, b"add " + os.fsencode(str(root / "inp")) + b"\t")
        time.sleep(0.3)
        _send(master_fd, b"\r")
        output += _feed_until_prompt(master_fd)

        text = _plain(output.decode("utf-8", "replace"))
        assert "Added input: " in text, f"`add` did not accept the completion:\n{text[-2000:]}"
        assert _compact(str(input_file)) in _compact(text), (
            f"{str(input_file)!r} missing from:\n{text[-2000:]}"
        )

        # setoutput <partial absolute path> + TAB
        _send(master_fd, b"setoutput " + os.fsencode(str(root / "o")) + b"\t")
        time.sleep(0.3)
        _send(master_fd, b"\r")
        output += _feed_until_prompt(master_fd)

        text = _plain(output.decode("utf-8", "replace"))
        assert "Output set: " in text, f"`setoutput` did not accept the completion:\n{text[-2000:]}"
        assert _compact(str(output_file)) in _compact(text), (
            f"{str(output_file)!r} missing from:\n{text[-2000:]}"
        )

        # add "<partial path under a directory with a space> + TAB: the completed
        # directory keeps a trailing separator and leaves the double quote open,
        # so a second TAB after the file prefix completes the quoted file path.
        _send(master_fd, b'add "' + os.fsencode(str(root / "my me")) + b"\t")
        time.sleep(0.3)
        _send(master_fd, b"cl\t")
        time.sleep(0.3)
        _send(master_fd, b"\r")
        output += _feed_until_prompt(master_fd)

        text = _plain(output.decode("utf-8", "replace"))
        assert "Added input: " in text, (
            f"quoted completion for a path with a space was not added:\n{text[-2000:]}"
        )
        assert _compact(str(clip_file)) in _compact(text), (
            f"{str(clip_file)!r} missing from:\n{text[-2000:]}"
        )

        _exit_repl(master_fd, process)
