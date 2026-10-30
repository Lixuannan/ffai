"""Interactive REPL and Rich presentation for ffai."""

from __future__ import annotations

import shlex
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import assert_never

from pydantic import SecretStr, ValidationError
from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.prompt import Confirm
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from ffai import __version__
from ffai.command_builder import build_command
from ffai.config import (
    API_KEY_ENV,
    MODEL_ENV,
    Settings,
    env_file_path,
    save_llm_settings,
)
from ffai.errors import CommandBuildError, ConfigError, FFAIError, ParseError
from ffai.executor import ExecutionResult, execute_ffmpeg
from ffai.llm import LLMClient
from ffai.models import TASK_DISPLAY_FIELDS, LLMDecision
from ffai.parser import BuiltinCommand, NaturalLanguage, ParsedInput, parse_input
from ffai.providers import (
    CUSTOM_PROVIDER,
    PROVIDER_CHOICES,
    ProviderPreset,
    identify_provider,
    provider_name_for,
)
from ffai.state import SessionState, TaskChange
from ffai.utils import (
    ffmpeg_available,
    format_command,
    format_file_size,
    probe_duration,
)

PROMPT = "[bold cyan]ffai[/bold cyan][bright_black]>[/bright_black] "

_FIELD_LABELS = {
    "video_filters": "Video filters",
    "audio_filters": "Audio filters",
    "filter_complex": "Filter complex",
    "maps": "Stream maps",
    "video_codec": "Video codec",
    "audio_codec": "Audio codec",
    "crf": "CRF",
    "preset": "Preset",
    "video_bitrate": "Video bitrate",
    "audio_bitrate": "Audio bitrate",
    "extra_options": "Extra options",
    "description": "Description",
}

_HELP_ROWS = [
    ("add <file> [file ...]", "Add one or more input media files"),
    ("setoutput <file>", "Set the output file"),
    ("show", "Show the current task state"),
    ("preview", "Build and display the command without running it"),
    ("exec", "Build, confirm, and run the command"),
    ("reset", "Clear the task state"),
    ("config [show|set]", "Show or update the API configuration"),
    ("help", "Show this help"),
    ("exit / quit", "Exit ffai"),
]

_CHINESE_ALIASES = "Chinese aliases: 预览, 显示, 执行, 重置, 配置, 帮助, 退出"


