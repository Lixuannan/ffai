# ffai

[English](README.md) | 简体中文

`ffai` 是一个基于自然语言、带会话状态的交互式 FFmpeg 工具。你描述视频处理需求，LLM 更新结构化任务，ffai 在本地构建实际的 FFmpeg 命令。在你确认完整命令之前，不会执行任何操作。

```text
ffai v0.1.0
FFmpeg 自然语言交互界面

ffai> add input.mp4
✓ 已添加输入：/media/input.mp4
ffai> setoutput final.mp4
✓ 输出已设置：/media/final.mp4
ffai> 把视频裁剪到 1920x1080，保持中央构图
╭─ ffai ──────────────────────────────────────────────────────────╮
│ 正在更新视频滤镜链，以缩放并居中裁剪。                            │
╰─────────────────────────────────────────────────────────────────╯
ffai> 使用 H.265 编码，CRF 23
...
ffai> preview
╭─ 预览 未执行 ───────────────────────────────────────────────────╮
│ ffmpeg -hide_banner -nostdin -y -i /media/input.mp4 \           │
│   -vf 'scale=1920:1080:force_original_aspect_ratio=increase,...' │
│   -c:v libx265 -crf 23 /media/final.mp4                         │
╰─────────────────────────────────────────────────────────────────╯
ffai> exec
```

## 功能

- 带持久 FFmpeg 任务状态的交互式 REPL。
- 增量式自然语言修改；除非请求要求修改，否则保留已有字段。
- LLM 只返回经过 Pydantic 校验的结构化输出，永远不会生成 Shell 命令。
- 使用参数列表安全构建命令，不使用 `shell=True`。
- 支持多输入，并要求显式配置流映射和 `filter_complex`。
- Rich 任务面板、语法高亮命令预览、执行确认和实时 FFmpeg 进度。
- 内置 OpenAI、OpenRouter、DeepSeek、GLM、Kimi、Qwen 提供商预设，并支持自定义 OpenAI 兼容端点。
- 首次启动自动进入 API 配置向导；`.env` 以仅当前用户可读写的权限保存。`config` 命令可查看或修改当前配置。
- 支持英文和简体中文界面，自动检测系统语言，也可手动切换。LLM 回复会跟随用户输入语言。

## 环境要求

- Python 3.11 或更高版本
- `PATH` 中可用的 FFmpeg
- 一个 OpenAI 兼容的 API Key 和模型。ffai 在进入 REPL 前强制要求完成该配置。
- 可选：`PATH` 中可用的 `ffprobe`，用于估算进度百分比；没有它时仍可执行并显示已用时间。

## 安装

