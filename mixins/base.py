from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from gateway.platforms.base import BasePlatformAdapter, MessageEvent

logger = logging.getLogger(__name__)


def _is_retryable_http_status(status: int) -> bool:
    """Classify a MAX API HTTP status for the gateway reconnect loop.

    429 (rate limited) and 5xx (server side) are transient — reconnecting may
    succeed. Every other non-200 status (401/403/404/...) signals a token,
    access or configuration problem that a blind retry will not fix.
    """
    return status == 429 or status >= 500


def _http_body_snippet(resp: Any, limit: int = 200) -> str:
    """Best-effort ``": <body excerpt>"`` for error messages. Never raises."""
    try:
        text = " ".join((resp.text or "").split())
    except Exception:  # noqa: BLE001 — error reporting must never raise
        return ""
    return f": {text[:limit]}" if text else ""


class MaxBaseMixin(BasePlatformAdapter):
    """
    Base mixin for MAX Platform Adapter.
    Holds core state and shared properties.
    """

    _http_client: httpx.AsyncClient | None
    _token: str
    _message_queue: asyncio.Queue[MessageEvent]
    _running: bool
    _stop: asyncio.Event
    _background_tasks: set[asyncio.Task]

    # Shared properties and utilities can be added here
