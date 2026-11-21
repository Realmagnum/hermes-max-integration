"""Real installed Core loader + MAX send_voice, external HTTP/CDN only mocked.

The identities below belong to this isolated process, NOT live PID memory.
"""
import asyncio
import hashlib
import importlib
import json
import logging
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from gateway.config import PlatformConfig
from gateway.run_voice import GatewayVoiceMixin
from hermes_cli.plugins_loader import PluginLoaderMixin

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "hermes_plugins.max_platform"


def load_generation():
    loader = PluginLoaderMixin()
    loader.scope_key = "isolated-same-profile-replay"
    module = loader._load_directory_module(
        SimpleNamespace(path=ROOT, key="max-platform", name="max-platform"))
    assert module.__name__ == PREFIX  # Core chooses the name; don't force an alias.
    return SimpleNamespace(**{
        name: importlib.import_module(f"{PREFIX}.{suffix}")
        for name, suffix in {
            "adapter": "adapter", "upload": "mixins.media_upload",
            "stream": "mixins.upload_stream", "diag": "mixins.media_diagnostics",
            "readiness": "mixins.media_readiness",
        }.items()
    })


def summaries(caplog):
    return [json.loads(r.getMessage().split("MAX media: ", 1)[1])
            for r in caplog.records if r.getMessage().startswith("MAX media: ")]


def artifact(path):
    st = path.stat()
    return hashlib.sha256(
        f"max-file-v1:{st.st_dev}:{st.st_ino}:{st.st_size}:{st.st_mtime_ns}".encode("ascii")
    ).hexdigest()


@pytest.mark.asyncio
async def test_real_loader_replacement_preserves_cached_gateway_admission(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    path = tmp_path / "private-voice.ogg"
    path.write_bytes(b"OggS" + b"synthetic non-speech fixture" * 3)
    a = load_generation()
    adapter = a.adapter.MaxAdapter(PlatformConfig(enabled=True, token="fixture-secret"))
    adapter.send_action = AsyncMock()
    calls = []
    phase = ["healthy"]
    posts = {}

    def handle(request):
        calls.append((phase[0], request.url.path))
        if request.url.path == "/uploads":
            return httpx.Response(200, json={"url": "https://upload.max.ru/fixture?secret=CDN_SECRET",
                                             "token": "UPLOAD_TOKEN_SECRET"})
        assert request.url.path == "/messages"
        posts[phase[0]] = posts.get(phase[0], 0) + 1
        if posts[phase[0]] == 1:
            return httpx.Response(400, json={"code": "attachment.not.ready"})
        return httpx.Response(200, json={"message": {"body": {"mid": "fixture-" + phase[0]}}})

    async def cdn(*args, **kwargs):
        assert int(kwargs["admitted"]) == path.stat().st_size
        return 200, {}

    adapter._http_client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(a.upload, "post_file", cdn)
    monkeypatch.setattr(a.readiness.asyncio, "sleep", AsyncMock())
    try:
        first = await adapter.send_voice("user:42", str(path), caption="PRIVATE_SPEECH")
        assert first.success
        healthy = summaries(caplog)[-1]
        assert healthy["size"] == path.stat().st_size
        assert healthy["file_fingerprint"] == artifact(path)

        # Core evicts the package and children, while existing adapter references survive.
        b = load_generation()
        assert a.diag.__name__ == b.diag.__name__ == PREFIX + ".mixins.media_diagnostics"
        assert a.diag is not b.diag
        assert a.diag._current is not b.diag._current
        assert adapter._upload_send.__func__.__globals__["_current"] is a.diag._current
        assert sys.modules[a.diag.__name__] is b.diag
        assert "admitted_media" in a.stream.async_check_upload.__code__.co_names
        phase[0] = "cached-gateway"
        runner = SimpleNamespace(
            _delivery_adapter_for=lambda source: adapter,
            _get_guild_id=lambda event: None,
            _reply_anchor_for_event=lambda event: None,
            _thread_metadata_for_source=lambda source, anchor: {},
        )
        event = SimpleNamespace(source=SimpleNamespace(chat_id="user:42"))
        await GatewayVoiceMixin._deliver_voice_reply(runner, event, [str(path)])
        cached = summaries(caplog)[-1]

        # Fresh generation remains a healthy control; no stale file bytes involved.
        fresh = b.adapter.MaxAdapter(PlatformConfig(enabled=True, token="fixture-secret"))
        fresh.send_action = AsyncMock()
        fresh._http_client = adapter._http_client
        monkeypatch.setattr(b.upload, "post_file", cdn)
        phase[0] = "fresh-gateway"
        third = await fresh.send_voice("user:42", str(path), caption="PRIVATE_SPEECH")
        assert third.success
        rows = summaries(caplog)
        assert len(rows) == 3
        assert rows[2]["size"] == path.stat().st_size
        assert rows[2]["file_fingerprint"] == artifact(path)
        assert len({r["operation_id"] for r in rows}) == 3
        assert all(r["source_id"] for r in rows)
        assert all(r["attempts"]["normalize"] == 1 and r["attempts"]["admission"] == 1
                   and r["attempts"]["readiness"] == 2 for r in rows)
        assert all(r["result"] == "success" and r["mid"] for r in rows)
        print("ISOLATED loader identities: same namespace; helper_objects_differ=true; "
              "contextvars_differ=true; cached_gateway_bound_to_A=true; sys_modules_points_B=true; "
              "cached_async_check_has_callback=true")
        print("ISOLATED phase metadata:", [(r["size"], bool(r["file_fingerprint"])) for r in rows])
        assert cached["size"] == path.stat().st_size
        assert cached["file_fingerprint"] == artifact(path)
        assert all(len(json.dumps(r)) < 2048 for r in rows)
        private = (str(path), path.name, "PRIVATE_SPEECH", "fixture-secret", "CDN_SECRET",
                   "UPLOAD_TOKEN_SECRET", "https://", "fixture-cached-gateway")
        diagnostic_text = "\n".join(r.getMessage() for r in caplog.records
                                     if r.name.startswith(PREFIX) and "MAX media:" in r.getMessage())
        assert all(value not in diagnostic_text for value in private)
        assert all(calls.count((p, "/uploads")) == 1 and calls.count((p, "/messages")) == 2
                   for p in ("healthy", "cached-gateway", "fresh-gateway"))
    finally:
        await adapter._http_client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["audio", "video", "image", "file"])
