# ffai

English | [简体中文](README.zh-CN.md)

`ffai` is an interactive, stateful natural-language format conversion assistant.
Describe a media operation or a document conversion, a language model updates a
structured task, and ffai builds the actual command locally with **FFmpeg**
(media files) or **Pandoc** (documents, ebooks, markup, and PDF). Nothing is
executed until you review the complete command and confirm it.

```text
ffai v0.2.0
Natural-language interface for media and document conversion

ffai> add notes.md
✓ Added input: /home/you/notes.md
Detected Pandoc from the input file type; the tool was selected automatically.
ffai> setoutput notes.docx
✓ Output set: /home/you/notes.docx
ffai> convert to a Word document with a table of contents
╭─ ffai ──────────────────────────────────────────────────────────╮
│ Enabling a table of contents for the Word output.               │
╰─────────────────────────────────────────────────────────────────╯
ffai> preview
╭─ Preview not executed ──────────────────────────────────────────╮
│ pandoc --toc -o /home/you/notes.docx /home/you/notes.md         │
╰─────────────────────────────────────────────────────────────────╯
ffai> exec
```

## Features

- Two external tools behind one REPL: FFmpeg for media and Pandoc for documents.
- Extension-based tool routing when you add files, plus an explicit
  `tool <ffmpeg|pandoc>` command to switch at any time.
- Each tool keeps its own task, so switching preserves the other tool's work;
  `reset` clears only the active task.
- Incremental natural-language edits; existing fields are preserved unless the
  request changes them.
- Structured LLM output validated by Pydantic. A response is a tool-scoped
  patch, and the model never emits a shell command.
- Safe command construction from an argv list, with no `shell=True`.
- FFmpeg: multi-input support with explicit stream maps and `filter_complex`.
- Pandoc: table of contents, section numbering, metadata, templates, reference
  documents, citeproc with bibliographies, PDF engines, syntax highlighting,
  and embedded resources.
- Rich task panels, syntax-highlighted command previews, confirmation prompts,
  and live FFmpeg progress.
- Interactive line editing: history with the arrow keys, TAB completion of file
  paths for `add` and `setoutput`, and a `ffai>` prompt that survives editing.
- Provider presets for OpenAI, OpenRouter, DeepSeek, GLM, Kimi, and Qwen, plus
  a custom OpenAI-compatible endpoint.
- First-run API setup wizard; `.env` settings are written with owner-only
  permissions. The `config` command displays or updates the active settings.
- English and Simplified Chinese UI with locale detection and an explicit
  language override. Natural-language replies follow the user's language.

## Requirements

- Python 3.11 or newer
- FFmpeg and/or Pandoc on `PATH`. Both are supported; install at least the tool
  you intend to use.
- An OpenAI-compatible API key and model. ffai requires this configuration
  before the REPL starts.
- `ffprobe` on `PATH` for an estimated FFmpeg progress percentage (optional;
  execution and live elapsed time still work without it)
- A LaTeX or Typst engine only for Pandoc PDF output (for example Tectonic or a
  TeX Live distribution). Non-PDF document conversions do not need one.

## Installation

Install from PyPI:

```bash
pip install ffai-cli
```

For an isolated command install:

```bash
pipx install ffai-cli
```

The distribution is named `ffai-cli` on PyPI; the Python package and the
`ffai` command keep the shorter name.

Verify the entry point:

```bash
ffai --version
```

### From source

```bash
git clone https://github.com/Lixuannan/ffai.git
cd ffai
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### FFmpeg

Install FFmpeg with the package manager you use, or download a build from
https://ffmpeg.org/download.html:

```bash
# macOS
brew install ffmpeg

# Debian / Ubuntu
sudo apt install ffmpeg

# Windows (Chocolatey)
choco install ffmpeg
```

### Pandoc

```bash
# macOS
brew install pandoc

# Debian / Ubuntu
sudo apt install pandoc

