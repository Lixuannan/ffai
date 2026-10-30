# ffai

English | [简体中文](README.zh-CN.md)

`ffai` is an interactive, stateful natural-language interface for FFmpeg. You
describe a media operation, the LLM updates a structured task, and ffai builds
the actual FFmpeg command locally. Nothing is executed until you confirm the
full command.

```text
ffai v0.1.0
Natural Language Interface for FFmpeg

ffai> add input.mp4
✓ Added input: /media/input.mp4
ffai> setoutput final.mp4
✓ Output set: /media/final.mp4
ffai> crop the video to 1920x1080, keeping the center framing
╭─ ffai ──────────────────────────────────────────────────────────╮
│ Updating the video filter chain to scale and center-crop.        │
╰─────────────────────────────────────────────────────────────────╯
ffai> use H.265 with CRF 23
...
ffai> preview
╭─ Preview not executed ──────────────────────────────────────────╮
│ ffmpeg -hide_banner -nostdin -y -i /media/input.mp4 \           │
│   -vf 'scale=1920:1080:force_original_aspect_ratio=increase,...' │
│   -c:v libx265 -crf 23 /media/final.mp4                         │
╰─────────────────────────────────────────────────────────────────╯
ffai> exec
```

## Features

- Interactive REPL with a persistent FFmpeg task.
- Incremental natural-language edits; existing fields are preserved unless the
  request changes them.
- Structured LLM output validated by Pydantic. The model never emits a shell
  command.
- Safe command construction from an argv list, with no `shell=True`.
- Multi-input support with explicit stream maps and `filter_complex`.
- Rich task panels, syntax-highlighted command previews, confirmation prompts,
  and live FFmpeg progress.
- Provider presets for OpenAI, OpenRouter, DeepSeek, GLM, Kimi, and Qwen, plus
  a custom OpenAI-compatible endpoint.
- First-run API setup wizard; `.env` settings are written with owner-only
  permissions. The `config` command displays or updates the active settings.
- English and Simplified Chinese UI with locale detection and an explicit
  language override. Natural-language replies follow the user's language.

## Requirements

- Python 3.11 or newer
- FFmpeg on `PATH`
- An OpenAI-compatible API key and model. ffai requires this configuration
  before the REPL starts.
- `ffprobe` on `PATH` for an estimated progress percentage (optional; execution
  and live elapsed time still work without it)

## Installation

