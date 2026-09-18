from __future__ import annotations

import asyncio
import json
import logging
import secrets
import socket as _socket
import time
from typing import Any

import httpx

from .base import MaxBaseMixin

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────

MAX_API_BASE = "https://platform-api.max.ru"
WEBHOOK_MAX_BODY_BYTES = 1_048_576  # 1 MB
WEBHOOK_SECRET_HEADER = "X-Max-Bot-Api-Secret"
# Bind hosts accepted for the explicit secretless development opt-in. Values
# such as `0.0.0.0`, `::`, a LAN IP or a public hostname listen on interfaces
# reachable from other machines and are therefore never loopback.
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", "[::1]"})


def _is_loopback_host(host: str | None) -> bool:
    """True only for an explicit loopback bind host.

    ``0.0.0.0``/``::`` bind every interface, so they are *not* loopback and can
    never be used for the secretless dev mode.
    """
    if not host:
        return False
    return str(host).strip().lower() in LOOPBACK_HOSTS


def _verify_raw_secret(body: bytes, secret: str, secret_header: str | None) -> bool:
    """Constant-time comparison of webhook secret.

    Max sends the raw secret in X-Max-Bot-Api-Secret header (not HMAC).
    Uses secrets.compare_digest for timing-safe string comparison.

    Fails closed: an unconfigured secret, or a missing/empty request header,
    is never a match — an empty secret must not act as a wildcard.
    """
    del body  # kept for API compatibility
    if not secret or not secret_header:
        return False
    return secrets.compare_digest(str(secret), str(secret_header))


class WebhookMixin(MaxBaseMixin):
    """
    Mixin for aiohttp webhook server logic.
    """

    def _build_webhook_app(self, web: Any) -> Any:
        """Build the aiohttp application serving the webhook endpoint.

        Split out of :meth:`_start_webhook` so the routing and authentication
        logic can be exercised without binding a socket.
        """
        secret = self._webhook_secret
        insecure_dev = bool(getattr(self, "_webhook_insecure_dev", False))

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

            # ── Authenticate BEFORE reading or parsing the body ──────────
            # The header is checked first so an unauthenticated caller never
            # makes the server buffer or parse attacker-controlled JSON.
            if secret:
                if not _verify_raw_secret(
                    b"", secret, req.headers.get(WEBHOOK_SECRET_HEADER)
                ):
                    logger.warning("MAX: webhook secret verification failed")
                    return web.Response(status=403, text="forbidden")
            elif not insecure_dev:
                # Defence in depth: _start_webhook refuses to serve this case,
                # but never accept an unauthenticated event even if reached.
                logger.error("MAX: webhook request rejected — no secret configured")
                return web.Response(
                    status=503, text="webhook is not configured with a secret"
                )

            # ── Body: bounded read, parsed only after authentication ─────
            length = req.content_length
            if length is not None and length > WEBHOOK_MAX_BODY_BYTES:
                return web.Response(status=413, text="payload too large")
            body = await req.content.read(WEBHOOK_MAX_BODY_BYTES + 1)
            if len(body) > WEBHOOK_MAX_BODY_BYTES:
                return web.Response(status=413, text="payload too large")
            try:
                payload = json.loads(body)
            except (json.JSONDecodeError, TypeError, ValueError):
                return web.Response(status=400, text="invalid json")

            event = await self._build_event(payload)
            if event is not None:
                await self._message_queue.put(event)
            return web.Response(text="ok")

        app.router.add_get("/health", health_handler)
        app.router.add_post(self._webhook_path, webhook_handler)
        return app

    async def _start_webhook(self) -> bool:
        """Start the aiohttp webhook server.

        Fails closed: without a configured secret the server refuses to start,
        unless the explicit ``MAX_WEBHOOK_INSECURE_DEV`` opt-in is set *and*
        the server is bound to a loopback host.
        """
        try:
            from aiohttp import web
        except ImportError:
            self._set_fatal_error("no_aiohttp", "aiohttp not installed", retryable=False)
            return False

        secret = self._webhook_secret
        insecure_dev = bool(getattr(self, "_webhook_insecure_dev", False))
        endpoint = (
            self._webhook_url
            or f"{self._webhook_host}:{self._webhook_port}{self._webhook_path}"
        )

        # ── Fail closed before binding anything ─────────────────────────
        if not secret:
            if not insecure_dev:
                self._set_fatal_error(
                    "webhook_secret_required",
                    "MAX_WEBHOOK_SECRET is required in webhook mode; refusing to "
                    "start a secretless endpoint that would accept forged events. "
                    "Set MAX_WEBHOOK_SECRET, or for local development only set "
                    "MAX_WEBHOOK_INSECURE_DEV=true with MAX_WEBHOOK_HOST=127.0.0.1.",
                    retryable=False,
                )
                logger.error("MAX: refusing to start webhook without a secret (%s)", endpoint)
                return False
            if not _is_loopback_host(self._webhook_host):
                self._set_fatal_error(
                    "webhook_insecure_dev_non_loopback",
                    f"MAX_WEBHOOK_INSECURE_DEV is set but MAX_WEBHOOK_HOST="
                    f"{self._webhook_host!r} is not a loopback address; refusing to "
                    "expose a secretless endpoint beyond 127.0.0.1. Use long-polling "
                    "for development, or set a webhook secret.",
                    retryable=False,
                )
                logger.error(
                    "MAX: refusing secretless webhook on non-loopback host %r",
                    self._webhook_host,
                )
                return False
            logger.warning(
                "MAX: webhook started WITHOUT a secret on loopback %s "
                "(MAX_WEBHOOK_INSECURE_DEV=true) — development only; do not expose "
                "this port.",
                endpoint,
            )

        # Port-in-use check
        try:
            with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as sock:
                sock.settimeout(1)
                sock.connect(("127.0.0.1", self._webhook_port))
            self._set_fatal_error("port_in_use", f"Port {self._webhook_port} already in use", retryable=False)
            return False
        except (ConnectionRefusedError, OSError):
            pass  # Port is free

        path = self._webhook_path
        app = self._build_webhook_app(web)

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
            except Exception as e:  # noqa: BLE001 — adapter must not crash on transport/API errors
                logger.error("MAX: webhook register failed: %s", e)

        # Start poll loop for draining the queue
        self._poll_task = asyncio.create_task(self._queue_poll_loop())
        self._mark_connected()
        return True
