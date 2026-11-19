"""Real aiohttp multipart bytes through gateway and standalone production paths."""
import hashlib
import resource
import sys
import threading
import tracemalloc
from pathlib import Path
from unittest.mock import AsyncMock

import aiohttp
import pytest
from aiohttp import web
from max.mixins import standalone


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["gateway", "standalone"])
@pytest.mark.parametrize("cdn_status", [200, 503])
async def test_upload_streams_without_read_bytes(mode, cdn_status, tmp_path, monkeypatch, make_adapter, max_api, max_config):
    from max.mixins import upload_stream
    reads = []
    main_thread = threading.get_ident()
    real_open = open
    class TrackedFile:
        def __init__(self, value):
            self.value = value
        def read(self, n=-1):
            reads.append((n, threading.get_ident()))
            return self.value.read(n)
        def fileno(self):
            return self.value.fileno()
        def close(self):
            return self.value.close()
    monkeypatch.setattr(upload_stream, "open", lambda *a: TrackedFile(real_open(*a)), raising=False)
    path = tmp_path / "large.pdf"
    # Finite sparse file above the old global 50 MiB ceiling.
    with path.open("wb") as f:
        f.truncate(51 * 1024 * 1024)
    received = 0
    digest = hashlib.sha256()
    async def receive(request):
        nonlocal received
        reader = await request.multipart()
        part = await reader.next()
        assert part.name == "data" and part.filename == path.name
        while chunk := await part.read_chunk(65536):
            received += len(chunk)
            digest.update(chunk)
        return web.json_response({"token": "fixture-token"}, status=cdn_status)
    app = web.Application()
    app.router.add_post("/upload", receive)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    real_post = aiohttp.ClientSession.post
    def local_post(self, url, **kwargs):
        assert str(url) == "https://upload.max.ru/upload"
        return real_post(self, f"http://127.0.0.1:{port}/upload", **kwargs)
    monkeypatch.setattr(aiohttp.ClientSession, "post", local_post)
    def forbidden(*args, **kwargs):
        raise AssertionError("whole-file buffering is forbidden")
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    max_api.route("POST", "/uploads", json_body={"url": "https://upload.max.ru/upload"})
    monkeypatch.setattr(standalone, "_standalone_get_token", lambda _: "fixture")
    monkeypatch.setattr(standalone.httpx, "AsyncClient", lambda **kw: max_api.client())
    monkeypatch.setattr(standalone, "UPLOAD_DELAY", 0)
    try:
        rss_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        tracemalloc.start()
        if mode == "gateway":
            a = make_adapter()
            a.send_action = AsyncMock()
            result = await a.send_document("-42", str(path))
            assert result.success == (cdn_status == 200), result.error
            await a._http_client.aclose()
        else:
            result = await standalone._standalone_send(max_config, "-42", "", media_files=[(str(path), False)])
            assert bool(result.get("success")) == (cdn_status == 200), result
        assert received == path.stat().st_size
        expected_digest = hashlib.sha256()
        for _ in range(received // 65536):
            expected_digest.update(bytes(65536))
        expected_digest.update(bytes(received % 65536))
        assert digest.digest() == expected_digest.digest()
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        rss_after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        rss_growth = (rss_after - rss_before) * (1 if sys.platform == "darwin" else 1024)
        print(f"{mode}: transmitted={received} peak_python_bytes={peak} rss_highwater_growth={rss_growth} reads={len(reads)} max_read={max(n for n, _ in reads)}")
        assert peak < 16 * 1024 * 1024
        assert rss_growth < 24 * 1024 * 1024
        assert reads and all(0 < n <= 65536 and thread != main_thread for n, thread in reads)
        if cdn_status == 200:
            assert max_api.params(max_api.calls("POST", "/messages")[0]) == {"chat_id": "-42"}
        else:
            assert not max_api.calls("POST", "/messages")
    finally:
        tracemalloc.stop()
        await runner.cleanup()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,limit", [("image", 50_000_000), ("video", 250_000_000), ("audio", 256_000_000), ("file", 4_000_000_000)])
async def test_per_type_size_rejected_before_api(kind, limit, tmp_path, make_adapter, max_api):
    p = tmp_path / "oversize.bin"
    with p.open("wb") as f:
        f.truncate(limit + 1)
    a = make_adapter()
    assert await a._upload(str(p), kind) is None
    assert not max_api.calls("POST", "/uploads")
    await a._http_client.aclose()
