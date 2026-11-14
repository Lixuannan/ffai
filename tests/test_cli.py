from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from rich.console import Console

from ffai.config import Settings
from ffai.i18n import Translator
from ffai.repl import FFaiRepl
from ffai.state import TaskChange

ROOT = Path(__file__).resolve().parents[1]


def _clean_env() -> dict[str, str]:
    env = os.environ.copy()
    for name in ("OPENAI_API_KEY", "OPENAI_MODEL", "OPENAI_BASE_URL"):
        env.pop(name, None)
    env["NO_COLOR"] = "1"
    env["FFAI_LANG"] = "en"
    return env


def _configured_env() -> dict[str, str]:
    env = _clean_env()
    env["OPENAI_API_KEY"] = "sk-test-secret-value"
    env["OPENAI_MODEL"] = "test-model"
    # Pin the endpoint: find_dotenv(usecwd=True) otherwise fills this from a
    # developer's local .env (override=False), which changes the provider name
    # shown by `config` and makes CLI assertions depend on the machine.
    env["OPENAI_BASE_URL"] = "https://api.openai.com/v1"
    return env


def test_version_uses_real_module_entry_point() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "ffai", "--version"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=15,
        env=_clean_env(),
        check=False,
    )
    assert completed.returncode == 0
    assert completed.stdout.strip() == "ffai 0.2.0"


def test_help_and_exit_through_the_repl() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "ffai"],
        cwd=ROOT,
        input="help\nexit\n",
        capture_output=True,
        text=True,
        timeout=15,
        env=_configured_env(),
        check=False,
    )
    assert completed.returncode == 0
    assert "ffai help" in completed.stdout
    assert "tool <ffmpeg|pandoc>" in completed.stdout
    assert "convert notes.md to report.pdf" in completed.stdout
    assert "Goodbye." in completed.stdout
    assert "Traceback" not in completed.stderr


def test_tool_command_switches_to_pandoc() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "ffai"],
        cwd=ROOT,
        input="tool pandoc\nshow\nexit\n",
        capture_output=True,
        text=True,
        timeout=15,
        env=_configured_env(),
        check=False,
    )
    assert completed.returncode == 0
    assert "Conversion tool set to Pandoc." in completed.stdout
    assert "Pandoc task" in completed.stdout
    assert "New Pandoc task" in completed.stdout
    assert "From format" in completed.stdout
    assert "Standalone" in completed.stdout
    assert "Traceback" not in completed.stderr


def test_adding_document_file_auto_selects_pandoc(tmp_path: Path) -> None:
    document = tmp_path / "notes.md"
    document.write_text("# Notes\n", encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, "-m", "ffai"],
        cwd=ROOT,
        input=f'add "{document}"\nshow\nexit\n',
        capture_output=True,
        text=True,
        timeout=15,
        env=_configured_env(),
        check=False,
    )
    assert completed.returncode == 0
    assert "Detected Pandoc from the input file type" in completed.stdout
    assert "Pandoc task" in completed.stdout
    assert "Traceback" not in completed.stderr


def test_prompt_returns_after_every_command_output() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "ffai"],
        cwd=ROOT,
        input="help\nshow\nsetoutput /definitely/missing/out.mp4\nexit\n",
        capture_output=True,
        text=True,
        timeout=15,
        env=_configured_env(),
        check=False,
    )
    assert completed.returncode == 0
    assert completed.stdout.count("ffai>") >= 4
    assert "ffai help" in completed.stdout
    assert "Output directory does not exist" in completed.stdout
    assert "Traceback" not in completed.stderr


def test_missing_api_configuration_fails_fast_when_not_interactive(tmp_path: Path) -> None:
    env = _clean_env()
    env["PYTHONPATH"] = str(ROOT)
    completed = subprocess.run(
        [sys.executable, "-m", "ffai"],
        cwd=tmp_path,
        input="help\nexit\n",
        capture_output=True,
        text=True,
        timeout=15,
        env=env,
        check=False,
    )
    assert completed.returncode == 2
    assert "API configuration is required" in completed.stdout
    assert "ffai help" not in completed.stdout
    assert "ffai>" not in completed.stdout
    assert "Traceback" not in completed.stderr


def test_config_command_masks_api_key() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "ffai"],
        cwd=ROOT,
        input="config\nexit\n",
        capture_output=True,
        text=True,
        timeout=15,
        env=_configured_env(),
        check=False,
    )
    assert completed.returncode == 0
    assert "API configuration" in completed.stdout
    assert "Provider                  OpenAI" in completed.stdout
    assert "test-model" in completed.stdout
    assert "sk-test-secret-value" not in completed.stdout
    assert "********alue" in completed.stdout
    assert "Use 'config set'" in completed.stdout
    assert "Traceback" not in completed.stderr


def test_chinese_ui_can_be_selected() -> None:
    env = _configured_env()
    env["FFAI_LANG"] = "zh"
    completed = subprocess.run(
        [sys.executable, "-m", "ffai"],
        cwd=ROOT,
        input="help\nshow\nconfig\nexit\n",
        capture_output=True,
        text=True,
        timeout=15,
        env=env,
        check=False,
    )
    assert completed.returncode == 0
    assert "媒体与文档转换的自然语言界面" in completed.stdout
    assert "ffai 帮助" in completed.stdout
    assert "当前任务" in completed.stdout
    assert "API 配置" in completed.stdout
    assert "输出文件" in completed.stdout
    assert "再见。" in completed.stdout
    assert "Traceback" not in completed.stderr


def test_tool_change_renders_tool_labels_instead_of_ids() -> None:
    console = Console(record=True, width=120, highlight=False)
    repl = FFaiRepl(Settings(), console=console, translator=Translator("en"))
    repl._render_changes([TaskChange(field="tool", before="ffmpeg", after="pandoc")])
    output = console.export_text()
    assert "Tool" in output
    assert "FFmpeg" in output
    assert "Pandoc" in output
    assert "ffmpeg" not in output
    assert "pandoc" not in output


def test_pandoc_fields_render_localized_booleans_and_joined_lists() -> None:
    console = Console(record=True, width=120, highlight=False)
    repl = FFaiRepl(Settings(), console=console, translator=Translator("en"))
    repl._render_changes(
        [
            TaskChange(field="standalone", before=False, after=True),
            TaskChange(field="metadata", before=[], after=["title=Report", "author=Ada"]),
            TaskChange(field="extra_options", before=[], after=["-N", "--wrap=preserve"]),
        ]
    )
    output = console.export_text()
    assert "No" in output
    assert "Yes" in output
    assert "title=Report, author=Ada" in output
    assert "-N --wrap=preserve" in output


def test_language_flag_overrides_locale_and_environment() -> None:
    env = _configured_env()
    env["FFAI_LANG"] = "zh"
    completed = subprocess.run(
        [sys.executable, "-m", "ffai", "--lang", "en"],
        cwd=ROOT,
        input="help\nexit\n",
        capture_output=True,
        text=True,
        timeout=15,
        env=env,
        check=False,
    )
    assert completed.returncode == 0
    assert "ffai help" in completed.stdout
    assert "Goodbye." in completed.stdout
