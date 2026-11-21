"""Standalone public sender: upload once, bounded definite-rejection retries only."""
import asyncio
import json
from unittest.mock import AsyncMock

import httpx
import pytest
from gateway.config import PlatformConfig
from max.mixins import media_readiness, standalone

READY = (400, {"code": "attachment.not.ready"})
OK = (200, {"message": {"body": {"mid": "standalone-once"}}})


async def run_case(responses, monkeypatch, tmp_path, extra=None):
    source = tmp_path / "attachment.bin"
    source.write_bytes(b"synthetic payload")
    real_client = httpx.AsyncClient
    requests, uploads = [], []

    async def handle(request):
        if request.url.path == "/uploads":
            uploads.append(request)
            return httpx.Response(200, json={"url": "https://upload.max.ru/test"})
        requests.append(request)
        item = responses[min(len(requests) - 1, len(responses) - 1)]
        if isinstance(item, BaseException):
            raise item
        if callable(item):
            return await item(request)
        status, body = item
        return httpx.Response(status, content=body if isinstance(body, bytes) else json.dumps(body).encode())

    def client(*args, **kwargs):
        return real_client(*args, **kwargs, transport=httpx.MockTransport(handle))

    monkeypatch.setattr(standalone.httpx, "AsyncClient", client)
    monkeypatch.setattr(standalone, "_standalone_get_token", lambda config: "fixture-secret")
    cdn = AsyncMock(return_value=(200, {"token": "immutable-cdn-token"}))
    monkeypatch.setattr(standalone, "post_file", cdn)
    sleep = AsyncMock()
    monkeypatch.setattr(media_readiness.asyncio, "sleep", sleep)
    result = await standalone._standalone_send(
        PlatformConfig(enabled=True, token="test", extra=extra or {}),
        "user:42", "", media_files=[(str(source), False)], caption="caption")
    cdn.assert_awaited_once()
    assert len(uploads) == 1
    return result, requests, sleep


@pytest.mark.asyncio
async def test_eventual_success_after_three_definite_rejections(monkeypatch, tmp_path):
    result, requests, _ = await run_case([READY] * 3 + [OK], monkeypatch, tmp_path)
    assert result.get("success") is True, result
    assert result["media_sent"] == 1 and result["message_id"] == "standalone-once"
    assert len(requests) == 4
    assert len({request.content for request in requests}) == 1
    assert all(request.headers["Authorization"] == "fixture-secret" for request in requests)


@pytest.mark.asyncio
@pytest.mark.parametrize("response", [
    (400, {"code": "bad", "message": "signed-secret"}),
    (400, b"not JSON signed-secret"), (400, []),
    (503, {"code": "attachment.not.ready"}),
    httpx.ReadTimeout("signed-secret"), httpx.ConnectError("signed-secret"),
    (200, b"invalid JSON signed-secret"), (200, []), (200, {"ok": False}),
])
async def test_no_replay_other_or_ambiguous(monkeypatch, tmp_path, caplog, response):
    result, requests, sleep = await run_case([response], monkeypatch, tmp_path)
    assert not result.get("success") and result["media_sent"] == 0
    assert len(requests) == 1 and sleep.await_count == 0
    assert "signed-secret" not in caplog.text and "immutable-cdn-token" not in caplog.text


@pytest.mark.asyncio
async def test_default_attempt_bound(monkeypatch, tmp_path):
    result, requests, sleep = await run_case([READY], monkeypatch, tmp_path)
    assert not result.get("success") and len(requests) == 8
    assert [call.args[0] for call in sleep.await_args_list] == [2, 4, 8, 16, 16, 16, 16]
    assert len({request.content for request in requests}) == 1


@pytest.mark.asyncio
async def test_remaining_budget_prevents_extra_post_or_sleep(monkeypatch, tmp_path):
    result, requests, sleep = await run_case([READY], monkeypatch, tmp_path,
                                            {"media_ready_timeout": 2})
    assert not result.get("success") and len(requests) == 1
    assert sleep.await_count == 0


@pytest.mark.asyncio
async def test_cancel_propagates_without_replay(monkeypatch, tmp_path):
    with pytest.raises(asyncio.CancelledError):
        await run_case([asyncio.CancelledError()], monkeypatch, tmp_path)


@pytest.mark.asyncio
async def test_post_timeout_cancels_without_replay(monkeypatch, tmp_path):
    cancelled = asyncio.Event()

    async def hang(request):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    result, requests, sleep = await run_case([hang], monkeypatch, tmp_path,
                                            {"media_ready_timeout": .1})
    assert not result.get("success") and cancelled.is_set()
    assert len(requests) == 1 and sleep.await_count == 0


@pytest.mark.asyncio
async def test_env_settings_override_extra(monkeypatch, tmp_path):
    monkeypatch.setenv("MAX_MEDIA_READY_ATTEMPTS", "4")
    monkeypatch.setenv("MAX_MEDIA_READY_TIMEOUT", "25")
    result, requests, sleep = await run_case([READY], monkeypatch, tmp_path,
                                            {"media_ready_attempts": 1})
    assert not result.get("success") and len(requests) == 4
    assert [call.args[0] for call in sleep.await_args_list] == [2, 4, 8]


@pytest.mark.parametrize("extra,expected", [
    ({}, (8, 90)),
    ({"media_ready_attempts": 100, "media_ready_timeout": 999}, (12, 300)),
    ({"media_ready_attempts": -1, "media_ready_timeout": -1}, (8, 90)),
    ({"media_ready_attempts": "x", "media_ready_timeout": "nan"}, (8, 90)),
    ({"media_ready_attempts": "3.5", "media_ready_timeout": "inf"}, (8, 300)),
    ({"media_ready_attempts": 1, "media_ready_timeout": .1}, (1, .1)),
])
def test_shared_validated_settings(monkeypatch, extra, expected):
    from max.mixins.media_readiness import readiness_settings
    monkeypatch.delenv("MAX_MEDIA_READY_ATTEMPTS", raising=False)
    monkeypatch.delenv("MAX_MEDIA_READY_TIMEOUT", raising=False)
    assert readiness_settings(extra) == expected
