"""F4 rollback: constructor/start faults and fast-start ownership races."""
import asyncio
import threading

import pytest
from max.mixins import upload_stream as stream


@pytest.mark.asyncio
@pytest.mark.parametrize('path', ['admission', 'file'])
@pytest.mark.parametrize('fault', ['constructor', 'start'])
async def test_launch_failure_returns_all_capacity(path, fault, monkeypatch, tmp_path):
    semaphore = threading.BoundedSemaphore(4)
    monkeypatch.setattr(stream, '_IO_SLOTS', semaphore)
    source = tmp_path / 'fixture.bin'
    source.write_bytes(b'x')
    admitted = stream.check_upload(str(source), 'file')
    real_thread = threading.Thread
    class BrokenThread:
        def __init__(self, *args, **kwargs):
            if fault == 'constructor':
                raise RuntimeError('synthetic thread resource failure')
        def start(self):
            raise RuntimeError('synthetic thread resource failure')
    monkeypatch.setattr(stream.threading, 'Thread', BrokenThread)
    with pytest.raises(OSError):
        if path == 'admission':
            await stream.async_check_upload(str(source), 'file')
        else:
            stream._FileWorker(str(source), admitted)
    acquired = [semaphore.acquire(blocking=False) for _ in range(4)]
    assert all(acquired)
    for value in acquired:
        if value:
            semaphore.release()
    monkeypatch.setattr(stream.threading, 'Thread', real_thread)
    assert await stream.async_check_upload(str(source), 'file') == 1


@pytest.mark.asyncio
async def test_fast_worker_then_start_raises_does_not_double_release(monkeypatch, tmp_path):
    semaphore = threading.BoundedSemaphore(4)
    monkeypatch.setattr(stream, '_IO_SLOTS', semaphore)
    source = tmp_path / 'fixture.bin'
    source.write_bytes(b'x')
    class FastThread:
        def __init__(self, *, target, **kwargs):
            self.target = target
        def start(self):
            self.target()
            raise RuntimeError('synthetic failure after worker finished')
    monkeypatch.setattr(stream.threading, 'Thread', FastThread)
    with pytest.raises(OSError):
        await stream.async_check_upload(str(source), 'file')
    assert all(semaphore.acquire(blocking=False) for _ in range(4))
    assert not semaphore.acquire(blocking=False)
    for _ in range(4):
        semaphore.release()


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['gateway', 'standalone'])
@pytest.mark.parametrize('stage', ['admission', 'file'])
@pytest.mark.parametrize('fault', ['constructor', 'start'])
async def test_public_send_returns_failed_result_on_thread_fault(mode, stage, fault, monkeypatch, tmp_path, make_adapter, max_api, max_config):
    from unittest.mock import AsyncMock

    import aiohttp
    from aiohttp import web
    from max.mixins import standalone
    slots = threading.BoundedSemaphore(4)
    monkeypatch.setattr(stream, '_IO_SLOTS', slots)
    real_thread = threading.Thread
    def thread(*args, **kwargs):
        if kwargs.get('name') == f'max-upload-{stage}' and fault == 'constructor':
            raise RuntimeError('synthetic launch fault')
        value = real_thread(*args, **kwargs)
        if kwargs.get('name') == f'max-upload-{stage}' and fault == 'start':
            def fail():
                raise RuntimeError('synthetic launch fault')
            value.start = fail
        return value
    monkeypatch.setattr(stream.threading, 'Thread', thread)
    path = tmp_path / 'finite.bin'
    path.write_bytes(b'x' * 1024)
    async def receive(request):
        try:
            await request.read()
        except ConnectionResetError:
            pass
        return web.json_response({'token': 'fixture-token'})
    app = web.Application()
    app.router.add_post('/upload', receive)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    real_post = aiohttp.ClientSession.post
    monkeypatch.setattr(aiohttp.ClientSession, 'post', lambda self, url, **kw: real_post(self, f'http://127.0.0.1:{port}/upload', **kw))
    max_api.route('POST', '/uploads', json_body={'url': 'https://upload.max.ru/upload'})
    monkeypatch.setattr(standalone, '_standalone_get_token', lambda _: 'fixture')
    monkeypatch.setattr(standalone.httpx, 'AsyncClient', lambda **kw: max_api.client())
    try:
        if mode == 'gateway':
            adapter = make_adapter()
            adapter.send_action = AsyncMock()
            result = await adapter.send_document('-42', str(path))
            assert not result.success and result.error
            await adapter._http_client.aclose()
        else:
            result = await standalone._standalone_send(max_config, '-42', '', media_files=[(str(path), False)])
            assert not result.get('success') and result.get('error')
        await asyncio.sleep(.02)
        assert all(slots.acquire(blocking=False) for _ in range(4))
        assert not slots.acquire(blocking=False)
        for _ in range(4):
            slots.release()
        assert not max_api.calls('POST', '/messages')
    finally:
        await runner.cleanup()
