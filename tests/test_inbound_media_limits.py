"""SEC-07: inbound media limits.

The adapter fetches MAX attachments itself, so it must bound what one update
can cost: bytes per body, bytes and count per message, wall-clock per download
and downloads in flight. These tests drive the streaming downloader with a
fake httpx stream (no sockets) and assert both the refusals and the cleanup.
"""

import asyncio
import contextlib
import socket

import httpx
import pytest

import adapter

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
OGG_BYTES = b"OggS" + b"\x00" * 64
PDF_BYTES = b"%PDF-1.7\n" + b"\x00" * 64


@pytest.fixture(autouse=True)
def _mock_dns_for_limits(monkeypatch):
    """Mock DNS so streaming tests don't fail when resolving cdn.max.ru offline."""
    def fake_getaddrinfo(host, port, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port, 0, 0))]

    monkeypatch.setattr(adapter.socket, "getaddrinfo", fake_getaddrinfo)


class _Failure(Exception):
    """Transport-level failure raised from inside a streamed body."""


class _Stream:
    """Streaming-response stand-in: yields *chunks* and counts what was read."""

    def __init__(self, chunks, *, headers=None, status_code=200, delay=0.0):
        self._chunks = list(chunks)
        self.headers = headers if headers is not None else {}
        self.status_code = status_code
        self.delay = delay
        self.chunks_yielded = 0

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://cdn.max.ru/x")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError(f"status {self.status_code}", request=request, response=response)

    async def aiter_bytes(self, chunk_size=None):
        for chunk in self._chunks:
            if self.delay:
                await asyncio.sleep(self.delay)
            self.chunks_yielded += 1
            yield chunk


class _EndlessStream(_Stream):
    """Response that never finishes — a slow/infinite sender."""

    def __init__(self, **kwargs):
        super().__init__([], **kwargs)

    async def aiter_bytes(self, chunk_size=None):
        while True:
            await asyncio.sleep(0.005)
            self.chunks_yielded += 1
            yield b"a" * 64


class _BrokenStream(_Stream):
    """Response whose body raises part-way through — a dropped connection."""

    def __init__(self, chunks, *, fail_after, **kwargs):
        super().__init__(chunks, **kwargs)
        self._fail_after = fail_after

    async def aiter_bytes(self, chunk_size=None):
        for index, chunk in enumerate(self._chunks):
            if index >= self._fail_after:
                raise _Failure("connection reset mid-body")
            self.chunks_yielded += 1
            yield chunk


class FakeClient:
    """Minimal ``httpx.AsyncClient`` stand-in exposing only ``stream()``."""

    def __init__(self, streams):
        self._streams = list(streams)
        self.requests = []
        self.active = 0
        self.max_active = 0

    @contextlib.asynccontextmanager
    async def _stream_ctx(self, response):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            yield response
        finally:
            self.active -= 1

    def stream(self, method, url, **kwargs):
        self.requests.append((method, url, kwargs))
        response = self._streams.pop(0) if self._streams else _Stream([b"x"])
        return self._stream_ctx(response)


@pytest.fixture
def cache_dirs(tmp_path, monkeypatch):
    """Point the core media caches at throwaway directories."""
    from gateway.platforms import base

    dirs = {}
    for prefix, constant in (
        ("image", "IMAGE_CACHE_DIR"),
        ("audio", "AUDIO_CACHE_DIR"),
        ("document", "DOCUMENT_CACHE_DIR"),
    ):
        directory = tmp_path / prefix
        directory.mkdir()
        monkeypatch.setattr(base, constant, directory, raising=False)
        dirs[prefix] = directory
    return dirs


@pytest.fixture
def make_adapter(cache_dirs):
    """Factory for adapters wired to a fake client and temp caches."""
    from gateway.config import PlatformConfig

    def _make(*streams, **attrs):
        cfg = PlatformConfig(enabled=True, token="test-token", extra={})
        instance = adapter.MaxAdapter(cfg)
        instance._connected = True
        instance._http_client = FakeClient(streams)
        for name, value in attrs.items():
            setattr(instance, name, value)
        return instance

    return _make


def _image_attachment(url, name="pic.png"):
    return {"type": "image", "payload": {"url": url, "filename": name}}


def _update(*attachments):
    return {"message": {"body": {"attachments": list(attachments)}}}


def _cache_files(*dirs):
    return [path for directory in dirs for path in directory.iterdir()]


