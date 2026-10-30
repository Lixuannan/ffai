"""Small, dependency-free localization layer for the interactive UI."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Literal

Language = Literal["en", "zh"]

_CATALOGS: dict[Language, dict[str, str]] = {
    "en": {
        "banner.tagline": "Natural Language Interface for FFmpeg",
        "loop.quit_hint": "Press Ctrl+D or type 'exit' to quit.",
        "loop.goodbye": "Goodbye.",
        "loop.interrupt_kept": "Interrupted. The current task was kept.",
        "status.thinking": "Thinking...",
        "error.input_title": "Input error",
        "error.title": "Error",
        "error.cannot_build_title": "Cannot build command",
        "error.config_title": "Configuration error",
        "error.invalid_config_title": "Invalid configuration",
        "error.invalid_base_url_title": "Invalid base URL",
        "error.config_required_title": "Configuration required",
        "startup.api_label": "API: ",
        "startup.api_value": "{provider} / {model} at {endpoint}",
        "startup.ffmpeg_missing": (
            "FFmpeg was not found on PATH. Install it before running commands."
        ),
        "startup.hint": (
            "Type 'help' for commands, or describe a video operation in natural "
            "language. 'exit' quits."
        ),
        "startup.setup_required_intro": (
            "ffai requires an OpenAI-compatible API configuration.\n\n"
        ),
        "startup.missing_label": "Missing: ",
        "startup.setup_hint": ("\n\nComplete the setup below. Ctrl+C cancels startup."),
        "startup.setup_cancelled": "API configuration was not completed; ffai cannot start.",
        "startup.noninteractive": (
            "API configuration is required before ffai can start. Missing: {missing}. "
            "Set the environment variables or run ffai in an interactive terminal to "
            "use the setup wizard."
        ),
        "action.added": "Added input: {path}",
        "action.duplicate": "Already added: {path}",
        "action.add_tip": (
            "Tip: set an output with 'setoutput <file>', then describe the operation."
        ),
        "action.no_files": "No files were added.",
        "action.output_set": "Output set: {path}",
        "action.reset": "Task state cleared.",
        "action.config_saved": "API configuration saved to {path}",
        "config.show_hint": "Use 'config set' to update the API connection settings.",
        "config.title": "[bold]API configuration[/bold]",
        "config.provider": "Provider",
        "config.api_key": "API key",
        "config.model": "Model",
        "config.base_url": "Base URL",
        "config.config_file": "Config file",
        "config.file_not_created": "{path} (not created)",
        "config.openai_default": "(OpenAI default)",
        "config.setup_required_title": "[bold yellow]API setup required[/bold yellow]",
        "config.wizard_intro": "Configure the API connection.\n",
        "config.wizard_hint": (
            "Press Enter to keep a current value. Choose a provider by number or ID.\n"
        ),
        "config.save_location": "Settings are saved to {path}.",
        "config.setup_cancelled": "Configuration cancelled; no changes saved.",
        "config.interactive_required": "Interactive setup requires a terminal.",
        "config.column_number": "#",
        "config.column_provider": "Provider",
        "config.column_base_url": "Base URL",
        "config.column_model": "Suggested model",
        "config.current_marker": "{name} (current)",
        "config.custom_url_placeholder": "(enter a custom URL)",
        "config.custom_model_placeholder": "(enter a model)",
        "config.docs_label": "Docs: ",
        "config.api_keys_label": "API keys: ",
        "config.provider_prompt_keep": ("Provider (Enter keeps {current}) (number or ID): "),
        "config.provider_prompt_new": "Provider (1-{count}) (number or ID): ",
        "config.provider_required": "Choose a provider.",
        "config.provider_unknown": "Unknown provider. Enter a listed number or provider ID.",
        "config.api_key_prompt_keep": "{provider} API key (Enter keeps current): ",
        "config.api_key_prompt_new": "{provider} API key: ",
        "config.api_key_required": "{provider} API key is required.",
        "config.model_prompt_keep": "Model (Enter keeps current): ",
        "config.model_prompt_default": "Model (default: {model}): ",
        "config.model_prompt_new": "Model: ",
        "config.model_required": "Model is required.",
        "config.base_url_prompt_keep": "Base URL (required; Enter keeps current): ",
        "config.base_url_prompt_new": "Base URL (required): ",
        "config.base_url_required": "Base URL is required for a custom provider.",
        "config.invalid_configuration": "Invalid configuration",
        "config.not_set": "(not set)",
        "help.title": "[bold]ffai help[/bold]",
        "help.command": "Command",
        "help.description": "Description",
        "help.add": "Add one or more input media files",
        "help.setoutput": "Set the output file",
        "help.show": "Show the current task state",
        "help.preview": "Build and display the command without running it",
        "help.exec": "Build, confirm, and run the command",
        "help.reset": "Clear the task state",
        "help.config": "Show or update the API configuration",
        "help.help": "Show this help",
        "help.exit": "Exit ffai",
        "help.examples_title": "Natural language examples\n",
        "help.example_crop": "  crop the video to 1920x1080, centered\n",
        "help.example_codec": "  use H.265 with CRF 23\n",
        "help.example_audio": "  audio AAC at 192k\n\n",
        "help.llm_note": (
            "Unrecognized input is sent to the LLM. It updates structured task state; "
            "it never executes commands."
        ),
        "help.aliases": "Chinese aliases: 预览, 显示, 执行, 重置, 配置, 帮助, 退出",
        "task.title": "[bold]Current task[/bold] [dim]revision {revision}[/dim]",
        "task.inputs": "Inputs",
        "task.output": "Output",
        "task.description": "Description",
        "task.default_description": "New FFmpeg task",
        "task.none": "(none)",
        "task.not_set": "(not set)",
        "field.video_filters": "Video filters",
        "field.audio_filters": "Audio filters",
        "field.filter_complex": "Filter complex",
        "field.maps": "Stream maps",
        "field.video_codec": "Video codec",
        "field.audio_codec": "Audio codec",
        "field.crf": "CRF",
        "field.preset": "Preset",
        "field.video_bitrate": "Video bitrate",
        "field.audio_bitrate": "Audio bitrate",
        "field.extra_options": "Extra options",
        "field.description": "Description",
        "changes.title": "Updated fields",
        "changes.field": "Field",
        "changes.before": "Before",
        "changes.after": "After",
        "changes.hint": "Run 'show' or 'preview' to inspect the updated task.",
        "changes.none": "The model proposed no effective task changes.",
        "decision.question_title": "[bold yellow]Question[/bold yellow]",
        "decision.clarification_title": "[bold yellow]Need clarification[/bold yellow]",
        "panel.preview_title": "[bold]Preview[/bold] [dim]not executed[/dim]",
        "panel.exec_title": "[bold]Command to execute[/bold]",
        "panel.overwrite_warning": (
            "Warning: the output file already exists and will be overwritten."
        ),
        "panel.confirm_execute": "Execute this command?",
        "execution.cancelled": "Execution cancelled.",
        "execution.interrupted": "Execution interrupted.",
        "execution.interrupted_partial": (
            "Execution interrupted. A partial output file may exist and can be removed."
        ),
        "execution.done_title": "[bold green]Done[/bold green]",
        "execution.success": "Command completed successfully.\n",
        "execution.output_label": "Output: ",
        "execution.elapsed": "\nElapsed: {seconds:.1f}s",
        "execution.failed_title": "[bold red]FFmpeg failed[/bold red]",
        "execution.exit_code": "FFmpeg exited with code {code}.",
        "cli.interrupted": "Interrupted. Goodbye.",
        "cli.config_error_title": "[bold red]Configuration error[/bold red]",
        "cli.config_required_title": "[bold red]Configuration required[/bold red]",
    },
    "zh": {
        "banner.tagline": "FFmpeg 自然语言交互界面",
        "loop.quit_hint": "按 Ctrl+D 或输入 'exit' 退出。",
        "loop.goodbye": "再见。",
        "loop.interrupt_kept": "已中断，当前任务已保留。",
        "status.thinking": "思考中...",
        "error.input_title": "输入错误",
        "error.title": "错误",
        "error.cannot_build_title": "无法构建命令",
        "error.config_title": "配置错误",
        "error.invalid_config_title": "配置无效",
        "error.invalid_base_url_title": "Base URL 无效",
        "error.config_required_title": "需要配置",
        "startup.api_label": "API：",
        "startup.api_value": "{provider} / {model} · {endpoint}",
        "startup.ffmpeg_missing": "未在 PATH 中找到 FFmpeg，请先安装再执行命令。",
        "startup.hint": (
            "输入 'help' 查看命令，或直接用自然语言描述视频处理需求；输入 'exit' 退出。"
        ),
        "startup.setup_required_intro": "ffai 需要配置一个 OpenAI 兼容的 API。\n\n",
        "startup.missing_label": "缺少：",
        "startup.setup_hint": "\n\n请在下方完成配置。按 Ctrl+C 取消启动。",
        "startup.setup_cancelled": "API 配置未完成，ffai 无法启动。",
        "startup.noninteractive": (
            "ffai 启动前必须完成 API 配置。缺少：{missing}。"
            "请设置环境变量，或在交互式终端中运行 ffai 以使用配置向导。"
        ),
        "action.added": "已添加输入：{path}",
        "action.duplicate": "已经添加过：{path}",
        "action.add_tip": "提示：使用 'setoutput <文件>' 设置输出，然后描述你的处理需求。",
        "action.no_files": "没有添加任何文件。",
        "action.output_set": "输出已设置：{path}",
        "action.reset": "任务状态已清空。",
        "action.config_saved": "API 配置已保存至 {path}",
        "config.show_hint": "使用 'config set' 更新 API 连接配置。",
        "config.title": "[bold]API 配置[/bold]",
        "config.provider": "提供商",
        "config.api_key": "API 密钥",
        "config.model": "模型",
        "config.base_url": "Base URL",
        "config.config_file": "配置文件",
        "config.file_not_created": "{path}（尚未创建）",
        "config.openai_default": "（OpenAI 默认）",
        "config.setup_required_title": "[bold yellow]需要配置 API[/bold yellow]",
        "config.wizard_intro": "配置 API 连接。\n",
        "config.wizard_hint": "按回车保留当前值。通过序号或 ID 选择提供商。\n",
        "config.save_location": "配置将保存到 {path}。",
        "config.setup_cancelled": "已取消配置，未保存任何更改。",
        "config.interactive_required": "交互式配置需要在终端中运行。",
        "config.column_number": "序号",
        "config.column_provider": "提供商",
        "config.column_base_url": "Base URL",
        "config.column_model": "建议模型",
        "config.current_marker": "{name}（当前）",
        "config.custom_url_placeholder": "（请输入自定义 URL）",
        "config.custom_model_placeholder": "（请输入模型）",
        "config.docs_label": "文档：",
        "config.api_keys_label": "API 密钥：",
        "config.provider_prompt_keep": "提供商（回车保留 {current}）（序号或 ID）：",
        "config.provider_prompt_new": "提供商（1-{count}，序号或 ID）：",
        "config.provider_required": "请选择提供商。",
        "config.provider_unknown": "未知提供商，请输入列表中的序号或提供商 ID。",
        "config.api_key_prompt_keep": "{provider} API Key（回车保留当前值）：",
        "config.api_key_prompt_new": "{provider} API Key：",
        "config.api_key_required": "需要填写 {provider} API Key。",
        "config.model_prompt_keep": "模型（回车保留当前值）：",
        "config.model_prompt_default": "模型（默认：{model}）：",
        "config.model_prompt_new": "模型：",
        "config.model_required": "需要填写模型名称。",
        "config.base_url_prompt_keep": "Base URL（必填，回车保留当前值）：",
        "config.base_url_prompt_new": "Base URL（必填）：",
        "config.base_url_required": "自定义提供商必须填写 Base URL。",
        "config.invalid_configuration": "配置无效",
        "config.not_set": "（未设置）",
        "help.title": "[bold]ffai 帮助[/bold]",
        "help.command": "命令",
        "help.description": "说明",
        "help.add": "添加一个或多个输入媒体文件",
        "help.setoutput": "设置输出文件",
        "help.show": "显示当前任务状态",
        "help.preview": "构建并显示命令，但不执行",
        "help.exec": "构建命令，确认后执行",
        "help.reset": "清空当前任务状态",
        "help.config": "查看或更新 API 配置",
        "help.help": "显示帮助",
        "help.exit": "退出 ffai",
        "help.examples_title": "自然语言示例\n",
        "help.example_crop": "  把视频裁剪到 1920x1080，保持中央构图\n",
        "help.example_codec": "  使用 H.265 编码，CRF 23\n",
        "help.example_audio": "  音频使用 AAC，码率 192k\n\n",
        "help.llm_note": "无法识别的输入会交给 LLM 解析。LLM 只更新结构化任务状态，不会执行命令。",
        "help.aliases": "中文命令别名：预览、显示、执行、重置、配置、帮助、退出",
        "task.title": "[bold]当前任务[/bold] [dim]版本 {revision}[/dim]",
        "task.inputs": "输入文件",
        "task.output": "输出文件",
        "task.description": "任务描述",
        "task.default_description": "新的 FFmpeg 任务",
        "task.none": "（无）",
        "task.not_set": "（未设置）",
        "field.video_filters": "视频滤镜",
        "field.audio_filters": "音频滤镜",
        "field.filter_complex": "复杂滤镜图",
        "field.maps": "流映射",
        "field.video_codec": "视频编码器",
        "field.audio_codec": "音频编码器",
        "field.crf": "CRF",
        "field.preset": "Preset",
        "field.video_bitrate": "视频码率",
        "field.audio_bitrate": "音频码率",
        "field.extra_options": "额外参数",
        "field.description": "任务描述",
        "changes.title": "已更新字段",
        "changes.field": "字段",
        "changes.before": "修改前",
        "changes.after": "修改后",
        "changes.hint": "使用 'show' 或 'preview' 查看更新后的任务。",
        "changes.none": "模型没有产生有效的任务变更。",
        "decision.question_title": "[bold yellow]问题[/bold yellow]",
        "decision.clarification_title": "[bold yellow]需要澄清[/bold yellow]",
        "panel.preview_title": "[bold]预览[/bold] [dim]未执行[/dim]",
        "panel.exec_title": "[bold]待执行命令[/bold]",
        "panel.overwrite_warning": "警告：输出文件已存在，执行时会覆盖该文件。",
        "panel.confirm_execute": "执行此命令？",
        "execution.cancelled": "已取消执行。",
        "execution.interrupted": "执行已中断。",
        "execution.interrupted_partial": "执行已中断。可能留下不完整的输出文件，可自行删除。",
        "execution.done_title": "[bold green]完成[/bold green]",
        "execution.success": "命令执行成功。\n",
        "execution.output_label": "输出：",
        "execution.elapsed": "\n耗时：{seconds:.1f}s",
        "execution.failed_title": "[bold red]FFmpeg 执行失败[/bold red]",
        "execution.exit_code": "FFmpeg 退出码为 {code}。",
        "cli.interrupted": "已中断，再见。",
        "cli.config_error_title": "[bold red]配置错误[/bold red]",
        "cli.config_required_title": "[bold red]需要配置[/bold red]",
    },
}


class Translator:
    """Look up UI text for one language, falling back to English."""

    def __init__(self, language: Language) -> None:
        self.language = language

    def __call__(self, key: str, **values: object) -> str:
        template = _CATALOGS[self.language].get(key) or _CATALOGS["en"].get(key, key)
        return template.format(**values)


def resolve_language(
    explicit: str | None = None,
    env: Mapping[str, str] | None = None,
) -> Language:
    """Resolve the UI language from a flag, ``FFAI_LANG``, or the locale."""

    if explicit == "en":
        return "en"
    if explicit == "zh":
        return "zh"
    source = os.environ if env is None else env
    configured = (source.get("FFAI_LANG") or "").strip().lower()
    normalized = _normalize_language(configured)
    if normalized is not None:
        return normalized
    locale_name = (
        source.get("LC_ALL") or source.get("LC_MESSAGES") or source.get("LANG") or ""
    ).lower()
    return "zh" if locale_name.startswith("zh") else "en"


def _normalize_language(value: str) -> Language | None:
    if value.startswith("zh"):
        return "zh"
    if value.startswith("en"):
        return "en"
    return None
