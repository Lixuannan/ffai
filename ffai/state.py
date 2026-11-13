"""Stateful, locally owned conversion task session.

A session holds one task per conversion tool plus the currently selected tool.
Inputs and outputs are shared user-facing files for the active tool, and are
still changed exclusively through :meth:`SessionState.add_inputs` and
:meth:`SessionState.set_output`, which validate paths locally. LLM patches can
only update the technical fields of the tool they target.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ffai.errors import StateError
from ffai.models import (
    FFmpegPatch,
    FFmpegTask,
    PandocPatch,
    PandocTask,
    ToolName,
    ToolPatch,
)
from ffai.tools import TOOL_SPECS, ToolSpec, detect_tool, get_tool

_LIST_PATCH_FIELDS = {
    "video_filters",
    "audio_filters",
    "extra_options",
    "maps",
    "metadata",
    "bibliography",
    "resource_path",
}
_BOOL_PATCH_FIELDS = {
    "standalone",
    "toc",
    "number_sections",
    "embed_resources",
    "citeproc",
}


@dataclass(frozen=True, slots=True)
class AddInputsResult:
    added: tuple[str, ...]
    duplicates: tuple[str, ...]
    tool: ToolName
    switched_tool: ToolName | None = None


@dataclass(frozen=True, slots=True)
class TaskChange:
    field: str
    before: Any
    after: Any


@dataclass(slots=True)
class SessionState:
    """Owns the tasks and all filesystem-facing mutations.

    Each tool keeps its own task, so switching tools preserves the other
    tool's work. When the active task is still empty, adding files whose
    extensions clearly belong to the other tool selects that tool
    automatically.
    """

    tool: ToolName = "ffmpeg"
    ffmpeg_task: FFmpegTask = field(default_factory=FFmpegTask)
    pandoc_task: PandocTask = field(default_factory=PandocTask)
    revision: int = 0

    @property
    def task(self) -> FFmpegTask | PandocTask:
        return self._task_for(self.tool)

    @property
    def spec(self) -> ToolSpec:
        return get_tool(self.tool)

    def _task_for(self, tool: ToolName) -> FFmpegTask | PandocTask:
        return self.ffmpeg_task if tool == "ffmpeg" else self.pandoc_task

    def _store_task(self, tool: ToolName, task: FFmpegTask | PandocTask) -> None:
        if tool == "ffmpeg":
            self.ffmpeg_task = task  # type: ignore[assignment]
        else:
            self.pandoc_task = task  # type: ignore[assignment]

    def select_tool(self, tool: ToolName) -> bool:
        """Switch the active tool. Returns whether the selection changed."""

        if tool not in TOOL_SPECS:
            raise StateError(f"Unknown conversion tool: {tool}")
        if tool == self.tool:
            return False
        self.tool = tool
        self.revision += 1
        return True

    def add_inputs(self, raw_paths: list[str] | tuple[str, ...]) -> AddInputsResult:
        if not raw_paths:
            raise StateError("add requires at least one input file")

        candidates: list[Path] = []
        seen: list[Path] = []
        for raw in raw_paths:
            if not raw.strip():
                raise StateError("Input filenames must not be empty")
            candidate = self._resolve_existing_file(raw)
            if any(_same_file(candidate, existing) for existing in seen):
                continue
            seen.append(candidate)
            candidates.append(candidate)

        # Resolving every path above keeps the operation atomic: a missing
        # file never leaves the session partially updated.
        pending = [str(path) for path in candidates]
        switched: ToolName | None = None
        if not self.task.inputs and self.task.output is None:
            detected = detect_tool(pending)
            if detected is not None and detected != self.tool:
                switched = detected

        activation = switched or self.tool
        task = self._task_for(activation)

        added: list[str] = []
        duplicates: list[str] = []
        for candidate in candidates:
            candidate_str = str(candidate)
            if candidate_str in task.inputs or any(
                _same_file(candidate, existing) for existing in task.inputs
            ):
                duplicates.append(candidate_str)
                continue
            if task.output is not None and _same_file(candidate, task.output):
                raise StateError(
                    f"Input file is also the current output: {candidate_str}. "
                    "Choose a different output with setoutput."
                )
            added.append(candidate_str)

        if not added and switched is None:
            return AddInputsResult(
                added=(),
                duplicates=tuple(duplicates),
                tool=self.tool,
            )

        self.tool = activation
        task.inputs.extend(added)
        self.revision += 1
        return AddInputsResult(
            added=tuple(added),
            duplicates=tuple(duplicates),
            tool=self.tool,
            switched_tool=switched,
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

    def apply_patch(self, patch: ToolPatch) -> list[TaskChange]:
        """Apply only explicitly supplied patch fields and return a diff.

        A patch with no tool is a no-op. Selecting a different tool is itself
        a visible change even when the tool payload is empty.
        """

        tool = patch.tool
        fields = patch.fields
        if tool is None or fields is None:
            return []

        target = self._task_for(tool)
        updates = _patch_updates(fields)
        if not updates and tool == self.tool:
            return []

        candidate_data = target.model_dump()
        candidate_data.update(updates)
        try:
            candidate = type(target).model_validate(candidate_data)
        except ValidationError as exc:
            raise StateError(f"The proposed task is invalid: {exc}") from exc

        if isinstance(candidate, FFmpegTask) and candidate.filter_complex and (
            candidate.video_filters or candidate.audio_filters
        ):
            raise StateError(
                "filter_complex cannot be combined with simple video_filters or "
                "audio_filters. Clear the simple filters or remove filter_complex."
            )

        before_data = target.model_dump()
        candidate_snapshot = candidate.model_dump()
        changes: list[TaskChange] = []
        if tool != self.tool:
            changes.append(TaskChange(field="tool", before=self.tool, after=tool))
        changes.extend(
            TaskChange(field=name, before=before_data[name], after=candidate_snapshot[name])
            for name in updates
            if before_data[name] != candidate_snapshot[name]
        )
        if not changes:
            return []

        self._store_task(tool, candidate)
        self.tool = tool
        self.revision += 1
        return changes

    def reset(self) -> None:
        self._store_task(self.tool, get_tool(self.tool).task_type())
        self.revision += 1

    def llm_context(self) -> dict[str, Any]:
        context = self.task.model_dump()
        context["tool"] = self.tool
        context["revision"] = self.revision
        return context

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


def _patch_updates(fields: FFmpegPatch | PandocPatch) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    for field_name in fields.model_fields_set:
        value = getattr(fields, field_name)
        if field_name in _LIST_PATCH_FIELDS and value is None:
            value = []
        if field_name in _BOOL_PATCH_FIELDS and value is None:
            value = False
        if field_name == "description" and value is None:
            value = ""
        updates[field_name] = value
    return updates


def _same_file(left: str | Path, right: str | Path) -> bool:
    try:
        return os.path.samefile(left, right)
    except OSError:
        # At least one path does not exist yet; lexical comparison is the only
        # available check and is sufficient for normalized SessionState paths.
        return Path(left) == Path(right)