class TestStreamingCaps:
    async def test_body_without_content_length_is_cached(self, make_adapter, cache_dirs):
        stream = _Stream([PNG_BYTES], headers={"content-type": "image/png"})
        a = make_adapter(stream)

        cached = await a._cache_image_attachment(_image_attachment("https://cdn.max.ru/a.png"))

        assert cached is not None
        path, content_type = cached
        assert content_type == "image/png"
        assert path.startswith(str(cache_dirs["image"]))
        assert stream.chunks_yielded == 1

    async def test_oversized_content_length_is_refused_before_reading(self, make_adapter, cache_dirs):
        stream = _Stream(
            [b"x" * 4096],
            headers={"content-type": "image/png", "content-length": str(10 * 1024 * 1024)},
        )
        a = make_adapter(stream, _inbound_attachment_max_bytes=1024)

        assert await a._cache_image_attachment(_image_attachment("https://cdn.max.ru/big.png")) is None
        assert stream.chunks_yielded == 0, "the declared size must refuse the body before it is read"
        assert _cache_files(cache_dirs["image"]) == []

    async def test_lying_content_length_is_caught_by_the_running_total(self, make_adapter, cache_dirs):
        chunks = [b"x" * 512] * 10
        stream = _Stream(chunks, headers={"content-type": "image/png", "content-length": "10"})
        a = make_adapter(stream, _inbound_attachment_max_bytes=1024)

        assert await a._cache_image_attachment(_image_attachment("https://cdn.max.ru/lie.png")) is None
        assert stream.chunks_yielded < len(chunks), "reading must stop once the actual byte cap is passed"
        assert _cache_files(cache_dirs["image"]) == []

    async def test_invalid_content_length_is_ignored(self, make_adapter):
        stream = _Stream([OGG_BYTES], headers={"content-type": "audio/ogg", "content-length": "not-a-number"})
        a = make_adapter(stream)

        cached = await a._cache_audio_attachment({"type": "voice", "payload": {"url": "https://cdn.max.ru/v.ogg"}}, "voice")

        assert cached is not None and cached[1] == "audio/ogg"

    async def test_slow_infinite_response_hits_the_deadline(self, make_adapter, cache_dirs):
        stream = _EndlessStream(headers={"content-type": "image/png"})
        a = make_adapter(stream, _inbound_media_timeout=0.05)

        assert await a._cache_image_attachment(_image_attachment("https://cdn.max.ru/never.png")) is None
        assert _cache_files(cache_dirs["image"]) == []

    async def test_transport_failure_returns_none_without_files(self, make_adapter, cache_dirs):
        stream = _BrokenStream(
            [PNG_BYTES[:8], b"x" * 32], headers={"content-type": "image/png"}, fail_after=1
        )
        a = make_adapter(stream)

        assert await a._cache_image_attachment(_image_attachment("https://cdn.max.ru/broken.png")) is None
        assert _cache_files(cache_dirs["image"]) == []

    async def test_error_status_is_refused(self, make_adapter):
        stream = _Stream([b"denied"], headers={"content-type": "text/plain"}, status_code=500)
        a = make_adapter(stream)

        assert await a._cache_document_attachment(
            {"type": "file", "payload": {"url": "https://cdn.max.ru/d.pdf", "filename": "d.pdf"}}
        ) is None

    async def test_blocked_host_never_reaches_the_client(self, make_adapter):
        a = make_adapter()

        assert await a._cache_image_attachment(_image_attachment("http://127.0.0.1/secret.png")) is None
        assert a._http_client.requests == []


