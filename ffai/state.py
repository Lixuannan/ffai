"""Stateful, locally owned FFmpeg task session."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ffai.errors import StateError
from ffai.models import FFmpegTask, TaskPatch

_LIST_PATCH_FIELDS = {"video_filters", "audio_filters", "extra_options", "maps"}


@dataclass(frozen=True, slots=True)
class AddInputsResult:
    added: tuple[str, ...]
    duplicates: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TaskChange:
    field: str
    before: Any
    after: Any


@dataclass(slots=True)
class SessionState:
    """Owns the task and all filesystem-facing mutations.

    Task patches produced by an LLM can update technical fields only. Inputs
    and outputs can be changed exclusively through :meth:`add_inputs` and
    :meth:`set_output`, which validate paths locally.
    """

    task: FFmpegTask = field(default_factory=FFmpegTask)
    revision: int = 0

    def add_inputs(self, raw_paths: list[str] | tuple[str, ...]) -> AddInputsResult:
        if not raw_paths:
            raise StateError("add requires at least one input file")

        candidates: list[Path] = []
        duplicates: list[str] = []
        for raw in raw_paths:
            if not raw.strip():
                raise StateError("Input filenames must not be empty")
            candidate = self._resolve_existing_file(raw)
            candidate_str = str(candidate)

            if candidate_str in self.task.inputs or any(
                _same_file(candidate, existing) for existing in candidates
            ):
                duplicates.append(candidate_str)
                continue
            if self.task.output is not None and _same_file(candidate, self.task.output):
                raise StateError(
                    f"Input file is also the current output: {candidate_str}. "
                    "Choose a different output with setoutput."
                )
            candidates.append(candidate)

        if not candidates:
            return AddInputsResult(added=(), duplicates=tuple(duplicates))

        self.task.inputs.extend(str(path) for path in candidates)
        self.revision += 1
        return AddInputsResult(
            added=tuple(str(path) for path in candidates),
            duplicates=tuple(duplicates),
        )

    def set_output(self, raw_path: str) -> str:
        if not raw_path.strip():
            raise StateError("Output filename must not be empty")

        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        if path.name in {"", ".", ".."}:
            raise StateError("Output must be a filename, not a directory")

        try:
            parent = path.parent.resolve(strict=True)
        except OSError as exc:
            raise StateError(f"Output directory does not exist: {path.parent}") from exc
        if not parent.is_dir():
            raise StateError(f"Output parent is not a directory: {parent}")
        if not os.access(parent, os.W_OK | os.X_OK):
            raise StateError(f"Output directory is not writable: {parent}")

        target = parent / path.name
        if target.exists() and target.is_dir():
            raise StateError(f"Output path is a directory: {target}")
        for source in self.task.inputs:
            if _same_file(target, source):
                raise StateError(
                    f"Output would overwrite an input file: {target}. Choose a different path."
                )

        self.task.output = str(target)
        self.revision += 1
        return str(target)

    def apply_patch(self, patch: TaskPatch) -> list[TaskChange]:
        """Apply only explicitly supplied patch fields and return a diff."""

        if not patch.model_fields_set:
            return []

        updates: dict[str, Any] = {}
        for field_name in patch.model_fields_set:
            value = getattr(patch, field_name)
            if field_name in _LIST_PATCH_FIELDS and value is None:
                value = []
            if field_name == "description" and value is None:
                value = ""
            updates[field_name] = value

        candidate_data = self.task.model_dump()
        candidate_data.update(updates)
        try:
            candidate = FFmpegTask.model_validate(candidate_data)
        except ValidationError as exc:
            raise StateError(f"The proposed task is invalid: {exc}") from exc

        if candidate.filter_complex and (candidate.video_filters or candidate.audio_filters):
            raise StateError(
                "filter_complex cannot be combined with simple video_filters or "
                "audio_filters. Clear the simple filters or remove filter_complex."
            )

        before_data = self.task.model_dump()
        changes = [
            TaskChange(field=field, before=before_data[field], after=value)
            for field, value in candidate.model_dump().items()
            if field not in {"inputs", "output"} and before_data[field] != value
        ]
        if not changes:
            return []

        self.task = candidate
        self.revision += 1
        return changes

    def reset(self) -> None:
        self.task = FFmpegTask()
        self.revision += 1

    def llm_context(self) -> dict[str, Any]:
        return {
            "inputs": list(self.task.inputs),
            "output": self.task.output,
            "video_filters": list(self.task.video_filters),
            "audio_filters": list(self.task.audio_filters),
            "filter_complex": self.task.filter_complex,
            "maps": list(self.task.maps),
            "video_codec": self.task.video_codec,
            "audio_codec": self.task.audio_codec,
            "video_bitrate": self.task.video_bitrate,
            "audio_bitrate": self.task.audio_bitrate,
            "crf": self.task.crf,
            "preset": self.task.preset,
            "extra_options": list(self.task.extra_options),
            "description": self.task.description,
            "revision": self.revision,
        }

    @staticmethod
    def _resolve_existing_file(raw_path: str) -> Path:
        try:
            path = Path(raw_path).expanduser().resolve(strict=True)
        except OSError as exc:
            raise StateError(f"Input file does not exist: {raw_path}") from exc
        if not path.is_file():
            raise StateError(f"Input is not a regular file: {path}")
        if not os.access(path, os.R_OK):
            raise StateError(f"Input file is not readable: {path}")
        return path


def _same_file(left: str | Path, right: str | Path) -> bool:
    try:
        return os.path.samefile(left, right)
    except OSError:
        # At least one path does not exist yet; lexical comparison is the only
        # available check and is sufficient for normalized SessionState paths.
        return Path(left) == Path(right)
