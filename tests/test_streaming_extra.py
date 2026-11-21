"""Bounded read and cancellation coverage at the actual os.open/read boundary."""
import asyncio
import os
import threading
from unittest.mock import AsyncMock

import pytest
from max.mixins import upload_stream as stream


async def wait_event(event):
    async with asyncio.timeout(1):
        while not event.is_set():
            await asyncio.sleep(.001)


@pytest.mark.asyncio
async def test_reads_are_bounded_off_loop_and_cancel_closes(monkeypatch, tmp_path):
    path = tmp_path / 'owned.bin'
    path.write_bytes(b'x' * (stream.CHUNK_SIZE * 2))
    admitted = stream.check_upload(str(path), 'file')
    loop_thread = threading.get_ident()
    entered, release, closed = threading.Event(), threading.Event(), threading.Event()
    reads = []
    real_read, real_close = os.read, os.close
    def read(fd, n):
        reads.append((n, threading.get_ident()))
        entered.set()
        release.wait(2)
        return real_read(fd, n)
    def close(fd):
        real_close(fd)
        closed.set()
    monkeypatch.setattr(stream.os, 'read', read)
    monkeypatch.setattr(stream.os, 'close', close)
    writer = type('Writer', (), {'write': AsyncMock()})()
    task = asyncio.create_task(stream.FilePayload(str(path), admitted).write(writer))
    try:
        await wait_event(entered)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, .2)
        assert not closed.is_set()
    finally:
        release.set()
        await wait_event(closed)
    assert reads and all(0 < n <= stream.CHUNK_SIZE and thread != loop_thread for n, thread in reads)


@pytest.mark.parametrize('kind', sorted(stream.UPLOAD_LIMITS))
def test_exact_size_boundary_no_transfer(kind, tmp_path):
    path = tmp_path / 'boundary.bin'
    limit = stream.UPLOAD_LIMITS[kind]
    with path.open('wb') as file:
        file.truncate(limit)
    assert stream.check_upload(str(path), kind) == limit
    with path.open('ab') as file:
        file.write(b'x')
    with pytest.raises(ValueError):
        stream.check_upload(str(path), kind)


@pytest.mark.asyncio
async def test_cancel_during_open_closes(monkeypatch, tmp_path):
    path = tmp_path / 'owned.bin'
    path.write_bytes(b'x')
    admitted = stream.check_upload(str(path), 'file')
    entered, release, closed = threading.Event(), threading.Event(), threading.Event()
    real_open, real_close = os.open, os.close
    def slow_open(*args):
        entered.set()
        release.wait(2)
        return real_open(*args)
    def close(fd):
        real_close(fd)
        closed.set()
    monkeypatch.setattr(stream.os, 'open', slow_open)
    monkeypatch.setattr(stream.os, 'close', close)
    task = asyncio.create_task(stream.FilePayload(str(path), admitted).write(None))
    try:
        await wait_event(entered)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, .2)
        assert not closed.is_set()
    finally:
        release.set()
        await wait_event(closed)
