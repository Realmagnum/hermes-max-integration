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
    _dm_user_ids: dict[str, str]
    _dm_chat_ids: dict[str, str]

    def _remember_dm(self, chat_id: str | int | None, user_id: str | int | None) -> None:
        """Record bidirectional mapping between MAX DM chat_id and user_id.

        Hermes Core addresses DMs via scoped 'user:<user_id>' for user-level session
        isolation, but the MAX Bot API strictly requires the integer chat_id for
        chat endpoints such as POST /chats/{chat_id}/actions and GET /chats/{chat_id}.
        """
        if not chat_id or not user_id:
            return
        cid = str(chat_id).strip()
        uid = str(user_id).strip()
        if not cid or not uid:
            return
        if not hasattr(self, "_dm_user_ids") or self._dm_user_ids is None:
            self._dm_user_ids = {}
        if not hasattr(self, "_dm_chat_ids") or self._dm_chat_ids is None:
            self._dm_chat_ids = {}
        self._dm_user_ids[cid] = uid
        self._dm_user_ids[f"chat:{cid}"] = uid
        self._dm_chat_ids[uid] = cid
        self._dm_chat_ids[f"user:{uid}"] = cid

    def _resolve_chat_id(self, chat_id: str) -> str:
        """Resolve a scoped chat_id (e.g. 'user:123' or 'chat:456') to a MAX chat_id.

        For DMs where chat_id is 'user:<uid>' or '<uid>', looks up the actual
        MAX dialog chat_id in _dm_chat_ids. If known, returns that chat_id.
        Otherwise falls back to the raw target ID.
        """
        if not chat_id:
            return ""
        dm_chat_ids = getattr(self, "_dm_chat_ids", None)
        if dm_chat_ids:
            if chat_id in dm_chat_ids:
                return dm_chat_ids[chat_id]
            parts = chat_id.split(":", 1)
            raw_id = parts[1] if len(parts) > 1 else chat_id
            if raw_id in dm_chat_ids:
                return dm_chat_ids[raw_id]
            return raw_id
        parts = chat_id.split(":", 1)
        return parts[1] if len(parts) > 1 else chat_id
