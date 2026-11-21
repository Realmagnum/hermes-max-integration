"""Actual registered max_send_attachments entrypoint, not direct batch helpers."""
import asyncio
import copy
import hashlib
import json
import logging
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from max import attachment_tool, tools
from max.mixins import media_diagnostics, media_readiness, media_upload


def rows(caplog):
    return [json.loads(r.message.split("MAX media: ", 1)[1]) for r in caplog.records
            if r.message.startswith("MAX media: ")]


@pytest.mark.asyncio
@pytest.mark.parametrize("kinds", [("image",), ("video",), ("audio",), ("file",), ("image", "image")])
@pytest.mark.parametrize("case", ["success", "reject", "not_ready", "cancel", "upload_error", "upload_cancel", "prepare_error", "prepare_cancel", "transport_error", "invalid_json"])
async def test_registered_tool_owns_final_delivery(kinds, case, monkeypatch, tmp_path, caplog):
    caplog.set_level(logging.INFO)
    registered = {}
    tools.register_tools(SimpleNamespace(register_tool=lambda **kw: registered.update({kw["name"]: kw})))
    handler = registered["max_send_attachments"]["handler"]
    assert handler is attachment_tool.send_attachments
    paths = [tmp_path / f"private-{i}.bin" for i in range(len(kinds))]
    for path in paths:
        path.write_bytes(b"OggSprivate speech")
    if case == "prepare_error":
        paths[-1].write_bytes(b"")
    args = {"attachments": [{"type": kind, "path": str(path)} for kind, path in zip(kinds, paths)],
            "text": "private speech", "format": "html", "notify": True,
            "link": {"type": "reply", "mid": "private-mid"}}
    before = copy.deepcopy(args)
    real_client, real_to_thread = httpx.AsyncClient, attachment_tool.asyncio.to_thread
    uploads, sends, cdn_calls, premature = [], [], [], []

    async def to_thread(fn, *args, **kw):
        if case == "prepare_cancel" and fn is attachment_tool._stat_media_source and args[0] == str(paths[-1]):
            raise asyncio.CancelledError()
        return await real_to_thread(fn, *args, **kw)

    def handle(req):
        if req.url.path == "/uploads":
            uploads.append(req.url.params["type"])
            return httpx.Response(200, json={"url": "https://upload.max.ru/private?token=URL_SECRET", "token": "CDN_SECRET"})
        premature.append(bool(rows(caplog)))
        sends.append(bytes(req.content))
        if case == "cancel":
            raise asyncio.CancelledError()
        if case == "transport_error":
            raise RuntimeError("private speech URL_SECRET AUTH_SECRET")
        if case == "invalid_json":
            return httpx.Response(200, content=b"private speech URL_SECRET not JSON")
        if case == "unknown_mid":
            return httpx.Response(200, json={"message": {"body": {}}})
        if case == "postprocess_error":
            return httpx.Response(200, json={"message": {"body": {"mid": "tool-receipt"}, "recipient": []}})
        if case == "reject":
            return httpx.Response(403, json={"message": "private speech"})
        if case == "not_ready" and len(sends) == 1:
            return httpx.Response(400, json={"code": "attachment.not.ready"})
        return httpx.Response(200, json={"message": {"body": {"mid": "tool-receipt"}}})

    async def cdn(*args, **kwargs):
        premature.append(bool(rows(caplog)))
        cdn_calls.append(args)
        if len(cdn_calls) == len(kinds):
            if case == "upload_error":
                return 503, {}
            if case == "upload_cancel":
                raise asyncio.CancelledError()
        return 200, {"token": "CDN_SECRET"}

    monkeypatch.setattr(attachment_tool, "get_session_env", lambda key: {"HERMES_SESSION_PLATFORM": "max", "HERMES_SESSION_CHAT_ID": "user:42"}.get(key, ""))
    monkeypatch.setattr(attachment_tool, "get_max_secret", lambda *args: "AUTH_SECRET")
    monkeypatch.setattr(attachment_tool.httpx, "AsyncClient", lambda **kw: real_client(**kw, transport=httpx.MockTransport(handle)))
    monkeypatch.setattr(attachment_tool.asyncio, "to_thread", to_thread)
    monkeypatch.setattr(media_upload, "post_file", cdn)
    monkeypatch.setattr(media_readiness.asyncio, "sleep", AsyncMock())
    cancelled = case in {"cancel", "upload_cancel", "prepare_cancel"}
    success = case in {"success", "not_ready", "unknown_mid"}
    if cancelled:
        with pytest.raises(asyncio.CancelledError):
            await handler(args)
    else:
        result = json.loads(await handler(args))
        assert bool(result.get("success")) is success
        assert result["retryable"] is False
        if success:
            assert result["message_id"] == ("" if case == "unknown_mid" else "tool-receipt")
    assert args == before
    assert uploads == ([] if case.startswith("prepare_") else list(kinds))
    no_send = case.startswith(("prepare_", "upload_"))
    assert len(sends) == (0 if no_send else 2 if case == "not_ready" else 1)
    assert len(cdn_calls) == (0 if case.startswith("prepare_") else len(kinds))
    expected = copy.deepcopy(before)
    expected["attachments"] = [{"type": kind, "payload": {"token": "CDN_SECRET"}} for kind in kinds]
    for sent in sends:
        assert json.loads(sent) == expected
    assert not sends or all(sent == sends[0] for sent in sends), "readiness must reuse the immutable body"
    assert not any(premature), "live gap: successful receipt but premature upload-only summaries"
    summaries = rows(caplog)
    assert len(summaries) == len(kinds)
    assert len({r["operation_id"] for r in summaries}) == len(kinds)
    for index, (row, path, kind) in enumerate(zip(summaries, paths, kinds)):
        assert row["result"] == ("cancelled" if cancelled else "success" if success else "error")
        assert row["mid"] == (hashlib.sha256(b"tool-receipt").hexdigest() if (success and case != "unknown_mid") or case == "postprocess_error" else "")
        assert row["attempts"]["readiness"] == (0 if no_send else 2 if case == "not_ready" else 1)
        if not no_send:
            assert row["status"] == (None if case in {"cancel", "transport_error"} else 403 if case == "reject" else 200)
            assert row["error_stage"] == ("" if success else "send" if case == "postprocess_error" else "readiness")
        assert row["media_type"] == kind and row["attachment_index"] == index
        if not (case == "prepare_cancel" and index == len(kinds) - 1):
            assert row["source_id"] == hashlib.sha256(b"max-source-path-v1\0" + os.fsencode(os.path.normcase(os.path.abspath(path)))).hexdigest()
        if not case.startswith("prepare_"):
            assert row["file_fingerprint"] and row["size"] == path.stat().st_size
        assert len(json.dumps(row, separators=(",", ":")).encode()) <= 2048
    if len(kinds) > 1:
        assert len({r["batch_id"] for r in summaries}) == 1 and summaries[0]["batch_id"]
        if case != "prepare_cancel":
            assert len({r["source_id"] for r in summaries}) == len(kinds)
    plugin_logs = "\n".join(r.message for r in caplog.records if not r.name.startswith("httpx"))
    for secret in [str(tmp_path), "private speech", "private-mid", "URL_SECRET", "CDN_SECRET", "AUTH_SECRET"]:
        assert secret not in plugin_logs
    assert len([r for r in caplog.records if ".mixins." in r.name and r.levelno >= logging.INFO]) == len(kinds)
    assert media_diagnostics._current.get() is None


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [200, 503])
async def test_bare_upload_never_claims_delivery(status, make_adapter, max_api, monkeypatch, tmp_path, caplog):
    caplog.set_level(logging.INFO)
    path = tmp_path / "private-upload.bin"
    path.write_bytes(b"synthetic")
    max_api.route("POST", "/uploads", json_body={"url": "https://upload.max.ru/private?token=URL_SECRET"})
    monkeypatch.setattr(media_upload, "post_file", AsyncMock(return_value=(status, {"token": "CDN_SECRET"})))
    instance = make_adapter()
    try:
        result = await instance._upload(str(path), "file")
    finally:
        await instance._http_client.aclose()
    assert bool(result) is (status == 200)
    row, = rows(caplog)
    assert row["result"] == ("uploaded" if status == 200 else "error")
    assert row["mid"] == "" and row["attempts"]["readiness"] == row["attempts"]["send"] == 0
    assert not max_api.calls("POST", "/messages")