@pytest.mark.parametrize("outcome", ["success", "error", "cancelled", "admission_error"])
async def test_cached_generation_native_results(kind, outcome, tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    path = tmp_path / ("PRIVATE_FILENAME_" + kind + ".ogg")
    if outcome != "admission_error":
        path.write_bytes(b"OggS" + kind.encode() * 20)
    a = load_generation()
    instance = a.adapter.MaxAdapter(PlatformConfig(enabled=True, token="FIXTURE_BOT_SECRET"))
    instance.send_action = AsyncMock()
    load_generation()  # Same production namespace, a new helper/ContextVar object.
    requests = []
    bodies = []

    def handle(request):
        requests.append(request.url.path)
        if request.url.path == "/uploads":
            return httpx.Response(200, json={"url": "https://upload.max.ru/private?token=PRIVATE_URL",
                                             "token": "PRIVATE_UPLOAD_TOKEN"})
        assert request.url.path == "/messages"
        body = json.loads(request.content)
        bodies.append(body)
        assert body["attachments"] == [{"type": kind, "payload": {"token": "PRIVATE_UPLOAD_TOKEN"}}]
        if outcome == "cancelled":
            raise asyncio.CancelledError
        if outcome == "error":
            return httpx.Response(403, json={"code": "forbidden"})
        if len(bodies) == 1:
            return httpx.Response(400, json={"code": "attachment.not.ready"})
        return httpx.Response(200, json={"message": {"body": {"mid": "PRIVATE_RAW_MID"}}})

    cdn_calls = []

    async def cdn(session, url, file_path, media_type, *, admitted):
        cdn_calls.append((file_path, media_type, int(admitted)))
        return 200, {"token": "PRIVATE_UPLOAD_TOKEN"}

    monkeypatch.setattr(a.upload, "post_file", cdn)
    monkeypatch.setattr(a.readiness.asyncio, "sleep", AsyncMock())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        instance._http_client = client
        send = getattr(instance, {"audio": "send_voice", "image": "send_image_file",
                                  "video": "send_video", "file": "send_document"}[kind])
        if outcome == "cancelled":
            with pytest.raises(asyncio.CancelledError):
                await send("user:42", str(path), caption="PRIVATE_SPEECH")
        else:
            result = await send("user:42", str(path), caption="PRIVATE_SPEECH")
            assert result.success is (outcome == "success")
    rows = summaries(caplog)
    assert len(rows) == 1
    row = rows[0]
    assert row["media_type"] == kind
    assert row["source_id"]
    assert row["attempts"]["admission"] == 1
    assert row["result"] == ("error" if outcome == "admission_error" else outcome)
    assert a.diag._current.get() is None
    if outcome == "admission_error":
        assert row["size"] == -1 and not row["file_fingerprint"]
        assert requests == [] and cdn_calls == []
    else:
        assert row["size"] == path.stat().st_size
        assert row["file_fingerprint"] == artifact(path)
        assert requests.count("/uploads") == 1 and len(cdn_calls) == 1
        assert requests.count("/messages") == (2 if outcome == "success" else 1)
        assert row["attempts"]["readiness"] == (2 if outcome == "success" else 1)
        if outcome == "success":
            assert bodies[0] == bodies[1]  # Immutable payload on readiness retry.
            assert row["mid"] == hashlib.sha256(b"PRIVATE_RAW_MID").hexdigest()
        else:
            assert row["mid"] == ""
    text = json.dumps(row)
    assert len(text) < 2048
    assert not any(value in text for value in [str(path), path.name, "PRIVATE_SPEECH",
                   "PRIVATE_URL", "PRIVATE_UPLOAD_TOKEN", "PRIVATE_RAW_MID", "FIXTURE_BOT_SECRET", "https://"])


@pytest.mark.asyncio
async def test_fresh_registered_tool_after_replacement_keeps_admission(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    path = tmp_path / "private-tool-audio.ogg"
    path.write_bytes(b"OggS" + b"synthetic audio control" * 4)
    load_generation()
    b = load_generation()
    tool = importlib.import_module(PREFIX + ".attachment_tool")
    tools = importlib.import_module(PREFIX + ".tools")
    registrations = {}
    tools.register_tools(SimpleNamespace(register_tool=lambda **kw: registrations.update({kw["name"]: kw})))
    monkeypatch.setattr(tool, "get_session_env", lambda key: {
        "HERMES_SESSION_PLATFORM": "max", "HERMES_SESSION_CHAT_ID": "user:42"}[key])
    monkeypatch.setattr(tool, "get_max_secret", lambda key: "FIXTURE_BOT_SECRET")
    real_client = httpx.AsyncClient
    bodies = []

    def handle(request):
        if request.url.path == "/uploads":
            return httpx.Response(200, json={"url": "https://upload.max.ru/fixture",
                                             "token": "PRIVATE_UPLOAD_TOKEN"})
        bodies.append(json.loads(request.content))
        if len(bodies) == 1:
            return httpx.Response(400, json={"code": "attachment.not.ready"})
        return httpx.Response(200, json={"message": {"body": {"mid": "PRIVATE_TOOL_MID"}}})

    monkeypatch.setattr(tool.httpx, "AsyncClient", lambda **kw: real_client(
        transport=httpx.MockTransport(handle), **kw))
    monkeypatch.setattr(b.upload, "post_file", AsyncMock(return_value=(200, {})))
    monkeypatch.setattr(b.readiness.asyncio, "sleep", AsyncMock())
    args = {"attachments": [{"type": "audio", "path": str(path)}], "text": "PRIVATE_SPEECH"}
    original = json.loads(json.dumps(args))
    result = json.loads(await registrations["max_send_attachments"]["handler"](args))
    assert result["success"] is True
    assert args == original
    rows = summaries(caplog)
    assert len(rows) == 1
    row = rows[0]
    assert row["size"] == path.stat().st_size and row["file_fingerprint"] == artifact(path)
    assert row["source_id"] and row["result"] == "success"
    assert row["mid"] == hashlib.sha256(b"PRIVATE_TOOL_MID").hexdigest()
    assert row["attempts"]["admission"] == 1 and row["attempts"]["readiness"] == 2
    assert bodies[0] == bodies[1]
    assert b.diag._current.get() is None
    text = json.dumps(row)
    assert len(text) < 2048
    assert not any(value in text for value in [str(path), path.name, "PRIVATE_SPEECH",
                   "PRIVATE_UPLOAD_TOKEN", "PRIVATE_TOOL_MID", "FIXTURE_BOT_SECRET", "https://"])


@pytest.mark.asyncio
async def test_cached_admission_concurrent_files_are_distinct(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    paths = [tmp_path / "private-A.bin", tmp_path / "private-B.bin"]
    for path in paths:
        path.write_bytes(b"same-length synthetic data")
    a = load_generation()
    b = load_generation()

    async def admit(path):
        with a.diag.MediaOperation("adapter", "file") as operation:
            await a.stream.async_check_upload(str(path), "file")
            operation.finish("success")

    await asyncio.gather(*(admit(path) for path in paths))
    rows = summaries(caplog)
    assert len(rows) == 2
    assert len({r["operation_id"] for r in rows}) == 2
    assert len({r["source_id"] for r in rows}) == 2
    assert {r["file_fingerprint"] for r in rows} == {artifact(path) for path in paths}
    assert all(r["size"] == paths[0].stat().st_size for r in rows)
    assert a.diag._current.get() is b.diag._current.get() is None
    assert all(len(json.dumps(r)) < 2048 for r in rows)
    text = json.dumps(rows)
    assert all(str(path) not in text and path.name not in text for path in paths)
