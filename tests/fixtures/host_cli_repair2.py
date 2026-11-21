"""Isolated synthetic host CLI harness. Core parser/cmd_send/auth/send engine are real."""
import importlib.util
import json
import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

# A test process is already provisioned by run-python: do not run install/bootstrap hooks.
sys.modules['hermes_bootstrap'] = ModuleType('hermes_bootstrap')

import httpx

root = Path(os.environ['MAX_PROBE_SOURCE'])
spec = importlib.util.spec_from_file_location('max_host_probe', root / '__init__.py', submodule_search_locations=[str(root)])
plugin = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = plugin
spec.loader.exec_module(plugin)
from hermes_cli.plugins import PluginContext, PluginManager, PluginManifest

plugin.register(PluginContext(PluginManifest(name='max-platform', kind='platform', source='user'), PluginManager()))
import gateway.config
from gateway.config import Platform, PlatformConfig

pconfig = PlatformConfig(enabled=True, token='synthetic-fixture-not-a-live-credential')
gateway.config.load_gateway_config = lambda: SimpleNamespace(platforms={Platform('max'): pconfig}, get_home_channel=lambda _: None)
# Synthetic policy STATE, not a mocked authorization verdict. Real authorize_relay_target runs.
from gateway.relay import egress

log = Path(os.environ['MAX_PROBE_LOG'])
def record(data):
    with log.open('a') as file:
        file.write(json.dumps(data) + '\n')
egress.relay_routed_platform = lambda name: name == 'max'
def provenance(name):
    record({'policy_snapshot': name})
    return {'-42'}
egress.attested_relay_targets = provenance
from gateway.session_context import set_session_vars

set_session_vars(platform=os.environ.get('MAX_PROBE_ORIGIN', 'api'), source='desktop', chat_id='synthetic-desktop-session', user_id='42')
real_client = httpx.AsyncClient
def api(request):
    record({'http': request.method, 'path': request.url.path, 'query': dict(request.url.params), 'body': json.loads(request.content) if request.content else None})
    if request.url.path == '/uploads':
        return httpx.Response(200, json={'url': 'https://upload.max.ru/upload', 'token': 'fixture-token'})
    if request.url.path == '/messages':
        return httpx.Response(200, json={'message': {'body': {'mid': 'fixture-mid'}}})
    return httpx.Response(403, json={'code': 'fixture.denied'})
httpx.AsyncClient = lambda **kwargs: real_client(**{k: v for k, v in kwargs.items() if k != 'transport'}, transport=httpx.MockTransport(api))
os.environ['MAX_BOT_TOKEN'] = 'synthetic-fixture-not-a-live-credential'
if os.environ.get('MAX_PROBE_CDN'):
    import aiohttp
    real_post = aiohttp.ClientSession.post
    def local_post(self, url, **kwargs):
        assert url == 'https://upload.max.ru/upload'
        return real_post(self, os.environ['MAX_PROBE_CDN'], **kwargs)
    aiohttp.ClientSession.post = local_post
# Real stock host CLI entrypoint, not mockdispatch or copied send logic.
from hermes_cli.main import main

main()
