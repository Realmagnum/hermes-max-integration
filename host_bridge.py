"""Explicit v1 host CLI bridge. No model destination tool or Core-private import."""
from __future__ import annotations

import base64
import binascii
import json
import os
import selectors
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from agent.file_safety import raise_if_read_blocked
from hermes_constants import get_hermes_home

from .attachment_tool import send_to_resolved, validate

PREFIX = "HERMES_MAX_TYPED_V1:"
OPT_IN = "HERMES_MAX_TYPED_ENVELOPE_V1"
LIMIT = 65536


def hermes_command(args):
    from hermes_cli.chat_launch import hermes_command as command
    return command(args)


def run_host(command, env):
    """Bound both captured pipes while retaining a finite host command deadline."""
    with subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE) as proc:
        assert proc.stdout is not None and proc.stderr is not None
        output = {proc.stdout.fileno(): bytearray(), proc.stderr.fileno(): bytearray()}
        deadline = time.monotonic() + 4000
        try:
            with selectors.DefaultSelector() as selector:
                for pipe in output:
                    selector.register(pipe, selectors.EVENT_READ)
                while selector.get_map():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise subprocess.TimeoutExpired(command, 4000)
                    for key, _ in selector.select(min(remaining, 1)):
                        chunk = os.read(key.fd, min(8192, LIMIT + 1 - sum(map(len, output.values()))))
                        if not chunk:
                            selector.unregister(key.fileobj)
                            continue
                        output[key.fd].extend(chunk)
                        if sum(map(len, output.values())) > LIMIT:
                            raise ValueError("Host output exceeds64KiB; outcome uncertain, do not resend")
                code = proc.wait(timeout=max(.01, deadline - time.monotonic()))
            return code, bytes(output[proc.stdout.fileno()])
        except BaseException:
            proc.kill()
            proc.wait()
            raise


def read_limited(path):
    raise_if_read_blocked(str(path))
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > LIMIT:
            raise ValueError("Body/envelope must be a regular file <=64KiB")
        raw = os.read(fd, LIMIT + 1)
        if len(raw) > LIMIT:
            raise ValueError("Body/envelope exceeds64KiB")
        return raw
    finally:
        os.close(fd)


def encode_body(body):
    body = validate(body)
    for item in body['attachments']:
        if 'path' in item:
            raise_if_read_blocked(item['path'])
    raw = json.dumps({'version': 1, 'body': body}, ensure_ascii=False, separators=(',', ':')).encode()
    text = PREFIX + base64.b64encode(raw).decode('ascii')
    if len(text.encode()) > LIMIT:
        raise ValueError("Encoded v1 transport exceeds64KiB")
    return text


def decode_body(text):
    if not isinstance(text, str) or not text.startswith(PREFIX) or len(text.encode()) > LIMIT:
        raise ValueError("Invalid explicit MAX typed v1 envelope")
    try:
        obj = json.loads(base64.b64decode(text[len(PREFIX):], validate=True))
    except (ValueError, binascii.Error) as exc:
        raise ValueError("Malformed MAX typed v1 envelope") from exc
    if not isinstance(obj, dict) or set(obj) != {'version', 'body'} or type(obj['version']) is not int or obj['version'] != 1:
        raise ValueError("Unknown MAX typed transport version/fields")
    return validate(obj['body'])


def registration_options():
    """Only the explicit producer child installs a handler. Ordinary MAX stays unchanged.

    The opt-in path is transient process context, not a body-controlled env lookup.
    A non-protocol file leaves the original Core/live-adapter/standalone route intact.
    The callback binds the exact file text; any mutation/subject rewrite is refused.
    """
    path = os.environ.get(OPT_IN)
    if not path:
        return {}
    expected = read_limited(path).decode('utf-8')
    if not expected.startswith(PREFIX):
        return {}
    async def handle(args, chat_id, platform_name, pconfig):
        if platform_name != 'max' or args.get('message') != expected:
            return {'error': 'Typed envelope changed in transit; message not sent', 'retryable': False}
        if args.get('thread_id') or args.get('mentions'):
            return {'error': 'Typed v1 does not support threads/mentions', 'retryable': False}
        try:
            body = decode_body(args['message'])
            from .mixins.standalone import _standalone_get_token
            token = _standalone_get_token(pconfig)
            if not token:
                return {'error': 'MAX credentials unavailable', 'retryable': False}
            # chat_id is the Core-resolved/authorized destination, never from envelope.
            result = json.loads(await send_to_resolved(body, str(chat_id), token))
            if result.get('success'):
                result.pop('error', None)  # Core treats presence of error as a failure diagnostic.
            return {**result, 'platform': 'max', 'chat_id': str(chat_id)}
        except (ValueError, TypeError, OSError):
            return {'error': 'Invalid typed MAX v1 request; not sent', 'retryable': False}
    return {'send_message_handler': handle}


def setup_cli(parser):
    subs = parser.add_subparsers(dest='max_command', required=True)
    send = subs.add_parser('send-attachments', help='Explicit typed MAX send via host hermes send policy')
    send.add_argument('--to', required=True, help='Explicit max:<destination>; resolved/authorized by Core')
    send.add_argument('--body-file', required=True, help='NewMessageBody JSON, <=64KiB; not a native Core JSON flag')
    send.set_defaults(func=run_cli)


def run_cli(args):
    try:
        if not isinstance(args.to, str) or not args.to.startswith('max:') or len(args.to) > 512 or any(c in args.to for c in '\r\n'):
            raise ValueError("--to must explicitly name max:<destination>")
        text = encode_body(json.loads(read_limited(args.body_file)))
        folder = get_hermes_home() / 'cache'
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='max-typed-v1-', dir=folder) as tmp:
            path = Path(tmp) / 'envelope.txt'
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as file:
                file.write(text.encode('ascii'))
            env = os.environ.copy()
            env['HERMES_HOME'] = str(get_hermes_home())
            env[OPT_IN] = str(path)
            command = hermes_command(['send', '--to', args.to, '--file', str(path), '--json'])
            code, stdout = run_host(command, env)
            # No body/token in argv; Core's regular JSON result is the only output.
            sys.stdout.write(stdout.decode('utf-8', 'replace'))
            if code and not stdout:
                sys.stderr.write('Host MAX send failed; do not automatically resend.\n')
        raise SystemExit(code)
    except (ImportError, ValueError, OSError, subprocess.TimeoutExpired):
        sys.stderr.write('MAX typed send rejected/uncertain; no automatic resend.\n')
        raise SystemExit(1) from None