def test_shared_group_is_bounded_synchronous_and_context_scoped(monkeypatch, caplog):
    import gc
    import threading
    import tracemalloc

    caplog.set_level(logging.INFO)
    owners = (media_diagnostics.MediaOperation("adapter", "image"), media_diagnostics.MediaOperation("adapter", "image"))
    def forbidden(*args, **kw):
        raise AssertionError("shared diagnostics must not read files/spawn tasks/threads")
    monkeypatch.setattr("builtins.open", forbidden)
    monkeypatch.setattr(asyncio, "create_task", forbidden)
    monkeypatch.setattr(asyncio, "to_thread", forbidden)
    monkeypatch.setattr(threading.Thread, "start", forbidden)
    growth = None
    tracemalloc.start()
    try:
        with media_diagnostics.media_group(owners):
            for _ in range(100):
                media_diagnostics.media_begin("readiness")
                media_diagnostics.media_event("readiness", "not_ready", status=400, attempt=100000)
            gc.collect()
            before = tracemalloc.get_traced_memory()[0]
            for _ in range(20000):
                media_diagnostics.media_begin("readiness")
                media_diagnostics.media_event("readiness", "not_ready", status=400, attempt=100000)
                media_diagnostics.media_wait(.01)
            gc.collect()
            growth = tracemalloc.get_traced_memory()[0] - before
            assert growth < 65536
            assert not rows(caplog)
            for owner in owners:
                assert not hasattr(owner, "__dict__")
                assert set(owner.attempts) == set(owner.durations) == set(media_diagnostics.STAGES)
                assert owner.attempts["readiness"] == media_diagnostics.MAX_COUNT
                assert owner.wait_ms <= media_diagnostics.MAX_MS
            raise asyncio.CancelledError()
    except asyncio.CancelledError:
        pass
    finally:
        tracemalloc.stop()
    assert media_diagnostics._current.get() is None
    for owner in owners:
        owner.finish("cancelled")
        owner.finish("success")
    assert len(rows(caplog)) == 2 and all(row["result"] == "cancelled" for row in rows(caplog))
    print(f"shared_group_retained_growth_bytes={growth} owners=2 group_context_reset=true no_file_reads_or_task_thread_creation=true")
