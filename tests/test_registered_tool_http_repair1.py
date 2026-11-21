"""Repair1 integration evidence: real registry/task context -> typed upload -> local aiohttp."""
import asyncio
import hashlib
import importlib
import json

import aiohttp
import pytest
from aiohttp import web

import adapter


@pytest.mark.asyncio
@pytest.mark.parametrize('kind,suffix', [('image', '.png'), ('video', '.mp4'), ('audio', '.mp3'), ('file', '.pdf')])
async def test_registered_tool_streams_pinned_file(kind, suffix, monkeypatch, tmp_path, max_api):
    from gateway.session_context import reset_session_vars, set_session_vars
    from hermes_cli.plugins import PluginContext, PluginManager, PluginManifest
    from tools.registry import registry
    tool = importlib.import_module(f'{adapter.__package__}.attachment_tool')
    payload = bytes(range(256)) * 4096
    path = tmp_path / ('synthetic' + suffix)
    path.write_bytes(payload)
    digest = hashlib.sha256()
    received = 0
    async def receive(request):
        nonlocal received
        part = await (await request.multipart()).next()
        while chunk := await part.read_chunk(65536):
            received += len(chunk)
            digest.update(chunk)
        return web.json_response({'token': 'fixture-token'})
    app = web.Application()
    app.router.add_post('/upload', receive)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    real_post = aiohttp.ClientSession.post
    def local_post(self, url, **kwargs):
        assert url == 'https://upload.max.ru/upload'
        return real_post(self, f'http://127.0.0.1:{port}/upload', **kwargs)
    monkeypatch.setattr(aiohttp.ClientSession, 'post', local_post)
    monkeypatch.setattr(tool, 'get_max_secret', lambda *args: 'fixture')
    monkeypatch.setattr(tool.httpx, 'AsyncClient', lambda **kwargs: max_api.client())
    max_api.route('POST', '/uploads', json_body={'url': 'https://upload.max.ru/upload', 'token': 'fixture-token'})
    adapter.register(PluginContext(PluginManifest(name='max-platform', source='user', kind='platform'), PluginManager()))
    set_session_vars(platform='max', source='gateway', chat_id='user:42', user_id='42')
    try:
        result = await asyncio.to_thread(registry.dispatch, 'max_send_attachments', {'attachments': [{'type': kind, 'path': str(path)}], 'text': 'Synthetic fixture'})
        result = json.loads(result) if isinstance(result, str) else result
        assert result.get('success'), result
        assert received == len(payload)
        assert digest.digest() == hashlib.sha256(payload).digest()
        message = max_api.calls('POST', '/messages')[0]
        assert max_api.params(message) == {'user_id': '42'}
        assert max_api.json_body(message)['attachments'] == [{'type': kind, 'payload': {'token': 'fixture-token'}}]
        print(f'tool {kind}: bytes={received} sha256={digest.hexdigest()}')
    finally:
        reset_session_vars()
        await runner.cleanup()