# Windows (Chocolatey)
choco install pandoc
```

You can also download an installer for your platform from
https://pandoc.org/installing.html. Verify with `pandoc --version`.

### PDF engine for Pandoc

Pandoc writes PDF by invoking an external engine. Install one if you want PDF
output:

```bash
# Tectonic (standalone, downloads packages on demand)
brew install tectonic
# or
cargo install tectonic
```

A TeX Live installation that provides `xelatex`, `lualatex`, `pdflatex`, or
`latexmk` also works. A Typst installation can be selected as the PDF engine
instead of a LaTeX engine. ffai restricts `pdf_engine` to the engines supported
by the command builder (see
[Command construction and safety](#command-construction-and-safety)).

## Quick start

### FFmpeg: crop and encode a video

```text
ffai> add input.mp4
✓ Added input: /media/input.mp4
ffai> setoutput final.mp4
✓ Output set: /media/final.mp4
ffai> crop the video to 1920x1080, keeping the center framing
╭─ ffai ──────────────────────────────────────────────────────────╮
│ Updating the video filter chain to scale and center-crop.       │
╰─────────────────────────────────────────────────────────────────╯
ffai> use H.265 with CRF 23
...
ffai> preview
╭─ Preview not executed ──────────────────────────────────────────╮
│ ffmpeg -hide_banner -nostdin -y -i /media/input.mp4 \           │
│   -vf 'scale=1920:1080:force_original_aspect_ratio=increase'    │
│   -c:v libx265 -crf 23 /media/final.mp4                         │
╰─────────────────────────────────────────────────────────────────╯
ffai> exec
```

`exec` asks for confirmation before FFmpeg runs.

### Pandoc: Markdown to Word with a table of contents

```text
ffai> add notes.md
✓ Added input: /home/you/notes.md
Detected Pandoc from the input file type; the tool was selected automatically.
ffai> setoutput notes.docx
✓ Output set: /home/you/notes.docx
ffai> convert to a Word document with a table of contents
ffai> preview
╭─ Preview not executed ──────────────────────────────────────────╮
│ pandoc --toc -o /home/you/notes.docx /home/you/notes.md         │
╰─────────────────────────────────────────────────────────────────╯
ffai> exec
```

### Pandoc: Markdown to PDF with xelatex

```text
ffai> add report.md
✓ Added input: /home/you/report.md
ffai> setoutput report.pdf
✓ Output set: /home/you/report.pdf
ffai> export to PDF with a table of contents using xelatex
ffai> preview
╭─ Preview not executed ──────────────────────────────────────────╮
│ pandoc --toc --pdf-engine xelatex \                             │
│   -o /home/you/report.pdf /home/you/report.md                   │
╰─────────────────────────────────────────────────────────────────╯
ffai> exec
```

Pandoc infers the input and output formats from the file extensions; ffai adds
`-f`/`-t` only when you set an explicit format. PDF output requires the selected
PDF engine to be installed.

### Switching tools manually

```text
ffai> tool pandoc
✓ Conversion tool set to Pandoc.
ffai> tool ffmpeg
✓ Conversion tool set to FFmpeg.
```

Switching never discards the other tool's task. `show`, `preview`, `exec`, and
`reset` act on the active tool.

## Built-in commands

| Command | Action |
| --- | --- |
| `add <file> [file ...]` | Add existing, readable input files to the active task. Duplicates are ignored. When the active task is still empty, recognized extensions can select the tool. |
| `setoutput <file>` | Set an output whose parent directory exists. The output cannot overwrite an input. |
| `tool <ffmpeg\|pandoc>` | Switch the active tool. Each tool keeps its own inputs, output, and fields. |
| `show` | Display the active task, including inputs, output, and the tool-specific fields. |
| `preview` | Build and display the complete command without executing it. |
| `exec` | Display the command and ask for confirmation before running it. |
| `reset` | Clear the active tool's task only; the other tool's task is kept. |
| `config`, `config show` | Display the active API configuration with the key masked. |
| `config set` | Interactively update API settings and save them to `.env`. |
| `help` | Show command help. |
| `exit`, `quit` | Exit the REPL. |

Paths use shell-like quoting, so spaces in filenames work:

```text
add "my input video.mp4"
setoutput "renders/final cut.mp4"
```

TAB completes file paths for the argument of `add` and `setoutput`. Completion
works from the current directory, from a relative subpath, or from an absolute
path as typed; `~/` is expanded for lookup but stays `~/` in the inserted text.
Directories are completed with a trailing `/` so you can keep navigating, hidden
entries are only offered when the typed prefix starts with `.`, and names with
spaces are escaped or kept inside an open quote automatically. TAB does nothing
for other built-in commands or natural-language input.

```text
add vid<TAB>                # completes an input file in the current directory
setoutput "renders/rec<TAB>  # completes paths, quoting names with spaces
```

Exact Chinese aliases are also accepted: `预览`, `显示`, `执行`, `重置`,
`配置`, `工具`, `帮助`, `退出`.

Any unrecognized input is sent to the LLM. For example:

```text
convert to 1080p
use H.265 at CRF 23
audio AAC at 192k
crop to 1920x1080, center composition
remove all video filters
convert the document to EPUB
add a table of contents and number the sections
export to PDF with xelatex
use the template letter.template
```

Only the task's input files and output path are controlled by `add` and
`setoutput`; the LLM cannot change them. Auxiliary Pandoc paths such as
`template`, `reference_doc`, `bibliography`, `csl`, and `resource_path` can be
set through natural language and are validated against the local filesystem.

## How tool routing works

- Adding files to an empty task (no inputs and no output yet) inspects their
  extensions. If all recognized extensions belong to one tool, that tool becomes
  active. The REPL announces the detected tool.
- If the extensions are mixed across tools, unknown, or the active task already
  has inputs or an output, the current tool is kept.
- `tool ffmpeg` and `tool pandoc` switch manually at any time. `add` only
  auto-selects a tool while the active task is still empty (no inputs and no
  output); after that it keeps the current tool.
- Each tool has its own task. `show`, `preview`, and `exec` use the active task;
  the other tool's task is preserved until you reset it.

Representative extension routing (the complete sets live in `ffai/tools.py`):

| Tool | Example extensions |
| --- | --- |
| FFmpeg | `.mp4`, `.mkv`, `.mov`, `.avi`, `.webm`, `.ts`, `.mp3`, `.m4a`, `.wav`, `.flac`, `.ogg`, `.opus`, `.jpg`, `.png`, `.gif`, `.webp` |
| Pandoc | `.md`, `.markdown`, `.txt`, `.docx`, `.odt`, `.html`, `.epub`, `.tex`, `.rst`, `.org`, `.adoc`, `.ipynb`, `.pptx` |

Unknown extensions keep the current tool. Use `tool` when a file type is not
recognized.

## Pandoc task fields

Natural language fills these fields. `from_format` and `to_format` are only
emitted when set; otherwise Pandoc infers the formats from file extensions.

| Field | Meaning |
| --- | --- |
| `from_format`, `to_format` | Explicit Pandoc reader/writer format names, for example `gfm` or `docx`. |
| `standalone` | Produce a standalone document. |
| `toc`, `toc_depth` | Add a table of contents, optionally with a depth from 1 to 6. |
| `number_sections` | Number section headings. |
| `shift_heading_level_by` | Shift heading levels by an offset from -10 to 10. |
| `metadata` | Repeatable `key=value` metadata entries. |
| `template` | Local template file used for the output. |
| `reference_doc` | Local reference document used for styling. |
| `pdf_engine` | PDF engine; restricted to the allowlist below. |
| `highlight_style` | Syntax-highlighting theme; restricted to the allowlist below. |
| `embed_resources` | Embed images and other resources into the output. |
| `citeproc` | Run Pandoc's citation processor. |
| `bibliography` | One or more local bibliography files. |
| `csl` | Local CSL citation style file. |
| `resource_path` | One or more local directories searched for resources. |
| `extra_options` | Allowlisted Pandoc options with a fixed number of values. |
| `description` | Short summary of the conversion. |

`pdf_engine` accepts `pdflatex`, `xelatex`, `lualatex`, `latexmk`, `tectonic`,
`typst`, `context`, `wkhtmltopdf`, `weasyprint`, `prince`, or `pdfroff`.
`highlight_style` accepts `pygments`, `tango`, `espresso`, `zenburn`, `kate`,
`monochrome`, `breezedark`, or `haddock`.

## Supported formats

- **FFmpeg** handles the media containers, codecs, filters, and image formats
  supported by your FFmpeg build. Common examples include MP4, MKV, MOV, AVI,
  WebM, MP3, AAC, WAV, FLAC, Ogg/Opus, GIF, and JPEG/PNG/WebP images.
- **Pandoc** reads and writes the document formats supported by your Pandoc
  version, including Markdown variants, HTML, EPUB, DOCX, ODT, RTF, LaTeX,
  reStructuredText, Org, AsciiDoc, MediaWiki, Textile, Jupyter notebooks,
  OPML, and PPTX output. PDF output is produced through an external PDF engine.

In both cases the installed tool is the authority on format availability; ffai
passes through what the task expresses and rejects values that violate its
validation rules.

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
         │  JSON: intent + tool-scoped patch (ffmpeg | pandoc)
         ▼
   Pydantic validation ──► SessionState.apply_patch
         │
         ▼
   tool builder (command_builder | pandoc_builder)   argv list, no shell
         │
         ▼
   preview ──► user confirmation ──► executor (subprocess, live FFmpeg progress)
```

