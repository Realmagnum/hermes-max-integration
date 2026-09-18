from __future__ import annotations

import asyncio
import json
import logging
import socket as _socket
import time
from typing import Any

import httpx

from .base import MaxBaseMixin, _http_body_snippet, _is_retryable_http_status

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
            self._webhook_ready_reason = "aiohttp not installed"
            self._set_fatal_error("no_aiohttp", "aiohttp not installed", retryable=False)
            return False

        # Port-in-use check
        try:
            with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as sock:
                sock.settimeout(1)
                sock.connect(("127.0.0.1", self._webhook_port))
            self._webhook_ready_reason = f"port {self._webhook_port} already in use"
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
            """Liveness only: the HTTP server is up. Says nothing about MAX."""
            return web.json_response({"status": "ok"})

        async def readiness_handler(req: web.Request) -> web.Response:
            """Readiness: MAX actually routes updates to this server.

            Answers 503 while the subscription is unregistered/rejected, so a
            probe can never read "healthy" from a bot that receives nothing.
            """
            if self._webhook_ready:
                return web.json_response({"status": "ready"})
            return web.json_response(
                {"status": "not_ready", "reason": self._webhook_ready_reason or "registering"},
                status=503,
            )

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
                except (json.JSONDecodeError, TypeError, ValueError):
                    return web.Response(status=400, text="invalid json")

            event = await self._build_event(payload)
            if event is not None:
                await self._message_queue.put(event)
            return web.Response(text="ok")

        app.router.add_get("/health", health_handler)
        app.router.add_get("/ready", readiness_handler)
        app.router.add_post(path, webhook_handler)

        self._webhook_ready = False
        self._webhook_ready_reason = "registering"
        self._webhook_app = app
        self._webhook_runner = web.AppRunner(app)
        await self._webhook_runner.setup()
        site = web.TCPSite(self._webhook_runner, self._webhook_host, self._webhook_port)
        await site.start()
        self._webhook_site = site
        logger.info("MAX: webhook on %s:%s%s", self._webhook_host, self._webhook_port, path)

        # Auto-register webhook if URL is set. A failed registration means MAX
        # will never deliver a single update here, so it must fail connect()
        # (and release the port) instead of reporting "connected".
        if self._webhook_url:
            ok, reason, retryable = await self._register_webhook(secret)
            if not ok:
                self._webhook_ready_reason = reason
                await self._teardown_webhook_server()
                self._set_fatal_error("webhook_register_failed", reason, retryable=retryable)
                logger.error("MAX: webhook registration failed, not connected: %s", reason)
                return False

        self._webhook_ready = True
        self._webhook_ready_reason = ""

        # Start poll loop for draining the queue
        self._poll_task = asyncio.create_task(self._queue_poll_loop())
        self._mark_connected()
        return True

    async def _register_webhook(self, secret: str) -> tuple[bool, str, bool]:
        """Register the webhook subscription with the MAX API.

        Returns ``(ok, reason, retryable)``. Registration counts as successful
        only when the transport completed, the status is 200 AND the body
        reports success — MAX answers 200 with ``{"success": false}`` for a
        rejected URL/secret, which must not be treated as connected.
        """
        body: dict[str, Any] = {
            "url": self._webhook_url,
            "update_types": ["message_created", "message_callback", "bot_started", "bot_added"],
        }
        if secret:
            body["secret"] = secret
        try:
            resp = await self._http_client.post(
                f"{MAX_API_BASE}/subscriptions",
                json=body,
                timeout=httpx.Timeout(10.0),
            )
        except Exception as e:  # noqa: BLE001 — transport error, adapter must not crash
            return False, f"webhook registration transport error: {type(e).__name__}: {e}", True

        if resp.status_code != 200:
            detail = (
                f"webhook registration returned HTTP {resp.status_code}"
                f"{_http_body_snippet(resp)}"
            )
            return False, detail, _is_retryable_http_status(resp.status_code)

        try:
            payload = resp.json()
        except ValueError:
            return False, "webhook registration returned a non-JSON body", False

        if not isinstance(payload, dict) or not payload.get("success"):
            detail = payload.get("message") if isinstance(payload, dict) else None
            return False, f"webhook registration rejected: {detail or 'success=false'}", False

        logger.info("MAX: webhook registered: %s", self._webhook_url)
        return True, "", False

    async def _teardown_webhook_server(self) -> None:
        """Stop the aiohttp server, release the port. Idempotent."""
        self._webhook_ready = False
        runner, self._webhook_runner = self._webhook_runner, None
        self._webhook_site = None
        self._webhook_app = None
        if runner is None:
            return
        try:
            await runner.cleanup()
        except Exception as exc:  # noqa: BLE001 — cleanup must not raise
            logger.debug("MAX: webhook teardown error: %s", exc)
