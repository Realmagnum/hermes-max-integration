"""One final, bounded diagnostic summary per attachment; no progress logging.

Source IDs are guessable lexical-path mappings, not cryptographic anonymity.
State is fixed-size per attachment, never an event/attempt history. Hard-crash
loss is accepted. Existing application handlers own persistence and rotation.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps

logger = logging.getLogger(__name__)
_current: ContextVar[MediaOperation | tuple[MediaOperation, ...] | None] = ContextVar("max_media_operation", default=None)
STAGES = ("prepare", "normalize", "admission", "upload_url", "cdn", "readiness", "send")
MAX_MS = 86_400_000
MAX_COUNT = 9999


def _milliseconds(seconds):
    return min(MAX_MS, max(0, int(seconds * 1000)))


def _digest_mid(mid):
    # MAX IDs are short; do not allocate/hash arbitrarily large response strings.
    if not isinstance(mid, str) or not mid or len(mid) > 4096:
        return ""
    return hashlib.sha256(mid.encode("utf-8", "surrogatepass")).hexdigest()


class MediaOperation:
    """Fixed keys/counters; the only logger call occurs once in finish()."""
    __slots__ = ("active", "attachment_index", "attempts", "batch_id", "context_token",
                 "durations", "error", "error_stage", "file_fingerprint", "finished",
                 "media_type", "mid", "operation_id", "previous", "result", "sender",
                 "size", "source_id", "source_identified", "started", "status", "wait_ms")

    def __init__(self, sender, media_type):
        self.sender = sender if sender in {"adapter", "standalone"} else "unknown"
        self.media_type = media_type if media_type in {"file", "image", "audio", "video"} else "unknown"
        self.operation_id = uuid.uuid4().hex
        self.file_fingerprint = self.source_id = ""
        self.source_identified = False
        self.size = -1
        self.started = self.previous = time.monotonic()
        self.active = "prepare"
        self.durations = dict.fromkeys(STAGES, 0)
        self.attempts = dict.fromkeys(STAGES, 0)
        self.wait_ms = 0
        self.status = None
        self.error_stage = self.error = self.mid = ""
        self.result = "error"
        self.finished = False
        self.batch_id = ""
        self.attachment_index = -1

    def __enter__(self):
        self.context_token = _current.set(self)
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            self.finish("cancelled" if exc_type and issubclass(exc_type, asyncio.CancelledError) else self.result)
        finally:
            _current.reset(self.context_token)

    @contextmanager
    def bind(self):
        """Batch upload borrows context; its local caller owns final completion."""
        token = _current.set(self)
        try:
            yield self
        finally:
            _current.reset(token)

    def _settle(self):
        now = time.monotonic()
        self.durations[self.active] = min(MAX_MS, self.durations[self.active] + _milliseconds(now - self.previous))
        self.previous = now

    def begin(self, stage):
        if self.finished:
            return
        self._settle()
        self.active = stage if stage in STAGES else "prepare"
        self.status = None  # No response yet for this stage/attempt, not a prior CDN/API status.
        self.error_stage = self.error = ""
        self.attempts[self.active] = min(MAX_COUNT, self.attempts[self.active] + 1)

    def admit(self, info):
        if self.finished:
            return
        value = f"max-file-v1:{info.st_dev}:{info.st_ino}:{info.st_size}:{info.st_mtime_ns}"
        self.file_fingerprint = hashlib.sha256(value.encode("ascii")).hexdigest()
        self.size = min(4_000_000_000, max(0, info.st_size))

    def emit(self, stage, outcome, *, status=None, attempt=0, mid=""):
        """Accumulate a fixed schema, despite the historical helper name; no I/O."""
        if self.finished:
            return
        if stage == "result":
            self.finish(outcome, mid=mid)
            return
        if stage in STAGES:
            self._settle()
            self.active = stage
            if type(attempt) is int:
                self.attempts[stage] = min(MAX_COUNT, max(self.attempts[stage], attempt, 0))
        if type(status) is int and 100 <= status <= 599:
            self.status = status
        if outcome in {"error", "rejected", "not_ready", "budget_exhausted"}:
            self.error_stage = stage if stage in STAGES else self.active
            self.error = outcome
        if mid:
            self.mid = _digest_mid(mid)

    def finish(self, result, *, mid=""):
        if self.finished:
            return
        self._settle()
        self.finished = True  # Before any handler call; never replay a failed log write.
        self.result = result if result in {"success", "uploaded", "error", "cancelled"} else "error"
        if self.result in {"success", "uploaded"}:
            self.error_stage = self.error = ""
        elif self.result == "cancelled":
            self.error_stage, self.error = self.active, "cancelled"
        elif not self.error_stage:
            self.error_stage, self.error = self.active, "error"
        if mid:
            self.mid = _digest_mid(mid)
        row = {"operation_id": self.operation_id, "batch_id": self.batch_id,
               "attachment_index": self.attachment_index, "sender": self.sender,
               "media_type": self.media_type, "source_id": self.source_id,
               "file_fingerprint": self.file_fingerprint, "size": self.size,
               "durations_ms": self.durations, "attempts": self.attempts,
               "wait_ms": self.wait_ms, "elapsed_ms": _milliseconds(time.monotonic() - self.started),
               "result": self.result, "status": self.status, "error_stage": self.error_stage,
               "error": self.error, "mid": self.mid}
        try:
            logger.info("MAX media: %s", json.dumps(row, separators=(",", ":")))
        except Exception:  # noqa: BLE001, S110 — logging failures must not change/replay delivery.
            pass


def batch_operation(operations, index):
    """Local batch list only: one fixed accumulator per existing input item."""
    while len(operations) <= index:
        operation = MediaOperation("adapter", "image")
        operation.batch_id = operations[0].operation_id if operations else operation.operation_id
        operation.attachment_index = len(operations)
        operations.append(operation)
    return operations[index]


def identify_media_source(path):
    """Bounded lexical hashing in the existing normalization/admission worker."""
    operation = _current.get()
    if not isinstance(operation, MediaOperation) or operation.source_identified or operation.finished:
        return
    operation.source_identified = True
    try:
        path = os.fspath(path)
        if len(path) > 32768:
            raise ValueError("Source mapping input too long")
        lexical = os.fsencode(os.path.normcase(os.path.abspath(path)))
        if len(lexical) > 32768:
            raise ValueError("Source mapping input too long")
        digest = hashlib.sha256(b"max-source-path-v1\0" + lexical).hexdigest()
    except (OSError, TypeError, ValueError):
        return  # Mapping failure must not alter file admission/delivery.
    if not operation.finished:
        operation.source_id = digest


@contextmanager
def media_group(operations):
    """Borrow the validated request's <=12 owners for one shared send, not a cache."""
    token = _current.set(tuple(operations))
    try:
        yield
    finally:
        _current.reset(token)


