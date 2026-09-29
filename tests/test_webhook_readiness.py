"""CODE-05: false "connected" state for the webhook receive path.

The adapter must only report a live connection when MAX really accepts the
token AND (in webhook mode) really accepts the subscription registration:

* ``/me`` must validate transport, HTTP status AND body, not just "not 401";
* a failed ``POST /subscriptions`` must fail ``connect()``, release the port
  and expose a readiness probe that differs from liveness;
* every failure class (403/429/500/timeout/``success=false``) is covered by an
  ``httpx.MockTransport`` scenario, no real network involved.
"""

import socket

import httpx
import pytest

import adapter as adapter_mod

REAL_ASYNC_CLIENT = httpx.AsyncClient
WEBHOOK_URL = "https://example.test/max/webhook"


# ── helpers ──────────────────────────────────────────────────────────────


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _port_is_free(port: int) -> bool:
    """True when nothing listens on the port any more."""
    with socket.socket() as sock:
        sock.settimeout(1)
        try:
            sock.connect(("127.0.0.1", port))
        except OSError:
            return True
        return False


def _transport(routes: dict):
    """Route by URL path; a value may be a Response, a callable or an exception."""

    def handler(request: httpx.Request) -> httpx.Response:
        responder = routes.get(request.url.path)
        if responder is None:
            return httpx.Response(404, json={"success": False, "message": "unmapped route"})
        if isinstance(responder, Exception):
            raise responder
        if callable(responder):
            return responder(request)
        assert isinstance(responder, httpx.Response)
        return responder

    return httpx.MockTransport(handler)


def _me_ok() -> httpx.Response:
    return httpx.Response(200, json={"user_id": 42, "username": "max_bot"})


def _make_adapter(monkeypatch, transport, *, webhook_url: str | None = WEBHOOK_URL, port=None):
    """Build a MaxAdapter whose HTTP client talks to ``transport``."""
    for var in (
        "MAX_BOT_TOKEN",
        "MAX_WEBHOOK_URL",
        "MAX_WEBHOOK_HOST",
        "MAX_WEBHOOK_PORT",
        "MAX_WEBHOOK_PATH",
        "MAX_WEBHOOK_SECRET",
        "MAX_TABLE_AS_IMAGE",
        "MAX_CROSS_SESSION",
    ):
        monkeypatch.delenv(var, raising=False)

    from gateway.config import PlatformConfig

    extra = {"token": "test-token", "host": "127.0.0.1"}
    if webhook_url:
        extra["webhook_url"] = webhook_url
    if port is not None:
        extra["port"] = port

    created: list = []

    class _BoundTransportClient(REAL_ASYNC_CLIENT):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)
            created.append(self)

    monkeypatch.setattr(adapter_mod.httpx, "AsyncClient", _BoundTransportClient)
    instance = adapter_mod.MaxAdapter(PlatformConfig(enabled=True, token="test-token", extra=extra))
    return instance, created


# ── /me validation ───────────────────────────────────────────────────────


