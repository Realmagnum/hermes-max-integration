from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from urllib.parse import urlparse

import httpx
from gateway.config import PlatformConfig
from gateway.platforms.base import SendResult

try:
    from ..ssl_support import get_max_ssl_context
except (ImportError, ValueError):
    from ssl_support import get_max_ssl_context
from ..credential_support import get_max_secret
from .media_upload import _ALLOWED_UPLOAD_HOSTS

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

    parts = chat_id.split(":", 1)
    target_type = parts[0] if len(parts) > 1 else "user"
    target_id = parts[1] if len(parts) > 1 else chat_id

    params = {"chat_id": target_id} if target_type == "chat" else {"user_id": target_id}
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


async def _standalone_send(
    pconfig: PlatformConfig,
    chat_id: str,
    message: str,
    *,
    thread_id: str | None = None,
    media_files: list[tuple[str, bool]] | None = None,
    force_document: bool = False,
) -> dict:
    """Standalone sender contract for send_message/cron delivery.

    Supports native file delivery from Core-provided ``media_files`` descriptors:
    uploads each file via the 3-step MAX protocol, and attaches them to the
    outgoing message. Works with or without a running gateway adapter.
    """
    del thread_id, force_document

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
                parts = chat_id.split(":", 1)
                target_type = parts[0] if len(parts) > 1 else "user"
                target_id = parts[1] if len(parts) > 1 else chat_id
                params = {"chat_id": target_id} if target_type == "chat" else {"user_id": target_id}
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
                if not os.path.exists(media_path):
                    logger.warning("MAX: standalone media file not found: %s", media_path)
                    continue

                # Determine attachment type from extension (for native playback)
                _ATTACH_TYPES = {
                    ".jpg": "image", ".jpeg": "image", ".png": "image",
                    ".webp": "image", ".gif": "image", ".bmp": "image",
                    ".mp4": "video", ".mov": "video", ".avi": "video",
                    ".mkv": "video", ".webm": "video",
                    ".mp3": "audio", ".wav": "audio", ".ogg": "audio",
                    ".opus": "audio", ".m4a": "audio", ".flac": "audio",
                }
                _ext = os.path.splitext(media_path)[1].lower()
                _attach_type = _ATTACH_TYPES.get(_ext, "file")
                _upload_token = ""

                # Step 1: get upload URL
                # For audio/video: use proper type so /uploads returns a token
                # For file/image: use type=file for reliability
                _upload_type = _attach_type if _attach_type in ("audio", "video") else "file"
                try:
                    resp = await client.post(f"{MAX_API_BASE}/uploads", params={"type": _upload_type}, headers=headers)
                    if resp.status_code != 200:
                        logger.warning("MAX: upload URL request failed for %s (status %d)", media_path, resp.status_code)
                        # Fall back to type=file for audio/video
                        if _upload_type in ("audio", "video"):
                            resp = await client.post(f"{MAX_API_BASE}/uploads", params={"type": "file"}, headers=headers)
                            if resp.status_code != 200:
                                continue
                            _upload_type = "file"
                        else:
                            continue
                    upload_json = resp.json()
                    upload_url = upload_json.get("url", "")
                    if not upload_url:
                        logger.warning("MAX: upload URL response missing 'url' for %s", media_path)
                        continue
                    # For audio/video: token comes from /uploads response itself
                    if _upload_type in ("audio", "video"):
                        _upload_token = upload_json.get("token", "")
                        if _upload_token:
                            logger.info("MAX: audio/video token obtained from /uploads for %s", media_path)
                except Exception as e:  # noqa: BLE001 — adapter must not crash on transport/API errors
                    logger.warning("MAX: upload URL parse failed for %s: %s", media_path, e)
                    continue

                logger.info("MAX: upload url obtained for %s: %s", media_path, upload_url[:80])

                # SSRF protection: only upload to known MAX/CDN domains
                parsed_upload = urlparse(upload_url)
                if not parsed_upload.hostname or not (
                    parsed_upload.hostname in _ALLOWED_UPLOAD_HOSTS
                    or parsed_upload.hostname.endswith(".max.ru")
                    or parsed_upload.hostname.endswith(".oneme.ru")
                    or parsed_upload.hostname.endswith(".okcdn.ru")
                    or parsed_upload.hostname.endswith(".cdn-max.ru")
                ):
                    logger.warning("MAX: upload URL rejected (SSRF): %s", upload_url[:80])
                    continue

                # Step 2: upload file as multipart
                try:
                    import aiohttp as _aiohttp
                    aio_conn = _aiohttp.TCPConnector(ssl=get_max_ssl_context())
                    async with _aiohttp.ClientSession(connector=aio_conn, timeout=_aiohttp.ClientTimeout(total=120)) as aio_session:
                        # Read file bytes off the event loop (ASYNC230).
                        file_bytes = await asyncio.to_thread(Path(media_path).read_bytes)
                        form = _aiohttp.FormData()
                        form.add_field("data", file_bytes, filename=os.path.basename(media_path))
                        async with aio_session.post(upload_url, data=form) as r:
                                if r.status != 200:
                                    try:
                                        err_body = await r.text()
                                        logger.warning("MAX: CDN upload failed for %s (status %d): %s", media_path, r.status, err_body[:200])
                                    except Exception:  # noqa: BLE001 — adapter must not crash on transport/API errors
                                        logger.warning("MAX: CDN upload failed for %s (status %d)", media_path, r.status)
                                    # For audio/video with token from /uploads: even if CDN fails, we might still try
                                    if _upload_type in ("audio", "video") and _upload_token:
                                        logger.info("MAX: CDN failed but using token from /uploads anyway for %s", media_path)
                                        file_token = _upload_token
                                    else:
                                        continue
                                else:
                                    # For audio/video: use token from /uploads (CDN just returns <retval>1</retval>)
                                    if _upload_type in ("audio", "video") and _upload_token:
                                        file_token = _upload_token
                                    else:
                                        # For file/image: parse CDN JSON response for token
                                        try:
                                            upload_data = await r.json()
                                        except Exception:  # noqa: BLE001 — adapter must not crash on transport/API errors
                                            logger.warning("MAX: CDN returned non-JSON for %s", media_path)
                                            continue
                                        file_token = upload_data.get("token")
                                        if not file_token:
                                            # type=image returns: {"photos": {"id": {"token": "..."}}}
                                            photos = upload_data.get("photos", {})
                                            if isinstance(photos, dict):
                                                for _pdata in photos.values():
                                                    if isinstance(_pdata, dict) and _pdata.get("token"):
                                                        file_token = _pdata["token"]
                                                        break
                                        if not file_token:
                                            logger.warning("MAX: CDN response missing token for %s", media_path)
                                            continue
                except Exception as e:  # noqa: BLE001 — adapter must not crash on transport/API errors
                    logger.warning("MAX: CDN upload error for %s: %s", media_path, e)
                    continue

                # Wait for MAX to process the file
                await asyncio.sleep(UPLOAD_DELAY)

                # Step 3: send message with attachment (with retry for attachment.not.ready)
                parts = chat_id.split(":", 1)
                target_type = parts[0] if len(parts) > 1 else "user"
                target_id = parts[1] if len(parts) > 1 else chat_id
                params = {"chat_id": target_id} if target_type == "chat" else {"user_id": target_id}
                body = {
                    "text": os.path.basename(media_path),
                    "attachments": [{"type": _attach_type, "payload": {"token": file_token}}],
                }
                _sent_ok = False
                for _retry in range(3):
                    try:
                        resp = await client.post(f"{MAX_API_BASE}/messages", params=params, json=body, headers=headers)
                        if resp.status_code in (200, 201):
                            data = resp.json()
                            if data.get("ok", True) is not False:
                                last_message_id = str(
                                    data.get("message", {}).get("body", {}).get("mid", "")
                                    or data.get("message", {}).get("message_id", "")
                                    or ""
                                )
                                _sent_ok = True
                                break
                        elif resp.status_code == 400:
                            err_body = resp.json()
                            if err_body.get("code") == "attachment.not.ready":
                                logger.info("MAX: attachment not ready for %s, retrying...", media_path)
                                await asyncio.sleep(5.0)
                                continue
                            logger.warning("MAX: message rejected for %s: %s", media_path, err_body)
                            break
                        else:
                            logger.warning("MAX: send failed for %s (status %d)", media_path, resp.status_code)
                            break
                    except Exception as _exc:  # noqa: BLE001 — adapter must not crash on transport/API errors
                        logger.warning("MAX: send exception for %s: %s", media_path, _exc)
                        break
                if not _sent_ok:
                    continue
                delivered_media += 1

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
        logger.error("MAX: standalone send failed: %s", exc)
        return delivery_error("MAX standalone send failed (see logs)")
