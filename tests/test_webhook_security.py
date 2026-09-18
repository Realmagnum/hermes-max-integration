"""SEC-04 — secretless webhook.

A webhook endpoint that starts without a secret lets anyone POST a crafted
event and forge an allowed ``user_id``. These tests pin the fail-closed
contract:

* ``_verify_raw_secret`` never treats an unset secret as a wildcard;
* ``_start_webhook`` refuses to bind without a secret, and the secretless
  development escape hatch only works on an explicit loopback host;
* the request handler authenticates the header *before* it reads or parses the
  body, so an unauthenticated caller can never feed the parser.
"""

import socket
from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from gateway.config import PlatformConfig
from max.mixins.webhook import (
    WEBHOOK_MAX_BODY_BYTES,
    WEBHOOK_SECRET_HEADER,
    _is_loopback_host,
    _verify_raw_secret,
)

WEBHOOK_PATH = "/max/webhook"


@pytest.fixture(autouse=True)
def _clean_webhook_env(monkeypatch):
    """Webhook settings must come from the test, never from the environment."""
    for name in (
        "MAX_WEBHOOK_SECRET",
        "MAX_WEBHOOK_INSECURE_DEV",
        "MAX_WEBHOOK_URL",
        "MAX_WEBHOOK_HOST",
        "MAX_WEBHOOK_PORT",
        "MAX_WEBHOOK_PATH",
    ):
        monkeypatch.delenv(name, raising=False)


def _make_adapter(**extra):
    from adapter import MaxAdapter

    cfg = PlatformConfig(enabled=True, token="tok", extra={"token": "tok", **extra})
    return MaxAdapter(cfg)


async def _started_client(app):
    client = TestClient(TestServer(app))
    await client.start_server()
    return client


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class TestVerifyRawSecretFailsClosed:
    """The helper must never authenticate on a missing secret."""

    def test_matching_secret_accepted(self):
        assert _verify_raw_secret(b"{}", "secret-123", "secret-123") is True

    def test_wrong_secret_rejected(self):
        assert _verify_raw_secret(b"{}", "secret-123", "different") is False

    def test_missing_header_rejected(self):
        assert _verify_raw_secret(b"{}", "secret-123", None) is False
        assert _verify_raw_secret(b"{}", "secret-123", "") is False

    def test_unconfigured_secret_is_not_a_wildcard(self):
        # An empty configured secret must never match, including when the
        # caller sends a header.
        assert _verify_raw_secret(b"{}", "", None) is False
        assert _verify_raw_secret(b"{}", "", "anything") is False


class TestLoopbackHostDetection:
    def test_loopback_hosts_accepted(self):
        for host in ("127.0.0.1", "::1", "localhost", "[::1]", " LOCALHOST "):
            assert _is_loopback_host(host) is True, host

    def test_public_and_wildcard_hosts_rejected(self):
        for host in ("0.0.0.0", "::", "10.0.0.5", "example.com", "", None):
            assert _is_loopback_host(host) is False, host


class TestStartWebhookFailsClosed:
    async def test_refuses_to_start_without_secret(self):
        a = _make_adapter(webhook_url="https://example.com/max/webhook")
        assert a._webhook_secret == ""
        assert await a._start_webhook() is False
        assert a._fatal_error_code == "webhook_secret_required"

    async def test_insecure_dev_requires_loopback_host(self):
        a = _make_adapter(
            webhook_insecure_dev=True,
            host="0.0.0.0",
            port=_free_port(),
        )
        assert a._webhook_insecure_dev is True
        assert await a._start_webhook() is False
        assert a._fatal_error_code == "webhook_insecure_dev_non_loopback"

    async def test_insecure_dev_on_loopback_starts(self):
        a = _make_adapter(
            webhook_insecure_dev=True,
            host="127.0.0.1",
            port=_free_port(),
        )
        try:
            assert await a._start_webhook() is True
            assert a._webhook_app is not None
        finally:
            await a.disconnect()


