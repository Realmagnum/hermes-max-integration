"""Bounded multipart I/O: pinned regular FD and capped late-worker ownership."""
from __future__ import annotations

import asyncio
import json
import os
import queue
import stat
import threading
from pathlib import Path
from urllib.parse import urlparse

import aiohttp

UPLOAD_LIMITS = {"image": 50_000_000, "video": 250_000_000,
                 "audio": 256_000_000, "file": 4_000_000_000}
CHUNK_SIZE = 64 * 1024
UPLOAD_TIMEOUT = 3600
RESPONSE_LIMIT = 64 * 1024
IO_WAIT = 10.0
# Includes admission, blocked open/read/close, and live upload workers. No queue/reaper.
IO_CAPACITY = 4
_IO_SLOTS = threading.BoundedSemaphore(IO_CAPACITY)


def _start_owned(target, name):
    """Exactly one owner releases the acquired slot, including failed starts."""
    semaphore = _IO_SLOTS
    if not semaphore.acquire(blocking=False):
        raise OSError("Upload disk capacity exhausted (pending I/O)")
    lock = threading.Lock()
    state = ["parent"]
    def run():
        with lock:
            if state[0] != "parent":
                return  # Launch failed before this thread claimed ownership.
            state[0] = "worker"
        try:
            target()
        finally:
            with lock:
                state[0] = "released"
                semaphore.release()
    try:
        thread = threading.Thread(target=run, name=name, daemon=True)
        thread.start()
        return thread
    except Exception as exc:
        with lock:
            if state[0] == "parent":
                state[0] = "released"
                semaphore.release()
        raise OSError("Unable to start upload I/O worker") from exc


def upload_timeout(size: int) -> float:
    return min(UPLOAD_TIMEOUT, max(120, 60 + size / 500_000))


class UploadSize(int):
    """An int for compatibility, carrying the exact admitted filesystem identity."""
    identity: tuple[int, int, int]
    def __new__(cls, info):
        value = super().__new__(cls, info.st_size)
        value.identity = (info.st_dev, info.st_ino, info.st_size)
        return value


def check_upload(path: str, kind: str) -> UploadSize:
    limit = UPLOAD_LIMITS.get(kind)
    if limit is None:
        raise ValueError("Unsupported upload type")
    # Reject a final-component symlink rather than silently resolve another target.
    info = os.lstat(path)
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
        raise ValueError(f"Invalid file size for {kind}; maximum {limit} bytes")
    if len(Path(path).name) > 200:
        raise ValueError("Filename exceeds 200 characters")
    return UploadSize(info)


def _settle(loop, future, value=None, error=None):
    def deliver():
        if not future.done():
            if error is not None:
                future.set_exception(error)
            else:
                future.set_result(value)
    try:
        loop.call_soon_threadsafe(deliver)
    except RuntimeError:
        pass  # Loop closed: worker still owns cleanup and releases its own slot.


async def async_check_upload(path: str, kind: str):
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    def run():
        try:
            _settle(loop, future, check_upload(path, kind))
        except Exception as exc:  # noqa: BLE001 — deliver original bounded-admission failure
            _settle(loop, future, error=exc)
    _start_owned(run, "max-upload-admission")
    return await asyncio.wait_for(future, IO_WAIT)


def _open_file(path):
    """Platform no-follow open; identity is checked on this exact FD by the worker."""
    if os.name == "nt":
        from ._windows_file import open_regular
        return open_regular(path)
    flags = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC
    return os.open(path, flags)


class _FileWorker:
    """Sole owner of its FD, including after caller timeout/cancellation.

    A stuck kernel call cannot be killed safely. It occupies one of four global
    slots until it returns, then closes its own FD. No other thread closes/reuses
    that FD, no executor shutdown wait, no detached tasks or unbounded reaper.
    """
    def __init__(self, path, admitted):

        self.path, self.admitted = path, admitted
        self.stop = threading.Event()
        self.commands = queue.Queue(maxsize=1)
        self.loop = asyncio.get_running_loop()
        self.thread = _start_owned(self._run, "max-upload-file")

    def _run(self):
        fd = None
        sent = 0
        try:
            while not self.stop.is_set():
                try:
                    count, future = self.commands.get(timeout=.05)
                except queue.Empty:
                    continue
                try:
                    if fd is None:
                        fd = _open_file(self.path)
                        info = os.fstat(fd)
                        actual = (info.st_dev, info.st_ino, info.st_size)
                        if not stat.S_ISREG(info.st_mode) or actual != self.admitted.identity:
                            raise ValueError("Upload file identity/type changed before open")
                    if self.stop.is_set():
                        break
                    chunk = os.read(fd, count)
                    sent += len(chunk)
                    _settle(self.loop, future, chunk)
                    if not chunk or sent >= self.admitted:
                        break
                except Exception as exc:  # noqa: BLE001 — worker owns FD even on failure
                    _settle(self.loop, future, error=exc)
                    break
        finally:
            if fd is not None:
                os.close(fd)

    async def read(self, count, deadline):
        future = self.loop.create_future()
        self.commands.put_nowait((count, future))
        remaining = min(IO_WAIT, deadline - self.loop.time())
        if remaining <= 0:
            raise TimeoutError("Upload disk deadline exhausted")
        return await asyncio.wait_for(future, remaining)


class FilePayload(aiohttp.payload.Payload):
    def __init__(self, path: str, size: int):
        super().__init__(path, content_type="application/octet-stream")
        if not isinstance(size, UploadSize):
            raise TypeError("Upload requires identity-bearing admission")
        self._size, self.admitted = int(size), size

    def decode(self, encoding="utf-8", errors="strict"):
        raise TypeError("File payload cannot be buffered")

    async def write(self, writer):
        worker = _FileWorker(self._value, self.admitted)
        deadline = asyncio.get_running_loop().time() + upload_timeout(self._size)
        try:
            remaining = self._size
            while remaining:
                chunk = await worker.read(min(CHUNK_SIZE, remaining), deadline)
                if not chunk:
                    raise ValueError("File truncated during upload")
                remaining -= len(chunk)
                remaining_time = deadline - asyncio.get_running_loop().time()
                if remaining_time <= 0:
                    raise TimeoutError("Upload deadline exhausted")
                await asyncio.wait_for(writer.write(chunk), remaining_time)
        finally:
            # Never await an uninterruptible syscall or close underneath it.
            worker.stop.set()


async def post_file(session, url: str, path: str, kind: str, *, admitted=None):
    size = admitted if admitted is not None else await async_check_upload(path, kind)
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
