# ffai

[English](README.md) | 简体中文

`ffai` 是一个基于自然语言、带会话状态的交互式格式转换助手。你描述一个媒体操作或文档转换需求，LLM 更新结构化任务，ffai 在本地使用 **FFmpeg**（媒体文件）或 **Pandoc**（文档、电子书、标记语言和 PDF）构建实际命令。在你确认完整命令之前，不会执行任何操作。

```text
ffai v0.2.0
媒体与文档转换的自然语言界面

ffai> add notes.md
✓ 已添加输入：/home/you/notes.md
已根据输入文件类型自动选择 Pandoc。
ffai> setoutput notes.docx
✓ 输出已设置：/home/you/notes.docx
ffai> 转换成带目录的 Word 文档
╭─ ffai ──────────────────────────────────────────────────────────╮
│ 正在为 Word 输出启用目录。                                      │
╰─────────────────────────────────────────────────────────────────╯
ffai> preview
╭─ 预览 未执行 ───────────────────────────────────────────────────╮
│ pandoc --toc -o /home/you/notes.docx /home/you/notes.md         │
╰─────────────────────────────────────────────────────────────────╯
ffai> exec
```

## 功能

- 一个 REPL 背后有两个外部工具：FFmpeg 处理媒体，Pandoc 处理文档。
- 添加文件时根据扩展名自动路由，也可以用 `tool <ffmpeg|pandoc>` 命令随时手动切换。
- 每个工具各自维护任务，切换工具不会丢失另一个工具的工作；`reset` 只清除当前工具的任务。
- 增量式自然语言修改；除非请求要求修改，否则保留已有字段。
- LLM 只返回经过 Pydantic 校验的结构化输出。响应是针对单个工具的任务补丁，模型永远不会生成 Shell 命令。
- 使用参数列表安全构建命令，不使用 `shell=True`。
- FFmpeg：支持多输入，并要求显式配置流映射和 `filter_complex`。
- Pandoc：支持目录、章节编号、元数据、模板、参考文档、带参考书目的 citeproc、PDF 引擎、语法高亮和资源嵌入。
- Rich 任务面板、语法高亮命令预览、执行确认和实时 FFmpeg 进度。
- 交互式行编辑：用方向键调用历史记录，`add` 和 `setoutput` 支持 TAB 补全文件路径，`ffai>` 提示符在编辑时不会被擦除。
- 内置 OpenAI、OpenRouter、DeepSeek、GLM、Kimi、Qwen 提供商预设，并支持自定义 OpenAI 兼容端点。
- 首次启动自动进入 API 配置向导；`.env` 以仅当前用户可读写的权限保存。`config` 命令可查看或修改当前配置。
- 支持英文和简体中文界面，自动检测系统语言，也可手动切换。LLM 回复会跟随用户输入语言。

## 环境要求

- Python 3.11 或更高版本
- `PATH` 中可用的 FFmpeg 和/或 Pandoc。两者都受支持；至少安装你准备使用的那个工具。
- 一个 OpenAI 兼容的 API Key 和模型。ffai 在进入 REPL 前强制要求完成该配置。
- 可选：`PATH` 中可用的 `ffprobe`，用于估算 FFmpeg 进度百分比；没有它时仍可执行并显示已用时间。
- 只有在使用 Pandoc 输出 PDF 时才需要 LaTeX 或 Typst 引擎（例如 Tectonic 或 TeX Live）。非 PDF 的文档转换不需要。

## 安装

从 PyPI 安装：

```bash
pip install ffai-cli
```

也可以使用隔离安装：

```bash
pipx install ffai-cli
```

PyPI 上的发行包名为 `ffai-cli`，Python 包名和 `ffai` 命令仍使用短名。

验证入口：

```bash
ffai --version
```

### 从源码安装

```bash
git clone https://github.com/Lixuannan/ffai.git
cd ffai
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### FFmpeg

使用你常用的包管理器安装 FFmpeg，或从 https://ffmpeg.org/download.html 下载构建版本：

```bash
# macOS
brew install ffmpeg

# Debian / Ubuntu
sudo apt install ffmpeg

# Windows（Chocolatey）
choco install ffmpeg
```

### Pandoc

```bash
# macOS
brew install pandoc

# Debian / Ubuntu
sudo apt install pandoc

