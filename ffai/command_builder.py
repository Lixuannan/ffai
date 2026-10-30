"""Build FFmpeg argument lists from validated task state.

No shell string is ever constructed. Every path and value is passed as its own
argv entry, and model-provided extra options are restricted to a small set of
common output options with known arity.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from ffai.errors import CommandBuildError
from ffai.models import FFmpegTask

FFMPEG_BINARY = "ffmpeg"

# Extra options are output options with a fixed number of values. Unknown
# options, stream mapping, filters, codec selection, and options that write
# auxiliary files are deliberately not accepted here; those concerns are
# represented by structured task fields and validated separately.
_EXTRA_OPTION_ARITY: dict[str, int] = {
    "-aspect": 1,
    "-bf": 1,
    "-bufsize": 1,
    "-color_primaries": 1,
    "-color_range": 1,
    "-color_trc": 1,
    "-colorspace": 1,
    "-disposition": 1,
    "-f": 1,
    "-flags": 1,
    "-frames": 1,
    "-g": 1,
    "-keyint_min": 1,
    "-level": 1,
    "-map_chapters": 1,
    "-map_metadata": 1,
    "-max_muxing_queue_size": 1,
    "-maxrate": 1,
    "-metadata": 1,
    "-minrate": 1,
    "-movflags": 1,
    "-pix_fmt": 1,
    "-profile": 1,
    "-qmax": 1,
    "-qmin": 1,
    "-qscale": 1,
    "-r": 1,
    "-rc": 1,
    "-rc-lookahead": 1,
    "-refs": 1,
    "-s": 1,
    "-sc_threshold": 1,
    "-shortest": 0,
    "-ss": 1,
    "-svtav1-params": 1,
    "-t": 1,
    "-tag": 1,
    "-thread_type": 1,
    "-threads": 1,
    "-to": 1,
    "-tune": 1,
    "-x264-params": 1,
    "-x265-params": 1,
}

_OPTION_TOKEN = re.compile(r"^-[A-Za-z0-9][A-Za-z0-9_.:+-]*$")
# Specifier suffixes such as ":v", ":a:0", or ":s:v:0" are permitted for
# these options.
_SPECIFIER_OPTIONS = {
    "-aspect",
    "-disposition",
    "-frames",
    "-level",
    "-map_chapters",
    "-map_metadata",
    "-metadata",
    "-profile",
    "-tag",
}


def build_command(task: FFmpegTask, *, overwrite: bool = True) -> list[str]:
    """Validate *task* and return an FFmpeg argv list.

    The current task must have at least one existing input and a usable output
    path. Paths are normalized before use so an input named ``-foo.mp4`` cannot
    be mistaken for an FFmpeg option.
    """

    inputs = [_validate_input(raw) for raw in task.inputs]
    if not inputs:
        raise CommandBuildError("No input files. Use 'add <file>' first.")
    output = _validate_output(task.output)
    _validate_no_overwrite(inputs, output)
    _validate_encoding_combination(task)
    _validate_filter_graph(task, input_count=len(inputs))
    extra_options = _validate_extra_options(task.extra_options)

    args = [FFMPEG_BINARY, "-hide_banner", "-nostdin"]
    if overwrite:
        args.append("-y")
    for media_input in inputs:
        args.extend(["-i", media_input])

    if task.filter_complex:
        args.extend(["-filter_complex", task.filter_complex])
    for stream_map in task.maps:
        args.extend(["-map", stream_map])
    if task.video_filters:
        args.extend(["-vf", ",".join(task.video_filters)])
    if task.audio_filters:
        args.extend(["-af", ",".join(task.audio_filters)])
    if task.video_codec:
        args.extend(["-c:v", task.video_codec])
    if task.audio_codec:
        args.extend(["-c:a", task.audio_codec])
    if task.crf is not None:
        args.extend(["-crf", str(task.crf)])
    if task.preset:
        args.extend(["-preset", task.preset])
    if task.video_bitrate:
        args.extend(["-b:v", task.video_bitrate])
    if task.audio_bitrate:
        args.extend(["-b:a", task.audio_bitrate])
    args.extend(extra_options)
    args.append(output)
    return args


def describe_allowed_extra_options() -> str:
    """Return a stable, human-readable allowlist for prompts and docs."""

    return ", ".join(sorted(_EXTRA_OPTION_ARITY))


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
    for media_input in inputs:
        if _same_file(media_input, output):
            raise CommandBuildError(
                f"Output would overwrite an input file: {output}. Choose a different output."
            )


def _validate_encoding_combination(task: FFmpegTask) -> None:
    if task.video_codec == "copy":
        conflicts = []
        if task.video_filters:
            conflicts.append("video filters")
        if task.filter_complex:
            conflicts.append("filter_complex")
        if task.crf is not None:
            conflicts.append("CRF")
        if task.preset:
            conflicts.append("preset")
        if task.video_bitrate:
            conflicts.append("video bitrate")
        if conflicts:
            raise CommandBuildError(
                "Video stream copy cannot be combined with "
                + ", ".join(conflicts)
                + ". Clear those fields or use a real video encoder."
            )

    if task.audio_codec == "copy":
        conflicts = []
        if task.audio_filters:
            conflicts.append("audio filters")
        if task.audio_bitrate:
            conflicts.append("audio bitrate")
        if conflicts:
            raise CommandBuildError(
                "Audio stream copy cannot be combined with "
                + ", ".join(conflicts)
                + ". Clear those fields or use a real audio encoder."
            )


def _validate_filter_graph(task: FFmpegTask, *, input_count: int) -> None:
    if task.filter_complex and (task.video_filters or task.audio_filters):
        raise CommandBuildError(
            "filter_complex cannot be combined with simple video filters or "
            "audio filters. Put the whole graph in filter_complex, or clear it."
        )
    if task.filter_complex and not task.maps:
        raise CommandBuildError(
            "filter_complex requires at least one -map entry (for example '[v]' and '[a]')."
        )
    if task.maps:
        for stream_map in task.maps:
            if stream_map.startswith("[") and not task.filter_complex:
                raise CommandBuildError(
                    f"Map label {stream_map} refers to filter_complex output, "
                    "but filter_complex is empty."
                )
    if input_count > 1 and not task.maps and not task.filter_complex:
        raise CommandBuildError(
            "Multiple inputs need explicit maps or a filter_complex so FFmpeg does not "
            "silently choose streams. Add maps such as '0:v:0' and '1:a:0'."
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
                "supported '-option' followed by its values."
            )
        base = option.split(":", 1)[0]
        if base not in _EXTRA_OPTION_ARITY:
            raise CommandBuildError(
                f"Unsupported extra option {option!r}. Use structured task fields for "
                "codecs, filters, and stream mapping."
            )
        if option != base and base not in _SPECIFIER_OPTIONS:
            raise CommandBuildError(f"Stream specifier is not allowed for extra option {option!r}")

        arity = _EXTRA_OPTION_ARITY[base]
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
