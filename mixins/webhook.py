from __future__ import annotations

import asyncio
import json
import logging
import socket as _socket
import time
from typing import Any

import httpx

from .base import MaxBaseMixin

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────

MAX_API_BASE = "https://platform-api.max.ru"
WEBHOOK_MAX_BODY_BYTES = 1_048_576  # 1 MB


def _verify_raw_secret(body: bytes, secret: str, secret_header: str | None) -> bool:
    """Constant-time comparison of webhook secret.

    Max sends the raw secret in X-Max-Bot-Api-Secret header (not HMAC).
    Uses secrets.compare for timing-safe string comparison.
    """
    import secrets
    del body  # kept for API compatibility
    if not secret:
        return True
    if not secret_header:
        return False
    return secrets.compare_digest(str(secret), str(secret_header))


class WebhookMixin(MaxBaseMixin):
    """
    Mixin for aiohttp webhook server logic.
    """

    async def _start_webhook(self) -> bool:
        """Start aiohttp webhook server."""
        try:
            from aiohttp import web
        except ImportError:
            self._set_fatal_error("no_aiohttp", "aiohttp not installed", retryable=False)
            return False

        # Port-in-use check
        try:
            with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as sock:
                sock.settimeout(1)
                sock.connect(("127.0.0.1", self._webhook_port))
            self._set_fatal_error("port_in_use", f"Port {self._webhook_port} already in use", retryable=False)
            return False
        except (ConnectionRefusedError, OSError):
            pass  # Port is free

        secret = self._webhook_secret
        path = self._webhook_path

        if not secret:
            logger.warning(
                "MAX: webhook started WITHOUT a secret (MAX_WEBHOOK_SECRET empty) — "
                "anyone can POST events to %s. Set MAX_WEBHOOK_SECRET in production.",
                self._webhook_url or f"{self._webhook_host}:{self._webhook_port}{path}",
            )

        app = web.Application()

        async def health_handler(req: web.Request) -> web.Response:
            return web.json_response({"status": "ok"})

        # Rate limiter for webhook (per-IP, in-memory, cleaned every 5 min)
        _webhook_hits: dict[str, list] = {}
        _WEBHOOK_LIMIT = 30   # max requests
        _WEBHOOK_WINDOW = 10  # per 10 seconds

        async def webhook_handler(req: web.Request) -> web.Response:
            nonlocal _webhook_hits
            # Simple per-IP rate limiting
            now = time.monotonic()
            peer = req.remote or "unknown"
            hits = _webhook_hits.get(peer, [])
            hits[:] = [t for t in hits if now - t < _WEBHOOK_WINDOW]
            if len(hits) >= _WEBHOOK_LIMIT:
                logger.warning("MAX: webhook rate limit exceeded for %s", peer)
                return web.Response(status=429)
            hits.append(now)
            _webhook_hits[peer] = hits
            # Periodic cleanup
            if len(_webhook_hits) > 1000:
                _webhook_hits = {k: v for k, v in _webhook_hits.items()
                                 if any(now - t < _WEBHOOK_WINDOW for t in v)}

            # Verify secret
            if secret:
                body = await req.read()
                sig = req.headers.get("X-Max-Bot-Api-Secret", "")
                if not _verify_raw_secret(body, secret, sig):
                    logger.warning("MAX: webhook secret verification failed")
                    return web.Response(status=403)
                try:
                    payload = json.loads(body)
                except json.JSONDecodeError:
                    return web.Response(status=400, text="invalid json")
            else:
                try:
                    payload = await req.json()
                except Exception:
                    return web.Response(status=400, text="invalid json")

            event = await self._build_event(payload)
            if event is not None:
                await self._message_queue.put(event)
            return web.Response(text="ok")

        app.router.add_get("/health", health_handler)
        app.router.add_post(path, webhook_handler)

        self._webhook_app = app
        self._webhook_runner = web.AppRunner(app)
        await self._webhook_runner.setup()
        site = web.TCPSite(self._webhook_runner, self._webhook_host, self._webhook_port)
        await site.start()
        logger.info("MAX: webhook on %s:%s%s", self._webhook_host, self._webhook_port, path)

        # Auto-register webhook if URL is set
        if self._webhook_url:
            try:
                body: dict[str, Any] = {
                    "url": self._webhook_url,
                    "update_types": ["message_created", "message_callback", "bot_started", "bot_added"],
                }
                if secret:
                    body["secret"] = secret
                resp = await self._http_client.post(
                    f"{MAX_API_BASE}/subscriptions",
                    json=body,
                    timeout=httpx.Timeout(10.0),
                )
                if resp.status_code == 200:
                    d = resp.json()
                    logger.info("MAX: webhook registered%s", "" if d.get("success") else f" — {d.get('message')}")
            except Exception as e:
                logger.error("MAX: webhook register failed: %s", e)

        # Start poll loop for draining the queue
        self._poll_task = asyncio.create_task(self._queue_poll_loop())
        self._mark_connected()
        return True
