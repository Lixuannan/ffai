from __future__ import annotations

from pathlib import Path

import pytest

from ffai.errors import StateError
from ffai.models import FFmpegPatch, PandocPatch, ToolPatch
from ffai.state import SessionState


@pytest.fixture
def media_file(tmp_path: Path) -> Path:
    path = tmp_path / "input.mp4"
    path.write_bytes(b"placeholder")
    return path


@pytest.fixture
def document_file(tmp_path: Path) -> Path:
    path = tmp_path / "notes.md"
    path.write_text("# Notes\n", encoding="utf-8")
    return path


@pytest.fixture
def state(media_file: Path, tmp_path: Path) -> SessionState:
    session = SessionState()
    session.add_inputs((str(media_file),))
    session.set_output(str(tmp_path / "out.mp4"))
    return session


def test_add_inputs_normalizes_and_deduplicates(tmp_path: Path) -> None:
    source = tmp_path / "input.mp4"
    source.write_bytes(b"placeholder")
    state = SessionState()

    first = state.add_inputs((str(source),))
    second = state.add_inputs((str(source),))

    assert first.added == (str(source.resolve()),)
    assert second.added == ()
    assert second.duplicates == (str(source.resolve()),)
    assert state.task.inputs == [str(source.resolve())]
    assert state.revision == 1


def test_add_inputs_is_atomic_when_one_path_is_missing(tmp_path: Path, media_file: Path) -> None:
    state = SessionState()
    with pytest.raises(StateError, match="does not exist"):
        state.add_inputs((str(media_file), str(tmp_path / "missing.mp4")))
    assert state.task.inputs == []
    assert state.revision == 0


def test_add_inputs_rejects_output_being_used_as_input(tmp_path: Path, media_file: Path) -> None:
    state = SessionState()
    output = tmp_path / "out.mp4"
    output.write_bytes(b"placeholder")
    state.set_output(str(output))
    with pytest.raises(StateError, match="also the current output"):
        state.add_inputs((str(output),))
    assert state.task.inputs == []


def test_add_inputs_auto_selects_pandoc_for_documents(tmp_path: Path) -> None:
    notes = tmp_path / "notes.md"
    notes.write_text("# Notes\n", encoding="utf-8")
    state = SessionState()

    result = state.add_inputs((str(notes),))

    assert result.switched_tool == "pandoc"
    assert result.tool == "pandoc"
    assert state.tool == "pandoc"
    assert state.task.inputs == [str(notes.resolve())]


def test_add_inputs_auto_selects_ffmpeg_for_media(tmp_path: Path) -> None:
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"placeholder")
    state = SessionState()
    state.select_tool("pandoc")
    revision = state.revision

    result = state.add_inputs((str(media),))

    assert result.switched_tool == "ffmpeg"
    assert state.tool == "ffmpeg"
    assert state.revision == revision + 1


def test_add_inputs_keeps_tool_when_extension_is_unknown(tmp_path: Path) -> None:
    blob = tmp_path / "data.bin"
    blob.write_bytes(b"placeholder")
    state = SessionState()

    result = state.add_inputs((str(blob),))

    assert result.switched_tool is None
    assert state.tool == "ffmpeg"


def test_add_inputs_does_not_switch_when_active_task_has_content(
    state: SessionState, document_file: Path
) -> None:
    revision = state.revision

    result = state.add_inputs((str(document_file),))

    assert result.switched_tool is None
    assert state.tool == "ffmpeg"
    assert str(document_file.resolve()) in state.task.inputs
    assert state.revision == revision + 1


def test_select_tool_preserves_the_other_task(
    media_file: Path, document_file: Path, tmp_path: Path
) -> None:
    state = SessionState()
    state.add_inputs((str(media_file),))
    state.set_output(str(tmp_path / "out.mp4"))
    state.apply_patch(ToolPatch(ffmpeg=FFmpegPatch(video_codec="libx264")))

    assert state.select_tool("pandoc") is True
    state.add_inputs((str(document_file),))
    state.set_output(str(tmp_path / "notes.docx"))
    state.apply_patch(ToolPatch(pandoc=PandocPatch(to_format="docx")))

    assert state.select_tool("ffmpeg") is True
    assert state.task.video_codec == "libx264"
    assert state.task.inputs == [str(media_file.resolve())]
    assert state.ffmpeg_task.output == str((tmp_path / "out.mp4").resolve())
    assert state.pandoc_task.to_format == "docx"
    assert state.pandoc_task.inputs == [str(document_file.resolve())]
    assert state.select_tool("ffmpeg") is False


def test_select_tool_rejects_unknown_tool() -> None:
    state = SessionState()
    with pytest.raises(StateError, match="Unknown conversion tool"):
        state.select_tool("imagemagick")  # type: ignore[arg-type]


def test_set_output_resolves_to_absolute_path(tmp_path: Path) -> None:
    state = SessionState()
    output = state.set_output(str(tmp_path / "nested name.mp4"))
    assert output == str((tmp_path / "nested name.mp4").resolve())


def test_set_output_requires_existing_parent(tmp_path: Path) -> None:
    state = SessionState()
    with pytest.raises(StateError, match="does not exist"):
        state.set_output(str(tmp_path / "missing" / "out.mp4"))


def test_set_output_rejects_directory(tmp_path: Path) -> None:
    state = SessionState()
    with pytest.raises(StateError, match="directory"):
        state.set_output(str(tmp_path))


def test_set_output_rejects_overwriting_input(state: SessionState, media_file: Path) -> None:
    with pytest.raises(StateError, match="overwrite an input"):
        state.set_output(str(media_file))


