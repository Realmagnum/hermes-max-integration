"""Real Core main -> discovered plugin CLI -> real child main -> HTTP; no Core dispatch mock."""
import hashlib
import importlib.util
import json
import os
import signal
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CORE = Path(os.environ.get('MAX_COMPLETION_CORE', str(Path(importlib.util.find_spec('hermes_cli').origin).parent.parent)))
PYTHON = os.environ.get('MAX_COMPLETION_PYTHON', sys.executable)

@pytest.fixture
def host(tmp_path):
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_POST(self):
            body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
            calls.append({'path': self.path, 'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest(), 'body': json.loads(body) if self.path.startswith('/messages') else None})
            status = 503 if os.environ.get('MAX_COMPLETION_FAIL') and self.path.startswith('/messages') else 200
            value = {'url': 'https://upload.max.ru/upload', 'token': 'fixture-token'} if self.path.startswith('/uploads') else {'token': 'fixture-token'} if self.path == '/upload' else {'message': {'body': {'mid': 'fixture-mid'}}}
            raw = json.dumps(value).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    home = tmp_path / 'home'
    (home / 'plugins').mkdir(parents=True)
    (home / 'plugins/max-platform').symlink_to(ROOT, target_is_directory=True)
    (home / 'config.yaml').write_text('plugins:\n  enabled: [max-platform]\ngateway:\n  platforms:\n    max:\n      enabled: true\n      token: synthetic-fixture-not-live\n')
    env = os.environ.copy()
    env.update(HOME=str(home), HERMES_HOME=str(home), HERMES_DISABLE_LAZY_INSTALLS='1', PYTHONDONTWRITEBYTECODE='1', MAX_BOT_TOKEN='synthetic-fixture-not-live', MAX_COMPLETION_HTTP=f'http://127.0.0.1:{server.server_port}', MAX_COMPLETION_EVENTS=str(tmp_path / 'events.jsonl'), PYTHONPATH=os.pathsep.join([str(ROOT / 'tests/fixtures/completion_site'), str(CORE)]))
    def run(args, origin='api'):
        env['MAX_COMPLETION_ORIGIN'] = origin
        proc = subprocess.Popen([PYTHON, '-m', 'hermes_cli.main', *args], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        try:
            out, err = proc.communicate(timeout=25)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            out, err = proc.communicate()
            pytest.fail(f'full host timeout: {err.decode()[-2500:]}')
        assert len(out) + len(err) < 131072
        (tmp_path / 'last.stdout').write_bytes(out)
        (tmp_path / 'last.stderr').write_bytes(err)
        return proc.returncode, out.decode(), err.decode()
    yield run, calls, tmp_path, env
    server.shutdown()
    server.server_close()
    thread.join(2)

BODIES = [
    {'attachments': [{'type': 'contact', 'payload': {'contact_id': 42, 'name': 'Synthetic fixture'}}]},
    {'attachments': [{'type': 'location', 'latitude': 0, 'longitude': 0}]},
    {'text': 'Synthetic keyboard', 'attachments': [{'type': 'inline_keyboard', 'payload': {'buttons': [[{'type': 'message', 'text': 'Fixture'}]]}}]},
]

@pytest.mark.parametrize('origin', ['local', 'api', 'max'])
@pytest.mark.parametrize('body', BODIES)
def test_full_host_typed(host, origin, body):
    run, calls, tmp, env = host
    path = tmp / 'body.json'
    path.write_text(json.dumps(body))
    code, out, err = run(['max', 'send-attachments', '--to', 'max:-42', '--body-file', str(path)], origin)
    assert code == 0, out + err
    messages = [x for x in calls if x['path'].startswith('/messages')]
    assert len(messages) == 1 and messages[0]['path'] == '/messages?chat_id=-42'
    assert messages[0]['body'] == body
    assert not list((Path(env['HERMES_HOME']) / 'cache').glob('max-typed-v1-*'))


def test_full_host_denied_zero_http(host):
    run, calls, tmp, env = host
    path = tmp / 'body.json'
    path.write_text(json.dumps(BODIES[0]))
    code, out, err = run(['max', 'send-attachments', '--to', 'max:-43', '--body-file', str(path)])
    assert code != 0 and not calls, (out, err, calls)
    assert 'policy_state_read' in Path(env['MAX_COMPLETION_EVENTS']).read_text()

@pytest.mark.parametrize('suffix', ['', '.pdf', '.mp3', '.png', '.mp4'])
def test_full_host_ordinary_fallback(host, suffix):
    run, calls, tmp, _env = host
    message = 'Ordinary fixture text'
    if suffix:
        path = tmp / ('finite' + suffix)
        path.write_bytes(b'ID3' + bytes(4093) if suffix == '.mp3' else bytes(4096))
        message = f'MEDIA:{path}'
    code, out, err = run(['send', '--to', 'max:-42', message, '--json'])
    import dataclasses

    from gateway.platform_registry import PlatformEntry
    if suffix and 'standalone_send' not in {f.name for f in dataclasses.fields(PlatformEntry)}:
        assert code != 0 and not calls, (out, err, calls)
        return
    assert code == 0, out + err
    messages = [x for x in calls if x['path'].startswith('/messages')]
    assert len(messages) == 1
    if suffix:
        expected = {'.pdf': 'file', '.mp3': 'audio', '.png': 'image', '.mp4': 'video'}[suffix]
        assert messages[0]['body']['attachments'] == [{'type': expected, 'payload': {'token': 'fixture-token'}}]
        assert any(x['path'] == '/upload' and x['bytes'] > 4096 for x in calls)
    else:
        assert messages[0]['body']['text'] == message


def test_full_host_no_ambiguous_replay(host, monkeypatch):
    run, calls, tmp, _env = host
    monkeypatch.setenv('MAX_COMPLETION_FAIL', '1')
    path = tmp / 'body.json'
    path.write_text(json.dumps(BODIES[0]))
    code, out, err = run(['max', 'send-attachments', '--to', 'max:-42', '--body-file', str(path)])
    assert code != 0, (out, err)
    assert len([x for x in calls if x['path'].startswith('/messages')]) == 1
