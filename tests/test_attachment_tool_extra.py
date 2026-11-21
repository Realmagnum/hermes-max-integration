import json

import pytest

import adapter


@pytest.mark.asyncio
async def test_real_plugin_context_registry_dispatch(monkeypatch, max_api):
    from hermes_cli.plugins import PluginContext, PluginManager, PluginManifest
    from max import attachment_tool
    from tools.registry import registry
    monkeypatch.setattr(attachment_tool, "get_session_env", lambda k: {"HERMES_SESSION_PLATFORM": "max", "HERMES_SESSION_CHAT_ID": "user:42"}.get(k, ""))
    monkeypatch.setattr(attachment_tool, "get_max_secret", lambda *a: "fixture")
    monkeypatch.setattr(attachment_tool.httpx, "AsyncClient", lambda **kw: max_api.client())
    adapter.register(PluginContext(PluginManifest(name="max-platform", source="user", kind="platform"), PluginManager()))
    entry = registry.get_entry("max_send_attachments")
    assert entry is not None and entry.is_async
    import asyncio
    result = await asyncio.to_thread(registry.dispatch, "max_send_attachments", {"attachments": [{"type": "sticker", "payload": {"code": "fixture"}}]})
    assert json.loads(result)["success"]
    assert max_api.params(max_api.calls("POST", "/messages")[0]) == {"user_id": "42"}


@pytest.mark.parametrize("button", [
    {"type": "callback", "text": "X", "payload": "a"},
    {"type": "link", "text": "X", "url": "https://example.com"},
    {"type": "request_contact", "text": "X"},
    {"type": "request_geo_location", "text": "X", "quick": False},
    {"type": "open_app", "text": "X", "web_app": "fixture_bot", "payload": "x"},
    {"type": "message", "text": "X"},
    {"type": "clipboard", "text": "X", "payload": "x"},
])
def test_all_official_button_types(button):
    from max.attachment_tool import validate
    args = {"attachments": [{"type": "inline_keyboard", "payload": {"buttons": [[button]]}}]}
    assert validate(args) == args


@pytest.mark.parametrize("attachments", [
    [{"type": "image", "payload": {"url": "http://127.0.0.1/"}}],
    [{"type": "image", "payload": {"token": "t", "url": "https://example.com"}}],
    [{"type": "location", "latitude": float("nan"), "longitude": 0}],
    [{"type": "location", "latitude": True, "longitude": 0}],
    [{"type": "file", "payload": {"token": "t"}}] * 2,
    [{"type": "sticker", "payload": {"code": "t"}}] * 2,
    [{"type": "contact", "payload": {"contact_id": 42, "vcf_info": "x"}}],
    [{"type": "inline_keyboard", "payload": {"buttons": [[{"type": "message", "text": "X"}] * 8]}}],
    [{"type": "inline_keyboard", "payload": {"buttons": [[{"type": "link", "text": "X", "url": "https://example.com"}] * 4]}}],
    [{"type": "inline_keyboard", "payload": {"buttons": [[{"type": "message", "text": "X"}]] * 31}}],
])
def test_invalid_fields_boundaries_and_combinations(attachments):
    from max.attachment_tool import validate
    with pytest.raises(ValueError):
        validate({"attachments": attachments})


def test_maximum_keyboard_and_media_combinations():
    from max.attachment_tool import validate
    keyboard = {"type": "inline_keyboard", "payload": {"buttons": [[{"type": "message", "text": "X"}] * 7] * 30}}
    validate({"attachments": [keyboard]})
    validate({"attachments": [{"type": "image", "payload": {"token": "t"}}] * 11 + [keyboard]})
    validate({"attachments": [{"type": "file", "payload": {"token": "t"}}, keyboard]})
    with pytest.raises(ValueError):
        validate({"attachments": [{"type": "image", "payload": {"token": "t"}}] * 12 + [keyboard]})
