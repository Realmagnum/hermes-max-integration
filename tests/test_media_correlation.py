"""One bounded final summary per attachment; external HTTP/CDN only are replaced."""
import asyncio
import hashlib
import json
import logging
import os
from unittest.mock import AsyncMock

import pytest
from max.mixins import media_upload


def records(caplog):
    return [json.loads(r.message.split("MAX media: ", 1)[1]) for r in caplog.records
            if r.message.startswith("MAX media: ")]


def fingerprint(path):
    s = path.stat()
    value = f"max-file-v1:{s.st_dev}:{s.st_ino}:{s.st_size}:{s.st_mtime_ns}"
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def source_id(path):
    return hashlib.sha256(b"max-source-path-v1\0" + os.fsencode(os.path.normcase(os.path.abspath(path)))).hexdigest()


def assert_private_final(row, path, caplog):
    assert row["source_id"] == source_id(path)
    assert row["file_fingerprint"] == fingerprint(path)
    assert row["size"] == path.stat().st_size
    assert len(json.dumps(row, separators=(",", ":")).encode()) <= 2048
    for secret in (str(path), path.name, "private speech", "CDN_SECRET", "URL_SECRET", "https://upload.max.ru"):
        assert secret not in "\n".join(r.message for r in caplog.records if not r.name.startswith("httpx"))
    assert "stage" not in row and "mode" not in row


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["image", "video", "audio", "file"])
async def test_one_final_adapter_summary_after_not_ready(kind, make_adapter, max_api, monkeypatch, tmp_path, caplog):
    caplog.set_level(logging.INFO)
    path = tmp_path / "private-source.bin"
    path.write_bytes(b"OggSprivate speech bytes")
    max_api.route("POST", "/uploads", json_body={"url": "https://upload.max.ru/private?token=URL_SECRET", "token": "CDN_SECRET"})
    responses = iter([(400, {"code": "attachment.not.ready"}), (200, {"message": {"body": {"mid": "sent-mid"}}})])
    max_api.route("POST", "/messages", json_body=lambda req: next(responses))
    cdn = AsyncMock(return_value=(200, {"token": "CDN_SECRET"}))
    monkeypatch.setattr(media_upload, "post_file", cdn)
    monkeypatch.setattr(media_upload.asyncio, "sleep", AsyncMock())
    a = make_adapter()
    a.send_action = AsyncMock()
    caplog.clear()
    try:
        result = await a._upload_send("user:42", str(path), kind, "private speech", None)
    finally:
        await a._http_client.aclose()
    assert result.success
    rows = records(caplog)
    assert len(rows) == 1, "exactly one final summary, no start/progress records"
    row = rows[0]
    assert row["result"] == "success" and row["status"] == 200
    assert row["media_type"] == kind and row["sender"] == "adapter"
    assert row["attempts"]["readiness"] == 2 and row["attempts"]["cdn"] == 1
    assert row["error_stage"] == "" and row["mid"] == hashlib.sha256(b"sent-mid").hexdigest()
    assert row["wait_ms"] >= 0 and row["elapsed_ms"] >= 0
    assert all(v >= 0 for v in row["durations_ms"].values())
    assert_private_final(row, path, caplog)
    plugin_rows = [r for r in caplog.records if ".mixins." in r.name and r.levelno >= logging.INFO]
    assert len(plugin_rows) == 1, "no legacy per-attempt/plugin stage noise"
    assert len(max_api.calls("POST", "/uploads")) == 1
    assert len(max_api.calls("POST", "/messages")) == 2
    cdn.assert_awaited_once()

