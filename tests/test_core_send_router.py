"""Actual Core send router -> registered MAX sender -> mocked HTTP boundary.

On a Core whose ``PlatformEntry`` accepts a standalone send policy the plugin declares
``StandaloneSendPolicy(media=True, captionable=True)``, so the public dispatch seam
routes media — including media-only requests — to the registered MAX standalone sender.
Core 0.21.4 has no such kwargs: there the plugin must still register cleanly and media
keeps the old text-only behaviour, which ``media_route_supported`` below distinguishes.
These tests pin both contracts against the real Core router plus the real plugin
registration; no Core router/sender function is replaced by a mock.
"""

import json

import httpx
import pytest
from max.media_caption import transform_max_media_output

import adapter


@pytest.fixture
def registered_max(monkeypatch, tmp_path):
    from gateway import platform_registry as registry_module
    from hermes_cli.plugins import PluginContext, PluginManager, PluginManifest

    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    monkeypatch.setenv("MAX_BOT_TOKEN", "fixture-token")
    registry = registry_module.PlatformRegistry()
    monkeypatch.setattr(registry_module, "platform_registry", registry)
    manager = PluginManager()
    manifest = PluginManifest(name="max-platform", source="user", kind="platform")
    adapter.register(PluginContext(manifest, manager))
    assert registry.get("max").standalone_sender_fn is adapter._standalone_send
    return registry


@pytest.fixture
def media_route_supported():
    """Whether this Core can route media to a plugin sender (False on Core 0.21.4)."""
    return adapter._STANDALONE_POLICY_SUPPORTED


@pytest.fixture
def max_http_boundary(monkeypatch):
    """Only API and CDN transports are intercepted; capture actual payloads."""
    from max.mixins import standalone

    requests = []
    uploads = []
    failure = {}
    real_client = httpx.AsyncClient

    def handle(request):
        requests.append(request)
        if request.url.path == "/uploads":
            if failure.get("upload"):
                return httpx.Response(503, json={"error": "fixture upload failure"})
            # Each upload type has its own CDN; the token issued there only works for a
            # matching attachment type.
            if request.url.params.get("type") == "image":
                return httpx.Response(200, json={"url": "https://iu.oneme.ru/uploadImage"})
            return httpx.Response(200, json={"url": "https://iu.oneme.ru/upload"})
        if request.url.host == "iu.oneme.ru" and request.url.path == "/uploadImage":
            return httpx.Response(200, json={"photos": {"1": {"token": "fixture-photo-token"}}})
        if failure.get("send") and json.loads(request.content).get("attachments"):
            return httpx.Response(400, json={"code": "fixture.rejected"})
        return httpx.Response(200, json={"message": {"body": {"mid": "actual-router-message"}}})

    def client(*args, **kwargs):
        return real_client(*args, **kwargs, transport=httpx.MockTransport(handle))

    class UploadResponse:
        status = 200

        def __init__(self, *, photos: bool = False):
            # The image CDN answers with {"photos": {id: {"token": ...}}}, every other
            # upload type with a flat {"token": ...}. The plugin must read the matching one.
            self._photos = photos

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def json(self):
            if self._photos:
                return {"photos": {"1": {"token": "fixture-photo-token"}}}
            return {"token": "fixture-upload-token"}

        async def text(self):
            return "fixture CDN failure"

    class UploadSession:
        def __init__(self, *, connector, **kwargs):
            self.connector = connector

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            await self.connector.close()
            return False

        def post(self, url, data):
            uploads.append((url, data))
            response = UploadResponse(photos="uploadImage" in str(url))
            if failure.get("cdn"):
                response.status = 503
            return response

    monkeypatch.setattr(standalone.httpx, "AsyncClient", client)
    monkeypatch.setattr("aiohttp.ClientSession", UploadSession)
    monkeypatch.setattr(standalone, "UPLOAD_DELAY", 0)
    return requests, uploads, failure


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["public_dispatch", "adapter_dispatch"])
@pytest.mark.parametrize("mode", ["text", "text_and_file", "media_only"])
async def test_actual_core_dispatch_contract(registered_max, max_http_boundary, tmp_path,
                                            media_route_supported, route, mode):
    from gateway.config import Platform, PlatformConfig
    from tools.send_message_tool import _send_to_platform, _send_via_adapter

    requests, uploads, _failure = max_http_boundary
    media = tmp_path / "router-file.txt"
    media.write_bytes(b"actual router payload")
    text = "Router text" if mode != "media_only" else ""
    media_files = [(str(media), False)] if mode != "text" else []
    pconfig = PlatformConfig(enabled=True, token="fixture-token")
    dispatcher = _send_to_platform if route == "public_dispatch" else _send_via_adapter
    result = await dispatcher(Platform("max"), pconfig, "user:42", text, media_files=media_files)

    # On a Core without the standalone-policy kwargs the public seam still rejects
    # media-only input before transport; the adapter route keeps working there.
    if route == "public_dispatch" and mode == "media_only" and not media_route_supported:
        assert "only media attachments" in result["error"]
        assert not [r for r in requests if r.url.path == "/messages"]
        return

    # With the declared policy the public router reaches the plugin sender for media-only
    # requests too — no Core edit, no output-hook workaround needed.
    assert result["success"] is True
    messages = [json.loads(request.content) for request in requests if request.url.path == "/messages"]
    if media_files:
        assert len(uploads) == 1
        assert uploads[0][0] == "https://iu.oneme.ru/upload"
        assert uploads[0][1]._fields[0][2] == b"actual router payload"
        assert messages[-1]["attachments"] == [{"type": "file", "payload": {"token": "fixture-upload-token"}}]
        assert result["media_delivered"] is True
        assert "warnings" not in result
        # The authored text reaches the user either as the media caption (public router,
        # captionable policy) or as its own message before the attachment (adapter route).
        # With no text at all the sender supplies the basename, because MAX drops
        # attachment-only messages with empty text.
        expected = text or "router-file.txt"
        assert any(m["text"] == expected for m in messages), messages
    else:
        assert not uploads
        assert len(messages) == 1
        assert messages[0]["text"] == text


