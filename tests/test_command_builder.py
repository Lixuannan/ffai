from __future__ import annotations

from pathlib import Path

import pytest

from ffai.errors import CommandBuildError
from ffai.models import FFmpegTask


@pytest.fixture
def media_file(tmp_path: Path) -> Path:
    path = tmp_path / "input.mp4"
    path.write_bytes(b"placeholder")
    return path


@pytest.fixture
def task(tmp_path: Path, media_file: Path) -> FFmpegTask:
    return FFmpegTask(inputs=[str(media_file)], output=str(tmp_path / "out.mp4"))


def test_minimal_command_order(tmp_path: Path, media_file: Path) -> None:
    from ffai.command_builder import build_command

    output = tmp_path / "out.mp4"
    command = build_command(FFmpegTask(inputs=[str(media_file)], output=str(output)))
    assert command == [
        "ffmpeg",
        "-hide_banner",
        "-nostdin",
        "-y",
        "-i",
        str(media_file.resolve()),
        str(output.resolve()),
    ]


def test_overwrite_can_be_disabled(tmp_path: Path, media_file: Path) -> None:
    from ffai.command_builder import build_command

    command = build_command(
        FFmpegTask(inputs=[str(media_file)], output=str(tmp_path / "out.mp4")),
        overwrite=False,
    )
    assert "-y" not in command


def test_builds_filters_codecs_and_encoding_options(tmp_path: Path, media_file: Path) -> None:
    from ffai.command_builder import build_command

    output = tmp_path / "out.mp4"
    task = FFmpegTask(
        inputs=[str(media_file)],
        output=str(output),
        video_filters=["scale=1920:1080", "pad=1920:1080:(ow-iw)/2:(oh-ih)/2"],
        audio_filters=["volume=0.9"],
        video_codec="libx265",
        audio_codec="aac",
        crf=23,
        preset="medium",
        video_bitrate="10M",
        audio_bitrate="192k",
        extra_options=["-movflags", "+faststart", "-shortest"],
    )
    command = build_command(task)
    assert command[:5] == ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-i"]
    assert command[5] == str(media_file.resolve())
    assert command[6:] == [
        "-vf",
        "scale=1920:1080,pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
        "-af",
        "volume=0.9",
        "-c:v",
        "libx265",
        "-c:a",
        "aac",
        "-crf",
        "23",
        "-preset",
        "medium",
        "-b:v",
        "10M",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        "-shortest",
        str(output.resolve()),
    ]


def test_paths_with_spaces_are_single_argv_entries(tmp_path: Path) -> None:
    from ffai.command_builder import build_command

    source = tmp_path / "my [input] video.mp4"
    source.write_bytes(b"placeholder")
    output = tmp_path / "my output.mp4"
    command = build_command(FFmpegTask(inputs=[str(source)], output=str(output)))
    assert command[command.index("-i") + 1] == str(source.resolve())
    assert command[-1] == str(output.resolve())


def test_multiple_inputs_require_explicit_mapping(tmp_path: Path, media_file: Path) -> None:
    from ffai.command_builder import build_command

    second = tmp_path / "second.mp4"
    second.write_bytes(b"placeholder")
    task = FFmpegTask(
        inputs=[str(media_file), str(second)],
        output=str(tmp_path / "out.mp4"),
    )
    with pytest.raises(CommandBuildError, match="Multiple inputs"):
        build_command(task)


def test_multiple_inputs_with_maps_builds(tmp_path: Path, media_file: Path) -> None:
    from ffai.command_builder import build_command

    second = tmp_path / "second.mp4"
    second.write_bytes(b"placeholder")
    task = FFmpegTask(
        inputs=[str(media_file), str(second)],
        output=str(tmp_path / "out.mp4"),
        maps=["0:v:0", "1:a:0?"],
    )
    command = build_command(task)
    assert command.count("-i") == 2
    assert command[command.index("-map") : command.index("-map") + 4] == [
        "-map",
        "0:v:0",
        "-map",
        "1:a:0?",
    ]


def test_filter_complex_and_maps_build(tmp_path: Path, media_file: Path) -> None:
    from ffai.command_builder import build_command

    task = FFmpegTask(
        inputs=[str(media_file)],
        output=str(tmp_path / "out.mp4"),
        filter_complex="[0:v]scale=1280:720[v]",
        maps=["[v]"],
        video_codec="libx264",
    )
    command = build_command(task)
    fc_index = command.index("-filter_complex")
    assert command[fc_index + 1] == "[0:v]scale=1280:720[v]"
    assert command[fc_index + 2 : fc_index + 4] == ["-map", "[v]"]