@pytest.mark.asyncio
@pytest.mark.parametrize("kind,extension", [("image", ".png"), ("video", ".mp4"), ("audio", ".ogg"), ("file", ".bin")])
async def test_standalone_one_final_per_file(kind, extension, monkeypatch, tmp_path, caplog):
    import httpx
    from gateway.config import PlatformConfig
    from max.mixins import media_readiness, standalone
    caplog.set_level(logging.INFO)
    paths = [tmp_path / (name + extension) for name in ["private-one", "private-two"]]
    for p in paths:
        p.write_bytes(b"identical private speech")
    real_client = httpx.AsyncClient
    posts = []
    def handle(req):
        posts.append(req)
        if req.url.path == "/uploads":
            return httpx.Response(200, json={"url": "https://upload.max.ru/private?token=URL_SECRET", "token": "CDN_SECRET"})
        return httpx.Response(200, json={"message": {"body": {"mid": "standalone-mid"}}})
    monkeypatch.setattr(standalone.httpx, "AsyncClient", lambda **kw: real_client(**kw, transport=httpx.MockTransport(handle)))
    monkeypatch.setattr(standalone, "_standalone_get_token", lambda _: "AUTH_SECRET")
    monkeypatch.setattr(standalone, "post_file", AsyncMock(return_value=(200, {"token": "CDN_SECRET"})))
    monkeypatch.setattr(media_readiness.asyncio, "sleep", AsyncMock())
    result = await standalone._standalone_send(PlatformConfig(enabled=True, token="AUTH_SECRET", extra={}), "user:42", "", media_files=[(str(p), False) for p in paths])
    assert result.get("success")
    rows = records(caplog)
    assert len(rows) == 2 and len({r["operation_id"] for r in rows}) == 2
    for row, p in zip(rows, paths):
        assert row["result"] == "success" and row["media_type"] == kind
        assert row["attempts"]["cdn"] == 1 and row["attempts"]["readiness"] == 1
        assert_private_final(row, p, caplog)
    assert len([r for r in caplog.records if ".mixins." in r.name and r.levelno >= logging.INFO]) == 2
    assert len(posts) == 4


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["success", "send_error", "upload_error", "cancel"])
async def test_batch_uploads_join_final_send_once(case, make_adapter, max_api, monkeypatch, tmp_path, caplog):
    caplog.set_level(logging.INFO)
    paths = [tmp_path / (name + ".png") for name in ["private-one", "private-two"]]
    for p in paths:
        p.write_bytes(b"same private speech")
    max_api.route("POST", "/uploads", json_body={"url": "https://upload.max.ru/private?token=URL_SECRET"})
    sends = []
    def send(req):
        sends.append(req)
        if case == "cancel":
            raise asyncio.CancelledError()
        if case == "send_error" and len(sends) == 1:
            return 503, {"message": "private speech"}
        return 200, {"message": {"body": {"mid": "batch-mid"}}}
    max_api.route("POST", "/messages", json_body=send)
    uploads = []
    async def cdn(*args, **kw):
        uploads.append(args[2])
        assert not records(caplog), "upload completion must not flush batch summaries"
        if case == "upload_error" and len(uploads) == 1:
            return 503, {}
        return 200, {"token": "CDN_SECRET"}
    # In fallback a preceding attachment may already be finalized; check silence
    # only during the initial upload pass.
    async def checked_cdn(*args, **kw):
        if len(uploads) < (1 if case == "upload_error" else 2):
            return await cdn(*args, **kw)
        uploads.append(args[2])
        return 200, {"token": "CDN_SECRET"}
    monkeypatch.setattr(media_upload, "post_file", checked_cdn)
    a = make_adapter()
    a.send_action = AsyncMock()
    caplog.clear()
    try:
        if case == "cancel":
            with pytest.raises(asyncio.CancelledError):
                await a.send_multiple_images("user:42", [(str(p), "private speech") for p in paths])
        else:
            result = await a.send_multiple_images("user:42", [(str(p), "private speech") for p in paths])
            assert result.success
    finally:
        await a._http_client.aclose()
    rows = records(caplog)
    assert len(rows) == 2, "one final per input attachment, not per failed upload/fallback"
    assert len({r["batch_id"] for r in rows}) == 1 and rows[0]["batch_id"]
    for index, (row, p) in enumerate(zip(rows, paths)):
        assert row["attachment_index"] == index
        assert row["result"] == ("cancelled" if case == "cancel" else "success")
        if case != "cancel":
            assert row["mid"] == hashlib.sha256(b"batch-mid").hexdigest()
        assert row["attempts"]["send"] + row["attempts"]["readiness"] >= 1
        assert_private_final(row, p, caplog)
    assert len(sends) == (3 if case == "send_error" else 2 if case == "upload_error" else 1)
    assert len(uploads) == (4 if case == "send_error" else 3 if case == "upload_error" else 2)
    assert len([r for r in caplog.records if ".mixins." in r.name and r.levelno >= logging.INFO]) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("sender", ["adapter", "standalone"])
