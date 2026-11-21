"""A stuck syscall consumes bounded capacity, not unbounded executor threads."""
import asyncio
import os
import threading

import pytest
from max.mixins import upload_stream as stream


class Writer:
    async def write(self, chunk):
        pass


@pytest.fixture(autouse=True)
def no_leaked_probe_workers():
    yield
    workers = [t for t in threading.enumerate() if t.name.startswith('max-upload-')]
    for worker in workers:
        worker.join(timeout=.2)
    assert not [t.name for t in workers if t.is_alive()], 'controlled probe did not release its I/O worker'


@pytest.mark.asyncio
async def test_stalled_workers_are_capped_and_late_cleanup_owns_fd(tmp_path, monkeypatch):
    path = tmp_path / 'owned.bin'
    path.write_bytes(b'a')
    admitted = stream.check_upload(str(path), 'file')
    release = threading.Event()
    counts = {'entered': 0, 'closed': 0}
    lock = threading.Lock()
    real_read, real_close = os.read, os.close
    def read(fd, count):
        with lock:
            counts['entered'] += 1
        release.wait(3)
        return real_read(fd, count)
    def close(fd):
        real_close(fd)
        with lock:
            counts['closed'] += 1
    monkeypatch.setattr(stream.os, 'read', read)
    monkeypatch.setattr(stream.os, 'close', close)
    tasks = [asyncio.create_task(stream.FilePayload(str(path), admitted).write(Writer())) for _ in range(stream.IO_CAPACITY)]
    try:
        async with asyncio.timeout(1):
            while counts['entered'] != stream.IO_CAPACITY:
                await asyncio.sleep(.001)
        for task in tasks:
            task.cancel()
        await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), .2)
        assert counts['closed'] == 0
        with pytest.raises(OSError, match='capacity'):
            await stream.FilePayload(str(path), admitted).write(Writer())
        assert len([t for t in threading.enumerate() if t.name == 'max-upload-file']) <= stream.IO_CAPACITY
    finally:
        release.set()
        async with asyncio.timeout(1):
            while counts['closed'] != stream.IO_CAPACITY:
                await asyncio.sleep(.001)


@pytest.mark.asyncio
async def test_stalled_open_deadline_returns_before_syscall(tmp_path, monkeypatch):
    path = tmp_path / 'owned.bin'
    path.write_bytes(b'a')
    admitted = stream.check_upload(str(path), 'file')
    release, entered, closed = threading.Event(), threading.Event(), threading.Event()
    real_open, real_close = os.open, os.close
    def open_file(*args):
        entered.set()
        release.wait(2)
        return real_open(*args)
    def close(fd):
        real_close(fd)
        closed.set()
    monkeypatch.setattr(stream.os, 'open', open_file)
    monkeypatch.setattr(stream.os, 'close', close)
    monkeypatch.setattr(stream, 'IO_WAIT', .03)
    try:
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(stream.FilePayload(str(path), admitted).write(Writer()), .2)
        assert entered.is_set() and not closed.is_set()
    finally:
        release.set()
        async with asyncio.timeout(1):
            while not closed.is_set():
                await asyncio.sleep(.001)