The task and patch schemas are defined in `ffai/models.py`. Every patch
targets exactly one tool:

```python
class ToolPatch(BaseModel):
    ffmpeg: FFmpegPatch | None = None
    pandoc: PandocPatch | None = None
    # Exactly one tool; omitted fields are unchanged, explicit null clears.
```

The model returns one of three intents:

- `apply`: apply a non-empty patch for exactly one tool (an empty tool payload
  only selects that tool).
- `clarify`: ask one focused question; no task mutation.
- `noop`: explain without mutating state.

The full model result also includes `explanation` and an optional `question`.
`inputs` and `output` are not patchable. Each tool keeps its own task in
`SessionState`, so patches and switches never merge fields across tools.

### Modules

| Module | Responsibility |
| --- | --- |
| `ffai/cli.py` | Argparse entry point and top-level error handling |
| `ffai/repl.py` | REPL loop, dispatch, Rich presentation, confirmation |
| `ffai/line_input.py` | Readline-backed prompt, history, and TAB path completion |
| `ffai/parser.py` | Built-in command parsing versus natural language |
| `ffai/models.py` | Tool-scoped task, patch, and LLM decision schemas |
| `ffai/tools.py` | Tool registry, binaries, and extension-based routing |
| `ffai/state.py` | Per-tool session state and filesystem-validated changes |
| `ffai/prompt.py` | Two-tool system prompt and current-state context |
| `ffai/llm.py` | OpenAI-compatible client, JSON extraction, validation retry |
| `ffai/command_builder.py` | FFmpeg task-to-argv conversion and extra-option allowlist |
| `ffai/pandoc_builder.py` | Pandoc task-to-argv conversion, path checks, option allowlist |
| `ffai/executor.py` | Generic subprocess execution, progress parsing, interrupts |
| `ffai/config.py` | `.env`/environment configuration and safe persistence |
| `ffai/utils.py` | Command rendering, duration probing, environment scrubbing |
| `ffai/i18n.py` | English and Simplified Chinese UI strings and language detection |

