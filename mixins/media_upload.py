from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from gateway.platforms.base import SendResult

from .base import MaxBaseMixin, _message_recipient_params
from .media_diagnostics import (
    identify_media_source,
    media_begin,
    media_event,
    trace_adapter_send,
    trace_adapter_upload,
)
from .media_readiness import send_ready_attachment
from .upload_stream import async_check_upload, post_file, upload_timeout

try:
    from ..media_caption import media_caption
except (ImportError, ValueError):  # Legacy flat mixins import used by existing checks.
    from media_caption import media_caption

try:
    from ..ssl_support import get_max_ssl_context
except (ImportError, ValueError):
    from ssl_support import get_max_ssl_context

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────

MAX_API_BASE = "https://platform-api2.max.ru"
# Upload admission uses UPLOAD_LIMITS in upload_stream; remote fetch has its own cap.
UPLOAD_DELAY = 2.0

# Audio containers the Max CDN accepts for type=audio attachments.
# Verified: ogg/opus (native voice) and mp3 (edge TTS delivered fine).
# Anything else (wav, flac, m4a, ...) is transcoded to Ogg/Opus before
# upload so the delivery does not depend on what the TTS provider emits.
_AUDIO_PASSTHROUGH_CONTAINERS = frozenset({"ogg", "mp3"})

# SSRF allowlist for file upload CDNs (used by both adapter and standalone sender)
_ALLOWED_UPLOAD_HOSTS = frozenset({
    "platform-api2.max.ru",
    "platform-api.max.ru",
    "cdn.max.ru",
    "storage.max.ru",
    "upload.max.ru",
    "iu.oneme.ru",
    "fu.oneme.ru",
})


def _safe_url_for_log(url: str) -> str:
    """Strip credentials from URL for logging."""
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return "[invalid-url]"
    path = parsed.path or "/"
    return f"{parsed.scheme}://{parsed.netloc}{path}"


# ── Audio container normalization ────────────────────────────────────────
# TTS providers emit whatever format they emit (wav, mp3, ogg, flac, ...).
# The Max CDN rejects some containers (wav → 415), so normalize the file
# to a Max-accepted container before upload. Idempotent: already-accepted
# containers (ogg, mp3) pass through untouched; anything else is
# transcoded to Ogg/Opus via ffmpeg in place.


def _sniff_audio_container(path: str) -> str:
    """Return container id ('ogg', 'mp3', 'wav', 'flac', 'm4a') or 'unknown'."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(12)
    except OSError:
        return "unknown"
    if head.startswith(b"OggS"):
        return "ogg"
    if head.startswith(b"ID3") or (len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0):
        return "mp3"
    if head.startswith(b"RIFF") and head[8:12] == b"WAVE":
        return "wav"
    if head.startswith(b"fLaC"):
        return "flac"
    if head[4:8] == b"ftyp":
        return "m4a"
    return "unknown"


def _transcode_to_opus_ogg(src: str, dst: str) -> bool:
    """Transcode *src* to Ogg/Opus at *dst* using ffmpeg. Returns success."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        media_event("normalize", "error")
        return False
    try:
        proc = subprocess.run(
            [ffmpeg, "-y", "-i", src, "-c:a", "libopus", "-b:a", "48k", dst],
            capture_output=True,
            timeout=120,
            check=False,
        )
        if proc.returncode != 0:
            media_event("normalize", "error")
            return False
        return os.path.exists(dst) and os.path.getsize(dst) > 0
    except Exception:  # noqa: BLE001 — normalization must never break delivery
        media_event("normalize", "error")
        return False


def normalize_audio_for_max(path: str) -> str:
    """Return a path whose audio container the Max CDN accepts.

    Idempotent: ogg/mp3 pass through unchanged (same file, same bytes);
    other containers are transcoded to a NEW ``.ogg`` file next to the
    source (the CDN decides the format from the uploaded filename, so the
    extension must be honest — an in-place transcode of a ``.wav`` path
    still 415s). On any failure the original file is left untouched and
    returned, so the caller can still try.
    """
    container = _sniff_audio_container(path)
    if container in _AUDIO_PASSTHROUGH_CONTAINERS or container == "unknown":
        return path

    src = Path(path)
    dst = src.with_suffix(".ogg")
    try:
        if not _transcode_to_opus_ogg(path, str(dst)):
            return path
        return str(dst)
    except Exception:  # noqa: BLE001 — normalization must never break delivery
        media_event("normalize", "error")
        try:
            if dst.exists():
                dst.unlink()
        except OSError:
            pass
        return path


def _normalize_with_source(path):
    identify_media_source(path)
    return normalize_audio_for_max(path)