@pytest.mark.asyncio
async def test_image_upload_type_matches_attachment_type(registered_max, max_http_boundary, tmp_path,
                                                         media_route_supported):
    """Regression: a `type=file` token sent as an image attachment is rejected by MAX.

    MAX answers ``{"code": "proto.payload", "message": "Invalid photo token provided"}``
    when the upload type and the attachment type disagree, so an image must be uploaded
    with ``type=image`` and sent as ``{"type": "image"}``.
    """
    from gateway.config import Platform, PlatformConfig
    from tools.send_message_tool import _send_to_platform

    if not media_route_supported:
        pytest.skip("this Core cannot route media-only requests to a plugin sender")

    requests, uploads, _failure = max_http_boundary
    image = tmp_path / "chart.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n fixture")

    result = await _send_to_platform(
        Platform("max"), PlatformConfig(enabled=True, token="fixture-token"),
        "user:42", "", media_files=[(str(image), False)],
    )

    assert result["success"] is True and result["media_delivered"] is True
    upload_requests = [r for r in requests if r.url.path == "/uploads"]
    assert [r.url.params.get("type") for r in upload_requests] == ["image"]
    assert len(uploads) == 1
    messages = [json.loads(r.content) for r in requests if r.url.path == "/messages"]
    assert messages[-1]["attachments"] == [{"type": "image", "payload": {"token": "fixture-photo-token"}}]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_kind", ["missing", "upload", "cdn", "send", "partial"])