# Windows（Chocolatey）
choco install pandoc
```

也可以从 https://pandoc.org/installing.html 下载对应平台的安装程序。使用 `pandoc --version` 验证安装。

### Pandoc 的 PDF 引擎

Pandoc 通过调用外部引擎生成 PDF。如需 PDF 输出，请安装以下之一：

```bash
# Tectonic（独立引擎，按需下载宏包）
brew install tectonic
# 或
cargo install tectonic
```

提供 `xelatex`、`lualatex`、`pdflatex` 或 `latexmk` 的 TeX Live 发行版同样可用。也可以使用 Typst 安装作为 PDF 引擎来代替 LaTeX 引擎。ffai 的 `pdf_engine` 仅限命令构建器支持的引擎（见[命令构建与安全](#命令构建与安全)）。

## 快速开始

### FFmpeg：裁剪并编码视频

```text
ffai> add input.mp4
✓ 已添加输入：/media/input.mp4
ffai> setoutput final.mp4
✓ 输出已设置：/media/final.mp4
ffai> 把视频裁剪到 1920x1080，保持中央构图
╭─ ffai ──────────────────────────────────────────────────────────╮
│ 正在更新视频滤镜链，以缩放并居中裁剪。                          │
╰─────────────────────────────────────────────────────────────────╯
ffai> 使用 H.265 编码，CRF 23
...
ffai> preview
╭─ 预览 未执行 ───────────────────────────────────────────────────╮
│ ffmpeg -hide_banner -nostdin -y -i /media/input.mp4 \           │
│   -vf 'scale=1920:1080:force_original_aspect_ratio=increase'    │
│   -c:v libx265 -crf 23 /media/final.mp4                         │
╰─────────────────────────────────────────────────────────────────╯
ffai> exec
```

`exec` 会在运行 FFmpeg 前要求确认。

### Pandoc：Markdown 转带目录的 Word

```text
ffai> add notes.md
✓ 已添加输入：/home/you/notes.md
已根据输入文件类型自动选择 Pandoc。
ffai> setoutput notes.docx
✓ 输出已设置：/home/you/notes.docx
ffai> 转换成带目录的 Word 文档
ffai> preview
╭─ 预览 未执行 ───────────────────────────────────────────────────╮
│ pandoc --toc -o /home/you/notes.docx /home/you/notes.md         │
╰─────────────────────────────────────────────────────────────────╯
ffai> exec
```

### Pandoc：使用 xelatex 将 Markdown 转为 PDF

```text
ffai> add report.md
✓ 已添加输入：/home/you/report.md
ffai> setoutput report.pdf
✓ 输出已设置：/home/you/report.pdf
ffai> 使用 xelatex 导出带目录的 PDF
ffai> preview
╭─ 预览 未执行 ───────────────────────────────────────────────────╮
│ pandoc --toc --pdf-engine xelatex \                             │
│   -o /home/you/report.pdf /home/you/report.md                   │
╰─────────────────────────────────────────────────────────────────╯
ffai> exec
```

Pandoc 根据文件扩展名推断输入和输出格式；只有在你显式指定格式时，ffai 才会添加 `-f`/`-t`。PDF 输出要求所选 PDF 引擎已经安装。

### 手动切换工具

```text
ffai> tool pandoc
✓ 转换工具已设置为 Pandoc。
ffai> tool ffmpeg
✓ 转换工具已设置为 FFmpeg。
```

切换不会丢弃另一个工具的任务。`show`、`preview`、`exec` 和 `reset` 都作用于当前工具。

## 内置命令

| 命令 | 作用 |
| --- | --- |
| `add <file> [file ...]` | 向当前任务添加存在且可读的输入文件，重复文件会被忽略。当前任务为空时，可识别的扩展名可以自动选择工具。 |
| `setoutput <file>` | 设置输出文件，要求父目录已存在，且输出不能覆盖输入。 |
| `tool <ffmpeg\|pandoc>` | 切换当前工具。每个工具各自保留输入、输出和字段。 |
| `show` | 显示当前任务，包括输入、输出和该工具特有的字段。 |
| `preview` | 构建并显示完整命令，但不执行。 |
| `exec` | 显示命令，确认后运行。 |
| `reset` | 只清空当前工具的任务，另一个工具的任务会保留。 |
| `config`、`config show` | 显示当前 API 配置，API Key 仅以掩码显示。 |
| `config set` | 交互式修改 API 配置并保存到 `.env`。 |
| `help` | 显示命令帮助。 |
| `exit`、`quit` | 退出 REPL。 |

路径支持类 Shell 的引号，因此文件名中的空格可以正常处理：

```text
add "我的 输入视频.mp4"
setoutput "renders/最终成片.mp4"
```

`add` 和 `setoutput` 的参数支持 TAB 路径补全。补全会从当前目录查找，也支持逐级输入相对子路径或直接使用绝对路径；`~/` 会展开用于查找，但插入文本中仍保留 `~/`。目录补全后带尾部 `/` 以便继续逐级输入，隐藏项仅在输入前缀以 `.` 开头时提供，名称中的空格会自动转义或保留在已打开的引号内。其他内置命令和自然语言输入中按 TAB 不会触发补全。

```text
add vid<TAB>                # 补全当前目录下的输入文件
setoutput "renders/rec<TAB>  # 补全路径，自动为带空格的文件名加引号
```

还支持精确的中文命令别名：`预览`、`显示`、`执行`、`重置`、`配置`、`工具`、`帮助`、`退出`。

任何无法识别为内置命令的输入都会交给 LLM。例如：

```text
把视频转成 1080p
使用 H.265 编码，CRF 23
音频使用 AAC，码率 192k
裁剪到 1920x1080，保持中央构图
移除所有视频滤镜
把文档转换成 EPUB
添加目录并对章节编号
使用 xelatex 导出 PDF
使用模板 letter.template
```

输入文件和输出路径只能由 `add` 和 `setoutput` 修改，LLM 无权修改。`template`、`reference_doc`、`bibliography`、`csl`、`resource_path` 等 Pandoc 辅助路径可以通过自然语言设置，并会经过本地文件系统校验。

## 工具路由规则

- 向空任务（尚无输入和输出）添加文件时，ffai 会检查扩展名。如果所有可识别的扩展名都属于同一个工具，就切换到该工具，并在 REPL 中提示检测结果。
- 如果扩展名混合属于不同工具、无法识别，或者当前任务已经有输入或输出，则保持当前工具不变。
- `tool ffmpeg` 和 `tool pandoc` 可以随时手动切换。`add` 只在当前任务仍为空（尚无输入和输出）时自动选择工具；之后会保持当前工具。
- 每个工具都有独立任务。`show`、`preview` 和 `exec` 使用当前任务；另一个工具的任务会一直保留，直到你重置它。

常见扩展名路由如下（完整集合定义在 `ffai/tools.py`）：

| 工具 | 扩展示例 |
| --- | --- |
| FFmpeg | `.mp4`、`.mkv`、`.mov`、`.avi`、`.webm`、`.ts`、`.mp3`、`.m4a`、`.wav`、`.flac`、`.ogg`、`.opus`、`.jpg`、`.png`、`.gif`、`.webp` |
| Pandoc | `.md`、`.markdown`、`.txt`、`.docx`、`.odt`、`.html`、`.epub`、`.tex`、`.rst`、`.org`、`.adoc`、`.ipynb`、`.pptx` |

未知扩展名会保持当前工具。文件类型无法识别时，请使用 `tool` 手动切换。

## Pandoc 任务字段

自然语言会填充以下字段。只有显式设置时才会传入 `from_format` 和 `to_format`；否则 Pandoc 根据文件扩展名推断格式。

| 字段 | 含义 |
| --- | --- |
| `from_format`、`to_format` | 显式的 Pandoc 读取/写入格式名，例如 `gfm` 或 `docx`。 |
| `standalone` | 生成独立文档。 |
| `toc`、`toc_depth` | 添加目录，可指定 1 到 6 的目录深度。 |
| `number_sections` | 对章节标题编号。 |
| `shift_heading_level_by` | 以 -10 到 10 的偏移量调整标题级别。 |
| `metadata` | 可重复的 `key=value` 元数据条目。 |
| `template` | 用于输出的本地模板文件。 |
| `reference_doc` | 用于样式的本地参考文档。 |
| `pdf_engine` | PDF 引擎，仅限下方白名单。 |
| `highlight_style` | 语法高亮主题，仅限下方白名单。 |
| `embed_resources` | 将图片和其他资源嵌入输出。 |
| `citeproc` | 运行 Pandoc 的引用处理器。 |
| `bibliography` | 一个或多个本地参考文献文件。 |
| `csl` | 本地 CSL 引用样式文件。 |
| `resource_path` | 一个或多个用于查找资源的本地目录。 |
| `extra_options` | 参数数量固定且在白名单内的 Pandoc 选项。 |
| `description` | 转换的简短描述。 |

`pdf_engine` 接受 `pdflatex`、`xelatex`、`lualatex`、`latexmk`、`tectonic`、`typst`、`context`、`wkhtmltopdf`、`weasyprint`、`prince` 或 `pdfroff`。`highlight_style` 接受 `pygments`、`tango`、`espresso`、`zenburn`、`kate`、`monochrome`、`breezedark` 或 `haddock`。

## 支持的格式

- **FFmpeg** 支持你的 FFmpeg 构建所包含的媒体容器、编解码器、滤镜和图像格式。常见示例包括 MP4、MKV、MOV、AVI、WebM、MP3、AAC、WAV、FLAC、Ogg/Opus、GIF 以及 JPEG/PNG/WebP 图像。
- **Pandoc** 读写你的 Pandoc 版本支持的文档格式，包括各种 Markdown 变体、HTML、EPUB、DOCX、ODT、RTF、LaTeX、reStructuredText、Org、AsciiDoc、MediaWiki、Textile、Jupyter notebook、OPML 以及 PPTX 输出。PDF 输出通过外部 PDF 引擎生成。

无论使用哪个工具，已安装的工具才是格式可用性的最终依据；ffai 只传递任务表达的选项，并拒绝违反其校验规则的值。

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
         │  JSON：intent + 单工具任务补丁（ffmpeg | pandoc）
         ▼
   Pydantic 校验 ──► SessionState.apply_patch
         │
         ▼
   工具构建器（command_builder | pandoc_builder）   参数列表，不使用 Shell
         │
         ▼
   预览 ──► 用户确认 ──► executor（子进程，FFmpeg 实时进度）
```