class TestHandlerAuthenticatesBeforeBody:
    """Header check precedes any body read/parse."""

    async def test_missing_header_is_403(self):
        a = _make_adapter(webhook_secret="s3cret", path=WEBHOOK_PATH)
        a._build_event = AsyncMock(return_value=None)
        client = await _started_client(a._build_webhook_app(web))
        try:
            resp = await client.post(
                WEBHOOK_PATH, data=b'{"update_type":"message_created"}'
            )
            assert resp.status == 403
            a._build_event.assert_not_awaited()
        finally:
            await client.close()

    async def test_wrong_secret_is_403(self):
        a = _make_adapter(webhook_secret="s3cret", path=WEBHOOK_PATH)
        a._build_event = AsyncMock(return_value=None)
        client = await _started_client(a._build_webhook_app(web))
        try:
            resp = await client.post(
                WEBHOOK_PATH,
                data=b'{"update_type":"message_created"}',
                headers={WEBHOOK_SECRET_HEADER: "wrong"},
            )
            assert resp.status == 403
            a._build_event.assert_not_awaited()
        finally:
            await client.close()

    async def test_auth_precedes_body_parsing(self):
        """Malformed body + bad secret must be 403, not 400."""
        a = _make_adapter(webhook_secret="s3cret", path=WEBHOOK_PATH)
        a._build_event = AsyncMock(return_value=None)
        client = await _started_client(a._build_webhook_app(web))
        try:
            resp = await client.post(
                WEBHOOK_PATH,
                data=b"this is not json",
                headers={WEBHOOK_SECRET_HEADER: "wrong"},
            )
            assert resp.status == 403
        finally:
            await client.close()

    async def test_auth_precedes_body_buffering(self):
        """Oversized body + bad secret must be 403, not 413."""
        a = _make_adapter(webhook_secret="s3cret", path=WEBHOOK_PATH)
        a._build_event = AsyncMock(return_value=None)
        client = await _started_client(a._build_webhook_app(web))
        try:
            resp = await client.post(
                WEBHOOK_PATH,
                data=b"x" * (WEBHOOK_MAX_BODY_BYTES + 10),
                headers={WEBHOOK_SECRET_HEADER: "wrong"},
            )
            assert resp.status == 403
        finally:
            await client.close()

    async def test_valid_secret_dispatches_event(self):
        sentinel = object()
        a = _make_adapter(webhook_secret="s3cret", path=WEBHOOK_PATH)
        a._build_event = AsyncMock(return_value=sentinel)
        client = await _started_client(a._build_webhook_app(web))
        try:
            resp = await client.post(
                WEBHOOK_PATH,
                data=b'{"update_type":"message_created"}',
                headers={WEBHOOK_SECRET_HEADER: "s3cret"},
            )
            assert resp.status == 200
            assert a._message_queue.get_nowait() is sentinel
        finally:
            await client.close()

    async def test_valid_secret_invalid_json_is_400(self):
        a = _make_adapter(webhook_secret="s3cret", path=WEBHOOK_PATH)
        a._build_event = AsyncMock(return_value=None)
        client = await _started_client(a._build_webhook_app(web))
        try:
            resp = await client.post(
                WEBHOOK_PATH,
                data=b"{not json",
                headers={WEBHOOK_SECRET_HEADER: "s3cret"},
            )
            assert resp.status == 400
            a._build_event.assert_not_awaited()
        finally:
            await client.close()

    async def test_oversized_body_is_413(self):
        a = _make_adapter(webhook_secret="s3cret", path=WEBHOOK_PATH)
        a._build_event = AsyncMock(return_value=None)
        client = await _started_client(a._build_webhook_app(web))
        try:
            resp = await client.post(
                WEBHOOK_PATH,
                data=b"x" * (WEBHOOK_MAX_BODY_BYTES + 10),
                headers={WEBHOOK_SECRET_HEADER: "s3cret"},
            )
            assert resp.status == 413
            a._build_event.assert_not_awaited()
        finally:
            await client.close()

    async def test_secretless_app_rejects_without_dev_optin(self):
        """Defence in depth: even a directly-built secretless app says no."""
        a = _make_adapter(path=WEBHOOK_PATH)
        a._build_event = AsyncMock(return_value=None)
        client = await _started_client(a._build_webhook_app(web))
        try:
            resp = await client.post(
                WEBHOOK_PATH, data=b'{"update_type":"message_created"}'
            )
            assert resp.status == 503
            a._build_event.assert_not_awaited()
        finally:
            await client.close()

    async def test_secretless_dev_optin_accepts(self):
        a = _make_adapter(path=WEBHOOK_PATH, webhook_insecure_dev=True)
        sentinel = object()
        a._build_event = AsyncMock(return_value=sentinel)
        client = await _started_client(a._build_webhook_app(web))
        try:
            resp = await client.post(
                WEBHOOK_PATH, data=b'{"update_type":"message_created"}'
            )
            assert resp.status == 200
            assert a._message_queue.get_nowait() is sentinel
        finally:
            await client.close()
