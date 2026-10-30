"""Typed errors shared across ffai modules."""

from __future__ import annotations


class FFAIError(Exception):
    """Base class for errors that can be presented to the user."""


class ConfigError(FFAIError):
    """API or runtime configuration is invalid."""


class StateError(FFAIError):
    """A task-state transition was rejected."""


class ParseError(FFAIError):
    """Command-line input could not be parsed."""


class CommandBuildError(FFAIError):
    """The current task cannot be converted into a safe FFmpeg command."""


class ExecutionError(FFAIError):
    """FFmpeg could not be started or did not produce its requested output."""


class LLMError(FFAIError):
    """The language-model request failed or returned unusable output."""