@pytest.mark.parametrize("kind,extension", [("image", ".png"), ("video", ".mp4"), ("audio", ".ogg"), ("file", ".bin")])
@pytest.mark.parametrize("case,stage,status", [("upload_url", "upload_url", None), ("cdn", "cdn", None), ("reject", "readiness", 403), ("not_ready", "readiness", 400), ("cancel", "cdn", None), ("missing", "admission", None)])
async def test_error_cancel_single_final_uniform(sender, kind, extension, case, stage, status, make_adapter, max_api, monkeypatch, tmp_path, caplog):
    import httpx
    from gateway.config import PlatformConfig
    from max.mixins import standalone
    caplog.set_level(logging.INFO)
    path = tmp_path / ("private-source" + extension)
    if case != "missing":
        path.write_bytes(b"OggSprivate speech")
    url_calls, send_calls = [], []
    def handle(req):
        if req.url.path == "/uploads":
            url_calls.append(req)
            if case == "upload_url":
                raise RuntimeError("private speech URL_SECRET https://upload.max.ru/private")
            return httpx.Response(200, json={"url": "https://upload.max.ru/private?token=URL_SECRET", "token": "CDN_SECRET"})
        send_calls.append(req)
        return httpx.Response(400 if case == "not_ready" else 403,
                              json={"code": "attachment.not.ready" if case == "not_ready" else "bad", "message": "private speech"})
    async def cdn(*args, **kw):
        if case == "cancel":
            raise asyncio.CancelledError()
        if case == "cdn":
            raise RuntimeError("private speech URL_SECRET")
        return 200, {"token": "CDN_SECRET"}
    real_client = httpx.AsyncClient
    monkeypatch.setattr(media_upload.asyncio, "sleep", AsyncMock())
    if sender == "adapter":
        a = make_adapter(extra={"media_ready_attempts": 3})
        await a._http_client.aclose()
        a._http_client = real_client(transport=httpx.MockTransport(handle))
        a.send_action = AsyncMock()
        monkeypatch.setattr(media_upload, "post_file", cdn)
        run = a._upload_send("user:42", str(path), kind, "private speech", None)
    else:
        monkeypatch.setattr(standalone.httpx, "AsyncClient", lambda **kw: real_client(**kw, transport=httpx.MockTransport(handle)))
        monkeypatch.setattr(standalone, "_standalone_get_token", lambda _: "AUTH_SECRET")
        monkeypatch.setattr(standalone, "post_file", cdn)
        run = standalone._standalone_send(PlatformConfig(enabled=True, token="AUTH_SECRET", extra={"media_ready_attempts": 3}), "user:42", "", media_files=[(str(path), False)])
    caplog.clear()
    try:
        if case == "cancel":
            with pytest.raises(asyncio.CancelledError):
                await run
        else:
            result = await run
            assert not (result.success if sender == "adapter" else result.get("success"))
    finally:
        if sender == "adapter":
            await a._http_client.aclose()
    rows = records(caplog)
    assert len(rows) == 1
    row = rows[0]
    assert row["result"] == ("cancelled" if case == "cancel" else "error")
    assert row["error_stage"] == stage and row["status"] == status
    assert row["source_id"] == source_id(path)
    assert row["media_type"] == kind
    assert row["attempts"]["readiness"] == (3 if case == "not_ready" else 1 if case == "reject" else 0)
    assert len(url_calls) == (0 if case == "missing" else 1)
    if case == "missing":
        assert row["file_fingerprint"] == "" and row["size"] == -1
    else:
        assert_private_final(row, path, caplog)
    assert len([r for r in caplog.records if ".mixins." in r.name and r.levelno >= logging.INFO]) == 1
    from max.mixins import media_diagnostics as diagnostics
    assert diagnostics._current.get() is None


