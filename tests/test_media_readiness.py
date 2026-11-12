"""Real adapter, real httpx serialization; only network and sleeps replaced."""
import asyncio
import json
from unittest.mock import AsyncMock

import httpx
import pytest
from gateway.config import PlatformConfig
from max.mixins import media_upload

import adapter


async def run_case(responses, monkeypatch, extra=None):
    a = adapter.MaxAdapter(PlatformConfig(enabled=True, token="test", extra=extra or {}))
    a.send_action = AsyncMock()
    a._upload = AsyncMock(return_value="private-upload-token")
    requests = []
    def handle(req):
        requests.append(req)
        item = responses[min(len(requests) - 1, len(responses) - 1)]
        if isinstance(item, BaseException):
            raise item
        status, body = item
        return httpx.Response(status, content=body if isinstance(body, bytes) else json.dumps(body).encode())
    sleep = AsyncMock()
    monkeypatch.setattr(media_upload.asyncio, "sleep", sleep)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        a._http_client = client
        result = await a._upload_send("user:42", "/not-read/test.mp3", "file", "caption", "reply-mid")
    a._upload.assert_awaited_once()
    return a, result, requests, sleep


READY = (400, {"code": "attachment.not.ready"})
OK = (200, {"message": {"body": {"mid": "sent-once"}}})


@pytest.mark.asyncio
async def test_later_success_same_payload_no_reupload(monkeypatch):
    _, result, requests, sleep = await run_case([READY] * 5 + [OK], monkeypatch)
    assert result.success and result.message_id == "sent-once"
    assert len(requests) == 6
    assert len({r.content for r in requests}) == 1
    assert all(r.url == requests[0].url for r in requests)
    assert [x.args[0] for x in sleep.await_args_list] == [2, 4, 8, 16, 16]
    assert json.loads(requests[0].content)["link"] == {"type": "REPLY", "mid": "reply-mid"}


@pytest.mark.asyncio
async def test_exhausted_safe_final_code(monkeypatch, caplog):
    _, result, requests, sleep = await run_case([READY], monkeypatch)
    assert not result.success and not result.retryable
    assert len(requests) == 8 and sleep.await_count == 7
    assert "status=400 code=attachment.not.ready attempts=8" in caplog.text
    assert "private-upload-token" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("response", [(400, {"code": "bad", "message": "signed-secret"}),
    (400, b"not JSON signed-secret"), (400, []), (503, {"code": "attachment.not.ready"}),
    httpx.ReadTimeout("signed-secret"), (200, b"invalid JSON")])
async def test_no_retry_other_or_ambiguous(monkeypatch, caplog, response):
    _, result, requests, sleep = await run_case([response], monkeypatch)
    assert not result.success and not result.retryable
    assert len(requests) == 1 and not sleep.await_count
    assert "signed-secret" not in caplog.text


@pytest.mark.asyncio
async def test_budget_boundary_no_sleep_or_post(monkeypatch):
    _, result, requests, sleep = await run_case([READY], monkeypatch, {"media_ready_timeout": 2})
    assert not result.success and len(requests) == 1 and sleep.await_count == 0


@pytest.mark.asyncio
async def test_cancellation_propagates(monkeypatch):
    with pytest.raises(asyncio.CancelledError):
        await run_case([asyncio.CancelledError()], monkeypatch)


@pytest.mark.asyncio
async def test_post_timeout_not_retried(monkeypatch):
    a = adapter.MaxAdapter(PlatformConfig(enabled=True, token="test", extra={"media_ready_timeout": 0.1}))
    a.send_action = AsyncMock()
    a._upload = AsyncMock(return_value="token")
    cancelled = asyncio.Event()
    async def hang(*args, **kwargs):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
    a._http_client = AsyncMock()
    a._http_client.post.side_effect = hang
    result = await a._upload_send("user:42", "x", "file", "", None)
    assert not result.success and not result.retryable and cancelled.is_set()
    assert a._http_client.post.await_count == 1


def test_config_bounds_and_env(monkeypatch):
    a = adapter.MaxAdapter(PlatformConfig(enabled=True, token="test", extra={"media_ready_attempts": 100, "media_ready_timeout": 999}))
    assert a._media_ready_attempts == 12 and a._media_ready_timeout == 300
    monkeypatch.setenv("MAX_MEDIA_READY_ATTEMPTS", "4")
    monkeypatch.setenv("MAX_MEDIA_READY_TIMEOUT", "25")
    a = adapter.MaxAdapter(PlatformConfig(enabled=True, token="test", extra={}))
    assert a._media_ready_attempts == 4 and a._media_ready_timeout == 25
    monkeypatch.setenv("MAX_MEDIA_READY_ATTEMPTS", "invalid")
    monkeypatch.setenv("MAX_MEDIA_READY_TIMEOUT", "nan")
    a = adapter.MaxAdapter(PlatformConfig(enabled=True, token="test", extra={}))
    assert a._media_ready_attempts == 8 and a._media_ready_timeout == 90
