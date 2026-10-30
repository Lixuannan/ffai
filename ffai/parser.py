"""Parse REPL input into built-in commands or natural-language text."""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import Literal, TypeAlias

from ffai.errors import ParseError

BuiltinName = Literal[
    "add",
    "setoutput",
    "show",
    "preview",
    "exec",
    "reset",
    "help",
    "exit",
]

# Aliases are deliberately exact, single-token names. This keeps ordinary
# natural-language sentences from being mistaken for built-ins.
_ALIASES: dict[str, BuiltinName] = {
    "add": "add",
    "setoutput": "setoutput",
    "show": "show",
    "preview": "preview",
    "config": "config",
    "配置": "config",
    "exec": "exec",
    "reset": "reset",
    "help": "help",
    "exit": "exit",
    "quit": "exit",
    "?": "help",
    "预览": "preview",
    "显示": "show",
    "执行": "exec",
    "重置": "reset",
    "帮助": "help",
    "退出": "exit",
}

_NO_ARGUMENT_COMMANDS: set[BuiltinName] = {
    "show",
    "preview",
    "exec",
    "reset",
    "help",
    "exit",
}


@dataclass(frozen=True, slots=True)
class BuiltinCommand:
    name: BuiltinName
    args: tuple[str, ...]
    raw: str


@dataclass(frozen=True, slots=True)
class NaturalLanguage:
    text: str


ParsedInput: TypeAlias = BuiltinCommand | NaturalLanguage


def parse_input(raw: str) -> ParsedInput:
    """Parse one line of REPL input.

    Built-ins use shell-like quoting so paths containing spaces work. Any
    first token that is not a built-in is treated as natural language.
    """

    stripped = raw.strip()
    if not stripped:
        raise ParseError("Input is empty")

    try:
        tokens = shlex.split(stripped, posix=True)
    except ValueError as exc:
        raise ParseError(f"Could not parse quoting: {exc}") from exc

    if not tokens:
        raise ParseError("Input is empty")

    command_name = _ALIASES.get(tokens[0])
    if command_name is None:
        return NaturalLanguage(text=stripped)

    args = tuple(tokens[1:])
    if command_name in _NO_ARGUMENT_COMMANDS:
        if args:
            raise ParseError(f"{tokens[0]} does not accept arguments")
    elif command_name == "add":
        if not args:
            raise ParseError("Usage: add <input> [input ...]")
    elif command_name == "setoutput" and len(args) != 1:
        raise ParseError("Usage: setoutput <output>")
    elif command_name == "config" and args not in {(), ("show",), ("set",)}:
        raise ParseError("Usage: config [show|set]")

    return BuiltinCommand(name=command_name, args=args, raw=stripped)