class TestMeValidation:
    """A /me that is not a successful bot lookup must not mean 'connected'."""

    @pytest.mark.parametrize(
        ("status", "retryable"),
        [(403, False), (404, False), (429, True), (500, True), (503, True)],
    )
    async def test_non_200_me_is_not_connected(self, monkeypatch, status, retryable):
        transport = _transport({"/me": httpx.Response(status, json={"success": False})})
        instance, created = _make_adapter(monkeypatch, transport, webhook_url=None)

        assert await instance.connect() is False
        assert instance.is_connected is False
        assert instance.has_fatal_error is True
        assert instance.fatal_error_retryable is retryable
        assert str(status) in (instance.fatal_error_message or "")
        assert instance._http_client is None
        assert created and created[0].is_closed is True

    async def test_me_401_is_fatal_invalid_token(self, monkeypatch):
        transport = _transport({"/me": httpx.Response(401, json={"success": False})})
        instance, _ = _make_adapter(monkeypatch, transport, webhook_url=None)

        assert await instance.connect() is False
        assert instance.fatal_error_code == "invalid_token"
        assert instance.fatal_error_retryable is False
        assert instance.is_connected is False

    async def test_me_transport_error_is_retryable(self, monkeypatch):
        transport = _transport({"/me": httpx.ConnectTimeout("connect timed out")})
        instance, created = _make_adapter(monkeypatch, transport, webhook_url=None)

        assert await instance.connect() is False
        assert instance.fatal_error_code == "conn_fail"
        assert instance.fatal_error_retryable is True
        assert instance.is_connected is False
        assert created[0].is_closed is True

    async def test_me_200_with_success_false_is_not_connected(self, monkeypatch):
        transport = _transport(
            {"/me": httpx.Response(200, json={"success": False, "message": "bot is blocked"})}
        )
        instance, _ = _make_adapter(monkeypatch, transport, webhook_url=None)

        assert await instance.connect() is False
        assert instance.is_connected is False
        assert instance.fatal_error_retryable is False
        assert "bot is blocked" in (instance.fatal_error_message or "")

    async def test_me_200_with_non_json_body_is_not_connected(self, monkeypatch):
        transport = _transport({"/me": httpx.Response(200, text="<html>proxy</html>")})
        instance, _ = _make_adapter(monkeypatch, transport, webhook_url=None)

        assert await instance.connect() is False
        assert instance.is_connected is False

    async def test_me_200_polling_path_connects(self, monkeypatch):
        transport = _transport(
            {
                "/me": _me_ok(),
                "/me/commands": httpx.Response(200, json={"success": True}),
                "/subscriptions": httpx.Response(200, json={"subscriptions": []}),
                "/updates": httpx.Response(200, json={"updates": [], "marker": 0}),
            }
        )
        instance, _ = _make_adapter(monkeypatch, transport, webhook_url=None)

        assert await instance.connect() is True
        assert instance.is_connected is True
        await instance.disconnect()
        assert instance.is_connected is False


# ── webhook registration ─────────────────────────────────────────────────


class TestWebhookRegistration:
    """POST /subscriptions is the readiness gate of webhook mode."""

    @pytest.mark.parametrize(
        ("status", "retryable"),
        [(403, False), (429, True), (500, True), (503, True)],
    )
    async def test_registration_http_failure_blocks_connected(
        self, monkeypatch, status, retryable
    ):
        port = _free_port()
        transport = _transport(
            {
                "/me": _me_ok(),
                "/me/commands": httpx.Response(200, json={"success": True}),
                "/subscriptions": httpx.Response(status, json={"success": False}),
            }
        )
        instance, created = _make_adapter(monkeypatch, transport, port=port)

        assert await instance.connect() is False
        assert instance.is_connected is False
        assert instance.fatal_error_code == "webhook_register_failed"
        assert instance.fatal_error_retryable is retryable
        assert str(status) in (instance.fatal_error_message or "")
        # server torn down, port released, client closed
        assert instance._webhook_runner is None
        assert instance._webhook_app is None
        assert instance._webhook_ready is False
        assert instance._http_client is None
        assert created[0].is_closed is True
        assert _port_is_free(port) is True

    async def test_registration_success_false_blocks_connected(self, monkeypatch):
        port = _free_port()
        transport = _transport(
            {
                "/me": _me_ok(),
                "/me/commands": httpx.Response(200, json={"success": True}),
                "/subscriptions": httpx.Response(
                    200, json={"success": False, "message": "url is not reachable"}
                ),
            }
        )
        instance, _ = _make_adapter(monkeypatch, transport, port=port)

        assert await instance.connect() is False
        assert instance.is_connected is False
        assert instance.fatal_error_retryable is False
        assert "url is not reachable" in (instance.fatal_error_message or "")
        assert _port_is_free(port) is True

    async def test_registration_non_json_body_blocks_connected(self, monkeypatch):
        port = _free_port()
        transport = _transport(
            {
                "/me": _me_ok(),
                "/me/commands": httpx.Response(200, json={"success": True}),
                "/subscriptions": httpx.Response(200, text="OK"),
            }
        )
        instance, _ = _make_adapter(monkeypatch, transport, port=port)

        assert await instance.connect() is False
        assert instance.is_connected is False
        assert "non-JSON" in (instance.fatal_error_message or "")

    async def test_registration_timeout_blocks_connected_and_is_retryable(self, monkeypatch):
        port = _free_port()
        transport = _transport(
            {
                "/me": _me_ok(),
                "/me/commands": httpx.Response(200, json={"success": True}),
                "/subscriptions": httpx.ReadTimeout("registration timed out"),
            }
        )
        instance, _ = _make_adapter(monkeypatch, transport, port=port)

        assert await instance.connect() is False
        assert instance.is_connected is False
        assert instance.fatal_error_retryable is True
        assert "transport error" in (instance.fatal_error_message or "")
        assert _port_is_free(port) is True

    async def test_registration_transport_error_blocks_connected(self, monkeypatch):
        port = _free_port()
        transport = _transport(
            {
                "/me": _me_ok(),
                "/me/commands": httpx.Response(200, json={"success": True}),
                "/subscriptions": httpx.ConnectError("connection reset"),
            }
        )
        instance, _ = _make_adapter(monkeypatch, transport, port=port)

        assert await instance.connect() is False
        assert instance.is_connected is False
        assert instance.fatal_error_retryable is True
        assert _port_is_free(port) is True

    async def test_registration_success_connects_and_releases_port_on_disconnect(
        self, monkeypatch
    ):
        port = _free_port()
        transport = _transport(
            {
                "/me": _me_ok(),
                "/me/commands": httpx.Response(200, json={"success": True}),
                "/subscriptions": httpx.Response(200, json={"success": True}),
            }
        )
        instance, _ = _make_adapter(monkeypatch, transport, port=port)

        assert await instance.connect() is True
        assert instance.is_connected is True
        assert instance._webhook_ready is True
        assert _port_is_free(port) is False

        await instance.disconnect()
        assert instance.is_connected is False
        assert instance._webhook_ready is False
        assert _port_is_free(port) is True


