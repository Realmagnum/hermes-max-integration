"""Shared adapter/standalone bounded attachment readiness (never re-upload)."""
from __future__ import annotations

import asyncio
import os

import httpx
from gateway.platforms.base import SendResult

from .media_diagnostics import media_begin, media_event, media_wait


def readiness_settings(extra):
    """Use the same validated env/config settings in both outbound paths."""
    raw_attempts = os.getenv("MAX_MEDIA_READY_ATTEMPTS") or extra.get("media_ready_attempts")
    raw_timeout = os.getenv("MAX_MEDIA_READY_TIMEOUT") or extra.get("media_ready_timeout")
    try:
        attempts = int(str(raw_attempts).strip())
    except (TypeError, ValueError):
        attempts = 8
    attempts = min(attempts, 12) if attempts >= 1 else 8
    try:
        timeout = float(str(raw_timeout).strip())
    except (TypeError, ValueError):
        timeout = 90.0
    timeout = min(timeout, 300.0) if timeout >= 0.1 else 90.0
    return attempts, timeout


async def send_ready_attachment(client, url, params, body, attempts, timeout, *, headers=None):
    """Retry only definite HTTP 400/not-ready within one POST-inclusive budget.

    The caller owns the immutable body/token and uploads exactly once. Transport
    errors, cancellation, invalid JSON and every other HTTP rejection never replay.
    """
    deadline = asyncio.get_running_loop().time() + timeout
    for attempt in range(attempts):
        try:
            remaining = deadline - asyncio.get_running_loop().time()
            delay = min(2.0 * (2 ** (attempt - 1)), 16.0) if attempt else 0
            if remaining <= delay:
                break
            if delay:
                wait_started = asyncio.get_running_loop().time()
                try:
                    await asyncio.sleep(delay)
                finally:
                    media_wait(asyncio.get_running_loop().time() - wait_started)
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                break
            kwargs = {"params": params, "json": body}
            if headers is not None:
                kwargs["headers"] = headers
            media_begin("readiness")
            resp = await asyncio.wait_for(client.post(url, **kwargs), timeout=remaining)
            media_event("readiness", "response", status=getattr(resp, "status_code", None), attempt=attempt + 1)
            resp.raise_for_status()
            data = resp.json()
            if data.get("ok", True) is False:
                media_event("readiness", "rejected", status=getattr(resp, "status_code", None), attempt=attempt + 1)
                return SendResult(success=False, error="MAX rejected attachment", retryable=False)
            message = data.get("message", {})
            mid = str((message.get("body", {}) or {}).get("mid", "")
                      or message.get("message_id", "") or "")
            media_event("readiness", "success", status=getattr(resp, "status_code", None), attempt=attempt + 1, mid=mid)
            return SendResult(success=True, message_id=mid, raw_response=data)
        except httpx.HTTPStatusError as exc:
            code = "unavailable"
            try:
                error = exc.response.json()
                raw_code = error.get("code") if isinstance(error, dict) else None
                code = "attachment.not.ready" if raw_code == "attachment.not.ready" else "other"
            except (ValueError, TypeError):
                code = "invalid-json"
            media_event("readiness", "not_ready" if exc.response.status_code == 400 and code == "attachment.not.ready" else "error",
                        status=exc.response.status_code, attempt=attempt + 1)
            if (exc.response.status_code == 400 and code == "attachment.not.ready"
                    and attempt + 1 < attempts):
                continue
            return SendResult(success=False, error="Upload-send failed (see logs)", retryable=False)
        except Exception:  # noqa: BLE001 — ambiguous send must not be repeated
            media_event("readiness", "error", attempt=attempt + 1)
            return SendResult(success=False, error="Upload-send failed (see logs)", retryable=False)
    media_event("readiness", "budget_exhausted")

    return SendResult(success=False, error="Upload-send failed: attachment readiness budget exhausted", retryable=False)
