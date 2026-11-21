"""Explicit host CLI registration and envelope protocol, not model outbound."""
import argparse
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import adapter


def test_public_cli_bridge_is_registered():
    commands = {}
    ctx = SimpleNamespace(register_platform=lambda **kw: None, register_tool=lambda **kw: None,
                          register_hook=lambda *a, **kw: None, register_skill=lambda *a, **kw: None,
                          register_cli_command=lambda **kw: commands.update({kw['name']: kw}))
    adapter.register(ctx)
    assert 'max' in commands


def bridge_module():
    return importlib.import_module(f'{adapter.__package__}.host_bridge')


def harness_env(tmp_path, monkeypatch):
    home = tmp_path / 'isolated-home'
    home.mkdir()
    log = tmp_path / 'http.jsonl'
    monkeypatch.setenv('HERMES_HOME', str(home))
    monkeypatch.setenv('MAX_PROBE_SOURCE', str(Path(adapter.__file__).parent))
    monkeypatch.setenv('MAX_PROBE_LOG', str(log))
    monkeypatch.delenv('HERMES_MAX_TYPED_ENVELOPE_V1', raising=False)
    harness = Path(__file__).parent / 'fixtures' / 'host_cli_repair2.py'
    return harness, log, home


@pytest.mark.parametrize('destination,origin,allowed', [('max:-42', 'api', True), ('max:-43', 'api', False), ('max:-42', 'max', True)])
def test_real_host_cli_policy_then_typed_wire(destination, origin, allowed, monkeypatch, tmp_path, capsys):
    harness, log, home = harness_env(tmp_path, monkeypatch)
    monkeypatch.setenv('MAX_PROBE_ORIGIN', origin)
    bridge = bridge_module()
    # Replace only the public launcher argv with a synthetic-I/O host process.
    monkeypatch.setattr(bridge, 'hermes_command', lambda args: [sys.executable, str(harness), *args])
    from hermes_cli.plugins import PluginContext, PluginManager, PluginManifest
    manager = PluginManager()
    adapter.register(PluginContext(PluginManifest(name='max-platform', kind='platform', source='user'), manager))
    record = manager._cli_commands['max']
    parser = argparse.ArgumentParser()
    subs = parser.add_subparsers(dest='command', required=True)
    record['setup_fn'](subs.add_parser('max'))
    body = {'text': 'Synthetic contact', 'attachments': [{'type': 'contact', 'payload': {'contact_id': 42, 'name': 'Fixture'}}]}
    path = tmp_path / 'body.json'
    path.write_text(json.dumps(body))
    args = parser.parse_args(['max', 'send-attachments', '--to', destination, '--body-file', str(path)])
    with pytest.raises(SystemExit) as exc:
        args.func(args)
    output = capsys.readouterr()
    assert (exc.value.code == 0) == allowed, output
    events = [json.loads(x) for x in log.read_text().splitlines()]
    assert any('policy_snapshot' in x for x in events), events
    http = [x for x in events if 'http' in x]
    if allowed:
        message, = [x for x in http if x['path'] == '/messages']
        assert message['query'] == {'chat_id': '-42'}
        assert message['body'] == body
        assert 'fixture-mid' in output.out
    else:
        assert not http, events
    assert not list((home / 'cache').glob('max-typed-v1-*'))
    assert 'synthetic-fixture-not-a-live-credential' not in output.out + output.err


def test_ordinary_json_is_plain_text_without_marker(monkeypatch, tmp_path):
    harness, log, _ = harness_env(tmp_path, monkeypatch)
    body = '{"attachments":[{"type":"sticker","payload":{"code":"not-a-command"}}]}'
    path = tmp_path / 'normal.json'
    path.write_text(body)
    try:
        result = subprocess.run([sys.executable, str(harness), 'send', '--to', 'max:-42', '--file', str(path), '--json'], env=os.environ.copy(), capture_output=True, timeout=20, check=False)
    except subprocess.TimeoutExpired as exc:
        raise AssertionError((exc.stderr or b'').decode()[-6000:]) from exc
    assert result.returncode == 0, result.stderr
    events = [json.loads(x) for x in log.read_text().splitlines()]
    message, = [x for x in events if x.get('path') == '/messages']
    assert message['body']['text'] == body
    assert 'attachments' not in message['body']