@pytest.mark.asyncio
async def test_source_before_normalize_deleted_artifact_and_no_early_info(make_adapter, max_api, monkeypatch, tmp_path, caplog):
    import threading
    from pathlib import Path

    from max.mixins import media_diagnostics as diagnostics
    caplog.set_level(logging.DEBUG)
    path = tmp_path / "private-original.wav"
    path.write_bytes(b"RIFFxxxxWAVEprivate speech")
    source = source_id(path)
    loop_thread = threading.get_ident()
    def transcode(src, dst):
        assert diagnostics._current.get().source_id == source
        assert not records(caplog) and threading.get_ident() != loop_thread
        Path(dst).write_bytes(b"OggSartifact")
        return True
    monkeypatch.setattr(media_upload, "_transcode_to_opus_ogg", transcode)
    max_api.route("POST", "/uploads", json_body={"url": "https://upload.max.ru/private?token=URL_SECRET", "token": "CDN_SECRET"})
    monkeypatch.setattr(media_upload, "post_file", AsyncMock(return_value=(200, {})))
    a = make_adapter()
    a.send_action = AsyncMock(side_effect=RuntimeError(str(path)))
    caplog.clear()
    try:
        result = await a._upload_send("user:42", str(path), "audio", "private speech", None)
    finally:
        await a._http_client.aclose()
    assert result.success
    artifact = path.with_suffix(".ogg")
    artifact_id = fingerprint(artifact)
    artifact.unlink()
    rows = records(caplog)
    assert len(rows) == 1 and rows[0]["source_id"] == source_id(path)
    assert rows[0]["file_fingerprint"] == artifact_id and path.exists() and not artifact.exists()
    assert rows[0]["attempts"]["normalize"] == 1
    assert str(path) not in caplog.text and path.name not in caplog.text


