from __future__ import annotations

import asyncio
import logging
import os
from urllib.parse import urlparse

import httpx
from gateway.config import PlatformConfig
from gateway.platforms.base import SendResult

try:
    from ..ssl_support import get_max_ssl_context
except (ImportError, ValueError):
    from ssl_support import get_max_ssl_context
from ..credential_support import get_max_secret
from ..media_caption import media_caption
from .base import _message_recipient_params
from .media_diagnostics import MediaOperation, media_begin, media_event
from .media_readiness import readiness_settings, send_ready_attachment
from .media_upload import _ALLOWED_UPLOAD_HOSTS
from .upload_stream import async_check_upload, post_file, upload_timeout

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────

MAX_API_BASE = "https://platform-api2.max.ru"
MAX_MESSAGE_LENGTH = 4000
UPLOAD_DELAY = 2.0


# ═════════════════════════════════════════════════════════════════════════
# Standalone sender (for cron jobs and send_message tool)
# ═════════════════════════════════════════════════════════════════════════


async def _send_max_message(pconfig: PlatformConfig, chat_id: str, message: str) -> SendResult:
    """Send a message via Max API without the full adapter."""
    token = _standalone_get_token(pconfig)
    if not token:
        return SendResult(success=False, error="MAX_BOT_TOKEN not configured")

    params = _message_recipient_params(chat_id)
    body = {"text": message[:MAX_MESSAGE_LENGTH], "format": "markdown"}
    headers = {"Authorization": token, "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0), verify=get_max_ssl_context()) as client:
            resp = await client.post(f"{MAX_API_BASE}/messages", params=params, json=body, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return SendResult(
                success=True,
                message_id=str(data.get("message", {}).get("message_id", "")),
            )
    except Exception as exc:  # noqa: BLE001 — adapter must not crash on transport/API errors
        logger.error("MAX: send_message failed: %s", exc)
        return SendResult(success=False, error="Standalone send failed (see logs)")


def _standalone_get_token(pconfig: PlatformConfig) -> str:
    """Extract MAX bot token from config/env in the standalone path."""
    extra = getattr(pconfig, "extra", {}) or {}
    return get_max_secret("MAX_BOT_TOKEN", getattr(pconfig, "token", "") or extra.get("token", ""))


def _attachment_type(path):
    _ATTACH_TYPES = {
        ".jpg": "image", ".jpeg": "image", ".png": "image",
        ".webp": "image", ".gif": "image", ".bmp": "image",
        ".mp4": "video", ".mov": "video", ".avi": "video",
        ".mkv": "video", ".webm": "video",
        ".mp3": "audio", ".wav": "audio", ".ogg": "audio",
        ".opus": "audio", ".m4a": "audio", ".flac": "audio",
    }
    return _ATTACH_TYPES.get(os.path.splitext(path)[1].lower(), "file")


async def _standalone_send(
    pconfig: PlatformConfig,
    chat_id: str,
    message: str,
    *,
    thread_id: str | None = None,
    media_files: list[tuple[str, bool]] | None = None,
    force_document: bool = False,
    caption: str | None = None,
) -> dict:
    """Standalone sender contract for send_message/cron delivery.

    Supports native file delivery from Core-provided ``media_files`` descriptors:
    uploads each file via the 3-step MAX protocol, and attaches them to the
    outgoing message. Works with or without a running gateway adapter.

    ``caption`` is set by Core when a single file plus short text should ride on the
    media bubble (``StandaloneSendPolicy.captionable``); the text is then not sent as
    a separate message, so the recipient sees one message instead of two.
    """
    del thread_id, force_document

    processed_media = 0
    cancelled = False
    try:
        token = _standalone_get_token(pconfig)
        if not token:
            return {"error": "MAX_BOT_TOKEN not configured"}

        headers = {"Authorization": token, "Content-Type": "application/json"}
        requested_media = len(media_files or [])
        delivered_media = 0
        text_delivered = False
        last_message_id: str | None = None

        def delivery_error(reason):
            return {
                "error": f"{reason}: {delivered_media}/{requested_media} media files delivered",
                "media_requested": requested_media,
                "media_sent": delivered_media,
                "media_delivered": False,
                "text_delivered": text_delivered,
                "partial_delivery": text_delivered or delivered_media > 0,
                "message_id": last_message_id,
            }

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120.0), verify=get_max_ssl_context()) as client:
                # 1. Send text message first
                if message and message.strip():
                    params = _message_recipient_params(chat_id)
                    body = {"text": message[:MAX_MESSAGE_LENGTH], "format": "markdown"}
                    resp = await client.post(f"{MAX_API_BASE}/messages", params=params, json=body, headers=headers)
                    resp.raise_for_status()
                    data = resp.json()
                    if data.get("ok", True) is False:
                        return delivery_error("MAX rejected the text message")
                    text_delivered = True
                    last_message_id = str(data.get("message", {}).get("message_id", "") or data.get("message", {}).get("body", {}).get("mid", ""))

                # 2. Upload and send each media file
                for media_item in (media_files or []):
                    media_path, _ = media_item if isinstance(media_item, (list, tuple)) else (media_item, False)
                    _attach_type = _attachment_type(media_path)
                    processed_media += 1
                    with MediaOperation("standalone", _attach_type) as operation:
                        media_begin("admission")
                        try:
                            file_size = await async_check_upload(media_path, _attach_type)
                        except (OSError, ValueError):
                            continue
                        _upload_token = ""

                        # Step 1: get upload URL
                        # The upload `type` decides which CDN backend issues the token, and the
                        # attachment `type` in step 3 must match it: a token issued by `type=file`
                        # (fu.oneme.ru) is rejected by MAX as "Invalid photo token" when sent as an
                        # image attachment. So image/audio/video upload with their own type, and
                        # anything else (documents, archives, unknown extensions) goes as `file`.
                        _upload_type = _attach_type if _attach_type in ("audio", "video", "image") else "file"
                        diagnostic_attempt = 1
                        try:
                            media_begin("upload_url")
                            resp = await client.post(f"{MAX_API_BASE}/uploads", params={"type": _upload_type}, headers=headers)
                            media_event("upload_url", "success" if resp.status_code == 200 else "error", status=resp.status_code, attempt=1)
                            if resp.status_code != 200:
                                # Fall back to type=file — the token then only works as a file attachment.
                                if _upload_type != "file":
                                    diagnostic_attempt = 2
                                    media_begin("upload_url")
                                    resp = await client.post(f"{MAX_API_BASE}/uploads", params={"type": "file"}, headers=headers)
                                    media_event("upload_url", "success" if resp.status_code == 200 else "error", status=resp.status_code, attempt=2)
                                    if resp.status_code != 200:
                                        continue
                                    _upload_type = "file"
                                    _attach_type = "file"
                                    operation.media_type = _attach_type
                                else:
                                    continue
                            upload_json = resp.json()
                            upload_url = upload_json.get("url", "")
                            if not upload_url:
                                continue
                            # For audio/video: token comes from /uploads response itself
                            if _upload_type in ("audio", "video"):
                                _upload_token = upload_json.get("token", "")
                        except Exception:  # noqa: BLE001 — adapter must not crash on transport/API errors
                            media_event("upload_url", "error", attempt=diagnostic_attempt)
                            continue

                        # SSRF protection: only upload to known MAX/CDN domains
                        parsed_upload = urlparse(upload_url)
                        if not parsed_upload.hostname or not (
                            parsed_upload.hostname in _ALLOWED_UPLOAD_HOSTS
                            or parsed_upload.hostname.endswith(".max.ru")
                            or parsed_upload.hostname.endswith(".oneme.ru")
                            or parsed_upload.hostname.endswith(".okcdn.ru")
                            or parsed_upload.hostname.endswith(".cdn-max.ru")
                        ):
                            media_event("upload_url", "rejected")
                            continue

                        # Step 2: upload file as multipart
                        try:
                            media_begin("cdn")
                            import aiohttp as _aiohttp
                            aio_conn = _aiohttp.TCPConnector(ssl=get_max_ssl_context())
                            async with _aiohttp.ClientSession(connector=aio_conn, timeout=_aiohttp.ClientTimeout(total=upload_timeout(file_size), sock_connect=30, sock_read=120)) as aio_session:
                                status, upload_data = await post_file(aio_session, upload_url, media_path, _upload_type, admitted=file_size)
                                media_event("cdn", "success" if status == 200 else "error", status=status, attempt=1)
                                if status != 200:
                                    continue
                                file_token = _upload_token
                                if not file_token:
                                    file_token = upload_data.get("token")
                                    photos = upload_data.get("photos", {})
                                    if not file_token and isinstance(photos, dict):
                                        for photo in photos.values():
                                            if isinstance(photo, dict) and photo.get("token"):
                                                file_token = photo["token"]
                                                break
                                if not isinstance(file_token, str) or not file_token:
                                    continue
                        except Exception:  # noqa: BLE001 — adapter must not crash on transport/API errors
                            media_event("cdn", "error", attempt=1)
                            continue

                        # Upload once; share the adapter's bounded definite-rejection policy.
                        params = _message_recipient_params(chat_id)
                        body = {
                            "text": media_caption(caption, media_path),
                            "attachments": [{"type": _attach_type, "payload": {"token": file_token}}],
                        }
                        attempts, timeout = readiness_settings(getattr(pconfig, "extra", {}) or {})
                        result = await send_ready_attachment(
                            client, f"{MAX_API_BASE}/messages", params, body,
                            attempts, timeout, headers=headers,
                        )
                        if not result.success:
                            continue
                        last_message_id = result.message_id
                        operation.emit("result", "success", mid=result.message_id)
                        delivered_media += 1
                        # The caption is the caller's text riding on this message: once it is
                        # delivered the text counts as delivered, otherwise a captionable send
                        # would report text_delivered=False even though the user read the text.
                        if caption and caption.strip():
                            text_delivered = True
                if delivered_media != requested_media:
                    return delivery_error("MAX attachment delivery incomplete")
                if not text_delivered and not delivered_media:
                    return delivery_error("No deliverable text or media")
                return {
                    "success": True,
                    "message_id": last_message_id,
                    "media_delivered": bool(requested_media),
                    "media_sent": delivered_media,
                    "text_delivered": text_delivered,
                }
        except Exception as exc:  # noqa: BLE001 — adapter must not crash on transport/API errors
            if not media_files:
                logger.error("MAX: standalone send failed: error_type=%s", type(exc).__name__)
            return delivery_error("MAX standalone send failed (see logs)")
    except asyncio.CancelledError:
        cancelled = True
        raise
    finally:
        # Inputs never reached because preparation/cancellation failed still get
        # a single unknown-source completion; already processed contexts finalized.
        for index in range(processed_media, len(media_files or [])):
            item = media_files[index]
            try:
                path = item[0] if isinstance(item, (list, tuple)) else item
                kind = _attachment_type(path)
            except Exception:  # noqa: BLE001 — diagnostics must not alter malformed-input behavior.
                kind = "unknown"
            with MediaOperation("standalone", kind) as operation:
                operation.finish("cancelled" if cancelled else "error")