```bash
git clone https://github.com/Lixuannan/ffai.git
cd ffai
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

也可以使用隔离安装：

```bash
pipx install .
```

验证入口：

```bash
ffai --version
```

## 配置

API 配置是必需的。首次启动时，ffai 会在显示 `ffai>` 提示符之前强制完成 API 配置，未配置时以交互方式打开配置向导。非交互式启动且缺少配置时，进程以退出码 `2` 结束。也可以通过 `.env` 或进程环境变量提供配置：

```bash
cp .env.example .env
```

三个配置项如下（`.env` 和进程环境变量都会被读取；进程环境变量优先于 `.env`）：

| 变量 | 是否必需 | 含义 |
| --- | --- | --- |
| `OPENAI_API_KEY` | 是 | API 密钥 |
| `OPENAI_MODEL` | 是 | 聊天模型 ID |
| `OPENAI_BASE_URL` | 否 | OpenAI 兼容端点；留空时使用 OpenAI 默认地址 |

### 内置提供商

配置向导和 `config set` 提供以下预设。选择预设后会自动填入 Base URL，并给出建议模型；模型可手动修改，因为可用性会因账号和地区而异。所有提供商的 API Key 都存放在 `OPENAI_API_KEY` 中。

| 提供商 | Base URL | 建议模型 | 官方文档 |
| --- | --- | --- | --- |
| OpenAI | `https://api.openai.com/v1` | `gpt-5.4-mini` | [OpenAI GPT-5.4 mini](https://developers.openai.com/api/docs/models/gpt-5.4-mini) |
| OpenRouter | `https://openrouter.ai/api/v1` | `openai/gpt-5.4-mini` | [OpenRouter 快速开始](https://openrouter.ai/docs/quickstart) |
| DeepSeek | `https://api.deepseek.com` | `deepseek-flash` | [DeepSeek API 文档](https://api-docs.deepseek.com/) |
| GLM（智谱） | `https://open.bigmodel.cn/api/paas/v4` | `glm-5.3` | [GLM-5.3 文档](https://docs.bigmodel.cn/cn/guide/models/text/glm-5.3) |
| Kimi（月之暗面） | `https://api.moonshot.cn/v1` | `kimi-k3.1-pro` | [Kimi API 文档](https://platform.kimi.com/docs/get-api-key) |
| Qwen（百炼 DashScope） | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen3.8-flash` | [DashScope Base URL](https://www.alibabacloud.com/help/zh/model-studio/base-url) |
| 自定义 | 手动填写 | 手动填写 | 任意 OpenAI 兼容端点 |

可以通过列表序号或提供商 ID（`openai`、`openrouter`、`deepseek`、`glm`、`kimi`、`qwen`、`custom`）选择提供商。OpenRouter 的模型 ID 带供应商前缀。Qwen 预设使用中国区端点；API Key 必须与所选区域匹配，其他区域请使用对应区域的 compatible-mode URL。

OpenAI 环境变量示例：

```dotenv
OPENAI_API_KEY=sk-your-key
OPENAI_MODEL=gpt-5.4-mini
# OPENAI_BASE_URL=https://api.openai.com/v1
```

DeepSeek 环境变量示例：

```dotenv
OPENAI_API_KEY=sk-your-deepseek-key
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_MODEL=deepseek-flash
```

`.env.example` 中的占位值会被视为未配置，因此直接复制示例文件仍会触发配置向导。配置向导会把设置保存到当前目录的 `.env`，文件权限为 `0600`，不会回显 API Key，只显示掩码。使用 REPL 命令 `config` 查看当前配置，使用 `config set` 修改配置。在 `config set` 过程中按回车保留当前值，输入序号或 ID 可切换提供商；按 Ctrl+C 取消且不写入任何内容。

请从项目目录（或具有相同环境变量的目录）启动 ffai。

### 界面语言

界面会从 `LC_ALL`、`LC_MESSAGES` 或 `LANG` 自动检测中文；否则使用英文。也可以通过 `FFAI_LANG=en` / `FFAI_LANG=zh`（进程环境变量或 `.env`）或 `--lang en` / `--lang zh` 参数强制指定。LLM 回复会跟随用户当前请求的语言。

## 内置命令

| 命令 | 作用 |
| --- | --- |
| `add <file> [file ...]` | 添加一个或多个存在且可读的输入文件，重复文件会被忽略。 |
| `setoutput <file>` | 设置输出文件，要求父目录已存在，且输出不能覆盖输入。 |
| `show` | 显示当前任务，包括输入、输出、滤镜、映射、编码器和编码参数。 |
| `preview` | 构建并显示完整 FFmpeg 命令，但不执行。 |
| `exec` | 显示命令，确认后运行 FFmpeg。 |
| `reset` | 清空所有任务状态。 |
| `config` | 显示当前 API 配置，API Key 仅以掩码显示。 |
| `config set` | 交互式修改 API 配置并保存到 `.env`。 |
| `help` | 显示命令帮助。 |
| `exit`、`quit` | 退出 REPL。 |

路径支持类 Shell 的引号，因此文件名中的空格可以正常处理：

```text
add "我的 输入视频.mp4"
setoutput "renders/最终成片.mp4"
```

还支持精确的中文命令别名：`预览`、`显示`、`执行`、`重置`、`配置`、`帮助`、`退出`。

任何无法识别为内置命令的输入都会交给 LLM。例如：

```text
把视频转成 1080p
使用 H.265 编码，CRF 23
音频使用 AAC，码率 192k
裁剪到 1920x1080，保持中央构图
移除所有视频滤镜
```

输入文件和输出路径只能由 `add` 和 `setoutput` 修改，LLM 无权修改文件路径。当 LLM 需要缺失的输入或输出时，它会被要求提示你使用这两个命令。

## 架构

```text
用户输入
   │
   ├── 内置命令 ───────────────────────► SessionState（本地校验）
   │
   └── 自然语言
         │
         ▼
   OpenAI 兼容 LLM
         │  JSON：intent + TaskPatch + explanation/question
         ▼
   Pydantic 校验 ──► SessionState.apply_patch
         │
         ▼
   command_builder.build_command(task)   参数列表，不使用 Shell
         │
         ▼
   预览 ──► 用户确认 ──► executor（子进程，实时进度）
```

两个关键模型定义在 `ffai/models.py`：

```python
class FFmpegTask(BaseModel):
    inputs: list[str]
    output: str | None
    video_filters: list[str]
    audio_filters: list[str]
    video_codec: str | None
    audio_codec: str | None
    video_bitrate: str | None
    audio_bitrate: str | None
    crf: int | None
    preset: str | None
    extra_options: list[str]
    filter_complex: str | None
    maps: list[str]
    description: str


class TaskPatch(BaseModel):
    # 与 FFmpegTask 相同的技术字段，全部可选。
    # 未出现的字段保持不变；显式 null 清除值。
    ...
```

LLM 每轮返回三种意图之一：

- `apply`：应用非空 `TaskPatch`。
- `clarify`：提出一个聚焦的问题，不修改任务。
- `noop`：进行解释，不修改任务。

完整模型结果还包括 `explanation` 和可选的 `question`。`inputs` 和 `output` 不可通过 patch 修改。

### 模块

| 模块 | 职责 |
| --- | --- |
| `ffai/cli.py` | Argparse 入口和顶层错误处理 |
| `ffai/repl.py` | REPL 循环、命令分发、Rich 展示和确认 |
| `ffai/parser.py` | 内置命令与自然语言输入解析 |
| `ffai/providers.py` | 提供商端点、建议模型和文档链接 |
| `ffai/state.py` | 会话归属和经过文件系统校验的状态变更 |
| `ffai/models.py` | Pydantic 任务、patch 和 LLM 决策结构 |
| `ffai/llm.py` | OpenAI 兼容客户端、JSON 提取和校验重试 |
| `ffai/prompt.py` | FFmpeg 专家 System Prompt 和当前状态上下文 |
| `ffai/command_builder.py` | 任务到参数列表转换及额外参数白名单 |
| `ffai/executor.py` | FFmpeg 子进程、进度解析和中断处理 |
| `ffai/config.py` | `.env`/环境变量配置及安全持久化 |
| `ffai/utils.py` | 命令渲染、时长探测和环境变量脱敏 |
| `ffai/i18n.py` | 英文和简体中文界面文案及语言检测 |

## 命令构建与安全

- LLM 输出仅限 `TaskPatch` 结构，未知字段会被拒绝；不会解释或执行模型生成的 Shell/Python 代码。
- FFmpeg 通过参数列表和 `shell=False` 调用。
- 输入和输出路径会规范化，并检查存在性、可读性、父目录有效性以及是否误覆盖输入文件。
- 多输入必须显式提供 `maps` 或 `filter_complex`，输入永远不会被隐式拼接。
- `filter_complex` 不能与简单视频/音频滤镜链同时使用。
- 流复制模式会拒绝滤镜、CRF、Preset 或码率等无效组合。
- `extra_options` 只接受一组保守的常用输出参数，且每个参数必须有固定数量的值。设置编码器、滤镜、映射、覆盖行为或写入额外文件的参数会被拒绝。白名单定义在 `ffai/command_builder.py`，并嵌入 LLM prompt。
- 执行前始终显示完整的参数列表渲染命令并要求确认；已存在的输出文件会在确认前提示。
- FFmpeg 运行时关闭 stdin，并移除名称包含 `KEY`、`SECRET`、`TOKEN`、`PASSWORD`、`PASSWD` 或 `CREDENTIAL` 的环境变量。
- Ctrl+C 会终止 FFmpeg 进程组，超时后从 SIGTERM 升级到 SIGKILL，并按中断状态报告结果。
- 成功退出后会验证目标输出文件；退出码为 0 但文件缺失或为空时按失败处理。

最终确认可见命令和输出路径仍由你负责。FFmpeg 本身具有很强能力，确认界面是最后一道授权步骤。

## 开发

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
ruff check .
pytest
```

解析器、状态转换、命令构建器、配置和 LLM 响应解析都可以在无网络环境下测试。LLM 边界是核心路径中唯一非确定性的外部依赖。安装了 `ffmpeg` 时会运行真实的执行器测试。

## 已知限制

- 每个任务只有一个输出文件；不支持批处理或持久化会话。
- 只支持本地文件输入。
- 仅接受文档中列出的 `extra_options` 白名单；不支持的 FFmpeg 参数会被拒绝，而不是直接透传。
- FFmpeg 滤镜表达式和流标签只会在 ffai 已知的边界做语法检查。滤镜图有效性和编码器可用性仍以 FFmpeg 为准。
- 进度百分比估算需要 `ffprobe`；否则 REPL 只显示已用时间。

## 许可证

MIT。
