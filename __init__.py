"""Hermes MAX STT Platform Plugin — MAX messenger adapter with voice transcription."""
try:
    from .adapter import register
except ImportError:
    from adapter import register  # noqa: F401

__all__ = ["register"]
