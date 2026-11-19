"""Bounded read, off-loop I/O, cancellation and exact size boundary evidence."""
import asyncio
import io
import threading
import time
from unittest.mock import AsyncMock

import pytest
from max.mixins.upload_stream import (
    CHUNK_SIZE,
    UPLOAD_LIMITS,
    FilePayload,
    check_upload,
)


@pytest.mark.asyncio
async def test_reads_are_bounded_off_loop_and_cancel_closes(monkeypatch):
    loop_thread = threading.get_ident()
    entered = threading.Event()
    reads = []
    class SlowFile(io.BytesIO):
        def read(self, n=-1):
            reads.append((n, threading.get_ident()))
            entered.set()
            time.sleep(.03)
            return super().read(n)
        def fileno(self):
            return 123
    file = SlowFile(b'x' * (CHUNK_SIZE * 2))
    monkeypatch.setattr('builtins.open', lambda *a: file)
    monkeypatch.setattr('os.fstat', lambda _: type('Stat', (), {'st_size': CHUNK_SIZE * 2})())
    writer = type('Writer', (), {'write': AsyncMock()})()
    task = asyncio.create_task(FilePayload('/fixture', CHUNK_SIZE * 2).write(writer))
    while not entered.is_set():
        await asyncio.sleep(.001)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert file.closed
    assert reads and all(0 < n <= CHUNK_SIZE and thread != loop_thread for n, thread in reads)


@pytest.mark.parametrize('kind', sorted(UPLOAD_LIMITS))
def test_exact_size_boundary_no_transfer(kind, tmp_path):
    path = tmp_path / 'boundary.bin'
    limit = UPLOAD_LIMITS[kind]
    with path.open('wb') as file:
        file.truncate(limit)
    assert check_upload(str(path), kind) == limit
    with path.open('ab') as file:
        file.write(b'x')
    with pytest.raises(ValueError):
        check_upload(str(path), kind)


@pytest.mark.asyncio
async def test_cancel_during_open_closes(monkeypatch):
    started = threading.Event()
    file = io.BytesIO(b'x')
    def slow_open(*args):
        started.set()
        time.sleep(.03)
        return file
    monkeypatch.setattr('builtins.open', slow_open)
    task = asyncio.create_task(FilePayload('/fixture', 1).write(None))
    while not started.is_set():
        await asyncio.sleep(.001)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert file.closed