```bash
git clone https://github.com/Lixuannan/ffai.git
cd ffai
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

For an isolated command install:

```bash
pipx install .
```

Verify the entry point:

```bash
ffai --version
```

## Configuration

API configuration is mandatory. On first launch, ffai requires a complete
configuration and opens an interactive setup wizard before showing the
`ffai>` prompt. Non-interactive launches without configuration exit with code
2. Configuration can also be provided through `.env` or the process
environment:

```bash
cp .env.example .env
```

The three settings are (`.env` and the process environment are both read;
process environment values take precedence over `.env`):

| Variable | Required for LLM | Meaning |
| --- | --- | --- |
| `OPENAI_API_KEY` | yes | API key |
| `OPENAI_MODEL` | yes | Chat model identifier |
| `OPENAI_BASE_URL` | no | OpenAI-compatible endpoint; omit for the OpenAI default |

### Provider presets

The setup wizard and `config set` offer these presets. The provider's base URL
is filled in automatically; the model is suggested but can be edited because
availability varies by account and region. Every provider stores its key in
`OPENAI_API_KEY`.

| Provider | Base URL | Suggested model | Documentation |
| --- | --- | --- | --- |
| OpenAI | `https://api.openai.com/v1` | `gpt-5.4-mini` | [OpenAI GPT-5.4 mini](https://developers.openai.com/api/docs/models/gpt-5.4-mini) |
| OpenRouter | `https://openrouter.ai/api/v1` | `openai/gpt-5.4-mini` | [OpenRouter quickstart](https://openrouter.ai/docs/quickstart) |
| DeepSeek | `https://api.deepseek.com` | `deepseek-flash` | [DeepSeek API docs](https://api-docs.deepseek.com/) |
| GLM (Zhipu) | `https://open.bigmodel.cn/api/paas/v4` | `glm-5.3` | [GLM-5.3 docs](https://docs.bigmodel.cn/cn/guide/models/text/glm-5.3) |
| Kimi (Moonshot) | `https://api.moonshot.cn/v1` | `kimi-k3.1-pro` | [Kimi API docs](https://platform.kimi.com/docs/get-api-key) |
| Qwen (DashScope) | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen3.8-flash` | [DashScope base URLs](https://www.alibabacloud.com/help/zh/model-studio/base-url) |
| Custom | Enter manually | Enter manually | Any OpenAI-compatible endpoint |

Select a provider by its list number or ID (`openai`, `openrouter`, `deepseek`,
`glm`, `kimi`, `qwen`, `custom`). OpenRouter model IDs are vendor-prefixed.
The Qwen preset uses the China-region endpoint; its API key must match the
selected region, so use a regional compatible-mode URL for other regions.

OpenAI environment example:

```dotenv
OPENAI_API_KEY=sk-your-key
OPENAI_MODEL=gpt-5.4-mini
# OPENAI_BASE_URL=https://api.openai.com/v1
```

DeepSeek environment example:

```dotenv
OPENAI_API_KEY=sk-your-deepseek-key
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_MODEL=deepseek-flash
```

The placeholder values from `.env.example` are treated as unset, so copying
the example file still triggers setup. The wizard saves settings to `.env` in
the current directory with mode `0600`. It never echoes the API key and
displays only a masked form. Use the REPL command `config` to show the active
configuration and `config set` to change it. When `config set` prompts, Enter
keeps a current value; choose another provider by number or ID to switch.
Ctrl+C cancels without writing anything.

Start ffai from the project directory (or any directory with the same exported
variables).

### UI language

The interface auto-detects Chinese from `LC_ALL`, `LC_MESSAGES`, or `LANG`;
otherwise it uses English. Override the choice with `FFAI_LANG=en` /
`FFAI_LANG=zh` (process environment or `.env`) or the `--lang en` / `--lang zh`
flag. LLM replies follow the language used in your request.

## Built-in commands

| Command | Action |
| --- | --- |
| `add <file> [file ...]` | Add existing, readable input files. Duplicates are ignored. |
| `setoutput <file>` | Set an output whose parent directory exists. The output cannot overwrite an input. |
| `show` | Display the current task, including inputs, output, filters, maps, codecs, and encoding parameters. |
| `preview` | Build and display the complete FFmpeg command without executing it. |
| `exec` | Display the command and ask for confirmation before running FFmpeg. |
| `reset` | Clear all task state. |
| `config` | Display the active API configuration with the key masked. |
| `config set` | Interactively update API settings and save them to `.env`. |
| `help` | Show command help. |
| `exit`, `quit` | Exit the REPL. |

Paths use shell-like quoting, so spaces in filenames work:

```text
add "my input video.mp4"
setoutput "renders/final cut.mp4"
```

Exact Chinese aliases are also accepted for `preview`, `show`, `exec`, `reset`,
`config`, `help`, and `exit`: `预览`, `显示`, `执行`, `重置`, `配置`, `帮助`,
`退出`.

Any unrecognized input is sent to the LLM. For example:

```text
convert to 1080p
use H.265 at CRF 23
audio AAC at 192k
crop to 1920x1080, center composition
remove all video filters
```

Inputs and output paths are controlled only by `add` and `setoutput`; the LLM
cannot change file paths. An LLM that needs a missing input/output is instructed
to tell you to use those commands.

## Architecture

```text
user input
   │
   ├── built-in command ───────────────► SessionState (local validation)
   │
   └── natural language
         │
         ▼
   OpenAI-compatible LLM
         │  JSON: intent + TaskPatch + explanation/question
         ▼
   Pydantic validation ──► SessionState.apply_patch
         │
         ▼
   command_builder.build_command(task)   argv list, no shell
         │
         ▼
   preview ──► user confirmation ──► executor (subprocess, live progress)
```

The two important models are defined in `ffai/models.py`:

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
    # Same technical fields as FFmpegTask, all optional.
    # Omitted fields are unchanged; explicit null clears a value.
    ...
```

The model returns one of three intents:

- `apply`: apply a non-empty `TaskPatch`.
- `clarify`: ask one focused question; no task mutation.
- `noop`: explain without mutating state.

The full model result also includes `explanation` and an optional `question`.
`inputs` and `output` are not patchable.

### Modules

| Module | Responsibility |
| --- | --- |
| `ffai/cli.py` | Argparse entry point and top-level error handling |
| `ffai/repl.py` | REPL loop, dispatch, Rich presentation, confirmation |
| `ffai/parser.py` | Built-in command parsing versus natural language |
| `ffai/providers.py` | Provider endpoints, suggested models, and docs links |
| `ffai/state.py` | Session ownership and filesystem-validated state changes |
| `ffai/models.py` | Pydantic task, patch, and LLM decision schemas |
| `ffai/llm.py` | OpenAI-compatible client, JSON extraction, validation retry |
| `ffai/prompt.py` | FFmpeg-expert system prompt and current-state context |
| `ffai/command_builder.py` | Task-to-argv conversion and extra-option allowlist |
| `ffai/executor.py` | FFmpeg subprocess, progress parsing, interrupt handling |
| `ffai/config.py` | `.env`/environment configuration and safe persistence |
| `ffai/utils.py` | Command rendering, duration probing, environment scrubbing |
| `ffai/i18n.py` | English and Simplified Chinese UI strings and language detection |

## Command construction and safety

- The LLM output is limited to the `TaskPatch` schema. Unknown fields are
  rejected, and no model-generated shell or Python code is interpreted.
- FFmpeg is invoked with a list argument vector and `shell=False`.
- Inputs and outputs are normalized local paths and checked for existence,
  readability, parent-directory validity, and accidental overwrite of an input.
- Multiple inputs require explicit `maps` or `filter_complex`; inputs are never
  implicitly concatenated.
- `filter_complex` cannot be combined with the simple video/audio filter chains.
- Stream-copy mode rejects filters, CRF, preset, or bitrates that would be
  ignored or invalid.
- `extra_options` accepts only a conservative allowlist of common output
  options with known arity. Options that set codecs, filters, maps, overwrite
  behavior, or side files are rejected. The allowlist is defined in
  `ffai/command_builder.py` and embedded in the LLM prompt.
- Execution always displays the complete argv-rendered command and asks for
  confirmation. Existing outputs are flagged before confirmation.
- FFmpeg runs with stdin closed and with an environment scrubbed of variables
  whose names contain `KEY`, `SECRET`, `TOKEN`, `PASSWORD`, `PASSWD`, or
  `CREDENTIAL`.
- Ctrl+C terminates the FFmpeg process group, escalating from SIGTERM to SIGKILL
  after a timeout, and reports the run as interrupted.
- A successful exit is verified against the expected output file; a zero exit
  with a missing or empty output is reported as a failure.

It remains your responsibility to confirm the visible command and output path.
FFmpeg itself is powerful; the confirmation screen is the final authorization
step.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
ruff check .
pytest
```

The parser, state transitions, command builder, configuration, and LLM response
parsing are testable without a network connection. The LLM boundary is the only
non-deterministic external dependency in the core path. A real FFmpeg executor
test runs when `ffmpeg` is available.

## Limitations

- One output file per task; no batch or persistent session storage.
- Local file inputs only.
- Only the documented extra-option allowlist is accepted; unsupported FFmpeg
  options are rejected instead of passed through.
- FFmpeg filter expressions and stream labels are syntactically checked only at
  the boundaries ffai knows about. FFmpeg remains the authority on graph
  validity and codec availability.
- Estimated progress requires `ffprobe`; otherwise the REPL shows elapsed time.

## License

MIT.
