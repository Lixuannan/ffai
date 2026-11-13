"""Build Pandoc argument lists from validated task state.

No shell string is ever constructed. Every path and value is passed as its own
argv entry, and options that can execute external programs (``--filter``,
``--lua-filter``, ``--pdf-engine-opt``, ``--data-dir``) are deliberately not
expressible. The PDF engine stays restricted to :data:`ffai.models.PDF_ENGINES`,
and extra options are a small allowlist with fixed arity.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from ffai.errors import CommandBuildError
from ffai.models import HIGHLIGHT_STYLES, PDF_ENGINES, PandocTask

PANDOC_BINARY = "pandoc"

# Extra options are presentation/layout options with a fixed number of values.
# Unknown options, filters, and options that name external programs are
# deliberately absent: those either execute code or belong to structured task
# fields validated separately.
_EXTRA_OPTION_ARITY: dict[str, int] = {
    "--columns": 1,
    "--epub-chapter-level": 1,
    "--epub-cover-image": 1,
    "--epub-metadata": 1,
    "--file-scope": 0,
    "--id-prefix": 1,
    "--incremental": 0,
    "--katex": 0,
    "--listings": 0,
    "--no-highlight": 0,
    "--number-offset": 1,
    "--preserve-tabs": 0,
    "--reference-location": 1,
    "--section-divs": 0,
    "--slide-level": 1,
    "--tab-stop": 1,
    "--top-level-division": 1,
    "--verbose": 0,
    "--wrap": 1,
}

# Long options only; a bare positional token or a short option is rejected
# before the allowlist is consulted.
_OPTION_TOKEN = re.compile(r"^--[A-Za-z][A-Za-z0-9-]*$")


def describe_allowed_extra_options() -> str:
    """Return a stable, human-readable allowlist for prompts and docs."""

    return ", ".join(sorted(_EXTRA_OPTION_ARITY))


def build_command(task: PandocTask) -> list[str]:
    """Validate *task* and return a deterministic Pandoc argv list.

    Paths are normalized to resolved absolute strings, so an input or output
    whose name starts with ``-`` cannot be mistaken for an option. Formats are
    emitted only when set because Pandoc usually infers them from extensions.
    """

    if not task.inputs:
        raise CommandBuildError("No input files. Use 'add <file>' first.")
    inputs = [_validate_input(raw) for raw in task.inputs]
    output = _validate_output(task.output)
    _validate_no_overwrite(inputs, output)

    template = _validate_readable_file(task.template, "Template file")
    reference_doc = _validate_readable_file(task.reference_doc, "Reference document")
    bibliography = [
        _validate_readable_file(raw, "Bibliography file") for raw in task.bibliography
    ]
    csl = _validate_readable_file(task.csl, "CSL file")
    resource_path = [_validate_resource_directory(raw) for raw in task.resource_path]
    extra_options = _validate_extra_options(task.extra_options)
    _validate_pdf_engine(task.pdf_engine)
    _validate_highlight_style(task.highlight_style)

    args = [PANDOC_BINARY]
    if task.from_format:
        args.extend(["-f", task.from_format])
    if task.to_format:
        args.extend(["-t", task.to_format])
    if task.standalone:
        args.append("--standalone")
    if task.toc:
        args.append("--toc")
    if task.toc_depth is not None:
        args.extend(["--toc-depth", str(task.toc_depth)])
    if task.number_sections:
        args.append("--number-sections")
    if task.shift_heading_level_by is not None:
        args.extend(["--shift-heading-level-by", str(task.shift_heading_level_by)])
    for entry in task.metadata:
        args.extend(["-M", entry])
    if template is not None:
        args.extend(["--template", template])
    if reference_doc is not None:
        args.extend(["--reference-doc", reference_doc])
    if task.pdf_engine is not None:
        args.extend(["--pdf-engine", task.pdf_engine])
    if task.highlight_style is not None:
        args.extend(["--highlight-style", task.highlight_style])
    if task.embed_resources:
        args.append("--embed-resources")
    if task.citeproc:
        args.append("--citeproc")
    for bibliography_file in bibliography:
        args.extend(["--bibliography", bibliography_file])
    if csl is not None:
        args.extend(["--csl", csl])
    if resource_path:
        args.extend(["--resource-path", os.pathsep.join(resource_path)])
    args.extend(extra_options)
    args.extend(["-o", output])
    args.extend(inputs)
    return args


def _validate_input(raw_path: str) -> str:
    try:
        path = Path(raw_path).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise CommandBuildError(f"Input file does not exist: {raw_path}") from exc
    if not path.is_file():
        raise CommandBuildError(f"Input is not a regular file: {path}")
    if not os.access(path, os.R_OK):
        raise CommandBuildError(f"Input file is not readable: {path}")
    return str(path)


def _validate_output(raw_output: str | None) -> str:
    if raw_output is None or not raw_output.strip():
        raise CommandBuildError("No output file. Use 'setoutput <file>' first.")

    path = Path(raw_output).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    if path.name in {"", ".", ".."}:
        raise CommandBuildError("Output must be a filename, not a directory")
    try:
        parent = path.parent.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise CommandBuildError(f"Output directory does not exist: {path.parent}") from exc
    if not parent.is_dir():
        raise CommandBuildError(f"Output parent is not a directory: {parent}")
    if not os.access(parent, os.W_OK | os.X_OK):
        raise CommandBuildError(f"Output directory is not writable: {parent}")

    target = parent / path.name
    if target.exists() and target.is_dir():
        raise CommandBuildError(f"Output path is a directory: {target}")
    return str(target)


def _validate_no_overwrite(inputs: list[str], output: str) -> None:
    for source in inputs:
        if _same_file(source, output):
            raise CommandBuildError(
                f"Output would overwrite an input file: {output}. Choose a different output."
            )


def _validate_readable_file(raw_path: str | None, label: str) -> str | None:
    """Normalize an optional path-valued option to a resolved absolute file."""

    if raw_path is None:
        return None
    try:
        path = Path(raw_path).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise CommandBuildError(f"{label} does not exist: {raw_path}") from exc
    if not path.is_file():
        raise CommandBuildError(f"{label} is not a regular file: {path}")
    if not os.access(path, os.R_OK):
        raise CommandBuildError(f"{label} is not readable: {path}")
    return str(path)


def _validate_resource_directory(raw_path: str) -> str:
    """Normalize an optional ``--resource-path`` entry to a resolved directory."""

    try:
        path = Path(raw_path).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise CommandBuildError(f"Resource path does not exist: {raw_path}") from exc
    if not path.is_dir():
        raise CommandBuildError(f"Resource path is not a directory: {path}")
    return str(path)


def _validate_pdf_engine(pdf_engine: str | None) -> None:
    if pdf_engine is not None and pdf_engine not in PDF_ENGINES:
        raise CommandBuildError(
            f"Unsupported PDF engine {pdf_engine!r}. Use one of: {', '.join(PDF_ENGINES)}"
        )


def _validate_highlight_style(highlight_style: str | None) -> None:
    if highlight_style is not None and highlight_style not in HIGHLIGHT_STYLES:
        raise CommandBuildError(
            f"Unsupported highlight style {highlight_style!r}. "
            f"Use one of: {', '.join(HIGHLIGHT_STYLES)}"
        )


def _validate_extra_options(options: list[str]) -> list[str]:
    """Expand only allowlisted options with their exact number of values."""

    validated: list[str] = []
    index = 0
    while index < len(options):
        option = options[index]
        if not _OPTION_TOKEN.match(option):
            raise CommandBuildError(
                f"Invalid extra option token {option!r}. Each argv token must be a "
                "supported '--option' followed by its values."
            )
        if option not in _EXTRA_OPTION_ARITY:
            raise CommandBuildError(
                f"Unsupported extra option {option!r}. Use structured task fields for "
                "filters, PDF engines, and other Pandoc behavior."
            )

        arity = _EXTRA_OPTION_ARITY[option]
        values = options[index + 1 : index + 1 + arity]
        if len(values) != arity:
            raise CommandBuildError(f"Extra option {option!r} requires {arity} value(s)")
        for value in values:
            if not value or value.startswith("-"):
                raise CommandBuildError(
                    f"Invalid value {value!r} for extra option {option!r}; values must not "
                    "start with '-'"
                )
            if "\x00" in value or "\n" in value or "\r" in value:
                raise CommandBuildError(f"Invalid control character in value for {option!r}")

        validated.extend(options[index : index + 1 + arity])
        index += 1 + arity

    return validated


def _same_file(left: str | Path, right: str | Path) -> bool:
    try:
        return os.path.samefile(left, right)
    except OSError:
        # The output may not exist yet; normalized path equality still catches
        # the common overwrite case.
        return Path(left) == Path(right)