class FFaiRepl:
    def __init__(
        self,
        settings: Settings,
        console: Console | None = None,
    ) -> None:
        self.settings = settings
        self.console = console or Console(highlight=False)
        self.state = SessionState()
        self._llm_client: LLMClient | None = None
        self._running = True

    def run(self) -> None:
        self._render_banner()
        self._require_llm_configuration()
        self._render_startup_notes()
        first_prompt = True
        while self._running:
            if not first_prompt:
                # Keep the prompt visually distinct from every command's output.
                self.console.print()
            first_prompt = False
            try:
                raw = self.console.input(PROMPT)
            except EOFError:
                self.console.print()
                break
            except KeyboardInterrupt:
                self.console.print()
                self.console.print(Text("Press Ctrl+D or type 'exit' to quit.", style="dim"))
                continue

            if not raw.strip():
                continue
            try:
                parsed = parse_input(raw)
            except ParseError as exc:
                self._show_error("Input error", exc)
                continue

            try:
                self._dispatch(parsed)
            except FFAIError as exc:
                self._show_error("Error", exc)
            except KeyboardInterrupt:
                self.console.print()
                self._show_warning("Interrupted. The current task was kept.")
            except BrokenPipeError:
                break

        self.console.print(Text("Goodbye.", style="dim"))

    def _dispatch(self, parsed: ParsedInput) -> None:
        if isinstance(parsed, NaturalLanguage):
            self._handle_natural_language(parsed)
            return

        if not isinstance(parsed, BuiltinCommand):
            assert_never(parsed)

        match parsed.name:
            case "add":
                self._cmd_add(parsed.args)
            case "setoutput":
                self._cmd_setoutput(parsed.args[0])
            case "show":
                self._cmd_show()
            case "preview":
                self._cmd_preview()
            case "exec":
                self._cmd_exec()
            case "reset":
                self._cmd_reset()
            case "config":
                self._cmd_config(parsed.args)
            case "help":
                self._cmd_help()
            case "exit":
                self._running = False
            case _ as unreachable:
                raise AssertionError(f"Unhandled built-in command: {unreachable}")

    def _cmd_add(self, paths: Sequence[str]) -> None:
        result = self.state.add_inputs(paths)
        for path in result.added:
            self._success(f"Added input: {path}")
        for path in result.duplicates:
            self._show_warning(f"Already added: {path}")
        if result.added:
            self.console.print(
                Text(
                    "Tip: set an output with 'setoutput <file>', then describe the operation.",
                    style="dim",
                )
            )
        elif not result.duplicates:
            self._show_warning("No files were added.")

    def _cmd_setoutput(self, path: str) -> None:
        output = self.state.set_output(path)
        self._success(f"Output set: {output}")

    def _cmd_show(self) -> None:
        self.console.print(self._task_panel())

    def _cmd_preview(self) -> None:
        task = self.state.task
        try:
            command = build_command(task)
        except CommandBuildError as exc:
            self._show_error("Cannot build command", exc)
            return
        self.console.print(self._command_panel(command, preview=True))
        self._show_overwrite_notice(task.output)

    def _cmd_exec(self) -> None:
        task = self.state.task
        try:
            command = build_command(task)
        except CommandBuildError as exc:
            self._show_error("Cannot build command", exc)
            return

        self.console.print(self._command_panel(command, preview=False))
        self._show_overwrite_notice(task.output)

        try:
            confirmed = Confirm.ask(
                "Execute this command?",
                console=self.console,
                default=False,
            )
        except (EOFError, KeyboardInterrupt):
            self.console.print()
            self._show_warning("Execution cancelled.")
            return
        if not confirmed:
            self._show_warning("Execution cancelled.")
            return

        assert task.output is not None
        duration = probe_duration(task.inputs[0])
        try:
            result = execute_ffmpeg(
                command,
                expected_output=task.output,
                console=self.console,
                total_duration=duration,
            )
        except KeyboardInterrupt:
            self.console.print()
            self._show_warning("Execution interrupted.")
            return

        self._render_execution_result(result)

    def _cmd_reset(self) -> None:
        self.state.reset()
        self._success("Task state cleared.")

    def _cmd_config(self, args: Sequence[str]) -> None:
        action = args[0] if args else "show"
        if action == "set":
            if self._run_config_wizard():
                self.console.print(self._config_panel())
            return

        self.console.print(self._config_panel())
        self.console.print(
            Text("Use 'config set' to update the API connection settings.", style="dim")
        )

    def _can_prompt(self) -> bool:
        return self.console.is_terminal and sys.stdin.isatty()

    def _require_llm_configuration(self) -> None:
        if self.settings.llm_configured:
            return

        missing = []
        if self.settings.api_key is None:
            missing.append(API_KEY_ENV)
        if self.settings.model is None:
            missing.append(MODEL_ENV)

        if not self._can_prompt():
            raise ConfigError(
                "API configuration is required before ffai can start. Missing: "
                + ", ".join(missing)
                + ". Set the environment variables or run ffai in an interactive "
                "terminal to use the setup wizard."
            )

        intro = Text()
        intro.append("ffai requires an OpenAI-compatible API configuration.\n\n", style="bold")
        intro.append("Missing: ", style="bold")
        intro.append(", ".join(missing))
        intro.append("\n\nComplete the setup below. Ctrl+C cancels startup.", style="dim")
        self.console.print(
            Panel(
                intro,
                title="[bold yellow]API setup required[/bold yellow]",
                border_style="yellow",
                box=box.ROUNDED,
                padding=(1, 2),
            )
        )
        if not self._run_config_wizard():
            raise ConfigError("API configuration was not completed; ffai cannot start.")

    def _run_config_wizard(self) -> bool:
        if not self._can_prompt():
            self._show_error(
                "Configuration error",
                ConfigError("Interactive setup requires a terminal."),
            )
            return False

        instructions = Text()
        instructions.append("Configure the API connection.\n", style="bold")
        instructions.append(
            "Press Enter to keep a current value. Choose a provider by number or ID.\n",
            style="dim",
        )
        instructions.append(f"Settings are saved to {env_file_path()}.", style="dim")
        self.console.print(
            Panel(
                instructions,
                title="[bold]API configuration[/bold]",
                border_style="cyan",
                box=box.ROUNDED,
                padding=(1, 2),
            )
        )

        has_existing_settings = bool(
            self.settings.api_key or self.settings.base_url or self.settings.model
        )
        current_provider = (
            (identify_provider(self.settings.base_url) or CUSTOM_PROVIDER)
            if has_existing_settings
            else None
        )
        self._render_provider_menu(current_provider)
        current_key = self.settings.api_key.get_secret_value() if self.settings.api_key else None
        current_base_url = self.settings.base_url
        current_model = self.settings.model

        try:
            provider = self._ask_provider(current_provider)
            provider_changed = current_provider is None or provider.id != current_provider.id
            self._render_provider_details(provider)
            if provider is CUSTOM_PROVIDER:
                base_url = self._ask_custom_base_url(
                    current_base_url if not provider_changed else None
                )
            else:
                base_url = provider.base_url
            api_key = self._ask_required_secret(
                f"{provider.name} API key",
                current_key if not provider_changed else None,
            )
            model = self._ask_model(
                current_model if not provider_changed else None,
                provider.default_model,
            )
        except (EOFError, KeyboardInterrupt):
            self.console.print()
            self._show_warning("Configuration cancelled; no changes saved.")
            return False

        try:
            candidate = Settings(api_key=api_key, base_url=base_url, model=model)
            candidate.require_llm()
        except (ValidationError, ConfigError) as exc:
            self._show_error("Invalid configuration", ConfigError(_validation_message(exc)))
            return False

        try:
            saved = save_llm_settings(candidate)
        except ConfigError as exc:
            self._show_error("Configuration error", exc)
            return False

        self.settings = candidate
        self._llm_client = None
        self._success(f"API configuration saved to {saved}")
        return True

    def _render_provider_menu(self, current: ProviderPreset | None) -> None:
        table = Table(
            box=box.SIMPLE_HEAD,
            show_edge=False,
            pad_edge=False,
            expand=True,
            padding=(0, 1),
        )
        table.add_column("#", style="bold cyan", no_wrap=True)
        table.add_column("Provider", no_wrap=True)
        table.add_column("Base URL")
        table.add_column("Suggested model", no_wrap=True)
        for index, provider in enumerate(PROVIDER_CHOICES, start=1):
            label = provider.name
            if current is not None and provider.id == current.id:
                label = f"{label} (current)"
            table.add_row(
                str(index),
                label,
                provider.base_url or "(enter a custom URL)",
                provider.default_model or "(enter a model)",
            )
        self.console.print(table)

    def _render_provider_details(self, provider: ProviderPreset) -> None:
        details = Text()
        details.append(provider.name, style="bold")
        if provider.note:
            details.append(f" — {provider.note}", style="dim")
        self.console.print(details)
        if provider.docs_url:
            docs = Text("Docs: ", style="dim")
            docs.append(provider.docs_url, style="dim")
            self.console.print(docs)
        if provider.api_key_url:
            keys = Text("API keys: ", style="dim")
            keys.append(provider.api_key_url, style="dim")
            self.console.print(keys)

    def _ask_provider(self, current: ProviderPreset | None) -> ProviderPreset:
        aliases = {
            "openai": "openai",
            "openrouter": "openrouter",
            "deepseek": "deepseek",
            "glm": "glm",
            "zhipu": "glm",
            "kimi": "kimi",
            "moonshot": "kimi",
            "qwen": "qwen",
            "dashscope": "qwen",
            "custom": "custom",
        }
        hint = (
            f" (Enter keeps {current.name})"
            if current is not None
            else f" (1-{len(PROVIDER_CHOICES)})"
        )
        while True:
            raw = self.console.input(f"[bold]Provider[/bold]{hint} (number or ID): ").strip()
            if not raw:
                if current:
                    return current
                self._show_warning("Choose a provider.")
                continue
            if raw.isdigit():
                index = int(raw) - 1
                if 0 <= index < len(PROVIDER_CHOICES):
                    return PROVIDER_CHOICES[index]
            provider = next(
                (
                    item
                    for item in PROVIDER_CHOICES
                    if item.id == aliases.get(raw.lower(), raw.lower())
                ),
                None,
            )
            if provider is not None:
                return provider
            self._show_warning("Unknown provider. Enter a listed number or provider ID.")

    def _ask_required_secret(self, label: str, current: str | None) -> str:
        while True:
            hint = " (Enter keeps current): " if current else ": "
            value = self.console.input(f"[bold]{label}[/bold]{hint}", password=True).strip()
            if value:
                return value
            if current:
                return current
            self._show_warning(f"{label} is required.")

    def _ask_model(self, current: str | None, suggested: str | None) -> str:
        while True:
            if current:
                hint = " (Enter keeps current): "
            elif suggested:
                hint = f" (default: {suggested}): "
            else:
                hint = ": "
            value = self.console.input(f"[bold]Model[/bold]{hint}").strip()
            if value:
                return value
            if current:
                return current
            if suggested:
                return suggested
            self._show_warning("Model is required.")

    def _ask_custom_base_url(self, current: str | None) -> str:
        hint = " (required; Enter keeps current): " if current else " (required): "
        while True:
            value = self.console.input(f"[bold]Base URL[/bold]{hint}").strip()
            if not value:
                if current:
                    return current
                self._show_warning("Base URL is required for a custom provider.")
                continue
            try:
                validated = Settings(base_url=value).base_url
            except ValidationError as exc:
                self._show_error("Invalid base URL", ConfigError(_validation_message(exc)))
                continue
            if validated is None:
                self._show_warning("Base URL is required for a custom provider.")
                continue
            return validated

    def _config_panel(self) -> Panel:
        table = Table(
            box=box.SIMPLE,
            show_header=False,
            show_edge=False,
            pad_edge=False,
            expand=True,
            padding=(0, 1),
        )
        table.add_column("Field", style="bold cyan", no_wrap=True, width=18)
        table.add_column("Value")
        table.add_row("Provider", Text(provider_name_for(self.settings.base_url)))
        table.add_row("API key", Text(_mask_secret(self.settings.api_key)))
        table.add_row("Model", Text(self.settings.model or "(not set)"))
        table.add_row(
            "Base URL",
            Text(self.settings.base_url or "(OpenAI default)"),
        )
        config_path = env_file_path()
        path_label = str(config_path) if config_path.exists() else f"{config_path} (not created)"
        table.add_row("Config file", Text(path_label))

        return Panel(
            table,
            title="[bold]API configuration[/bold]",
            border_style="cyan",
            box=box.ROUNDED,
            padding=(1, 2),
        )

    def _cmd_help(self) -> None:
        table = Table(
            box=box.SIMPLE_HEAD,
            show_edge=False,
            pad_edge=False,
            expand=True,
            padding=(0, 1),
        )
        table.add_column("Command", style="bold cyan", no_wrap=True)
        table.add_column("Description", style="white")
        for command, description in _HELP_ROWS:
            table.add_row(command, description)

        examples = Text()
        examples.append("Natural language examples\n", style="bold")
        examples.append("  crop the video to 1920x1080, centered\n", style="dim")
        examples.append("  use H.265 with CRF 23\n", style="dim")
        examples.append("  audio AAC at 192k\n\n", style="dim")
        examples.append(
            "Unrecognized input is sent to the LLM. It updates structured task "
            "state; it never executes commands.",
            style="dim",
        )
        examples.append("\n")
        examples.append(_CHINESE_ALIASES, style="dim")

        self.console.print(
            Panel(
                Group(table, examples),
                title="[bold]ffai help[/bold]",
                border_style="cyan",
                box=box.ROUNDED,
                padding=(1, 2),
            )
        )

    def _handle_natural_language(self, request: NaturalLanguage) -> None:
        config = self.settings.require_llm()
        client = self._llm_client
        if client is None:
            client = LLMClient(config)
            self._llm_client = client
        with self.console.status("[cyan]Thinking...[/cyan]", spinner="dots"):
            decision = client.analyze(self.state.llm_context(), request.text)
        self._render_decision(decision)

    def _render_decision(self, decision: LLMDecision) -> None:
        if decision.intent == "apply":
            changes = self.state.apply_patch(decision.patch)
            self.console.print(Panel(Text(decision.explanation), title="ffai", border_style="cyan"))
            if changes:
                self._render_changes(changes)
                self.console.print(
                    Text(
                        "Run 'show' or 'preview' to inspect the updated task.",
                        style="dim",
                    )
                )
            else:
                self._show_warning("The model proposed no effective task changes.")
            if decision.question:
                self.console.print()
                self.console.print(
                    Panel(
                        Text(decision.question),
                        title="[bold yellow]Question[/bold yellow]",
                        border_style="yellow",
                    )
                )
            return

        if decision.intent == "clarify":
            self.console.print(Panel(Text(decision.explanation), title="ffai", border_style="cyan"))
            if decision.question:
                self.console.print(
                    Panel(
                        Text(decision.question),
                        title="[bold yellow]Need clarification[/bold yellow]",
                        border_style="yellow",
                    )
                )
            return

        if decision.intent == "noop":
            self.console.print(Panel(Text(decision.explanation), title="ffai", border_style="cyan"))
            return

        assert_never(decision.intent)

    def _render_execution_result(self, result: ExecutionResult) -> None:
        if result.interrupted:
            self._show_warning(
                "Execution interrupted. A partial output file may exist and can be removed."
            )
            return
        if result.succeeded:
            text = Text()
            text.append("Command completed successfully.\n", style="bold green")
            text.append("Output: ", style="dim")
            text.append(result.output_path)
            size = format_file_size(result.output_path)
            if size:
                text.append(f" ({size})", style="dim")
            text.append(f"\nElapsed: {result.elapsed_seconds:.1f}s", style="dim")
            self.console.print(
                Panel(text, title="[bold green]Done[/bold green]", border_style="green")
            )
            return

        details = Text()
        details.append(f"FFmpeg exited with code {result.exit_code}.", style="bold red")
        if result.stderr_tail:
            details.append("\n\n")
            details.append(result.stderr_tail[-6_000:], style="dim")
        self.console.print(
            Panel(details, title="[bold red]FFmpeg failed[/bold red]", border_style="red")
        )

    def _task_panel(self) -> Panel:
        task = self.state.task
        table = Table(
            box=box.SIMPLE,
            show_header=False,
            show_edge=False,
            pad_edge=False,
            expand=True,
            padding=(0, 1),
        )
        table.add_column("Field", style="bold cyan", no_wrap=True, width=18)
        table.add_column("Value")

        if task.inputs:
            inputs = Text()
            for index, media in enumerate(task.inputs):
                if index:
                    inputs.append("\n")
                inputs.append(f"{index + 1}. ", style="dim")
                inputs.append(media)
            table.add_row("Inputs", inputs)
        else:
            table.add_row("Inputs", Text("(none)", style="dim"))

        table.add_row("Output", Text(task.output) if task.output else Text("(none)", style="dim"))
        table.add_row("Description", Text(task.description or "(none)"))

        for field in TASK_DISPLAY_FIELDS:
            if field == "description":
                continue
            value = getattr(task, field)
            table.add_row(_FIELD_LABELS[field], _format_field(field, value))

        return Panel(
            table,
            title=f"[bold]Current task[/bold] [dim]revision {self.state.revision}[/dim]",
            border_style="cyan",
            box=box.ROUNDED,
            padding=(1, 2),
        )

    def _command_panel(self, command: Sequence[str], *, preview: bool) -> Panel:
        title = (
            "[bold]Preview[/bold] [dim]not executed[/dim]"
            if preview
            else "[bold]Command to execute[/bold]"
        )
        syntax = Syntax(
            format_command(command),
            "bash",
            theme="monokai",
            word_wrap=True,
            padding=0,
            background_color="default",
        )
        return Panel(
            syntax,
            title=title,
            border_style="bright_blue" if preview else "yellow",
            box=box.ROUNDED,
            padding=(1, 2),
        )

    def _render_changes(self, changes: Sequence[TaskChange]) -> None:
        table = Table(
            title="Updated fields",
            box=box.SIMPLE_HEAD,
            show_edge=False,
            header_style="bold",
            padding=(0, 1),
        )
        table.add_column("Field", style="cyan", no_wrap=True)
        table.add_column("Before", style="dim")
        table.add_column("After", style="white")
        for change in changes:
            label = _FIELD_LABELS.get(change.field, change.field)
            table.add_row(
                label,
                Text(_format_change_value(change.field, change.before)),
                Text(_format_change_value(change.field, change.after)),
            )
        self.console.print(table)

    def _show_overwrite_notice(self, output: str | None) -> None:
        if output and Path(output).exists():
            self.console.print(
                Text(
                    "Warning: the output file already exists and will be overwritten.",
                    style="yellow",
                )
            )

    def _render_banner(self) -> None:
        self.console.print(f"[bold cyan]ffai[/bold cyan] [dim]v{__version__}[/dim]")
        self.console.print(Text("Natural Language Interface for FFmpeg", style="dim"))
        self.console.print()

    def _render_startup_notes(self) -> None:
        provider = provider_name_for(self.settings.base_url)
        endpoint = self.settings.base_url or "OpenAI default"
        api_line = Text()
        api_line.append("API: ", style="dim")
        api_line.append(f"{provider} / {self.settings.model} at {endpoint}", style="dim")
        self.console.print(api_line)
        if not ffmpeg_available():
            self.console.print(
                Text(
                    "FFmpeg was not found on PATH. Install it before running commands.",
                    style="yellow",
                )
            )
        self.console.print(
            Text(
                "Type 'help' for commands, or describe a video operation in natural "
                "language. 'exit' quits.",
                style="dim",
            )
        )
        self.console.print()

    def _success(self, message: str) -> None:
        text = Text()
        text.append("✓ ", style="green")
        text.append(message)
        self.console.print(text)

    def _show_warning(self, message: str) -> None:
        text = Text()
        text.append("! ", style="yellow")
        text.append(message, style="yellow")
        self.console.print(text)

    def _show_error(self, title: str, exc: FFAIError) -> None:
        self.console.print(
            Panel(
                Text(str(exc), style="red"),
                title=f"[bold red]{title}[/bold red]",
                border_style="red",
                box=box.ROUNDED,
            )
        )


def _format_field(field: str, value: object) -> Text:
    if value is None or value == [] or value == "":
        return Text("(not set)", style="dim")
    if field in {"video_filters", "audio_filters"}:
        return Text(", ".join(str(item) for item in value))
    if field == "maps":
        return Text(", ".join(str(item) for item in value))
    if field == "extra_options":
        return Text(shlex.join(str(item) for item in value))
    return Text(str(value))


def _format_change_value(field: str, value: object) -> str:
    if value is None or value == [] or value == "":
        return "(not set)"
    if isinstance(value, list):
        if field == "extra_options":
            return shlex.join(str(item) for item in value)
        return ", ".join(str(item) for item in value)
    return str(value)


def _mask_secret(secret: SecretStr | None) -> str:
    if secret is None:
        return "(not set)"
    value = secret.get_secret_value()
    if len(value) <= 8:
        return "********"
    return f"********{value[-4:]}"


def _validation_message(exc: ValidationError | ConfigError) -> str:
    if isinstance(exc, ConfigError):
        return str(exc)
    return "; ".join(error["msg"] for error in exc.errors())
