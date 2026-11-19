"""F2: own FIFO/inode replacements and bounded late worker ownership."""
import asyncio
import os
import threading

import pytest
from max.mixins import upload_stream as stream


class Writer:
    def __init__(self):
        self.data = bytearray()
    async def write(self, chunk):
        self.data.extend(chunk)


@pytest.mark.asyncio
@pytest.mark.parametrize('replacement', ['fifo', 'inode'])
async def test_checked_identity_replacement_is_rejected(tmp_path, replacement):
    path = tmp_path / 'owned.bin'
    path.write_bytes(b'a')
    admitted = stream.check_upload(str(path), 'file')
    path.unlink()
    if replacement == 'fifo':
        os.mkfifo(path)
    else:
        path.write_bytes(b'b')
    writer = Writer()
    task = asyncio.create_task(stream.FilePayload(str(path), admitted).write(writer))
    try:
        try:
            await asyncio.wait_for(asyncio.shield(task), .3)
        except TimeoutError:
            pytest.fail('replacement blocked instead of failing promptly')
        except (OSError, ValueError):
            pass
        else:
            pytest.fail('replacement bytes were admitted')
        assert not writer.data
    finally:
        # Baseline FIFO open is released deterministically, never leave a probe thread.
        if not task.done():
            task.cancel()
            if replacement == 'fifo':
                fd = os.open(path, os.O_WRONLY | os.O_NONBLOCK)
                os.close(fd)
            try:
                await asyncio.wait_for(task, 1)
            except (asyncio.CancelledError, OSError, ValueError):
                pass


@pytest.mark.asyncio
async def test_cancel_stalled_read_returns_and_late_cleanup(tmp_path, monkeypatch):
    path = tmp_path / 'owned.bin'
    path.write_bytes(b'a')
    admitted = stream.check_upload(str(path), 'file')
    entered, release, closed = threading.Event(), threading.Event(), threading.Event()
    real_read, real_close = os.read, os.close
    def read(fd, n):
        entered.set()
        release.wait(2)
        return real_read(fd, n)
    def close(fd):
        closed.set()
        return real_close(fd)
    monkeypatch.setattr(stream.os, 'read', read)
    monkeypatch.setattr(stream.os, 'close', close)
    task = asyncio.create_task(stream.FilePayload(str(path), admitted).write(Writer()))
    try:
        async with asyncio.timeout(.5):
            while not entered.is_set():
                await asyncio.sleep(.001)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, .2)
        assert not closed.is_set(), 'FD closed under an active read'
    finally:
        release.set()
        async with asyncio.timeout(1):
            while not closed.is_set():
                await asyncio.sleep(.001)
