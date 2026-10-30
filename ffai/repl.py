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
from ffai.i18n import Translator, resolve_language
from ffai.llm import LLMClient
from ffai.models import TASK_DISPLAY_FIELDS, LLMDecision
from ffai.parser import BuiltinCommand, NaturalLanguage, ParsedInput, parse_input
from ffai.providers import (
    CUSTOM_PROVIDER,
    PROVIDER_CHOICES,
    ProviderPreset,
    identify_provider,
)
from ffai.state import SessionState, TaskChange
from ffai.utils import (
    ffmpeg_available,
    format_command,
    format_file_size,
    probe_duration,
)

PROMPT = "[bold cyan]ffai[/bold cyan][bright_black]>[/bright_black] "

_FIELD_LABEL_KEYS = {
    "video_filters": "field.video_filters",
    "audio_filters": "field.audio_filters",
    "filter_complex": "field.filter_complex",
    "maps": "field.maps",
    "video_codec": "field.video_codec",
    "audio_codec": "field.audio_codec",
    "crf": "field.crf",
    "preset": "field.preset",
    "video_bitrate": "field.video_bitrate",
    "audio_bitrate": "field.audio_bitrate",
    "extra_options": "field.extra_options",
    "description": "field.description",
}

_HELP_ROWS = [
    ("add <file> [file ...]", "help.add"),
    ("setoutput <file>", "help.setoutput"),
    ("show", "help.show"),
    ("preview", "help.preview"),
    ("exec", "help.exec"),
    ("reset", "help.reset"),
    ("config [show|set]", "help.config"),
    ("help", "help.help"),
    ("exit / quit", "help.exit"),
]


