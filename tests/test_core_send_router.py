"""Actual Core send router -> registered MAX sender -> mocked HTTP boundary.

The public dispatch seam currently rejects MAX media-only requests. The lower
adapter dispatcher can deliver them; keep both facts visible until Core enables
the generic media route. No Core router/sender function is replaced by a mock.
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
            return httpx.Response(200, json={"url": "https://iu.oneme.ru/upload"})
        if failure.get("send") and json.loads(request.content).get("attachments"):
            return httpx.Response(400, json={"code": "fixture.rejected"})
        return httpx.Response(200, json={"message": {"body": {"mid": "actual-router-message"}}})

    def client(*args, **kwargs):
        return real_client(*args, **kwargs, transport=httpx.MockTransport(handle))

    class UploadResponse:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def json(self):
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
            response = UploadResponse()
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
async def test_actual_core_dispatch_contract(registered_max, max_http_boundary, tmp_path, route, mode):
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

    if route == "public_dispatch" and mode == "media_only":
        assert "only media attachments" in result["error"]
        assert not requests and not uploads
        return

    assert result["success"] is True
    messages = [json.loads(request.content) for request in requests if request.url.path == "/messages"]
    if text:
        assert messages[0]["text"] == text
    if media_files:
        assert len(uploads) == 1
        assert uploads[0][0] == "https://iu.oneme.ru/upload"
        assert uploads[0][1]._fields[0][2] == b"actual router payload"
        assert messages[-1]["attachments"] == [{"type": "file", "payload": {"token": "fixture-upload-token"}}]
        assert result["media_delivered"] is True
        assert "warnings" not in result
    else:
        assert not uploads
        assert len(messages) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_kind", ["missing", "upload", "cdn", "send", "partial"])
async def test_actual_core_router_reports_incomplete_delivery(registered_max, max_http_boundary, tmp_path, failure_kind):
    from gateway.config import Platform, PlatformConfig
    from tools.send_message_tool import _send_to_platform

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
    assert result["text_delivered"] is True
    assert result["partial_delivery"] is True
    assert result["media_sent"] == (1 if failure_kind == "partial" else 0)
    assert result["media_requested"] == len(descriptors)
    assert "warnings" not in result
    assert json.loads(requests[0].content)["text"] == "Router text"


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
