"""Recipient query regression through real asynchronous media entry points."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from gateway.config import PlatformConfig
from max.mixins import standalone


@pytest.mark.asyncio
async def test_bare_negative_document_uses_chat_id(make_adapter, max_api):
    a = make_adapter()
    a.send_action = AsyncMock()
    a._upload = AsyncMock(return_value="dummy-token")
    max_api.route("POST", "/messages", json_body={"message": {"body": {"mid": "dummy-mid"}}})

    result = await a.send_document("-42", "/not-read/report.pdf", caption="Report")

    assert result.success
    request, = max_api.calls("POST", "/messages")
    assert max_api.params(request) == {"chat_id": "-42"}
    a._upload.assert_awaited_once_with("/not-read/report.pdf", "file")


TARGETS = [
    ("-42", {"chat_id": "-42"}),
    ("chat:-42", {"chat_id": "-42"}),
    ("chat:42", {"chat_id": "42"}),
    ("42", {"user_id": "42"}),
    ("user:42", {"user_id": "42"}),
    ("user:-42", {"user_id": "-42"}),
]
MEDIA = [("send_image_file", "image", ".png"), ("send_document", "file", ".pdf"),
         ("send_voice", "audio", ".mp3"), ("send_video", "video", ".mp4")]


@pytest.mark.asyncio
@pytest.mark.parametrize("target,expected", TARGETS + [
    ("99", {"user_id": "42"}), ("user:99", {"user_id": "99"}), ("chat:99", {"chat_id": "99"}),
])
@pytest.mark.parametrize("method,kind,suffix", MEDIA)
async def test_adapter_media_recipient(make_adapter, max_api, tmp_path, target, expected,
                                       method, kind, suffix):
    a = make_adapter()
    a._remember_dm("99", "42")
    a.send_action = AsyncMock()
    a._upload = AsyncMock(return_value="dummy-token")
    path = tmp_path / ("media" + suffix)
    path.write_bytes(b"ID3-dummy")  # Accepted audio container; no ffmpeg needed.

    result = await getattr(a, method)(target, str(path), caption="Caption", reply_to="reply-mid")

    assert result.success
    request, = max_api.calls("POST", "/messages")
    assert max_api.params(request) == expected
    body = max_api.json_body(request)
    assert body["attachments"] == [{"type": kind, "payload": {"token": "dummy-token"}}]
    assert body["text"] == "Caption"
    assert body["link"] == {"type": "REPLY", "mid": "reply-mid"}
    a._upload.assert_awaited_once_with(str(path), kind)


@pytest.mark.asyncio
@pytest.mark.parametrize("target,expected", TARGETS)
@pytest.mark.parametrize("sender", ["_send_max_message", "_standalone_send"])
async def test_standalone_text_recipient(max_api, monkeypatch, target, expected, sender):
    monkeypatch.setattr(standalone, "_standalone_get_token", lambda _: "dummy-token")
    monkeypatch.setattr(standalone.httpx, "AsyncClient", lambda **_: max_api.client())
    result = await getattr(standalone, sender)(PlatformConfig(enabled=True), target, "Caption")
    assert result.success if sender == "_send_max_message" else result["success"]
    request, = max_api.calls("POST", "/messages")
    assert max_api.params(request) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("target,expected", TARGETS)
@pytest.mark.parametrize("method,kind,suffix", MEDIA)
async def test_standalone_media_recipient(max_api, monkeypatch, tmp_path, target, expected,
                                          method, kind, suffix):
    import aiohttp

    monkeypatch.setattr(standalone, "_standalone_get_token", lambda _: "dummy-token")
    monkeypatch.setattr(standalone.httpx, "AsyncClient", lambda **_: max_api.client())
    monkeypatch.setattr(standalone.asyncio, "sleep", AsyncMock())
    monkeypatch.setattr(aiohttp, "TCPConnector", MagicMock())
    session = MagicMock()
    session.__aenter__.return_value = session
    response = MagicMock(status=200)
    response.json = AsyncMock(return_value={"token": "dummy-token"})
    response.content.read = AsyncMock(side_effect=[b'{"token":"dummy-token"}', b''])
    session.post.return_value.__aenter__.return_value = response
    monkeypatch.setattr(aiohttp, "ClientSession", lambda **_: session)
    max_api.route("POST", "/uploads", json_body={"url": "https://upload.max.ru/dummy",
                                                "token": "dummy-token"})
    path = tmp_path / ("media" + suffix)
    path.write_bytes(b"ID3-dummy")

    result = await standalone._standalone_send(PlatformConfig(enabled=True), target, "",
                                               media_files=[(str(path), False)], caption="Caption")

    assert result["success"] and result["media_sent"] == 1
    request, = max_api.calls("POST", "/messages")
    assert max_api.params(request) == expected
    assert max_api.json_body(request)["attachments"] == [
        {"type": kind, "payload": {"token": "dummy-token"}}]
    upload, = max_api.calls("POST", "/uploads")
    assert max_api.params(upload) == {"type": kind}
    session.post.assert_called_once()
