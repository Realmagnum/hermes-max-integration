#!/usr/bin/env python3
"""Native, Core-free upload probe. Synthetic data and loopback HTTP only; no skips."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import platform
import stat
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

import aiohttp
from aiohttp import web

# Import the real package/module (including its relative Windows helper), not a copy.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mixins import upload_stream as stream  # noqa: E402


class Writer:
    def __init__(self):
        self.data = bytearray()

    async def write(self, chunk):
        self.data.extend(chunk)


async def drained():
    async with asyncio.timeout(5):
        while any(t.name.startswith("max-upload-") for t in threading.enumerate()):
            await asyncio.sleep(.005)
    slots = [stream._IO_SLOTS.acquire(blocking=False) for _ in range(4)]
    try:
        assert all(slots), "worker leaked capacity"
        assert not stream._IO_SLOTS.acquire(blocking=False), "capacity exceeds four"
    finally:
        for acquired in slots:
            if acquired:
                stream._IO_SLOTS.release()


async def rejected(path, admitted):
    writer = Writer()
    try:
        await asyncio.wait_for(stream.FilePayload(str(path), admitted).write(writer), 3)
    except (OSError, ValueError):
        pass
    else:
        raise AssertionError("unsafe/replaced file was uploaded")
    assert not writer.data, "rejected handle leaked bytes"
    await drained()


async def multipart(source, content, status):
    reads, received = [], []
    owner = threading.get_ident()
    real_read = os.read

    def read(fd, count):
        chunk = real_read(fd, count)
        reads.append((count, len(chunk), threading.get_ident()))
        return chunk

    async def receive(request):
        reader = await request.multipart()
        part = await reader.next()
        assert part.name == "data" and part.filename == source.name
        data = bytearray()
        while chunk := await part.read_chunk(65536):
            data.extend(chunk)
        assert await reader.next() is None
        received.append(bytes(data))
        return web.json_response({"probe": True}, status=status)

    app = web.Application()
    app.router.add_post("/upload", receive)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]

    class LoopbackSession:
        # Only the final transport endpoint is redirected. post_file still checks
        # its HTTPS URL and creates the real production multipart FilePayload.
        def __init__(self, session):
            self.session = session
            self.calls = 0

        def post(self, url, **kwargs):
            assert url == "https://upload.max.ru/portability-probe"
            assert kwargs["allow_redirects"] is False
            self.calls += 1
            return self.session.post(f"http://127.0.0.1:{port}/upload", **kwargs)

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
            local = LoopbackSession(session)
            with patch.object(stream.os, "read", read):
                actual, body = await stream.post_file(
                    local, "https://upload.max.ru/portability-probe", str(source), "file")
            assert (actual, body) == (status, {"probe": True})
            assert local.calls == 1 and received == [content], "bytes/replay mismatch"
        assert reads and all(0 < n <= 65536 and tid != owner for n, _, tid in reads)
        assert sum(size for _, size, _ in reads) == len(content)
        assert [n for n, _, _ in reads] == [65536, 65536, len(content) - 131072]
        await drained()
        return {"status": status, "posts": local.calls, "bytes": len(content),
                "sha256": hashlib.sha256(received[0]).hexdigest(),
                "reads": len(reads), "max_read": max(n for n, _, _ in reads),
                "off_loop": True}
    finally:
        await runner.cleanup()


async def startup(source, admitted):
    for fault in ("constructor", "start"):
        class BrokenThread:
            def __init__(self, **kwargs):
                if fault == "constructor":
                    raise RuntimeError("synthetic constructor failure")

            def start(self):
                raise RuntimeError("synthetic start failure")

        for stage in ("admission", "file"):
            with patch.object(stream.threading, "Thread", BrokenThread):
                try:
                    if stage == "admission":
                        await stream.async_check_upload(str(source), "file")
                    else:
                        stream._FileWorker(str(source), admitted)
                except OSError:
                    pass
                else:
                    raise AssertionError("startup fault was swallowed")
            await drained()


async def cancel_capacity(source, admitted):
    entered, closed, release = [], [], threading.Event()
    lock = threading.Lock()
    real_read, real_close = os.read, os.close

    def read(fd, count):
        with lock:
            entered.append(fd)
        if not release.wait(10):
            raise AssertionError("probe did not release read")
        return real_read(fd, count)

    def close(fd):
        result = real_close(fd)
        with lock:
            closed.append(fd)
        return result

    tasks = []
    with patch.object(stream.os, "read", read), patch.object(stream.os, "close", close):
        try:
            for _ in range(4):
                tasks.append(asyncio.create_task(stream.FilePayload(str(source), admitted).write(Writer())))
            async with asyncio.timeout(5):
                while len(entered) < 4:
                    await asyncio.sleep(.005)
            try:
                stream._FileWorker(str(source), admitted)
            except OSError:
                pass
            else:
                raise AssertionError("fifth worker admitted")
            for task in tasks:
                task.cancel()
            async with asyncio.timeout(1):
                results = await asyncio.gather(*tasks, return_exceptions=True)
            assert all(isinstance(result, asyncio.CancelledError) for result in results)
            assert not closed, "closed underneath active reads"
        finally:
            release.set()
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await drained()
        assert len(closed) == 4 and set(closed) == set(entered), "late cleanup mismatch"


async def native_specials(root, admitted):
    # Exercise the actual open boundary even where normal admission rejects first.
    await rejected(root, admitted)
    target = root / "target.bin"
    target.write_bytes(b"reparse target")
    link = root / "link.bin"
    # Windows CI must have symlink privileges; failure is a gate, NOT a skip.
    link.symlink_to(target)
    assert stat.S_ISLNK(os.lstat(link).st_mode)
    await rejected(link, admitted)
    # Use the target's identity too: rejection must be no-follow, not mismatch.
    await rejected(link, stream.check_upload(str(target), "file"))
    coverage = ["directory", "final-symlink-no-follow"]
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        # A real junction is a non-symlink directory reparse point. No privilege
        # bypass or Linux Win32 emulation; fixture creation failure fails CI.
        junction = root / "junction"
        subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(root)],
                       check=True, capture_output=True, timeout=10)
        try:
            assert os.lstat(junction).st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
            await rejected(junction, admitted)
        finally:
            junction.rmdir()
        for name in ("NUL", "CON", "COM1", str(root / "NUL"), str(target) + ":ads"):
            await rejected(name, admitted)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        create = kernel.CreateNamedPipeW
        create.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                           wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                           wintypes.DWORD, wintypes.LPVOID)
        create.restype = wintypes.HANDLE
        close = kernel.CloseHandle
        close.argtypes, close.restype = (wintypes.HANDLE,), wintypes.BOOL
        name = rf"\\.\pipe\max-upload-portability-{os.getpid()}"
        handle = create(name, 1, 0, 1, 4096, 4096, 0, None)
        assert handle != ctypes.c_void_p(-1).value
        try:
            await rejected(name, admitted)
        finally:
            assert close(handle)
        coverage += ["junction", "DOS-device", "ADS", "live-named-pipe"]
    else:
        fifo = root / "fifo"
        os.mkfifo(fifo)
        await rejected(fifo, admitted)
        await rejected("/dev/null", admitted)
        coverage += ["FIFO-nonblocking", "character-device"]
    return coverage


async def main():
    assert stream.CHUNK_SIZE == 65536 and stream.IO_CAPACITY == 4
    result = {"platform": sys.platform, "python": platform.python_version(),
              "module_sha256": hashlib.sha256(Path(stream.__file__).read_bytes()).hexdigest(),
              "native_windows": "RUN" if os.name == "nt" else "NOT RUN"}
    with tempfile.TemporaryDirectory(prefix="max-upload-portability-") as directory:
        root = Path(directory)
        source = root / "binary.bin"
        # All byte values, CR/LF/NUL/Ctrl-Z and >2 full chunks catch CRT text mode.
        content = bytes(range(256)) * 512 + b"\x00\r\n\x1a\xfftail"
        source.write_bytes(content)
        admitted = await stream.async_check_upload(str(source), "file")
        fd = stream._open_file(str(source))
        try:
            info = os.fstat(fd)
            assert stat.S_ISREG(info.st_mode)
            assert (info.st_dev, info.st_ino, info.st_size) == admitted.identity
            assert info.st_ino != 0, "filesystem does not supply identity"
            assert not os.get_inheritable(fd)
            assert os.read(fd, len(content)) == content, "binary mode mismatch"
        finally:
            os.close(fd)
        result["identity_binary_noninherit"] = "PASS"
        result["multipart"] = [await multipart(source, content, status) for status in (200, 503)]
        kept = root / "original-kept.bin"
        source.rename(kept)  # Keep old inode alive: no accidental inode reuse.
        source.write_bytes(content)
        assert source.stat().st_ino != admitted.identity[1]
        await rejected(source, admitted)
        result["identity_swap"] = "PASS"
        result["specials"] = await native_specials(root, admitted)
        await startup(kept, admitted)
        result["startup_four_faults"] = "PASS"
        await cancel_capacity(kept, admitted)
        result["four_workers_cancel_latecleanup"] = "PASS"
        await drained()
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(asyncio.wait_for(main(), 60))
