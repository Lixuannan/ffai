"""Command-line entry point for ffai."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from ffai import __version__
from ffai.config import Settings
from ffai.errors import ConfigError
from ffai.i18n import Translator, resolve_language
from ffai.repl import FFaiRepl


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ffai",
        description="Natural-language, stateful FFmpeg command generator.",
    )
    parser.add_argument(
        "--lang",
        choices=("en", "zh"),
        default=None,
        help="UI language (default: FFAI_LANG or system locale)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    translator = Translator(resolve_language(args.lang))
    console = Console(highlight=False)

    try:
        settings = Settings.load()
    except ConfigError as exc:
        console.print(
            Panel(
                Text(str(exc), style="red"),
                title=translator("cli.config_error_title"),
                border_style="red",
            )
        )
        return 2

    # Settings.load populates os.environ from .env, so re-resolve here to let
    # FFAI_LANG live in either the process environment or the project .env.
    translator = Translator(resolve_language(args.lang))
    _configure_readline()
    try:
        FFaiRepl(settings, console=console, translator=translator).run()
    except ConfigError as exc:
        console.print(
            Panel(
                Text(str(exc), style="red"),
                title=translator("cli.config_required_title"),
                border_style="red",
            )
        )
        return 2
    except KeyboardInterrupt:
        console.print()
        console.print(Text(translator("cli.interrupted"), style="dim"))
        return 130
    except BrokenPipeError:
        return 0
    return 0


def _configure_readline() -> None:
    try:
        import readline
    except ImportError:
        # readline is unavailable on some platforms; Console.input still works,
        # only arrow-key input history is lost.
        return
    try:
        readline.set_history_length(1_000)
    except (AttributeError, OSError):
        # A stripped readline implementation may not expose history controls.
        return


if __name__ == "__main__":
    raise SystemExit(main())