def test_fixed_accumulator_memory_summary_bounds_and_no_event_noise(caplog, monkeypatch):
    import gc
    import threading
    import tracemalloc

    from max.mixins import media_diagnostics as diagnostics
    caplog.set_level(logging.INFO)
    with diagnostics.MediaOperation("adapter", "file") as operation:
        assert not records(caplog)
        thread_count_before = len(threading.enumerate())
        tracemalloc.start()
        for _ in range(100):
            operation.begin("readiness")
            operation.emit("readiness", "not_ready", status=400, attempt=1000000)
        gc.collect()
        before = tracemalloc.get_traced_memory()[0]
        for _ in range(100000):
            operation.begin("readiness")
            operation.emit("readiness", "not_ready", status=400, attempt=1000000)
            operation.emit("UNKNOWN_SECRET", "SECRET", mid="SECRET" * 10000)
        gc.collect()
        after = tracemalloc.get_traced_memory()[0]
        tracemalloc.stop()
        assert after - before < 65536
        assert len(threading.enumerate()) <= thread_count_before
        assert not hasattr(operation, "__dict__")
        assert set(operation.durations) == set(diagnostics.STAGES)
        assert set(operation.attempts) == set(diagnostics.STAGES)
        assert not records(caplog)
        # Stress the serialized upper bound with every fixed field at its cap.
        operation.source_id = "a" * 64
        operation.file_fingerprint = "b" * 64
        operation.batch_id = "c" * 32
        operation.attachment_index = 2**63 - 1
        operation.size = 4_000_000_000
        operation.durations = dict.fromkeys(diagnostics.STAGES, diagnostics.MAX_MS)
        operation.attempts = dict.fromkeys(diagnostics.STAGES, diagnostics.MAX_COUNT)
        operation.wait_ms = diagnostics.MAX_MS
        operation.status = 599
        operation.mid = diagnostics._digest_mid("x" * 4096)
        operation.started -= diagnostics.MAX_MS / 1000
        operation.finish("error")
        operation.finish("success")
    rows = records(caplog)
    assert len(rows) == 1 and len(json.dumps(rows[0], separators=(",", ":")).encode()) <= 2048
    print(f"retained_growth_bytes={after - before} summary_bytes={len(json.dumps(rows[0], separators=(',', ':')).encode())} summaries={len(rows)} no_new_threads=true")
    assert rows[0]["attempts"]["readiness"] == diagnostics.MAX_COUNT
    assert "SECRET" not in caplog.text
    def broken(*args, **kwargs):
        raise RuntimeError("private speech")
    monkeypatch.setattr(diagnostics.logger, "info", broken)
    with diagnostics.MediaOperation("adapter", "file"):
        pass


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["no_token", "client_error", "cancel_before_files"])
async def test_standalone_prepare_failure_final_per_attachment(case, monkeypatch, tmp_path, caplog):
    from gateway.config import PlatformConfig
    from max.mixins import standalone
    caplog.set_level(logging.INFO)
    paths = [tmp_path / "one.png", tmp_path / "two.mp4"]
    monkeypatch.setattr(standalone, "_standalone_get_token", lambda _: "" if case == "no_token" else "AUTH_SECRET")
    def client(**kw):
        if case == "cancel_before_files":
            raise asyncio.CancelledError()
        raise RuntimeError("private speech AUTH_SECRET")
    monkeypatch.setattr(standalone.httpx, "AsyncClient", client)
    run = standalone._standalone_send(PlatformConfig(enabled=True, token="AUTH_SECRET", extra={}), "user:42", "", media_files=[(str(p), False) for p in paths])
    if case == "cancel_before_files":
        with pytest.raises(asyncio.CancelledError):
            await run
    else:
        assert (await run).get("error")
    rows = records(caplog)
    assert len(rows) == 2
    assert [r["media_type"] for r in rows] == ["image", "video"]
    assert all(r["result"] == ("cancelled" if case == "cancel_before_files" else "error") and r["error_stage"] == "prepare" for r in rows)
    assert all(r["source_id"] == "" and r["size"] == -1 for r in rows)
    assert "AUTH_SECRET" not in caplog.text and "private speech" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["success", "reject", "cancel"])
async def test_remote_image_uses_same_single_summary(case, make_adapter, max_api, caplog):
    caplog.set_level(logging.INFO)
    if case == "cancel":
        max_api.fail("POST", "/messages", asyncio.CancelledError())
    else:
        max_api.route("POST", "/messages", status=503 if case == "reject" else 200, json_body={"message": {"body": {"mid": "remote-mid"}}})
    a = make_adapter()
    a.send_action = AsyncMock()
    caplog.clear()
    try:
        if case == "cancel":
            with pytest.raises(asyncio.CancelledError):
                await a.send_image("user:42", "https://private/image?token=URL_SECRET", "private speech")
        else:
            result = await a.send_image("user:42", "https://private/image?token=URL_SECRET", "private speech")
            assert result.success == (case == "success")
    finally:
        await a._http_client.aclose()
    rows = records(caplog)
    assert len(rows) == 1
    row = rows[0]
    assert row["result"] == {"success": "success", "reject": "error", "cancel": "cancelled"}[case]
    assert row["attempts"]["send"] == 1 and row["media_type"] == "image"
    assert row["source_id"] == "" and row["file_fingerprint"] == "" and row["size"] == -1
    assert "URL_SECRET" not in caplog.text and "private speech" not in caplog.text


