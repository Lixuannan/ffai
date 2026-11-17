"""Readline-backed interactive input: a protected prompt and path completion.

The REPL prompt must be handed to readline as the actual input prompt. When it
is printed separately and ``input()`` is called without a prompt, readline does
not know where the editable line starts, so recalling history or deleting text
can overwrite the prompt. The helpers here keep the prompt owned by readline and
add TAB completion of file paths for the commands that take one.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from rich.console import Console
from rich.text import Text

# Commands whose argument is a filesystem path, so TAB may complete it.
_PATH_COMMANDS = frozenset({"add", "setoutput"})

# readline treats text between these markers as zero-width (the prompt escapes).
_IGNORE_START = "\001"
_IGNORE_END = "\002"

_WHITESPACE = " \t\n"
_QUOTES = "\"'"
# Characters that shlex would give a special meaning outside quotes.
_UNQUOTED_SPECIAL = frozenset(_WHITESPACE + _QUOTES + "\\")

_HISTORY_LENGTH = 1_000


@dataclass(frozen=True, slots=True)
class Completion:
    """Replacement candidates for ``line[start:cursor]``.

    ``start`` is the absolute index where the current shell word begins,
    including any opening quote or backslash escapes.
    """

    start: int
    candidates: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _Word:
    start: int
    end: int
    value: str
    open_quote: str | None


def _load_readline() -> ModuleType | None:
    try:
        import readline
    except ImportError:
        return None
    return readline


def _is_editline(readline: ModuleType) -> bool:
    backend = getattr(readline, "backend", None)
    if backend is not None:
        return backend == "editline"
    return "libedit" in (readline.__doc__ or "")


def configure_line_editing() -> bool:
    """Enable REPL history and TAB completion; return whether readline works."""

    readline = _load_readline()
    if readline is None:
        return False
    try:
        readline.set_history_length(_HISTORY_LENGTH)
        # An empty delimiter set makes the whole line one completion word. That
        # lets quoted paths with spaces be replaced as a unit.
        readline.set_completer_delims("")
        readline.set_completer(_make_completer(readline))
        if _is_editline(readline):
            # libedit does not understand GNU readline's "tab: complete" syntax.
            readline.parse_and_bind("bind ^I rl_complete")
        else:
            readline.parse_and_bind("tab: complete")
    except (AttributeError, OSError):
        # A stripped readline build may not expose these controls.
        return False
    return True


def read_line(console: Console, prompt_markup: str, *, interactive: bool) -> str:
    """Read one REPL line.

    Interactive terminals pass a styled prompt to ``input()`` so readline owns
    it and cannot erase it while editing. Non-interactive runs keep the rich
    fallback, which prints the prompt before reading piped input.
    """

    if not interactive or _load_readline() is None:
        return console.input(prompt_markup)
    return input(_readline_prompt(console, prompt_markup))


def _readline_prompt(console: Console, prompt_markup: str) -> str:
    text = Text.from_markup(prompt_markup)
    color_system = console.color_system
    if color_system is None:
        return text.plain
    parts: list[str] = []
    for segment in text.render(console):
        if not segment.text:
            continue
        if segment.style is None:
            parts.append(segment.text)
            continue
        rendered = segment.style.render(segment.text, color_system=color_system)
        if rendered == segment.text:
            parts.append(segment.text)
        else:
            parts.append(_IGNORE_START + rendered + _IGNORE_END)
    return "".join(parts)


def _make_completer(readline: ModuleType):
    matches: list[str] = []

    def complete(text: str, state: int) -> str | None:
        if state == 0:
            line = readline.get_line_buffer()
            result = complete_line(line, readline.get_endidx())
            if result is None:
                matches.clear()
            else:
                matches[:] = [line[: result.start] + candidate for candidate in result.candidates]
        if state < len(matches):
            return matches[state]
        return None

    return complete


def complete_line(
    line: str,
    cursor: int | None = None,
    *,
    cwd: Path | None = None,
) -> Completion | None:
    """Complete a path token for ``add`` or ``setoutput``.

    ``Completion.start`` points at the beginning of the current shell word (not
    at the last whitespace), so candidates include their own quoting and replace
    the whole word.
    """

    if cursor is None:
        cursor = len(line)
    cursor = max(0, min(cursor, len(line)))
    prefix = line[:cursor]
    words = list(_scan_words(prefix))
    if not words or words[0].value not in _PATH_COMMANDS:
        return None

    command = words[0].value
    current = words[-1] if words[-1].end == cursor else None
    if current is None:
        if command == "setoutput" and len(words) >= 2:
            # setoutput takes exactly one argument; do not offer a second one.
            return None
        start = cursor
        value = ""
        quote = None
    else:
        if command == "add" and len(words) == 1:
            return None
        if command == "setoutput" and len(words) != 2:
            return None
        start = current.start
        value = current.value
        quote = current.open_quote

    base_dir = Path(cwd) if cwd is not None else Path.cwd()
    candidates = _path_candidates(value, base_dir=base_dir, quote=quote)
    if not candidates:
        return None
    return Completion(start=start, candidates=tuple(candidates))


def _scan_words(text: str) -> Iterator[_Word]:
    index = 0
    length = len(text)
    while index < length:
        while index < length and text[index].isspace():
            index += 1
        if index >= length:
            return
        start = index
        value: list[str] = []
        quote: str | None = None
        while index < length:
            char = text[index]
            if quote is None and char in _WHITESPACE:
                break
            if char == "\\" and quote != "'":
                if index + 1 < length:
                    value.append(text[index + 1])
                    index += 2
                else:
                    value.append(char)
                    index += 1
                continue
            if quote is None:
                if char in _QUOTES:
                    quote = char
                    index += 1
                    continue
                value.append(char)
                index += 1
                continue
            if char == quote:
                quote = None
                index += 1
                continue
            value.append(char)
            index += 1
        yield _Word(
            start=start,
            end=index,
            value="".join(value),
            open_quote=quote,
        )


def _path_candidates(value: str, *, base_dir: Path, quote: str | None) -> list[str]:
    if value.startswith("~") and os.sep not in value and "/" not in value:
        # Bare "~user" cannot be completed without enumerating system accounts.
        return []
    head, base = _split_path(value)
    directory = _resolve_directory(head, base_dir)
    if directory is None:
        return []

    candidates: list[str] = []
    try:
        entries = sorted(os.scandir(directory), key=lambda entry: entry.name.lower())
    except OSError:
        # The directory disappeared or is unreadable; nothing to offer.
        return []
    for entry in entries:
        if not entry.name.startswith(base):
            continue
        if entry.name.startswith(".") and not base.startswith("."):
            continue
        path_text = head + entry.name
        try:
            is_dir = entry.is_dir()
        except OSError:
            # A dangling symlink or vanished entry is offered as a plain file.
            is_dir = False
        candidates.append(_render_candidate(path_text, is_dir=is_dir, quote=quote))
    return candidates


def _split_path(value: str) -> tuple[str, str]:
    index = max(value.rfind("/"), value.rfind(os.sep))
    if index < 0:
        return "", value
    return value[: index + 1], value[index + 1 :]


def _resolve_directory(head: str, base_dir: Path) -> Path | None:
    if not head:
        return base_dir
    expanded = Path(os.path.expanduser(head))
    directory = expanded if expanded.is_absolute() else base_dir / expanded
    return directory if directory.is_dir() else None


def _render_candidate(path: str, *, is_dir: bool, quote: str | None) -> str:
    separator = os.sep
    if quote is None:
        rendered = _escape_unquoted(path)
        return rendered + separator if is_dir else rendered

    escaped = path.replace("\\", "\\\\").replace(quote, "\\" + quote)
    # Keep the quote open while the user navigates into a directory.
    rendered = quote + escaped + ("" if is_dir else quote)
    return rendered + separator if is_dir else rendered


def _escape_unquoted(value: str) -> str:
    if not any(char in _UNQUOTED_SPECIAL for char in value):
        return value
    return "".join("\\" + char if char in _UNQUOTED_SPECIAL else char for char in value)