def test_envelope_closed_versioned_and_nonprotocol_fallback(monkeypatch, tmp_path):
    bridge = bridge_module()
    body = {'attachments': [{'type': 'sticker', 'payload': {'code': 'fixture'}}]}
    text = bridge.encode_body(body)
    assert bridge.decode_body(text) == body
    with pytest.raises(ValueError):
        bridge.decode_body(json.dumps(body))
    with pytest.raises(ValueError):
        bridge.encode_body({**body, 'destination': 'max:-43'})
    path = tmp_path / 'plain.json'
    path.write_text(json.dumps(body))
    monkeypatch.setenv(bridge.OPT_IN, str(path))
    assert bridge.registration_options() == {}


@pytest.mark.asyncio
@pytest.mark.parametrize('typed', [True, False])
@pytest.mark.parametrize('kind,suffix', [('file', '.pdf'), ('audio', '.mp3')])
async def test_host_typed_and_ordinary_media_real_cdn(typed, kind, suffix, monkeypatch, tmp_path, capsys):
    import asyncio
    import hashlib

    from aiohttp import web
    harness, log, home = harness_env(tmp_path, monkeypatch)
    data = bytes(range(256)) * 4096
    path = tmp_path / ('finite' + suffix)
    path.write_bytes(data)
    digest = hashlib.sha256()
    received = 0
    async def receive(request):
        nonlocal received
        part = await (await request.multipart()).next()
        while chunk := await part.read_chunk(65536):
            digest.update(chunk)
            received += len(chunk)
        return web.json_response({'token': 'fixture-token'})
    app = web.Application()
    app.router.add_post('/upload', receive)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    monkeypatch.setenv('MAX_PROBE_CDN', f'http://127.0.0.1:{port}/upload')
    try:
        if typed:
            bridge = bridge_module()
            monkeypatch.setattr(bridge, 'hermes_command', lambda args: [sys.executable, str(harness), *args])
            bodyfile = tmp_path / 'body.json'
            bodyfile.write_text(json.dumps({'attachments': [{'type': kind, 'path': str(path)}]}))
            args = SimpleNamespace(to='max:-42', body_file=str(bodyfile))
            with pytest.raises(SystemExit) as exc:
                await asyncio.to_thread(bridge.run_cli, args)
            assert exc.value.code == 0, capsys.readouterr()
        else:
            result = await asyncio.to_thread(subprocess.run, [sys.executable, str(harness), 'send', '--to', 'max:-42', f'MEDIA:{path}', '--json'], env=os.environ.copy(), capture_output=True, timeout=30)
            if not adapter._STANDALONE_POLICY_SUPPORTED:
                # Older real Core rejects ordinary plugin media before transport.
                # Assert that contract, not a synthetic success or a skipped case.
                assert result.returncode == 1, result.stderr + result.stdout
                failure = json.loads(result.stdout)
                assert 'only media attachments' in failure['error']
                events = [json.loads(x) for x in log.read_text().splitlines()] if log.exists() else []
                assert not [event for event in events if 'http' in event]
                assert received == 0
                assert not list((home / 'cache').glob('max-typed-v1-*'))
                return
            assert result.returncode == 0, result.stderr + result.stdout
        events = [json.loads(x) for x in log.read_text().splitlines()]
        message, = [x for x in events if x.get('path') == '/messages']
        assert message['query'] == {'chat_id': '-42'}
        assert message['body']['attachments'] == [{'type': kind, 'payload': {'token': 'fixture-token'}}]
        assert received == len(data) and digest.digest() == hashlib.sha256(data).digest()
        assert not list((home / 'cache').glob('max-typed-v1-*'))
    finally:
        await runner.cleanup()


def test_limits_and_file_safety_and_bounded_child_output(tmp_path, monkeypatch):
    bridge = bridge_module()
    path = tmp_path / 'too-large.json'
    path.write_bytes(b'x' * (bridge.LIMIT + 1))
    with pytest.raises(ValueError):
        bridge.read_limited(path)
    with pytest.raises(ValueError):
        bridge.run_host([sys.executable, '-c', 'import os; os.write(1,b"x"*1000000)'], os.environ.copy())
    seen = []
    def safety(value):
        seen.append(value)
        raise PermissionError('synthetic file_safety refusal')
    monkeypatch.setattr(bridge, 'raise_if_read_blocked', safety)
    with pytest.raises(PermissionError):
        bridge.encode_body({'attachments': [{'type': 'file', 'path': str(path)}]})
    assert seen == [str(path)]
    with pytest.raises(PermissionError):
        bridge.read_limited(path)
