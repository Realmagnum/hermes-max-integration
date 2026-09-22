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
WEBHOOK_SECRET_HEADER = "X-Max-Bot-Api-Secret"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", "[::1]"})


def _is_loopback_host(host: str | None) -> bool:
    """Return whether *host* is an explicit loopback bind address."""
    return bool(host and str(host).strip().lower() in LOOPBACK_HOSTS)


def _verify_raw_secret(body: bytes, secret: str, secret_header: str | None) -> bool:
    """Constant-time comparison of webhook secret.

    Max sends the raw secret in X-Max-Bot-Api-Secret header (not HMAC).
    Uses secrets.compare for timing-safe string comparison.
    """
    import secrets
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
            """Liveness plus bounded-ingress telemetry; not MAX readiness."""
            return web.json_response({"status": "ok", "backpressure": self.backpressure_stats()})

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
                self._enqueue_event(event)
            return web.Response(text="ok")

        app.router.add_get("/health", health_handler)
        app.router.add_get("/ready", readiness_handler)
        app.router.add_post(self._webhook_path, webhook_handler)
        return app

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
        insecure_dev = bool(getattr(self, "_webhook_insecure_dev", False))
        path = self._webhook_path

        # ── Fail closed before binding anything ─────────────────────────
        if not secret:
            if insecure_dev and not _is_loopback_host(self._webhook_host):
                self._webhook_ready_reason = "webhook secret required for non-loopback bind"
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
            if not _is_loopback_host(self._webhook_host):
                self._webhook_ready_reason = "webhook secret required for non-loopback bind"
                self._set_fatal_error(
                    "webhook_secret_required",
                    "MAX_WEBHOOK_SECRET is required in webhook mode; refusing to "
                    "start a secretless endpoint that would accept forged events. "
                    "Set MAX_WEBHOOK_SECRET, or for local development only set "
                    "MAX_WEBHOOK_INSECURE_DEV=true with MAX_WEBHOOK_HOST=127.0.0.1.",
                    retryable=False,
                )
                logger.error("MAX: refusing to start webhook without a secret (%s)", self._webhook_url or f"{self._webhook_host}:{self._webhook_port}{path}")
                return False
            logger.warning(
                "MAX: webhook started WITHOUT a secret on loopback %s "
                "— development only; do not expose this port.",
                self._webhook_url or f"{self._webhook_host}:{self._webhook_port}{path}",
            )

        app = self._build_webhook_app(web)

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