def test_filter_complex_requires_maps(tmp_path: Path, media_file: Path) -> None:
    from ffai.command_builder import build_command

    task = FFmpegTask(
        inputs=[str(media_file)],
        output=str(tmp_path / "out.mp4"),
        filter_complex="[0:v]scale=1280:720[v]",
    )
    with pytest.raises(CommandBuildError, match="requires at least one"):
        build_command(task)


def test_simple_filters_conflict_with_filter_complex(tmp_path: Path, media_file: Path) -> None:
    from ffai.command_builder import build_command

    task = FFmpegTask(
        inputs=[str(media_file)],
        output=str(tmp_path / "out.mp4"),
        video_filters=["scale=1280:720"],
        filter_complex="[0:v]hflip[v]",
        maps=["[v]"],
    )
    with pytest.raises(CommandBuildError, match="cannot be combined"):
        build_command(task)


def test_label_map_without_filter_complex_is_rejected(tmp_path: Path, media_file: Path) -> None:
    from ffai.command_builder import build_command

    task = FFmpegTask(
        inputs=[str(media_file)],
        output=str(tmp_path / "out.mp4"),
        maps=["[v]"],
    )
    with pytest.raises(CommandBuildError, match="filter_complex output"):
        build_command(task)


def test_stream_copy_rejects_filters_and_crf(tmp_path: Path, media_file: Path) -> None:
    from ffai.command_builder import build_command

    task = FFmpegTask(
        inputs=[str(media_file)],
        output=str(tmp_path / "out.mp4"),
        video_codec="copy",
        crf=20,
    )
    with pytest.raises(CommandBuildError, match="stream copy"):
        build_command(task)


def test_missing_input_is_reported(tmp_path: Path) -> None:
    from ffai.command_builder import build_command

    task = FFmpegTask(
        inputs=[str(tmp_path / "missing.mp4")],
        output=str(tmp_path / "out.mp4"),
    )
    with pytest.raises(CommandBuildError, match="does not exist"):
        build_command(task)


def test_missing_output_is_reported(media_file: Path) -> None:
    from ffai.command_builder import build_command

    with pytest.raises(CommandBuildError, match="No output"):
        build_command(FFmpegTask(inputs=[str(media_file)]))


def test_output_must_not_overwrite_input(tmp_path: Path, media_file: Path) -> None:
    from ffai.command_builder import build_command

    task = FFmpegTask(inputs=[str(media_file)], output=str(media_file))
    with pytest.raises(CommandBuildError, match="overwrite an input"):
        build_command(task)


def test_extra_options_allow_specifiers() -> None:
    from ffai.command_builder import _validate_extra_options

    assert _validate_extra_options(
        ["-profile:v", "high", "-frames:v", "100", "-metadata:s:v", "title=test"]
    ) == ["-profile:v", "high", "-frames:v", "100", "-metadata:s:v", "title=test"]


def test_extra_options_require_allowlisted_option(tmp_path: Path, media_file: Path) -> None:
    from ffai.command_builder import build_command

    task = FFmpegTask(
        inputs=[str(media_file)],
        output=str(tmp_path / "out.mp4"),
        extra_options=["-map", "0:v:0"],
    )
    with pytest.raises(CommandBuildError, match="Unsupported extra option"):
        build_command(task)


def test_extra_options_cannot_smuggle_positional_argument() -> None:
    from ffai.command_builder import _validate_extra_options

    with pytest.raises(CommandBuildError, match="Invalid extra option token"):
        _validate_extra_options(["-metadata", "title=x", "extra-output.mp4"])


def test_extra_option_arity_is_checked() -> None:
    from ffai.command_builder import _validate_extra_options

    with pytest.raises(CommandBuildError, match="requires 1 value"):
        _validate_extra_options(["-movflags"])
    with pytest.raises(CommandBuildError, match="Invalid extra option token"):
        _validate_extra_options(["-shortest", "unexpected"])


def test_extra_option_value_starting_with_dash_is_rejected() -> None:
    from ffai.command_builder import _validate_extra_options

    with pytest.raises(CommandBuildError, match="must not start"):
        _validate_extra_options(["-metadata", "-title=x"])


def test_extra_option_with_unknown_specifier_is_rejected() -> None:
    from ffai.command_builder import _validate_extra_options

    with pytest.raises(CommandBuildError, match="Stream specifier"):
        _validate_extra_options(["-movflags:v", "+faststart"])


def test_builder_accepts_no_extra_options(task: FFmpegTask) -> None:
    from ffai.command_builder import build_command

    command = build_command(task)
    assert command[-1].endswith("out.mp4")