任务和补丁结构定义在 `ffai/models.py`。每个补丁只针对一个工具：

```python
class ToolPatch(BaseModel):
    ffmpeg: FFmpegPatch | None = None
    pandoc: PandocPatch | None = None
    # 只能包含一个工具；未出现的字段保持不变，显式 null 清除值。
```

LLM 每轮返回三种意图之一：

- `apply`：为一个工具应用非空补丁（空工具载荷只表示选择该工具）。
- `clarify`：提出一个聚焦的问题，不修改任务。
- `noop`：进行解释，不修改任务。

完整模型结果还包括 `explanation` 和可选的 `question`。`inputs` 和 `output` 不可通过补丁修改。每个工具在 `SessionState` 中各自持有任务，因此补丁和切换不会把不同工具的字段混在一起。

### 模块

| 模块 | 职责 |
| --- | --- |
| `ffai/cli.py` | Argparse 入口和顶层错误处理 |
| `ffai/repl.py` | REPL 循环、命令分发、Rich 展示和确认 |
| `ffai/line_input.py` | 基于 readline 的提示符、历史记录和 TAB 路径补全 |
| `ffai/parser.py` | 内置命令与自然语言输入解析 |
| `ffai/models.py` | 按工具划分的任务、补丁和 LLM 决策结构 |
| `ffai/tools.py` | 工具注册表、可执行文件与扩展名路由 |
| `ffai/state.py` | 按工具维护的会话状态和经过文件系统校验的变更 |
| `ffai/prompt.py` | 双工具 System Prompt 和当前状态上下文 |
| `ffai/llm.py` | OpenAI 兼容客户端、JSON 提取和校验重试 |
| `ffai/command_builder.py` | FFmpeg 任务到参数列表转换及额外参数白名单 |
| `ffai/pandoc_builder.py` | Pandoc 任务到参数列表转换、路径校验和选项白名单 |
| `ffai/executor.py` | 通用子进程执行、进度解析和中断处理 |
| `ffai/config.py` | `.env`/环境变量配置及安全持久化 |
| `ffai/utils.py` | 命令渲染、时长探测和环境变量脱敏 |
| `ffai/i18n.py` | 英文和简体中文界面文案及语言检测 |

