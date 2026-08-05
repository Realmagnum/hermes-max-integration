"""Hermes MAX Platform Plugin — MAX messenger adapter (voice transcription via Hermes core STT)."""
try:
    from .adapter import register
except ImportError:
    from adapter import register  # noqa: F401

__all__ = ["register"]