def _active_operations():
    operation = _current.get()
    if operation is None:
        return ()
    return operation if isinstance(operation, tuple) else (operation,)


def media_begin(stage):
    for operation in _active_operations():
        operation.begin(stage)


def media_wait(seconds):
    for operation in _active_operations():
        if not operation.finished:
            operation.wait_ms = min(MAX_MS, operation.wait_ms + _milliseconds(seconds))


def media_event(stage, outcome, **kwargs):
    for operation in _active_operations():
        operation.emit(stage, outcome, **kwargs)


def admitted_media(info):
    operation = _current.get()
    if isinstance(operation, MediaOperation):
        operation.admit(info)


def trace_adapter_send(function):
    @wraps(function)
    async def wrapped(self, chat_id, file_path, mtype, caption, reply_to):
        existing = _current.get()
        if isinstance(existing, MediaOperation):
            result = await function(self, chat_id, file_path, mtype, caption, reply_to)
            existing.finish("success" if result.success else "error", mid=result.message_id)
            return result
        with MediaOperation("adapter", mtype) as operation:
            result = await function(self, chat_id, file_path, mtype, caption, reply_to)
            operation.finish("success" if result.success else "error", mid=result.message_id)
            return result
    return wrapped


def trace_remote_image(function):
    @wraps(function)
    async def wrapped(self, chat_id, image_url, *args, **kwargs):
        if image_url.startswith("file://"):
            return await function(self, chat_id, image_url, *args, **kwargs)
        existing = _current.get()
        if isinstance(existing, MediaOperation):
            result = await function(self, chat_id, image_url, *args, **kwargs)
            existing.finish("success" if result.success else "error", mid=result.message_id)
            return result
        with MediaOperation("adapter", "image") as operation:
            result = await function(self, chat_id, image_url, *args, **kwargs)
            operation.finish("success" if result.success else "error", mid=result.message_id)
            return result
    return wrapped


def trace_adapter_upload(function):
    @wraps(function)
    async def wrapped(self, file_path, media_type):
        if _current.get() is not None:
            return await function(self, file_path, media_type)
        with MediaOperation("adapter", media_type) as operation:
            result = await function(self, file_path, media_type)
            operation.finish("uploaded" if result else "error")
            return result
    return wrapped