## 命令构建与安全

通用保证：

- LLM 输出仅限 `ToolPatch` 结构，未知字段会被拒绝；不会解释或执行模型生成的 Shell/Python 代码。
- 命令通过参数列表和 `shell=False` 调用。
- 输入和输出路径会规范化，并检查存在性、可读性、父目录有效性以及是否误覆盖输入文件。
- 执行前始终显示完整的参数列表渲染命令并要求确认；已存在的输出文件会在确认前提示。
- 工具运行时关闭 stdin，并移除名称包含 `KEY`、`SECRET`、`TOKEN`、`PASSWORD`、`PASSWD` 或 `CREDENTIAL` 的环境变量。
- Ctrl+C 会终止工具的进程组，超时后从 SIGTERM 升级到 SIGKILL，并按中断状态报告结果。
- 成功退出后会验证目标输出文件；退出码为 0 但文件缺失或为空时按失败处理。

FFmpeg 专项规则：

- 多输入必须显式提供 `maps` 或 `filter_complex`，输入永远不会被隐式拼接。
- `filter_complex` 不能与简单视频/音频滤镜链同时使用。
- 流复制模式会拒绝滤镜、CRF、Preset 或码率等无效组合。
- `extra_options` 只接受一组保守的常用输出参数，且每个参数必须有固定数量的值。设置编码器、滤镜、映射、覆盖行为或写入额外文件的参数会被拒绝。白名单定义在 `ffai/command_builder.py`，并嵌入 LLM prompt。