# ── health vs readiness ──────────────────────────────────────────────────


class TestHealthVsReadiness:
    """Liveness (/health) and readiness (/ready) must be distinguishable."""

    async def test_health_stays_ok_while_not_ready(self, monkeypatch):
        port = _free_port()
        transport = _transport(
            {
                "/me": _me_ok(),
                "/me/commands": httpx.Response(200, json={"success": True}),
                "/subscriptions": httpx.Response(200, json={"success": True}),
            }
        )
        instance, _ = _make_adapter(monkeypatch, transport, port=port)
        assert await instance.connect() is True

        base = f"http://127.0.0.1:{port}"
        async with REAL_ASYNC_CLIENT() as probe:
            ready = await probe.get(f"{base}/ready")
            assert ready.status_code == 200
            assert ready.json()["status"] == "ready"

            # Registration is lost (e.g. subscription removed on the MAX side):
            # liveness still succeeds, readiness must not.
            instance._webhook_ready = False
            instance._webhook_ready_reason = "subscription missing"

            health = await probe.get(f"{base}/health")
            assert health.status_code == 200
            assert health.json()["status"] == "ok"

            not_ready = await probe.get(f"{base}/ready")
            assert not_ready.status_code == 503
            body = not_ready.json()
            assert body["status"] == "not_ready"
            assert body["reason"] == "subscription missing"

        await instance.disconnect()

    async def test_manual_mode_is_ready_once_server_listens(self, monkeypatch):
        """Without MAX_WEBHOOK_URL nobody can register for us, so a listening
        server *is* the readiness — but /health and /ready stay separate."""
        port = _free_port()
        transport = _transport({"/me": _me_ok()})
        instance, _ = _make_adapter(monkeypatch, transport, webhook_url="", port=port)

        assert await instance._start_webhook() is True
        assert instance._webhook_ready is True
        assert instance._webhook_ready_reason == ""

        async with REAL_ASYNC_CLIENT() as probe:
            base = f"http://127.0.0.1:{port}"
            assert (await probe.get(f"{base}/health")).status_code == 200
            ready = await probe.get(f"{base}/ready")
            assert ready.status_code == 200
            assert ready.json()["status"] == "ready"

            instance._webhook_ready = False
            instance._webhook_ready_reason = "registering"
            assert (await probe.get(f"{base}/health")).status_code == 200
            assert (await probe.get(f"{base}/ready")).status_code == 503

        await instance.disconnect()


# ── helper classification ────────────────────────────────────────────────


class TestRetryClassification:
    def test_retryable_statuses(self):
        from mixins.base import _is_retryable_http_status

        assert _is_retryable_http_status(429) is True
        assert _is_retryable_http_status(500) is True
        assert _is_retryable_http_status(502) is True
        assert _is_retryable_http_status(400) is False
        assert _is_retryable_http_status(401) is False
        assert _is_retryable_http_status(403) is False

    def test_body_snippet_never_raises(self):
        from mixins.base import _http_body_snippet

        response = httpx.Response(200, text="  error   message  ")
        assert _http_body_snippet(response) == ": error message"
        assert _http_body_snippet(httpx.Response(200, text="")) == ""