class TestMessageBudget:
    async def test_attachment_count_is_capped(self, make_adapter):
        streams = [_Stream([PNG_BYTES], headers={"content-type": "image/png"}) for _ in range(5)]
        a = make_adapter(*streams, _inbound_media_max_attachments=2)
        update = _update(*[_image_attachment(f"https://cdn.max.ru/{i}.png") for i in range(5)])

        paths, _types = await a._extract_inbound_media(update, {}, {})

        assert len(paths) == 2
        assert len(a._http_client.requests) == 2

    async def test_aggregate_bytes_cap_stops_later_attachments(self, make_adapter, cache_dirs):
        body = PNG_BYTES + b"y" * 800
        streams = [_Stream([body], headers={"content-type": "image/png"}) for _ in range(3)]
        a = make_adapter(
            *streams,
            _inbound_attachment_max_bytes=4096,
            _inbound_media_total_max_bytes=len(body) + 10,
            _inbound_media_max_attachments=10,
        )
        update = _update(*[_image_attachment(f"https://cdn.max.ru/{i}.png") for i in range(3)])

        paths, _types = await a._extract_inbound_media(update, {}, {})

        assert len(paths) == 1, "the aggregate cap must stop the message's remaining attachments"
        assert len(_cache_files(cache_dirs["image"])) == 1

    async def test_duplicate_url_is_downloaded_once(self, make_adapter):
        stream = _Stream([PNG_BYTES], headers={"content-type": "image/png"})
        a = make_adapter(stream)
        update = _update(_image_attachment("https://cdn.max.ru/same.png"), _image_attachment("https://cdn.max.ru/same.png"))

        paths, _types = await a._extract_inbound_media(update, {}, {})

        assert len(paths) == 1
        assert len(a._http_client.requests) == 1

    async def test_budget_refunds_bytes_of_a_failed_download(self, make_adapter):
        stream = _BrokenStream(
            [b"x" * 128, b"x" * 128, b"x" * 128],
            headers={"content-type": "image/png"},
            fail_after=1,
        )
        a = make_adapter(stream, _inbound_attachment_max_bytes=4096)
        budget = adapter._InboundMediaBudget(max_attachments=5, max_bytes=1024)

        result = await a._download_inbound_media(
            "https://cdn.max.ru/abort.png", media_type="image", budget=budget
        )

        assert result is None
        assert budget._remaining == 1024, "an aborted download must not spend the message budget"


class TestConcurrency:
    async def test_concurrency_cap_is_enforced(self, make_adapter):
        streams = [
            _Stream([PNG_BYTES], headers={"content-type": "image/png"}, delay=0.02) for _ in range(4)
        ]
        a = make_adapter(*streams, _inbound_media_concurrency=2)
        update = _update(*[_image_attachment(f"https://cdn.max.ru/{i}.png") for i in range(4)])

        paths, _types = await a._extract_inbound_media(update, {}, {})

        assert len(paths) == 4
        assert a._http_client.max_active <= 2

    async def test_single_slot_serialises_downloads(self, make_adapter):
        streams = [
            _Stream([PNG_BYTES], headers={"content-type": "image/png"}, delay=0.01) for _ in range(3)
        ]
        a = make_adapter(*streams, _inbound_media_concurrency=1)
        update = _update(*[_image_attachment(f"https://cdn.max.ru/{i}.png") for i in range(3)])

        await a._extract_inbound_media(update, {}, {})

        assert a._http_client.max_active == 1


class TestPartialFileCleanup:
    async def test_failed_cache_write_removes_the_partial_file(
        self, make_adapter, cache_dirs, monkeypatch
    ):
        def exploding_writer(data, ext):
            (cache_dirs["image"] / "img_partial.png").write_bytes(data[:4])
            raise OSError(28, "No space left on device")

        monkeypatch.setattr(adapter, "cache_image_from_bytes", exploding_writer)
        stream = _Stream([PNG_BYTES], headers={"content-type": "image/png"})
        a = make_adapter(stream)

        result = await a._cache_image_attachment(_image_attachment("https://cdn.max.ru/diskfull.png"))

        assert result is None
        assert _cache_files(cache_dirs["image"]) == [], "a partial file must not survive a failed write"

    async def test_failed_cache_write_keeps_unrelated_files(
        self, make_adapter, cache_dirs, monkeypatch
    ):
        sentinel = cache_dirs["image"] / "img_existing.png"
        sentinel.write_bytes(PNG_BYTES)

        def exploding_writer(data, ext):
            (cache_dirs["image"] / "img_partial.png").write_bytes(data[:4])
            raise OSError(28, "No space left on device")

        monkeypatch.setattr(adapter, "cache_image_from_bytes", exploding_writer)
        stream = _Stream([PNG_BYTES], headers={"content-type": "image/png"})
        a = make_adapter(stream)

        assert await a._cache_image_attachment(_image_attachment("https://cdn.max.ru/x.png")) is None
        assert sorted(p.name for p in _cache_files(cache_dirs["image"])) == ["img_existing.png"]

    async def test_non_image_bytes_are_rejected_without_leaving_files(
        self, make_adapter, cache_dirs
    ):
        stream = _Stream([b"<html>not an image</html>"], headers={"content-type": "image/png"})
        a = make_adapter(stream)

        assert await a._cache_image_attachment(_image_attachment("https://cdn.max.ru/page.png")) is None
        assert _cache_files(cache_dirs["image"]) == []

    async def test_full_disk_is_refused_before_writing(self, make_adapter, cache_dirs, monkeypatch):
        monkeypatch.setattr(adapter.shutil, "disk_usage", lambda _path: _DiskUsage(0, 0, 0))
        stream = _Stream([PNG_BYTES], headers={"content-type": "image/png"})
        a = make_adapter(stream)

        result = await a._cache_image_attachment(_image_attachment("https://cdn.max.ru/nospace.png"))

        assert result is None
        assert _cache_files(cache_dirs["image"]) == []