Pandoc 专项规则：

- 无法使用 `--filter`、`--lua-filter`、`--pdf-engine-opt` 和 `--data-dir`：任何 Pandoc 选项都不能执行任意程序或追加任意引擎参数。
- `pdf_engine` 仅限上方白名单；任意可执行文件路径都会被拒绝。
- `highlight_style` 仅限文档中列出的白名单。
- `template`、`reference_doc`、`bibliography` 和 `csl` 必须指向存在且可读的本地文件；`resource_path` 条目必须是存在的本地目录。
- `extra_options` 只接受少量参数数量固定的 Pandoc 选项白名单。Shell 片段和白名单之外的选项会被拒绝。
- 只有显式设置时才把 `from_format` 和 `to_format` 作为 `-f`/`-t` 传入，并校验其为单个格式名 token。
- `metadata` 条目每个都作为一对 `-M key=value` 参数传入。

最终确认可见命令和输出路径仍由你负责。FFmpeg 和 Pandoc 本身都具有很强能力，确认界面是最后一道授权步骤。

## 故障排查

| 现象 | 处理方法 |
| --- | --- |
| 提示 `FFmpeg was not found on PATH` | 安装 FFmpeg（见[安装](#安装)），打开新终端，并检查 `ffmpeg -version`。 |
| 提示 `Pandoc was not found on PATH` | 安装 Pandoc（见[安装](#安装)），打开新终端，并检查 `pandoc --version`。 |
| PDF 转换因缺少 `pdflatex` 等引擎而失败 | 安装 PDF 引擎（Tectonic、TeX Live 或 Typst），并确认其在 `PATH` 中。在请求中选择已安装的引擎，例如“使用 xelatex 导出 PDF”或“使用 tectonic”。 |
| Pandoc 报未知格式错误 | 传入你的 Pandoc 版本支持的格式；使用 `pandoc --list-input-formats` 和 `pandoc --list-output-formats` 查看。 |
| FFmpeg 没有进度百分比 | 安装 `ffprobe`；没有它时 REPL 只显示已用时间。Pandoc 运行不报告百分比。 |
| 启动时提示缺少某个工具 | ffai 会分别提示缺失的工具；安装你需要的工具即可，另一个工具仍可使用。 |

## 开发

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
ruff check .
pytest
```

解析器、状态转换、命令构建器、配置和 LLM 响应解析都可以在无网络环境下测试。LLM 边界是核心路径中唯一非确定性的外部依赖。安装了对应工具时会运行真实的执行器测试。

### 发布

发布通过 `publish.yml` GitHub Actions 工作流，借助 [Trusted Publishing](https://docs.pypi.org/trusted-publishers/) 上传到 PyPI，仓库中不需要保存 API token。首次使用时在 PyPI 项目设置里为 `ffai-cli` 添加 pending publisher：owner `Lixuannan`、仓库 `ffai`、工作流 `publish.yml`、环境 `pypi`。之后每次发版，同步更新 `pyproject.toml` 的 `version` 和 `ffai/__init__.py` 的 `__version__`，再创建 GitHub Release 即触发上传。PyPI 的版本号不可重复使用。

```bash
python -m build
twine check dist/*
```

## 已知限制

- 每个工具的任务只有一个输出文件；不支持批处理或持久化会话。
- 只支持本地文件输入。
- 仅接受额外参数白名单中的选项。FFmpeg 与 Pandoc 的白名单分别定义在 `ffai/command_builder.py` 和 `ffai/pandoc_builder.py`，并嵌入 LLM prompt；白名单之外的参数会被拒绝，而不是直接透传。
- Pandoc 的 PDF 输出需要单独安装 PDF 引擎。
- 滤镜表达式和选项值只会在 ffai 已知的边界做语法检查。滤镜图有效性、编解码器可用性和格式支持仍以外部工具为准。
- 进度百分比估算需要 `ffprobe`，且仅适用于 FFmpeg。

## 许可证

MIT。