## Command construction and safety

Shared guarantees:

- The LLM output is limited to the `ToolPatch` schema. Unknown fields are
  rejected, and no model-generated shell or Python code is interpreted.
- Commands are invoked with an argument vector and `shell=False`.
- Inputs and outputs are normalized local paths and checked for existence,
  readability, parent-directory validity, and accidental overwrite of an input.
- Execution always displays the complete argv-rendered command and asks for
  confirmation. Existing outputs are flagged before confirmation.
- The tool runs with stdin closed and with an environment scrubbed of variables
  whose names contain `KEY`, `SECRET`, `TOKEN`, `PASSWORD`, `PASSWD`, or
  `CREDENTIAL`.
- Ctrl+C terminates the tool's process group, escalating from SIGTERM to SIGKILL
  after a timeout, and reports the run as interrupted.
- A successful exit is verified against the expected output file; a zero exit
  with a missing or empty output is reported as a failure.

FFmpeg-specific rules:

- Multiple inputs require explicit `maps` or `filter_complex`; inputs are never
  implicitly concatenated.
- `filter_complex` cannot be combined with the simple video/audio filter chains.
- Stream-copy mode rejects filters, CRF, preset, or bitrates that would be
  ignored or invalid.
- `extra_options` accepts only a conservative allowlist of common output
  options with known arity. Options that set codecs, filters, maps, overwrite
  behavior, or side files are rejected. The allowlist is defined in
  `ffai/command_builder.py` and embedded in the LLM prompt.

