"""Bounded, single-attempt CDN multipart upload shared by both senders."""
from __future__ import annotations

import asyncio
import json
import os
import stat
from pathlib import Path
from urllib.parse import urlparse

import aiohttp

# Docs say MB/GB without byte convention. Decimal is conservative under either.
UPLOAD_LIMITS = {"image": 50_000_000, "video": 250_000_000,
                 "audio": 256_000_000, "file": 4_000_000_000}
CHUNK_SIZE = 64 * 1024
UPLOAD_TIMEOUT = 3600  # finite wall clock, including stalled/slow uploads
RESPONSE_LIMIT = 64 * 1024


def upload_timeout(size: int) -> float:
    """Shared budget: 60s overhead + 0.5 MB/s, bounded at 120..3600s."""
    return min(UPLOAD_TIMEOUT, max(120, 60 + size / 500_000))


def check_upload(path: str, kind: str) -> int:
    limit = UPLOAD_LIMITS.get(kind)
    if limit is None:
        raise ValueError("Unsupported upload type")
    info = os.stat(path)
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
        raise ValueError(f"Invalid file size for {kind}; maximum {limit} bytes")
    if len(Path(path).name) > 200:
        raise ValueError("Filename exceeds 200 characters")
    return info.st_size


async def _disk_call(fn, *args):
    # A cancelled executor future still runs. Wait before closing its descriptor.
    task = asyncio.create_task(asyncio.to_thread(fn, *args))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await task
        raise


class FilePayload(aiohttp.payload.Payload):
    """No read-all, prefetch or replay; at most one 64 KiB read in flight."""
    def __init__(self, path: str, size: int):
        super().__init__(path, content_type="application/octet-stream")
        self._size = size

    def decode(self, encoding="utf-8", errors="strict"):
        raise TypeError("File payload cannot be buffered")

    async def write(self, writer):
        opening = asyncio.create_task(asyncio.to_thread(open, self._value, "rb"))
        try:
            file = await asyncio.shield(opening)
        except asyncio.CancelledError:
            file = await opening
            await _disk_call(file.close)
            raise
        try:
            if await _disk_call(lambda: os.fstat(file.fileno()).st_size) != self._size:
                raise ValueError("File changed before upload")
            remaining = self._size
            while remaining:
                chunk = await _disk_call(file.read, min(CHUNK_SIZE, remaining))
                if not chunk:
                    raise ValueError("File truncated during upload")
                remaining -= len(chunk)
                await writer.write(chunk)
        finally:
            await _disk_call(file.close)


async def post_file(session, url: str, path: str, kind: str):
    """Return (HTTP status, bounded JSON object). Never retries or follows redirects."""
    size = await asyncio.to_thread(check_upload, path, kind)
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("Unsafe upload URL")
    form = aiohttp.FormData()
    form.add_field("data", FilePayload(path, size), filename=Path(path).name)
    async with session.post(url, data=form, allow_redirects=False) as response:
        raw = bytearray()
        while chunk := await response.content.read(min(8192, RESPONSE_LIMIT + 1 - len(raw))):
            raw.extend(chunk)
            if len(raw) > RESPONSE_LIMIT:
                raise ValueError("CDN response too large")
        try:
            body = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            body = {}
        return response.status, body if isinstance(body, dict) else {}