@pytest.mark.asyncio
async def test_source_bound_and_wait_accounting(make_adapter, max_api, monkeypatch, tmp_path, caplog):
    from max.mixins import media_diagnostics as diagnostics
    caplog.set_level(logging.INFO)
    with diagnostics.MediaOperation("adapter", "file") as operation:
        await asyncio.to_thread(diagnostics.identify_media_source, "x" * 32769)
        assert operation.source_id == "" and not records(caplog)
    caplog.clear()
    path = tmp_path / "private-source.bin"
    path.write_bytes(b"synthetic")
    max_api.route("POST", "/uploads", json_body={"url": "https://upload.max.ru/private?token=URL_SECRET"})
    seq = iter([(400, {"code": "attachment.not.ready"}), (200, {"message": {"body": {"mid": "wait-mid"}}})])
    max_api.route("POST", "/messages", json_body=lambda req: next(seq))
    monkeypatch.setattr(media_upload, "post_file", AsyncMock(return_value=(200, {"token": "CDN_SECRET"})))
    real_sleep = asyncio.sleep
    requested_waits = []
    async def sleep(delay):
        requested_waits.append(delay)
        await real_sleep(.01)
    monkeypatch.setattr(media_upload.asyncio, "sleep", sleep)
    a = make_adapter()
    a.send_action = AsyncMock()
    caplog.clear()
    try:
        assert (await a._upload_send("user:42", str(path), "file", "", None)).success
    finally:
        await a._http_client.aclose()
    row, = records(caplog)
    assert [delay for delay in requested_waits if delay] == [2.0] and row["wait_ms"] >= 5
    assert row["durations_ms"]["readiness"] >= row["wait_ms"]
    assert row["attempts"]["readiness"] == 2


@pytest.mark.asyncio
async def test_standalone_existing_native_fallback_type_preserved(monkeypatch, tmp_path, caplog):
    import httpx
    from gateway.config import PlatformConfig
    from max.mixins import standalone
    caplog.set_level(logging.INFO)
    path = tmp_path / "private-source.png"
    path.write_bytes(b"synthetic image")
    real_client = httpx.AsyncClient
    upload_types, sent_types = [], []
    def handle(req):
        if req.url.path == "/uploads":
            upload_types.append(req.url.params["type"])
            return httpx.Response(503 if len(upload_types) == 1 else 200, json={"url": "https://upload.max.ru/private?token=URL_SECRET"})
        sent_types.append(json.loads(req.content)["attachments"][0]["type"])
        return httpx.Response(200, json={"message": {"body": {"mid": "fallback-mid"}}})
    monkeypatch.setattr(standalone.httpx, "AsyncClient", lambda **kw: real_client(**kw, transport=httpx.MockTransport(handle)))
    monkeypatch.setattr(standalone, "_standalone_get_token", lambda _: "AUTH_SECRET")
    monkeypatch.setattr(standalone, "post_file", AsyncMock(return_value=(200, {"token": "CDN_SECRET"})))
    result = await standalone._standalone_send(PlatformConfig(enabled=True, token="AUTH_SECRET", extra={}), "user:42", "", media_files=[(str(path), False)])
    assert result.get("success") and upload_types == ["image", "file"] and sent_types == ["file"]
    row, = records(caplog)
    assert row["media_type"] == "file" and row["attempts"]["upload_url"] == 2
    assert_private_final(row, path, caplog)