Pandoc-specific rules:

- `--filter`, `--lua-filter`, `--pdf-engine-opt`, and `--data-dir` are not
  expressible: no Pandoc option can execute an arbitrary program or add an
  arbitrary engine argument.
- `pdf_engine` is restricted to the allowlist shown above; arbitrary executable
  paths are rejected.
- `highlight_style` is restricted to the documented allowlist.
- `template`, `reference_doc`, `bibliography`, and `csl` must point at existing,
  readable local files; `resource_path` entries must be existing local
  directories.
- `extra_options` accepts only a small allowlist of Pandoc options with fixed
  arity. Shell fragments and options outside the allowlist are rejected.
- `from_format` and `to_format` are only passed as `-f`/`-t` when explicitly
  set, and are validated as single format-name tokens.
- `metadata` entries are passed as one `-M key=value` argv pair each.

It remains your responsibility to confirm the visible command and output path.
Both FFmpeg and Pandoc are powerful tools; the confirmation screen is the final
authorization step.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `FFmpeg was not found on PATH` | Install FFmpeg (see [Installation](#installation)), open a new terminal, and check `ffmpeg -version`. |
| `Pandoc was not found on PATH` | Install Pandoc (see [Installation](#installation)), open a new terminal, and check `pandoc --version`. |
| PDF conversion fails with a missing engine such as `pdflatex` | Install a PDF engine (Tectonic, TeX Live, or Typst) and make sure it is on `PATH`. Select the engine you installed in your request, for example "export to PDF with xelatex" or "use tectonic". |
| Pandoc exits with an unknown format error | Pass a format that your Pandoc version supports; check `pandoc --list-input-formats` and `pandoc --list-output-formats`. |
| No progress percentage for FFmpeg | Install `ffprobe`; without it the REPL shows only elapsed time. Pandoc runs do not report a percentage. |
| A tool is reported missing at startup | ffai warns about each missing tool; install the ones you need. The other tool remains usable. |

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
ruff check .
pytest
```

The parser, state transitions, command builders, configuration, and LLM
response parsing are testable without a network connection. The LLM boundary is
the only non-deterministic external dependency in the core path. Real executor
tests run when the corresponding tool is available.

### Publishing

Releases go to PyPI from the `publish.yml` GitHub Actions workflow using
[Trusted Publishing](https://docs.pypi.org/trusted-publishers/), so no API token
is stored in the repository. One-time setup on PyPI: add a pending publisher for
`ffai-cli` with owner `Lixuannan`, repository `ffai`, workflow `publish.yml`, and
environment `pypi`. For each release, bump `version` in `pyproject.toml` and
`__version__` in `ffai/__init__.py`, then publish a GitHub Release to trigger
the upload. PyPI never allows reusing a version number.

```bash
python -m build
twine check dist/*
```

## Limitations

- One output file per tool task; no batch or persistent session storage.
- Local file inputs only.
- Only the extra-option allowlists are accepted. The FFmpeg and Pandoc
  allowlists are defined in `ffai/command_builder.py` and `ffai/pandoc_builder.py`
  and embedded in the LLM prompt; unlisted options are rejected instead of
  passed through.
- Pandoc PDF output requires a separately installed PDF engine.
- Filter expressions and option values are syntactically checked only at the
  boundaries ffai knows about. The external tool remains the authority on graph
  validity, codec availability, and format support.
- Estimated progress requires `ffprobe` and applies to FFmpeg only.

## License

MIT.