async def test_actual_core_router_reports_incomplete_delivery(registered_max, max_http_boundary, tmp_path,
                                                              media_route_supported, failure_kind):
    from gateway.config import Platform, PlatformConfig
    from tools.send_message_tool import _send_to_platform

    if not media_route_supported:
        pytest.skip("captionable text+media delivery is a standalone-policy contract")

    requests, _uploads, failure = max_http_boundary
    media = tmp_path / "delivery-file.txt"
    media.write_bytes(b"actual router payload")
    missing = str(tmp_path / "missing-file.txt")
    descriptors = [(str(media), False)]
    if failure_kind == "missing":
        descriptors = [(missing, False)]
    elif failure_kind == "partial":
        descriptors.append((missing, False))
    else:
        failure[failure_kind] = True

    result = await _send_to_platform(
        Platform("max"), PlatformConfig(enabled=True, token="fixture-token"),
        "user:42", "Router text", media_files=descriptors,
    )
    assert "error" in result
    assert not result.get("success")
    assert result["media_delivered"] is False
    assert result["media_requested"] == len(descriptors)
    assert result["media_sent"] == (1 if failure_kind == "partial" else 0)
    assert "warnings" not in result

    # One short text plus one file is captionable: the text rides on the attachment, so
    # it is delivered only together with that attachment. Two files are not captionable
    # (the caption/file association would be ambiguous) and the text goes on its own,
    # which is why the partial case still reports the text as delivered.
    if failure_kind == "partial":
        assert result["text_delivered"] is True
        assert result["partial_delivery"] is True
        assert json.loads(requests[0].content)["text"] == "Router text"
    else:
        assert result["text_delivered"] is False
        assert result["partial_delivery"] is False
        if failure_kind != "send":
            # nothing reached the message endpoint (only the upload handshake may have)
            assert not [r for r in requests if r.url.path == "/messages"]


# ── Capability probe: registration must survive a Core without the policy API ──
# Core 0.21.4 ships neither `send_targets.StandaloneSendPolicy` nor a
# `standalone_send` field on `PlatformEntry`. Passing the keyword there raises
# TypeError inside `register()` and takes the whole platform down, so the adapter
# probes both and omits the keyword. CI pins that Core; these tests pin the probe.

def test_probe_is_false_when_entry_lacks_the_field(monkeypatch):
    """A Core with the policy class but an entry that cannot store it must read as unsupported."""
    from dataclasses import dataclass

    from gateway import platform_registry as registry_module

    @dataclass
    class EntryWithoutPolicy:
        name: str = ""
        label: str = ""

    monkeypatch.setattr(registry_module, "PlatformEntry", EntryWithoutPolicy, raising=False)
    assert adapter._core_accepts_standalone_policy() is False


def test_probe_is_false_when_policy_module_is_absent(monkeypatch):
    """Core 0.21.4 has no `gateway.platforms.send_targets` at all."""
    import sys

    monkeypatch.setitem(sys.modules, "gateway.platforms.send_targets", None)
    assert adapter._core_accepts_standalone_policy() is False


def test_reload_without_policy_api_omits_register_keyword(monkeypatch):
    """Reloading the adapter against a policy-less Core leaves the keyword out entirely."""
    import importlib
    import sys

    monkeypatch.setitem(sys.modules, "gateway.platforms.send_targets", None)
    reloaded = importlib.reload(adapter)
    try:
        assert reloaded._STANDALONE_POLICY_SUPPORTED is False
        assert reloaded._PLATFORM_ENTRY_EXTRA == {}
        assert reloaded.StandaloneSendPolicy is None
    finally:
        monkeypatch.undo()
        importlib.reload(adapter)  # restore the real module state for the other tests


@pytest.mark.asyncio
async def test_transformed_media_only_reaches_public_router(registered_max, max_http_boundary, tmp_path):
    from gateway.config import Platform, PlatformConfig
    from gateway.platforms.base import BasePlatformAdapter
    from tools.send_message_tool import _send_to_platform

    media = tmp_path / "report.pdf"
    media.write_bytes(b"fixture")
    transformed = transform_max_media_output(f"MEDIA:{media}", "max")
    files, text = BasePlatformAdapter.extract_media(transformed)
    result = await _send_to_platform(Platform("max"), PlatformConfig(enabled=True, token="fixture-token"),
                                     "user:42", text, media_files=files)
    assert result["success"] and result["media_delivered"]
    requests, uploads, _ = max_http_boundary
    messages = [json.loads(r.content) for r in requests if r.url.path == "/messages"]
    assert messages[0]["text"].strip() == "report.pdf"
    assert messages[-1]["text"] == "report.pdf"
    assert len(uploads) == 1
