"""Registered tool, current-session-only destination and actual HTTP serialization."""
import json
from types import SimpleNamespace

import pytest

import adapter


def registered_handler():
    tools = {}
    ctx = SimpleNamespace(register_platform=lambda **k: None,
                          register_hook=lambda *a, **k: None,
                          register_skill=lambda *a, **k: None,
                          register_tool=lambda **k: tools.update({k["name"]: k}))
    adapter.register(ctx)
    assert "max_send_attachments" in tools
    return tools["max_send_attachments"]["handler"]


@pytest.mark.asyncio
@pytest.mark.parametrize("attachment", [
    {"type": "image", "payload": {"token": "fixture"}},
    {"type": "video", "payload": {"token": "fixture"}},
    {"type": "audio", "payload": {"token": "fixture"}},
    {"type": "file", "payload": {"token": "fixture"}},
    {"type": "sticker", "payload": {"code": "fixture"}},
    {"type": "contact", "payload": {"contact_id": 42, "name": "Synthetic"}},
    {"type": "location", "latitude": 0, "longitude": 0},
    {"type": "share", "payload": {"url": "https://example.com/"}},
    {"type": "inline_keyboard", "payload": {"buttons": [[{"type": "message", "text": "Hello"}]]}},
])
async def test_registered_tool_reaches_api(attachment, monkeypatch, max_api):
    handler = registered_handler()
    from max import attachment_tool
    monkeypatch.setattr(attachment_tool, "get_session_env", lambda k: {"HERMES_SESSION_PLATFORM": "max", "HERMES_SESSION_CHAT_ID": "-42"}.get(k, ""))
    monkeypatch.setattr(attachment_tool, "get_max_secret", lambda *a: "fixture")
    monkeypatch.setattr(attachment_tool.httpx, "AsyncClient", lambda **kw: max_api.client())
    result = json.loads(await handler({"attachments": [attachment], "text": "Fixture"}))
    assert result.get("success"), result
    request = max_api.calls("POST", "/messages")[0]
    assert max_api.params(request) == {"chat_id": "-42"}
    assert max_api.json_body(request)["attachments"] == [attachment]


@pytest.mark.asyncio
async def test_tool_denies_other_destination_before_io(monkeypatch, max_api):
    handler = registered_handler()
    from max import attachment_tool
    monkeypatch.setattr(attachment_tool, "get_session_env", lambda _: "")
    result = json.loads(await handler({"target": "user:99", "attachments": [{"type": "sticker", "payload": {"code": "x"}}]}))
    assert "error" in result
    assert not max_api.requests
