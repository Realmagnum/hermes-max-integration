"""DOC-03 regression: the documented webhook procedure must actually work.

BACKLOG DOC-03 acceptance criteria (docs/audit-backlog branch):

* ``MAX_WEBHOOK_URL`` **and** ``MAX_WEBHOOK_SECRET`` are both mandatory in the
  documented example (the URL is the single switch that selects webhook mode,
  the secret must match the locally configured value);
* the documented mode is verified -- following the documented steps really
  turns on webhook mode, and the documented secret really protects the
  endpoint;
* following the procedure must not get the webhook subscription deleted by
  the long-polling auto-cleanup.
"""

import json
import socket
from unittest.mock import AsyncMock

import httpx
import pytest

import adapter

# Values copied from the documented example (SKILL.md / SKILL_EN.md /
# after-install*.md / AGENTS*.md).
WEBHOOK_URL = "https://max.example.com/max/webhook"
WEBHOOK_SECRET = "my-secret-abc123"
WEBHOOK_PATH = "/max/webhook"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _documented_env(monkeypatch, port: int) -> None:
    """The exact .env block the documentation tells the user to write."""
    monkeypatch.setenv("MAX_BOT_TOKEN", "test-token")
    monkeypatch.setenv("MAX_WEBHOOK_URL", WEBHOOK_URL)
    monkeypatch.setenv("MAX_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.setenv("MAX_WEBHOOK_HOST", "127.0.0.1")
    monkeypatch.setenv("MAX_WEBHOOK_PORT", str(port))
    monkeypatch.setenv("MAX_WEBHOOK_PATH", WEBHOOK_PATH)


def _make_adapter():
    from gateway.config import PlatformConfig

    return adapter.MaxAdapter(PlatformConfig(enabled=True, token="test-token"))


def _mock_api(calls, subscriptions=None):
    """MockTransport handler for platform-api.max.ru; records every call."""

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, str(request.url), request.content))
        if request.url.path == "/subscriptions":
            if request.method == "GET":
                return httpx.Response(200, json={"subscriptions": subscriptions or []})
            return httpx.Response(200, json={"success": True})
        if request.url.path == "/updates":
            return httpx.Response(200, json={"updates": [], "marker": 0})
        return httpx.Response(200, json={"username": "maxbot", "user_id": 1})

    return httpx.MockTransport(handler)


class TestDocumentedModeSelection:
    def test_documented_env_selects_webhook_mode(self, monkeypatch):
        """MAX_WEBHOOK_URL is what switches the plugin out of long polling."""
        _documented_env(monkeypatch, _free_port())
        a = _make_adapter()
        assert a._use_webhook is True
        assert a._webhook_url == WEBHOOK_URL
        assert a._webhook_secret == WEBHOOK_SECRET
        assert a._webhook_path == WEBHOOK_PATH

    def test_without_url_the_adapter_runs_long_polling(self, monkeypatch):
        """Without MAX_WEBHOOK_URL the adapter polls -- and deletes subs."""
        monkeypatch.setenv("MAX_BOT_TOKEN", "test-token")
        monkeypatch.delenv("MAX_WEBHOOK_URL", raising=False)
        a = _make_adapter()
        assert a._use_webhook is False


class TestDocumentedFlowIsVerifiable:
    @pytest.mark.asyncio
    async def test_documented_path_and_secret_end_to_end(self, monkeypatch):
        """Real HTTP server on the documented path + documented secret."""
        port = _free_port()
        _documented_env(monkeypatch, port)
        calls: list = []
        a = _make_adapter()
        a._http_client = httpx.AsyncClient(transport=_mock_api(calls))
        try:
            assert await a._start_webhook() is True

            payload = {
                "update_type": "bot_started",
                "chat_id": "1",
                "user": {"user_id": "2", "name": "user"},
            }
            async with httpx.AsyncClient() as client:
                health = await client.get(f"http://127.0.0.1:{port}/health")
                assert health.status_code == 200
                assert health.json() == {"status": "ok"}

                missing = await client.post(
                    f"http://127.0.0.1:{port}{WEBHOOK_PATH}", json=payload
                )
                assert missing.status_code == 403

                wrong = await client.post(
                    f"http://127.0.0.1:{port}{WEBHOOK_PATH}",
                    json=payload,
                    headers={"X-Max-Bot-Api-Secret": "not-the-documented-secret"},
                )
                assert wrong.status_code == 403

                ok = await client.post(
                    f"http://127.0.0.1:{port}{WEBHOOK_PATH}",
                    json=payload,
                    headers={"X-Max-Bot-Api-Secret": WEBHOOK_SECRET},
                )
                assert ok.status_code == 200

            # The adapter registered the subscription itself, with the same
            # URL and the same secret the documentation tells the user to use.
            posts = [
                c for c in calls
                if c[0] == "POST" and c[1].endswith("/subscriptions")
            ]
            assert len(posts) == 1
            body = json.loads(posts[0][2])
            assert body["url"] == WEBHOOK_URL
            assert body["secret"] == WEBHOOK_SECRET
            assert "message_created" in body["update_types"]
            assert "bot_started" in body["update_types"]

            # ...and following the documented procedure never removes a
            # manually registered subscription.
            assert not [c for c in calls if c[0] == "DELETE"]
        finally:
            await a.disconnect()

    @pytest.mark.asyncio
    async def test_manual_registration_is_kept_in_webhook_mode(self, monkeypatch):
        """A pre-existing manual subscription survives a webhook-mode start."""
        port = _free_port()
        _documented_env(monkeypatch, port)
        calls: list = []
        a = _make_adapter()
        a._http_client = httpx.AsyncClient(
            transport=_mock_api(calls, subscriptions=[{"url": WEBHOOK_URL}])
        )
        try:
            assert await a._start_webhook() is True
            assert not [c for c in calls if c[0] == "DELETE"], (
                "webhook mode must not delete the subscription it uses"
            )
        finally:
            await a.disconnect()


class TestPollingTrap:
    @pytest.mark.asyncio
    async def test_polling_mode_deletes_manual_subscription(self, monkeypatch):
        """The trap the documentation must warn about (adapter.py auto-clean)."""
        monkeypatch.setenv("MAX_BOT_TOKEN", "test-token")
        monkeypatch.delenv("MAX_WEBHOOK_URL", raising=False)
        monkeypatch.setattr(
            adapter.MaxAdapter, "_poll_loop", AsyncMock(return_value=None)
        )
        calls: list = []
        a = _make_adapter()
        a._http_client = httpx.AsyncClient(
            transport=_mock_api(calls, subscriptions=[{"url": WEBHOOK_URL}])
        )
        try:
            assert a._use_webhook is False
            assert await a._start_polling() is True
            deletes = [
                c for c in calls
                if c[0] == "DELETE" and "url=" in c[1]
            ]
            assert deletes, "long polling must clean the stale subscription"
            assert WEBHOOK_URL in deletes[0][1]
        finally:
            await a.disconnect()