class MediaUploadMixin(MaxBaseMixin):
    """
    Mixin for CDN file upload and send logic.

    Provides two-step upload (POST /uploads -> PUT file via multipart -> token -> send)
    with retry for CDN processing delays.
    """

    @trace_adapter_send
    async def _upload_send(
        self, chat_id: str, file_path: str, mtype: str,
        caption: str, reply_to: str | None,
    ) -> SendResult:
        """Upload file then send as attachment.

        Upload once, then retry only an explicit HTTP 400 attachment.not.ready.
        Keep the first 2/4s waits, then cap backoff at 16s, within a total
        readiness budget (including POST time). Ambiguous sends are never retried.
        """
        if not self._http_client:
            return SendResult(success=False, error="Not connected")

        # Emit chat action indicator so the user sees immediate feedback while uploading
        action_map = {
            "image": "sending_photo",
            "video": "sending_video",
            "audio": "sending_audio",
            "file": "sending_file",
        }
        action = action_map.get(mtype, "sending_file")
        try:
            await self.send_action(chat_id, action)
        except Exception:  # noqa: BLE001, S110 — cosmetic action failure must not add log noise.
            pass

        # Normalize audio to a Max-accepted container regardless of what the
        # TTS provider emitted (wav/flac/m4a are rejected by the CDN with 415).
        if mtype == "audio":
            media_begin("normalize")
            file_path = await asyncio.to_thread(_normalize_with_source, file_path)

        token = await self._upload(file_path, mtype)
        if not token:
            return SendResult(success=False, error="Upload failed")

        body: dict[str, Any] = {
            "text": media_caption(caption, file_path),
            "attachments": [{"type": mtype, "payload": {"token": token}}],
        }
        if reply_to:
            body["link"] = {"type": "REPLY", "mid": reply_to}

        return await self._send_attachment_body(chat_id, body)

    async def _send_attachment_body(self, chat_id: str, body: dict[str, Any]) -> SendResult:
        """Send a validated attachment body; ambiguous effects are not repeated."""
        params = _message_recipient_params(chat_id)
        if ":" not in chat_id and "user_id" in params:
            params["user_id"] = self._dm_user_ids.get(chat_id, params["user_id"])
        result = await send_ready_attachment(
            self._http_client, f"{MAX_API_BASE}/messages", params, body,
            self._media_ready_attempts, self._media_ready_timeout,
        )
        if result.success:
            try:
                rec = result.raw_response.get("message", {}).get("recipient", {})
                resp_cid = rec.get("chat_id")
                resp_uid = rec.get("user_id") or params.get("user_id")
                if resp_cid and resp_uid:
                    self._remember_dm(resp_cid, resp_uid)
            except Exception:  # noqa: BLE001 — post-send parsing must never replay
                media_event("send", "error")
                return SendResult(success=False, error="Upload-send failed (see logs)", retryable=False)
        return result

    @trace_adapter_upload
    async def _upload(self, file_path: str, media_type: str) -> str | None:
        """Two-step upload: get upload URL -> POST file (multipart) -> return token."""
        import aiohttp as _aiohttp

        media_begin("admission")
        try:
            file_size = await async_check_upload(file_path, media_type)
        except (OSError, ValueError):
            return None

        diagnostic_stage = "upload_url"
        try:
            # Step 1: get upload URL
            media_begin("upload_url")
            resp = await self._http_client.post(f"{MAX_API_BASE}/uploads", params={"type": media_type})
            media_event("upload_url", "success" if resp.status_code == 200 else "error", status=resp.status_code, attempt=1)
            if resp.status_code != 200:
                return None
            data = resp.json()
            upload_url = data.get("url")
            if not upload_url:
                return None

            # audio/video: token comes from POST /uploads response itself
            # file/image: token comes from CDN upload response
            upload_token = data.get("token") if media_type in ("audio", "video") else None

            # SECURITY: Only upload to known Max/Cdn domains (SSRF prevention).
            # If the API returns an unexpected URL, refuse to connect.
            parsed = urlparse(upload_url)
            if parsed.hostname and (
                parsed.hostname in _ALLOWED_UPLOAD_HOSTS
                or parsed.hostname.endswith(".max.ru")
                or parsed.hostname.endswith(".oneme.ru")
                or parsed.hostname.endswith(".okcdn.ru")
            ):
                pass  # Safe — within Max infrastructure
            else:
                media_event("upload_url", "rejected")
                return None

            # Step 2: upload file to the URL (use aiohttp for multipart)
            diagnostic_stage = "cdn"
            media_begin("cdn")
            connector = _aiohttp.TCPConnector(ssl=get_max_ssl_context())
            async with _aiohttp.ClientSession(connector=connector, timeout=_aiohttp.ClientTimeout(total=upload_timeout(file_size), sock_connect=30, sock_read=120)) as session:
                status, upload_data = await post_file(session, upload_url, file_path, media_type, admitted=file_size)
                media_event("cdn", "success" if status == 200 else "error", status=status, attempt=1)
                if status != 200:
                    return None
                if upload_token:
                    return upload_token
                token = upload_data.get("token")
                if not token and isinstance(upload_data.get("photos"), dict):
                    first = next(iter(upload_data["photos"].values()), {})
                    token = first.get("token") if isinstance(first, dict) else None
                return token if isinstance(token, str) and token else None
        except Exception:  # noqa: BLE001 — adapter must not crash on transport/API errors
            media_event(diagnostic_stage, "error", attempt=1)
            return None
