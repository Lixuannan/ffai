from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

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
    assert completed.stdout.strip() == "ffai 0.1.0"


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
    assert "Goodbye." in completed.stdout
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
    assert "FFmpeg 自然语言交互界面" in completed.stdout
    assert "ffai 帮助" in completed.stdout
    assert "当前任务" in completed.stdout
    assert "API 配置" in completed.stdout
    assert "输出文件" in completed.stdout
    assert "再见。" in completed.stdout
    assert "Traceback" not in completed.stderr


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