class _DiskUsage:
    """``shutil.disk_usage`` result stand-in."""

    def __init__(self, total, used, free):
        self.total = total
        self.used = used
        self.free = free


class TestHappyPaths:
    async def test_document_is_cached_under_its_filename(self, make_adapter, cache_dirs):
        stream = _Stream([PDF_BYTES], headers={"content-type": "application/pdf"})
        a = make_adapter(stream)
        attachment = {"type": "file", "payload": {"url": "https://cdn.max.ru/report.pdf", "filename": "report.pdf"}}

        cached = await a._cache_document_attachment(attachment)

        assert cached is not None
        path, content_type = cached
        assert content_type == "application/pdf"
        assert path.endswith("report.pdf")
        assert path.startswith(str(cache_dirs["document"]))

    async def test_all_media_of_a_message_is_returned_in_order(self, make_adapter):
        streams = [
            _Stream([OGG_BYTES], headers={"content-type": "audio/ogg"}),
            _Stream([PNG_BYTES], headers={"content-type": "image/png"}),
            _Stream([PDF_BYTES], headers={"content-type": "application/pdf"}),
        ]
        # This test verifies returned-media order. Keep the fake client's FIFO
        # streams deterministic; concurrency is covered by TestConcurrency.
        a = make_adapter(*streams, _inbound_media_concurrency=1)
        update = _update(
            {"type": "voice", "payload": {"url": "https://cdn.max.ru/v.ogg"}},
            _image_attachment("https://cdn.max.ru/i.png"),
            {"type": "file", "payload": {"url": "https://cdn.max.ru/d.pdf", "filename": "d.pdf"}},
        )

        paths, types = await a._extract_inbound_media(update, {}, {})

        assert len(paths) == 3
        assert types == ["audio/ogg", "image/png", "application/pdf"]


class TestConfiguration:
    def test_env_overrides_the_defaults(self, monkeypatch):
        from gateway.config import PlatformConfig

        monkeypatch.setenv("MAX_INBOUND_MEDIA_MAX_BYTES", "2048")
        monkeypatch.setenv("MAX_INBOUND_MEDIA_TOTAL_BYTES", "4096")
        monkeypatch.setenv("MAX_INBOUND_MEDIA_MAX_ATTACHMENTS", "3")
        monkeypatch.setenv("MAX_INBOUND_MEDIA_TIMEOUT", "12.5")
        monkeypatch.setenv("MAX_INBOUND_MEDIA_CONCURRENCY", "2")
        cfg = PlatformConfig(enabled=True, token="test-token", extra={})

        a = adapter.MaxAdapter(cfg)

        assert a._inbound_attachment_max_bytes == 2048
        assert a._inbound_media_total_max_bytes == 4096
        assert a._inbound_media_max_attachments == 3
        assert a._inbound_media_timeout == 12.5
        assert a._inbound_media_concurrency == 2

    def test_unusable_values_fall_back_to_defaults(self, monkeypatch):
        from gateway.config import PlatformConfig

        monkeypatch.setenv("MAX_INBOUND_MEDIA_MAX_BYTES", "not-a-number")
        monkeypatch.setenv("MAX_INBOUND_MEDIA_TIMEOUT", "-5")
        monkeypatch.setenv("MAX_INBOUND_MEDIA_CONCURRENCY", "0")
        cfg = PlatformConfig(enabled=True, token="test-token", extra={})

        a = adapter.MaxAdapter(cfg)

        assert a._inbound_attachment_max_bytes == adapter.DEFAULT_INBOUND_ATTACHMENT_MAX_BYTES
        assert a._inbound_media_timeout == adapter.DEFAULT_INBOUND_DOWNLOAD_TIMEOUT
        assert a._inbound_media_concurrency == adapter.DEFAULT_INBOUND_DOWNLOAD_CONCURRENCY

    def test_core_cap_bounds_the_plugin_cap(self, monkeypatch):
        from gateway.config import PlatformConfig
        from gateway.platforms import base

        monkeypatch.setattr(base, "get_inbound_media_max_bytes", lambda: 4096, raising=False)
        cfg = PlatformConfig(enabled=True, token="test-token", extra={})

        a = adapter.MaxAdapter(cfg)

        assert a._inbound_attachment_max_bytes == 4096
