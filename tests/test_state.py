from __future__ import annotations

from pathlib import Path

import pytest

from ffai.errors import StateError
from ffai.models import TaskPatch
from ffai.state import SessionState


@pytest.fixture
def media_file(tmp_path: Path) -> Path:
    path = tmp_path / "input.mp4"
    path.write_bytes(b"placeholder")
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
        TaskPatch(
            video_codec="libx265",
            audio_codec="aac",
            crf=23,
            audio_bitrate="192k",
            description="Transcode with H.265",
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
    state.apply_patch(TaskPatch(video_codec="libx264", crf=20))
    state.apply_patch(TaskPatch.model_validate({"video_codec": None, "crf": None}))
    assert state.task.video_codec is None
    assert state.task.crf is None


def test_apply_patch_explicit_null_clears_list(state: SessionState) -> None:
    state.apply_patch(TaskPatch(video_filters=["scale=1280:720"]))
    state.apply_patch(TaskPatch.model_validate({"video_filters": None}))
    assert state.task.video_filters == []


def test_apply_patch_omitted_fields_are_unchanged(state: SessionState) -> None:
    state.apply_patch(TaskPatch(video_codec="libx264", crf=18))
    state.apply_patch(TaskPatch(audio_codec="libopus"))
    assert state.task.video_codec == "libx264"
    assert state.task.crf == 18
    assert state.task.audio_codec == "libopus"


def test_apply_patch_rejects_filter_graph_conflict_without_mutation(
    state: SessionState,
) -> None:
    state.apply_patch(TaskPatch(video_filters=["scale=1280:720"]))
    before = state.task.model_dump()
    revision = state.revision
    with pytest.raises(StateError, match="filter_complex"):
        state.apply_patch(
            TaskPatch(
                filter_complex="[0:v]scale=640:360[v]",
                maps=["[v]"],
            )
        )
    assert state.task.model_dump() == before
    assert state.revision == revision


def test_empty_patch_makes_no_change(state: SessionState) -> None:
    revision = state.revision
    assert state.apply_patch(TaskPatch()) == []
    assert state.revision == revision


def test_reset_clears_all_task_fields(state: SessionState) -> None:
    state.apply_patch(TaskPatch(video_codec="libx265", crf=23))
    state.reset()
    assert state.task.inputs == []
    assert state.task.output is None
    assert state.task.video_codec is None


def test_llm_context_has_state_but_no_secret_material(state: SessionState) -> None:
    context = state.llm_context()
    assert context["inputs"] == state.task.inputs
    assert context["output"] == state.task.output
    assert context["revision"] == state.revision
    assert "api_key" not in context
