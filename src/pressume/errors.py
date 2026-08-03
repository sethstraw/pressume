"""User-facing exceptions raised at pressume's external boundaries."""

from __future__ import annotations


class PressumeError(Exception):
    """Base class for errors that should be shown without a traceback."""


class RenderError(PressumeError):
    """Raised when an external renderer or generated artifact fails."""