@pytest.mark.asyncio
async def test_batch_partial_fallback_reports_each_actual_result(make_adapter, max_api, monkeypatch, tmp_path, caplog):
    caplog.set_level(logging.INFO)
    paths = [tmp_path / "private-one.png", tmp_path / "private-two.png"]
    for path in paths:
        path.write_bytes(b"image")
    original_fingerprints = [fingerprint(path) for path in paths]
    max_api.route("POST", "/uploads", json_body={"url": "https://upload.max.ru/private?token=URL_SECRET"})
    calls = []
    def send(req):
        calls.append(req)
        if len(calls) == 1:
            paths[0].unlink()
            return 503, {}
        return 200, {"message": {"body": {"mid": "partial-mid"}}}
    max_api.route("POST", "/messages", json_body=send)
    monkeypatch.setattr(media_upload, "post_file", AsyncMock(return_value=(200, {"token": "CDN_SECRET"})))
    a = make_adapter()
    a.send_action = AsyncMock()
    caplog.clear()
    try:
        result = await a.send_multiple_images("user:42", [(str(p), "") for p in paths])
    finally:
        await a._http_client.aclose()
    assert result.success, "preserve baseline last-success fallback return"
    rows = records(caplog)
    assert len(rows) == 2
    assert [r["result"] for r in rows] == ["error", "success"]
    assert rows[0]["error_stage"] == "admission" and rows[0]["status"] is None
    assert rows[0]["file_fingerprint"] == original_fingerprints[0]
    assert rows[0]["source_id"] == source_id(paths[0])
    assert rows[1]["mid"] == hashlib.sha256(b"partial-mid").hexdigest()


@pytest.mark.asyncio
@pytest.mark.parametrize("sender", ["adapter", "standalone"])
@pytest.mark.parametrize("case", ["invalid_json", "unexpected_structure"])
async def test_readiness_parse_failure_preserves_observed_status(sender, case, make_adapter, monkeypatch, tmp_path, caplog):
    import httpx
    from gateway.config import PlatformConfig
    from max.mixins import standalone

    caplog.set_level(logging.INFO)
    path = tmp_path / "private-source.bin"
    path.write_bytes(b"private speech")
    real_client = httpx.AsyncClient
    sends, uploads = [], []

    def handle(req):
        if req.url.path == "/uploads":
            uploads.append(req)
            return httpx.Response(200, json={"url": "https://upload.max.ru/private?token=URL_SECRET", "token": "CDN_SECRET"})
        sends.append(req)
        if case == "invalid_json":
            return httpx.Response(200, content=b"private speech URL_SECRET not JSON")
        return httpx.Response(200, json={"message": ["private speech URL_SECRET"]})

    cdn = AsyncMock(return_value=(200, {"token": "CDN_SECRET"}))
    if sender == "adapter":
        adapter = make_adapter(extra={"media_ready_attempts": 3})
        await adapter._http_client.aclose()
        adapter._http_client = real_client(transport=httpx.MockTransport(handle))
        adapter.send_action = AsyncMock()
        monkeypatch.setattr(media_upload, "post_file", cdn)
        try:
            result = await adapter._upload_send("user:42", str(path), "file", "private speech", None)
        finally:
            await adapter._http_client.aclose()
        assert not result.success and result.retryable is False
        assert result.error == "Upload-send failed (see logs)"
    else:
        monkeypatch.setattr(standalone.httpx, "AsyncClient", lambda **kw: real_client(**kw, transport=httpx.MockTransport(handle)))
        monkeypatch.setattr(standalone, "_standalone_get_token", lambda _: "AUTH_SECRET")
        monkeypatch.setattr(standalone, "post_file", cdn)
        result = await standalone._standalone_send(PlatformConfig(enabled=True, token="AUTH_SECRET", extra={"media_ready_attempts": 3}), "user:42", "", media_files=[(str(path), False)])
        assert not result.get("success") and result.get("error")

    assert len(uploads) == 1 and len(sends) == 1, "ambiguous parse failure must not replay"
    cdn.assert_awaited_once()
    row, = records(caplog)
    assert row["result"] == "error" and row["error_stage"] == "readiness"
    assert row["attempts"]["readiness"] == 1 and row["mid"] == ""
    assert row["status"] == 200, "response status must survive JSON/structure failure"
    assert_private_final(row, path, caplog)
    assert "AUTH_SECRET" not in caplog.text
    assert len([r for r in caplog.records if ".mixins." in r.name and r.levelno >= logging.INFO]) == 1
