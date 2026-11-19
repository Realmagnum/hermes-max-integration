"""Real current Core host media router; never substitute absent policy with skips."""

import pytest
from gateway.config import Platform, PlatformConfig

import adapter


@pytest.mark.asyncio
@pytest.mark.parametrize('suffix', ['.pdf', '.mp3'])
async def test_policy_capable_core_routes_standalone_media(max_api, monkeypatch, tmp_path, suffix):
    # This test is explicitly run on current Core, not the legacy ca13 export.
    import aiohttp
    from gateway import platform_registry as registry_module
    from gateway.outbound.send import _send_to_platform
    from hermes_cli.plugins import PluginContext, PluginManager, PluginManifest
    from max.mixins import standalone
    assert adapter._STANDALONE_POLICY_SUPPORTED, 'required StandaloneSendPolicy absent'
    registry = registry_module.PlatformRegistry()
    monkeypatch.setattr(registry_module, 'platform_registry', registry)
    adapter.register(PluginContext(PluginManifest(name='max-platform', source='user', kind='platform'), PluginManager()))
    monkeypatch.setattr(standalone, '_standalone_get_token', lambda _: 'fixture')
    monkeypatch.setattr(standalone.httpx, 'AsyncClient', lambda **kw: max_api.client())
    monkeypatch.setattr(standalone, 'UPLOAD_DELAY', 0)
    # Real aiohttp boundary is covered by the companion controlled HTTP tests;
    # only CDN response I/O is replaced here, leaving Core routing unmodified.
    max_api.route('POST', '/uploads', json_body={'url': 'https://upload.max.ru/upload', 'token': 'fixture-token'})
    class Response:
        status = 200
        def __init__(self):
            self.content = self
            self.done = False
        async def read(self, n):
            if self.done:
                return b''
            self.done = True
            return b'{"token":"fixture-token"}'
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
    class Session:
        def __init__(self, connector, **kwargs):
            self.connector = connector
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            await self.connector.close()
        def post(self, url, **kwargs):
            return Response()
    monkeypatch.setattr(aiohttp, 'ClientSession', Session)
    media = tmp_path / ('fixture' + suffix)
    media.write_bytes(b'ID3-fixture')
    result = await _send_to_platform(Platform('max'), PlatformConfig(enabled=True, token='fixture'), '-42', '', media_files=[(str(media), False)])
    assert result['success'] and result['media_delivered']
    message = max_api.calls('POST', '/messages')[0]
    assert max_api.params(message) == {'chat_id': '-42'}
    assert max_api.json_body(message)['attachments'][0]['type'] == ('audio' if suffix == '.mp3' else 'file')
