"""Synthetic process state + final HTTP boundary only; real main/discovery/policy/CLI."""
import json
import os
from pathlib import Path

if os.environ.get('MAX_COMPLETION_HTTP'):
    import aiohttp
    import httpx
    from gateway.relay import egress
    from gateway.session_context import set_session_vars

    base = os.environ['MAX_COMPLETION_HTTP']
    log = Path(os.environ['MAX_COMPLETION_EVENTS'])
    def record(value):
        with log.open('a') as file:
            file.write(json.dumps(value) + '\n')
    # Synthetic relay provenance data, not an authorization verdict replacement.
    egress.relay_routed_platform = lambda name: name == 'max'
    def targets(name):
        record({'policy_state_read': name})
        return {'-42'}
    egress.attested_relay_targets = targets
    set_session_vars(platform=os.environ.get('MAX_COMPLETION_ORIGIN', 'api'), source='desktop', chat_id='fixture-session', user_id='42')
    real_send = httpx.AsyncClient.send
    async def send(self, request, **kwargs):
        assert request.url.host in {'platform-api.max.ru', 'platform-api2.max.ru', 'botapi.max.ru'}, str(request.url)
        record({'api_boundary': request.method, 'path': request.url.path})
        request.url = httpx.URL(base + str(request.url.raw_path, 'ascii'))
        return await real_send(self, request, **kwargs)
    httpx.AsyncClient.send = send
    real_post = aiohttp.ClientSession.post
    def post(self, url, **kwargs):
        assert str(url) == 'https://upload.max.ru/upload', str(url)
        return real_post(self, base + '/upload', **kwargs)
    aiohttp.ClientSession.post = post