class FFaiRepl:
    def __init__(
        self,
        settings: Settings,
        console: Console | None = None,
        translator: Translator | None = None,
    ) -> None:
        self.settings = settings
        self.console = console or Console(highlight=False)
        self.t = translator or Translator(resolve_language())
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
                self.console.print(Text(self.t("loop.quit_hint"), style="dim"))
                continue

            if not raw.strip():
                continue
            try:
                parsed = parse_input(raw)
            except ParseError as exc:
                self._show_error(self.t("error.input_title"), exc)
                continue

            try:
                self._dispatch(parsed)
            except FFAIError as exc:
                self._show_error(self.t("error.title"), exc)
            except KeyboardInterrupt:
                self.console.print()
                self._show_warning(self.t("loop.interrupt_kept"))
            except BrokenPipeError:
                break

        self.console.print(Text(self.t("loop.goodbye"), style="dim"))

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
            self._success(self.t("action.added", path=path))
        for path in result.duplicates:
            self._show_warning(self.t("action.duplicate", path=path))
        if result.added:
            self.console.print(Text(self.t("action.add_tip"), style="dim"))
        elif not result.duplicates:
            self._show_warning(self.t("action.no_files"))

    def _cmd_setoutput(self, path: str) -> None:
        output = self.state.set_output(path)
        self._success(self.t("action.output_set", path=output))

    def _cmd_show(self) -> None:
        self.console.print(self._task_panel())

    def _cmd_preview(self) -> None:
        task = self.state.task
        try:
            command = build_command(task)
        except CommandBuildError as exc:
            self._show_error(self.t("error.cannot_build_title"), exc)
            return
        self.console.print(self._command_panel(command, preview=True))
        self._show_overwrite_notice(task.output)

    def _cmd_exec(self) -> None:
        task = self.state.task
        try:
            command = build_command(task)
        except CommandBuildError as exc:
            self._show_error(self.t("error.cannot_build_title"), exc)
            return

        self.console.print(self._command_panel(command, preview=False))
        self._show_overwrite_notice(task.output)

        try:
            confirmed = Confirm.ask(
                self.t("panel.confirm_execute"),
                console=self.console,
                default=False,
            )
        except (EOFError, KeyboardInterrupt):
            self.console.print()
            self._show_warning(self.t("execution.cancelled"))
            return
        if not confirmed:
            self._show_warning(self.t("execution.cancelled"))
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
            self._show_warning(self.t("execution.interrupted"))
            return

        self._render_execution_result(result)

    def _cmd_reset(self) -> None:
        self.state.reset()
        self._success(self.t("action.reset"))

    def _cmd_config(self, args: Sequence[str]) -> None:
        action = args[0] if args else "show"
        if action == "set":
            if self._run_config_wizard():
                self.console.print(self._config_panel())
            return

        self.console.print(self._config_panel())
        self.console.print(Text(self.t("config.show_hint"), style="dim"))

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
            raise ConfigError(self.t("startup.noninteractive", missing=", ".join(missing)))

        intro = Text()
        intro.append(self.t("startup.setup_required_intro"), style="bold")
        intro.append(self.t("startup.missing_label"), style="bold")
        intro.append(", ".join(missing))
        intro.append(self.t("startup.setup_hint"), style="dim")
        self.console.print(
            Panel(
                intro,
                title=self.t("config.setup_required_title"),
                border_style="yellow",
                box=box.ROUNDED,
                padding=(1, 2),
            )
        )
        if not self._run_config_wizard():
            raise ConfigError(self.t("startup.setup_cancelled"))

    def _run_config_wizard(self) -> bool:
        if not self._can_prompt():
            self._show_error(
                self.t("error.config_title"),
                ConfigError(self.t("config.interactive_required")),
            )
            return False

        instructions = Text()
        instructions.append(self.t("config.wizard_intro"), style="bold")
        instructions.append(self.t("config.wizard_hint"), style="dim")
        instructions.append(self.t("config.save_location", path=env_file_path()), style="dim")
        self.console.print(
            Panel(
                instructions,
                title=self.t("config.title"),
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
                self._provider_name(provider),
                current_key if not provider_changed else None,
            )
            model = self._ask_model(
                current_model if not provider_changed else None,
                provider.default_model,
            )
        except (EOFError, KeyboardInterrupt):
            self.console.print()
            self._show_warning(self.t("config.setup_cancelled"))
            return False

        try:
            candidate = Settings(api_key=api_key, base_url=base_url, model=model)
            candidate.require_llm()
        except (ValidationError, ConfigError) as exc:
            self._show_error(
                self.t("error.invalid_config_title"), ConfigError(_validation_message(exc))
            )
            return False

        try:
            saved = save_llm_settings(candidate)
        except ConfigError as exc:
            self._show_error(self.t("error.config_title"), exc)
            return False

        self.settings = candidate
        self._llm_client = None
        self._success(self.t("action.config_saved", path=saved))
        return True

    def _provider_name(self, provider: ProviderPreset) -> str:
        if self.t.language == "zh" and provider.name_zh:
            return provider.name_zh
        return provider.name

    def _provider_note(self, provider: ProviderPreset) -> str | None:
        if self.t.language == "zh" and provider.note_zh:
            return provider.note_zh
        return provider.note

    def _current_provider(self) -> ProviderPreset:
        return identify_provider(self.settings.base_url) or CUSTOM_PROVIDER

    def _render_provider_menu(self, current: ProviderPreset | None) -> None:
        table = Table(
            box=box.SIMPLE_HEAD,
            show_edge=False,
            pad_edge=False,
            expand=True,
            padding=(0, 1),
        )
        table.add_column(self.t("config.column_number"), style="bold cyan", no_wrap=True)
        table.add_column(self.t("config.column_provider"), no_wrap=True)
        table.add_column(self.t("config.column_base_url"))
        table.add_column(self.t("config.column_model"), no_wrap=True)
        for index, provider in enumerate(PROVIDER_CHOICES, start=1):
            label = self._provider_name(provider)
            if current is not None and provider.id == current.id:
                label = self.t("config.current_marker", name=label)
            table.add_row(
                str(index),
                label,
                provider.base_url or self.t("config.custom_url_placeholder"),
                provider.default_model or self.t("config.custom_model_placeholder"),
            )
        self.console.print(table)

    def _render_provider_details(self, provider: ProviderPreset) -> None:
        details = Text()
        details.append(self._provider_name(provider), style="bold")
        note = self._provider_note(provider)
        if note:
            details.append(f" — {note}", style="dim")
        self.console.print(details)
        if provider.docs_url:
            docs = Text(self.t("config.docs_label"), style="dim")
            docs.append(provider.docs_url, style="dim")
            self.console.print(docs)
        if provider.api_key_url:
            keys = Text(self.t("config.api_keys_label"), style="dim")
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
        prompt = (
            self.t("config.provider_prompt_keep", current=self._provider_name(current))
            if current is not None
            else self.t("config.provider_prompt_new", count=len(PROVIDER_CHOICES))
        )
        while True:
            raw = self.console.input(prompt).strip()
            if not raw:
                if current:
                    return current
                self._show_warning(self.t("config.provider_required"))
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
            self._show_warning(self.t("config.provider_unknown"))

    def _ask_required_secret(self, provider: str, current: str | None) -> str:
        if current:
            prompt = self.t("config.api_key_prompt_keep", provider=provider)
        else:
            prompt = self.t("config.api_key_prompt_new", provider=provider)
        while True:
            value = self.console.input(prompt, password=True).strip()
            if value:
                return value
            if current:
                return current
            self._show_warning(self.t("config.api_key_required", provider=provider))

    def _ask_model(self, current: str | None, suggested: str | None) -> str:
        if current:
            prompt = self.t("config.model_prompt_keep")
        elif suggested:
            prompt = self.t("config.model_prompt_default", model=suggested)
        else:
            prompt = self.t("config.model_prompt_new")
        while True:
            value = self.console.input(prompt).strip()
            if value:
                return value
            if current:
                return current
            if suggested:
                return suggested
            self._show_warning(self.t("config.model_required"))

    def _ask_custom_base_url(self, current: str | None) -> str:
        prompt = (
            self.t("config.base_url_prompt_keep")
            if current
            else self.t("config.base_url_prompt_new")
        )
        while True:
            value = self.console.input(prompt).strip()
            if not value:
                if current:
                    return current
                self._show_warning(self.t("config.base_url_required"))
                continue
            try:
                validated = Settings(base_url=value).base_url
            except ValidationError as exc:
                self._show_error(
                    self.t("error.invalid_base_url_title"),
                    ConfigError(_validation_message(exc)),
                )
                continue
            if validated is None:
                self._show_warning(self.t("config.base_url_required"))
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
        table.add_row(
            self.t("config.provider"),
            Text(self._provider_name(self._current_provider())),
        )
        table.add_row(
            self.t("config.api_key"),
            Text(_mask_secret(self.settings.api_key, self.t("config.not_set"))),
        )
        table.add_row(
            self.t("config.model"),
            Text(self.settings.model or self.t("config.not_set")),
        )
        table.add_row(
            self.t("config.base_url"),
            Text(self.settings.base_url or self.t("config.openai_default")),
        )
        config_path = env_file_path()
        path_label = (
            str(config_path)
            if config_path.exists()
            else self.t("config.file_not_created", path=config_path)
        )
        table.add_row(self.t("config.config_file"), Text(path_label))

        return Panel(
            table,
            title=self.t("config.title"),
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
        table.add_column(self.t("help.command"), style="bold cyan", no_wrap=True)
        table.add_column(self.t("help.description"), style="white")
        for command, description_key in _HELP_ROWS:
            table.add_row(command, self.t(description_key))

        examples = Text()
        examples.append(self.t("help.examples_title"), style="bold")
        examples.append(self.t("help.example_crop"), style="dim")
        examples.append(self.t("help.example_codec"), style="dim")
        examples.append(self.t("help.example_audio"), style="dim")
        examples.append(self.t("help.llm_note"), style="dim")
        examples.append("\n")
        examples.append(self.t("help.aliases"), style="dim")

        self.console.print(
            Panel(
                Group(table, examples),
                title=self.t("help.title"),
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
        with self.console.status(f"[cyan]{self.t('status.thinking')}[/cyan]", spinner="dots"):
            decision = client.analyze(self.state.llm_context(), request.text)
        self._render_decision(decision)

    def _render_decision(self, decision: LLMDecision) -> None:
        if decision.intent == "apply":
            changes = self.state.apply_patch(decision.patch)
            self.console.print(Panel(Text(decision.explanation), title="ffai", border_style="cyan"))
            if changes:
                self._render_changes(changes)
                self.console.print(Text(self.t("changes.hint"), style="dim"))
            else:
                self._show_warning(self.t("changes.none"))
            if decision.question:
                self.console.print()
                self.console.print(
                    Panel(
                        Text(decision.question),
                        title=self.t("decision.question_title"),
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
                        title=self.t("decision.clarification_title"),
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
            self._show_warning(self.t("execution.interrupted_partial"))
            return
        if result.succeeded:
            text = Text()
            text.append(self.t("execution.success"), style="bold green")
            text.append(self.t("execution.output_label"), style="dim")
            text.append(result.output_path)
            size = format_file_size(result.output_path)
            if size:
                text.append(f" ({size})", style="dim")
            text.append(
                self.t("execution.elapsed", seconds=result.elapsed_seconds),
                style="dim",
            )
            self.console.print(
                Panel(text, title=self.t("execution.done_title"), border_style="green")
            )
            return

        details = Text()
        details.append(self.t("execution.exit_code", code=result.exit_code), style="bold red")
        if result.stderr_tail:
            details.append("\n\n")
            details.append(result.stderr_tail[-6_000:], style="dim")
        self.console.print(
            Panel(details, title=self.t("execution.failed_title"), border_style="red")
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
            table.add_row(self.t("task.inputs"), inputs)
        else:
            table.add_row(self.t("task.inputs"), Text(self.t("task.none"), style="dim"))

        table.add_row(
            self.t("task.output"),
            Text(task.output) if task.output else Text(self.t("task.none"), style="dim"),
        )
        description = task.description
        if description == "New FFmpeg task":
            description = self.t("task.default_description")
        table.add_row(
            self.t("task.description"),
            Text(description or self.t("task.none")),
        )

        for field in TASK_DISPLAY_FIELDS:
            if field == "description":
                continue
            value = getattr(task, field)
            table.add_row(
                self.t(_FIELD_LABEL_KEYS[field]),
                _format_field(field, value, self.t("task.not_set")),
            )

        return Panel(
            table,
            title=self.t("task.title", revision=self.state.revision),
            border_style="cyan",
            box=box.ROUNDED,
            padding=(1, 2),
        )

    def _command_panel(self, command: Sequence[str], *, preview: bool) -> Panel:
        title = self.t("panel.preview_title") if preview else self.t("panel.exec_title")
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
            title=self.t("changes.title"),
            box=box.SIMPLE_HEAD,
            show_edge=False,
            header_style="bold",
            padding=(0, 1),
        )
        table.add_column(self.t("changes.field"), style="cyan", no_wrap=True)
        table.add_column(self.t("changes.before"), style="dim")
        table.add_column(self.t("changes.after"), style="white")
        not_set = self.t("task.not_set")
        for change in changes:
            label = self.t(_FIELD_LABEL_KEYS.get(change.field, "changes.field"))
            table.add_row(
                label,
                Text(_format_change_value(change.field, change.before, not_set)),
                Text(_format_change_value(change.field, change.after, not_set)),
            )
        self.console.print(table)

    def _show_overwrite_notice(self, output: str | None) -> None:
        if output and Path(output).exists():
            self.console.print(Text(self.t("panel.overwrite_warning"), style="yellow"))

    def _render_banner(self) -> None:
        self.console.print(f"[bold cyan]ffai[/bold cyan] [dim]v{__version__}[/dim]")
        self.console.print(Text(self.t("banner.tagline"), style="dim"))
        self.console.print()

    def _render_startup_notes(self) -> None:
        provider = self._provider_name(self._current_provider())
        endpoint = self.settings.base_url or self.t("config.openai_default")
        api_line = Text()
        api_line.append(self.t("startup.api_label"), style="dim")
        api_line.append(
            self.t(
                "startup.api_value",
                provider=provider,
                model=self.settings.model,
                endpoint=endpoint,
            ),
            style="dim",
        )
        self.console.print(api_line)
        if not ffmpeg_available():
            self.console.print(Text(self.t("startup.ffmpeg_missing"), style="yellow"))
        self.console.print(Text(self.t("startup.hint"), style="dim"))
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


def _format_field(field: str, value: object, not_set: str) -> Text:
    if value is None or value == [] or value == "":
        return Text(not_set, style="dim")
    if field in {"video_filters", "audio_filters"}:
        return Text(", ".join(str(item) for item in value))
    if field == "maps":
        return Text(", ".join(str(item) for item in value))
    if field == "extra_options":
        return Text(shlex.join(str(item) for item in value))
    return Text(str(value))


def _format_change_value(field: str, value: object, not_set: str) -> str:
    if value is None or value == [] or value == "":
        return not_set
    if isinstance(value, list):
        if field == "extra_options":
            return shlex.join(str(item) for item in value)
        return ", ".join(str(item) for item in value)
    return str(value)


def _mask_secret(secret: SecretStr | None, not_set: str) -> str:
    if secret is None:
        return not_set
    value = secret.get_secret_value()
    if len(value) <= 8:
        return "********"
    return f"********{value[-4:]}"


def _validation_message(exc: ValidationError | ConfigError) -> str:
    if isinstance(exc, ConfigError):
        return str(exc)
    return "; ".join(error["msg"] for error in exc.errors())
