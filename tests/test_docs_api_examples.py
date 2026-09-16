"""Executable checks for the API examples in docs/api.md and docs/api_EN.md.

Two things are verified:

1. every ```json block in both docs parses, and the RU/EN files carry the
   same fixtures;
2. the documented upload / send / edit / callback examples actually run
   against the adapter with the network mocked (``httpx.MockTransport`` plus
   an ``aiohttp`` stub for the multipart CDN upload).
"""

import json
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

import adapter

_DOCS = Path(__file__).resolve().parents[1] / "docs"
_JSON_BLOCK_RE = re.compile(r"```json\n(.*?)```", re.DOTALL)


def _json_blocks(path: Path) -> list[str]:
    return [b.strip() for b in _JSON_BLOCK_RE.findall(path.read_text(encoding="utf-8"))]


def _blocks_by_name(path: Path) -> list[dict]:
    return [json.loads(b) for b in _json_blocks(path)]


# ── 1. Document fixtures ──────────────────────────────────────────────────


@pytest.mark.parametrize("name", ["api.md", "api_EN.md"])
def test_every_json_block_parses(name):
    blocks = _json_blocks(_DOCS / name)
    assert blocks, f"no ```json blocks found in {name}"
    for block in blocks:
        json.loads(block)  # raises on invalid JSON


def test_ru_and_en_fixtures_are_identical():
    ru = [json.dumps(b, sort_keys=True, ensure_ascii=False) for b in _blocks_by_name(_DOCS / "api.md")]
    en = [json.dumps(b, sort_keys=True, ensure_ascii=False) for b in _blocks_by_name(_DOCS / "api_EN.md")]
    assert ru == en


def _fixture(name: str, update_type: str) -> dict:
    for block in _blocks_by_name(_DOCS / name):
        if block.get("update_type") == update_type:
            return block
    raise AssertionError(f"{update_type} fixture missing from {name}")


def test_callback_fixture_uses_official_envelope():
    payload = _fixture("api.md", "message_callback")
    assert payload["callback"]["payload"].startswith("model:pick:")
    assert payload["callback"]["user"]["user_id"]
    # chat_id for callbacks lives in message.recipient, never in a root `chat`
    assert "chat" not in payload


def _noop_handler(request: httpx.Request):
    return httpx.Response(200, json={})


# ── 2. Executable mocked examples ─────────────────────────────────────────


def _adapter(handler):
    from gateway.config import PlatformConfig

    cfg = PlatformConfig(enabled=True, token="test-token", extra={"token": "test-token"})
    a = adapter.MaxAdapter(cfg)
    a._http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return a


class _StubUploadResponse:
    status = 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def json(self):
        # docs/api.md: CDN response for image/file
        return {"token": "cdn_token_abc123"}


class _StubUploadSession:
    """Stand-in for aiohttp.ClientSession used by _upload step 2."""

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def post(self, url, data=None):
        return _StubUploadResponse()


@pytest.mark.asyncio
async def test_documented_upload_send_flow(tmp_path, monkeypatch):
    """POST /uploads → multipart POST <url> → POST /messages."""
    monkeypatch.setattr("aiohttp.ClientSession", _StubUploadSession)

    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request):
        seen.append(request)
        if request.url.path == "/uploads":
            assert request.method == "POST"
            assert request.url.params["type"] == "image"
            return httpx.Response(200, json={"url": "https://iu.oneme.ru/upload.do?params=abc"})
        return httpx.Response(200, json={"message": {"body": {"mid": "mid-1"}}})

    f = tmp_path / "picture.jpg"
    f.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg")

    a = _adapter(handler)
    result = await a._upload_send("user:1", str(f), "image", "Вот изображение:", None)
    await a._http_client.aclose()

    assert result.success is True
    assert result.message_id == "mid-1"

    messages_call = [r for r in seen if r.url.path == "/messages"][-1]
    body = json.loads(messages_call.content)
    assert body["attachments"][0]["type"] == "image"
    assert body["attachments"][0]["payload"]["token"] == "cdn_token_abc123"


@pytest.mark.asyncio
async def test_documented_send_flow():
    seen = []

    async def handler(request: httpx.Request):
        seen.append(request)
        return httpx.Response(200, json={"message": {"body": {"mid": "mid-2"}}})

    a = _adapter(handler)
    result = await a.send("user:1", "Hello")
    await a._http_client.aclose()

    assert result.success is True
    assert result.message_id == "mid-2"
    assert json.loads(seen[-1].content)["text"] == "Hello"


@pytest.mark.asyncio
async def test_documented_edit_flow_uses_message_id_query():
    """PUT /messages?message_id=... — not chat_id, not mid in the body."""
    seen = []

    async def handler(request: httpx.Request):
        seen.append(request)
        return httpx.Response(200, json={"success": True})

    a = _adapter(handler)
    a.send_action = AsyncMock()
    result = await a.edit_message("chat:95825064", "mid-abc123", "Updated text", finalize=True)
    await a._http_client.aclose()

    assert result.success is True
    edit = [r for r in seen if r.method == "PUT"][-1]
    assert edit.url.path == "/messages"
    assert edit.url.params["message_id"] == "mid-abc123"
    assert "chat_id" not in edit.url.params
    body = json.loads(edit.content)
    assert body["text"] == "Updated text"
    assert "mid" not in body


@pytest.mark.asyncio
async def test_documented_callback_fixture_routes():
    """The message_callback fixture from docs/api.md reaches _on_callback."""
    payload = _fixture("api.md", "message_callback")
    user_id = str(payload["callback"]["user"]["user_id"])

    async def on_selected(chat_id, model_id, provider_slug):
        return f"✅ Switched to {model_id}"

    a = _adapter(_noop_handler)
    a._model_picker_state[f"user:{user_id}"] = {
        "providers": [],
        "session_key": "test",
        "on_model_selected": on_selected,
        "current_model": "gpt-4",
        "current_provider": "openrouter",
    }
    a.send = AsyncMock()
    a.delete_message = AsyncMock(return_value=MagicMock(success=True))

    result = await a._on_callback(payload)

    assert result is None  # handled, nothing injected into the agent context
    a.send.assert_called_once()
    assert "deepseek-v4-flash" in a.send.call_args[0][1]


@pytest.mark.asyncio
async def test_documented_unknown_prefix_is_ignored():
    a = _adapter(_noop_handler)
    assert await a._on_callback({"callback": {"payload": "nope:1", "user": {"user_id": 1}}}) is None
