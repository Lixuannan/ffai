from __future__ import annotations

import os
from io import StringIO
from pathlib import Path

import pytest
from rich.console import Console

from ffai.line_input import (
    Completion,
    _readline_prompt,
    complete_line,
    read_line,
)
from ffai.repl import PROMPT


@pytest.fixture
def files(tmp_path: Path) -> Path:
    (tmp_path / "input.mp4").write_bytes(b"placeholder")
    (tmp_path / "movie.mkv").write_bytes(b"placeholder")
    (tmp_path / "notes.md").write_text("# Notes\n", encoding="utf-8")
    (tmp_path / "my file.mp4").write_bytes(b"placeholder")
    (tmp_path / "my dir").mkdir()
    (tmp_path / "my dir" / "clip.mkv").write_bytes(b"placeholder")
    (tmp_path / ".hidden").write_bytes(b"placeholder")
    return tmp_path


def _candidate_names(result: Completion | None) -> tuple[str, ...]:
    assert result is not None
    return result.candidates


def test_completes_file_after_add(files: Path) -> None:
    result = complete_line(f"add {files}/in")

    assert result is not None
    assert result.start == len("add ")
    assert result.candidates == (str(files / "input.mp4"),)


def test_completes_every_add_argument(files: Path) -> None:
    line = f"add {files}/input.mp4 {files}/mo"

    result = complete_line(line)

    assert result is not None
    assert result.start == line.index(f"{files}/mo")
    assert result.candidates == (f"{files}/movie.mkv",)


def test_uncertain_prefix_lists_directories_and_escapes_spaces(files: Path) -> None:
    result = complete_line(f"add {files}/m")

    candidates = _candidate_names(result)
    assert f"{files}/movie.mkv" in candidates
    assert f"{files}/my\\ dir/" in candidates
    assert f"{files}/my\\ file.mp4" in candidates
    assert candidates == tuple(sorted(candidates, key=str.lower))


def test_directory_candidate_keeps_trailing_separator(files: Path) -> None:
    result = complete_line(f"add {files}/my\\ d")
    assert result is not None

    (candidate,) = result.candidates
    assert candidate.endswith(os.sep)
    assert candidate == f"{files}/my\\ dir/"


def test_quoted_context_stays_open_for_directories_and_closes_for_files(tmp_path: Path) -> None:
    (tmp_path / "my file.mp4").write_bytes(b"placeholder")
    (tmp_path / "my dir").mkdir()

    files = complete_line(f'add "{tmp_path}/my fi')
    directories = complete_line(f'add "{tmp_path}/my d')

    assert files is not None and directories is not None
    assert files.candidates == (f'"{tmp_path}/my file.mp4"',)
    assert directories.candidates == (f'"{tmp_path}/my dir{os.sep}',)


def test_quoted_path_containing_spaces_can_be_navigated(tmp_path: Path) -> None:
    spaced = tmp_path / "my media"
    spaced.mkdir()
    (spaced / "clip.mkv").write_bytes(b"placeholder")

    result = complete_line(f'add "{tmp_path}/my me')

    assert result is not None
    assert result.candidates == (f'"{spaced}{os.sep}',)

    deeper = complete_line(f'add "{spaced}/cl')
    assert deeper is not None
    assert deeper.candidates == (f'"{spaced}/clip.mkv"',)


def test_uncertain_quoted_prefix_keeps_candidates_quoted(tmp_path: Path) -> None:
    (tmp_path / "my file.mp4").write_bytes(b"placeholder")
    (tmp_path / "my folder.mp4").write_bytes(b"placeholder")

    result = complete_line(f'add "{tmp_path}/my f')

    candidates = _candidate_names(result)
    assert candidates == (
        f'"{tmp_path}/my file.mp4"',
        f'"{tmp_path}/my folder.mp4"',
    )


def test_completes_setoutput_argument(files: Path) -> None:
    result = complete_line(f"setoutput {files}/in")

    assert result is not None
    assert result.candidates == (str(files / "input.mp4"),)


def test_setoutput_never_completes_a_second_argument(files: Path) -> None:
    assert complete_line(f"setoutput {files}/input.mp4 ") is None
    assert complete_line(f"setoutput {files}/input.mp4 mo") is None


def test_add_accepts_a_new_argument_after_trailing_space(
    files: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(files)
    result = complete_line(f"add {files}/input.mp4 ")

    assert result is not None
    assert result.start == len(f"add {files}/input.mp4 ")
    assert "input.mp4" in result.candidates


def test_open_quote_completes_inside_a_directory_with_spaces(tmp_path: Path) -> None:
    spaced = tmp_path / "my media"
    spaced.mkdir()
    (spaced / "clip.mkv").write_bytes(b"placeholder")

    result = complete_line(f'add "{spaced}/{os.sep}cl')

    assert result is not None
    assert result.start == len("add ")
    assert result.candidates == (f'"{spaced}/{os.sep}clip.mkv"',)


def test_hidden_entries_require_a_dot_prefix(files: Path) -> None:
    visible = complete_line(f"add {files}/")
    hidden = complete_line(f"add {files}/.")

    assert visible is not None
    assert f"{files}/.hidden" not in visible.candidates
    assert hidden is not None
    assert f"{files}/.hidden" in hidden.candidates


def test_tilde_completion_expands_for_lookup_but_keeps_tilde(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / "document.md").write_text("# Doc\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))

    result = complete_line("add ~/doc")

    assert result is not None
    assert result.candidates == ("~/document.md",)


def test_cursor_ignores_text_after_it(files: Path) -> None:
    line = f"add {files}/in trailing text"
    cursor = len(f"add {files}/in")

    result = complete_line(line, cursor)

    assert result is not None
    assert result.candidates == (str(files / "input.mp4"),)


@pytest.mark.parametrize(
    "line",
    [
        "",
        "   ",
        "show",
        "tool ffmpeg",
        "help",
        "convert this file to mp4",
        "add",
        "setoutput",
    ],
)
def test_no_completion_outside_path_arguments(line: str) -> None:
    assert complete_line(line) is None


def test_read_line_non_interactive_prints_rich_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    buffer = StringIO()
    console = Console(file=buffer, color_system=None)
    monkeypatch.setattr("builtins.input", lambda prompt="": "help")

    assert read_line(console, PROMPT, interactive=False) == "help"
    assert buffer.getvalue() == "ffai> "


def test_read_line_interactive_passes_protected_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("readline")
    captured: list[str] = []

    def fake_input(prompt: str = "") -> str:
        captured.append(prompt)
        return "help"

    console = Console(color_system="standard", force_terminal=True)
    monkeypatch.setattr("builtins.input", fake_input)

    assert read_line(console, PROMPT, interactive=True) == "help"
    assert len(captured) == 1
    prompt = captured[0]
    assert "\001" in prompt and "\002" in prompt

    plain = prompt.replace("\001", "").replace("\002", "")
    for escape in ("\x1b[1;36m", "\x1b[90m", "\x1b[0m"):
        plain = plain.replace(escape, "")
    assert plain == "ffai> "


def test_readline_prompt_has_no_ansi_without_color() -> None:
    console = Console(color_system=None)

    assert _readline_prompt(console, PROMPT) == "ffai> "