def test_apply_patch_preserves_inputs_and_output(state: SessionState, media_file: Path) -> None:
    inputs_before = list(state.task.inputs)
    output_before = state.task.output
    revision_before = state.revision

    changes = state.apply_patch(
        ToolPatch(
            ffmpeg=FFmpegPatch(
                video_codec="libx265",
                audio_codec="aac",
                crf=23,
                audio_bitrate="192k",
                description="Transcode with H.265",
            )
        )
    )

    assert state.task.inputs == inputs_before
    assert state.task.output == output_before
    assert state.task.video_codec == "libx265"
    assert state.task.crf == 23
    assert state.task.audio_bitrate == "192k"
    assert state.revision == revision_before + 1
    assert {change.field for change in changes} == {
        "video_codec",
        "audio_codec",
        "crf",
        "audio_bitrate",
        "description",
    }


def test_apply_patch_explicit_null_clears_scalar(state: SessionState) -> None:
    state.apply_patch(ToolPatch(ffmpeg=FFmpegPatch(video_codec="libx264", crf=20)))
    state.apply_patch(
        ToolPatch(ffmpeg=FFmpegPatch.model_validate({"video_codec": None, "crf": None}))
    )
    assert state.task.video_codec is None
    assert state.task.crf is None


def test_apply_patch_explicit_null_clears_list(state: SessionState) -> None:
    state.apply_patch(ToolPatch(ffmpeg=FFmpegPatch(video_filters=["scale=1280:720"])))
    state.apply_patch(ToolPatch(ffmpeg=FFmpegPatch.model_validate({"video_filters": None})))
    assert state.task.video_filters == []


def test_apply_patch_omitted_fields_are_unchanged(state: SessionState) -> None:
    state.apply_patch(ToolPatch(ffmpeg=FFmpegPatch(video_codec="libx264", crf=18)))
    state.apply_patch(ToolPatch(ffmpeg=FFmpegPatch(audio_codec="libopus")))
    assert state.task.video_codec == "libx264"
    assert state.task.crf == 18
    assert state.task.audio_codec == "libopus"


def test_apply_patch_rejects_filter_graph_conflict_without_mutation(
    state: SessionState,
) -> None:
    state.apply_patch(ToolPatch(ffmpeg=FFmpegPatch(video_filters=["scale=1280:720"])))
    before = state.task.model_dump()
    revision = state.revision
    with pytest.raises(StateError, match="filter_complex"):
        state.apply_patch(
            ToolPatch(
                ffmpeg=FFmpegPatch(
                    filter_complex="[0:v]scale=640:360[v]",
                    maps=["[v]"],
                )
            )
        )
    assert state.task.model_dump() == before
    assert state.revision == revision


def test_apply_patch_switches_tool_and_reports_change(state: SessionState) -> None:
    changes = state.apply_patch(ToolPatch(pandoc=PandocPatch(to_format="docx")))

    assert state.tool == "pandoc"
    assert changes[0].field == "tool"
    assert changes[0].before == "ffmpeg"
    assert changes[0].after == "pandoc"
    assert changes[-1].field == "to_format"


def test_apply_patch_empty_tool_payload_switches_without_field_changes(
    state: SessionState,
) -> None:
    changes = state.apply_patch(ToolPatch(pandoc=PandocPatch()))

    assert state.tool == "pandoc"
    assert [change.field for change in changes] == ["tool"]


def test_apply_patch_pandoc_explicit_null_clears_list_and_bool(tmp_path: Path) -> None:
    state = SessionState()
    state.apply_patch(
        ToolPatch(
            pandoc=PandocPatch(
                toc=True,
                metadata=["title=Report"],
                bibliography=["refs.bib"],
            )
        )
    )
    state.apply_patch(
        ToolPatch(
            pandoc=PandocPatch.model_validate(
                {"toc": None, "metadata": None, "bibliography": None}
            )
        )
    )
    assert state.pandoc_task.toc is False
    assert state.pandoc_task.metadata == []
    assert state.pandoc_task.bibliography == []


def test_empty_patch_makes_no_change(state: SessionState) -> None:
    revision = state.revision
    assert state.apply_patch(ToolPatch()) == []
    assert state.revision == revision


def test_reset_clears_active_task_only(
    media_file: Path, document_file: Path, tmp_path: Path
) -> None:
    state = SessionState()
    state.add_inputs((str(media_file),))
    state.apply_patch(ToolPatch(ffmpeg=FFmpegPatch(video_codec="libx265", crf=23)))
    state.select_tool("pandoc")
    state.add_inputs((str(document_file),))
    state.apply_patch(ToolPatch(pandoc=PandocPatch(to_format="docx")))

    state.reset()

    assert state.tool == "pandoc"
    assert state.pandoc_task.inputs == []
    assert state.pandoc_task.to_format is None
    assert state.ffmpeg_task.inputs == [str(media_file.resolve())]
    assert state.ffmpeg_task.video_codec == "libx265"


def test_llm_context_has_tool_and_no_secret_material(state: SessionState) -> None:
    context = state.llm_context()
    assert context["tool"] == "ffmpeg"
    assert context["inputs"] == state.task.inputs
    assert context["output"] == state.task.output
    assert context["revision"] == state.revision
    assert "api_key" not in context


def test_llm_context_switches_with_the_active_tool(media_file: Path) -> None:
    state = SessionState()
    state.add_inputs((str(media_file),))
    state.select_tool("pandoc")
    context = state.llm_context()
    assert context["tool"] == "pandoc"
    assert context["to_format"] is None
    assert "video_codec" not in context
