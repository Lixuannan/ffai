from __future__ import annotations

import pytest

from ffai.errors import ParseError
from ffai.parser import BuiltinCommand, NaturalLanguage, parse_input


def test_parses_add_with_multiple_paths() -> None:
    parsed = parse_input("add one.mp4 two.mov")
    assert parsed == BuiltinCommand(
        name="add",
        args=("one.mp4", "two.mov"),
        raw="add one.mp4 two.mov",
    )


def test_parses_quoted_path_with_spaces() -> None:
    parsed = parse_input('add "my video.mp4"')
    assert isinstance(parsed, BuiltinCommand)
    assert parsed.name == "add"
    assert parsed.args == ("my video.mp4",)


def test_parses_setoutput() -> None:
    parsed = parse_input("setoutput final.mp4")
    assert parsed == BuiltinCommand(
        name="setoutput",
        args=("final.mp4",),
        raw="setoutput final.mp4",
    )


def test_parses_config_show_and_set() -> None:
    for raw, expected in [("config", ()), ("config show", ("show",)), ("config set", ("set",))]:
        parsed = parse_input(raw)
        assert isinstance(parsed, BuiltinCommand)
        assert parsed.name == "config"
        assert parsed.args == expected


def test_parses_chinese_config_alias() -> None:
    parsed = parse_input("配置")
    assert isinstance(parsed, BuiltinCommand)
    assert parsed.name == "config"


def test_config_rejects_unknown_subcommand() -> None:
    with pytest.raises(ParseError, match="Usage: config"):
        parse_input("config reset")


def test_parses_quit_as_exit() -> None:
    parsed = parse_input("quit")
    assert isinstance(parsed, BuiltinCommand)
    assert parsed.name == "exit"


def test_parses_chinese_preview_alias() -> None:
    parsed = parse_input("预览")
    assert isinstance(parsed, BuiltinCommand)
    assert parsed.name == "preview"


def test_unrecognized_input_is_natural_language() -> None:
    parsed = parse_input("把视频裁剪到 1920x1080，保持中央构图")
    assert parsed == NaturalLanguage(text="把视频裁剪到 1920x1080，保持中央构图")


def test_leading_whitespace_is_preserved_in_text_but_trimmed_at_edges() -> None:
    parsed = parse_input("  use H.265 encoding  ")
    assert parsed == NaturalLanguage(text="use H.265 encoding")


def test_add_requires_at_least_one_argument() -> None:
    with pytest.raises(ParseError, match="Usage: add"):
        parse_input("add")


def test_setoutput_requires_exactly_one_argument() -> None:
    with pytest.raises(ParseError, match="Usage: setoutput"):
        parse_input("setoutput")
    with pytest.raises(ParseError, match="Usage: setoutput"):
        parse_input("setoutput one.mp4 two.mp4")


@pytest.mark.parametrize("command", ["show", "preview", "exec", "reset", "help", "exit"])
def test_no_argument_commands_reject_arguments(command: str) -> None:
    with pytest.raises(ParseError, match="does not accept arguments"):
        parse_input(f"{command} extra")


def test_rejects_unbalanced_quotes() -> None:
    with pytest.raises(ParseError, match="quoting"):
        parse_input('add "unterminated')


def test_empty_input_is_rejected() -> None:
    with pytest.raises(ParseError, match="empty"):
        parse_input("   ")
