from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from gateway.platforms.base import SendResult

from .base import MaxBaseMixin

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────

MAX_API_BASE = "https://platform-api.max.ru"
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
UPLOAD_DELAY = 2.0

# SSRF allowlist for file upload CDNs (used by both adapter and standalone sender)
_ALLOWED_UPLOAD_HOSTS = frozenset({
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


class MediaUploadMixin(MaxBaseMixin):
    """
    Mixin for CDN file upload and send logic.

    Provides two-step upload (POST /uploads -> PUT file via multipart -> token -> send)
    with retry for CDN processing delays.
    """

    async def _upload_send(
        self, chat_id: str, file_path: str, mtype: str,
        caption: str, reply_to: str | None,
    ) -> SendResult:
        """Upload file then send as attachment.

        Retries up to 3 times with exponential backoff (2/4/6s) when MAX
        returns ``attachment.not.ready`` — the CDN needs time to scan
        and validate the uploaded file before it can be attached.
        """
        if not self._http_client:
            return SendResult(success=False, error="Not connected")

        token = await self._upload(file_path, mtype)
        if not token:
            return SendResult(success=False, error="Upload failed")

        parts = chat_id.split(":", 1)
        target_type = parts[0] if len(parts) > 1 else "user"
        target_id = parts[1] if len(parts) > 1 else chat_id
        params = {"chat_id": target_id} if target_type == "chat" else {"user_id": target_id}

        body: dict[str, Any] = {
            "text": caption,
            "attachments": [{"type": mtype, "payload": {"token": token}}],
        }
        if reply_to:
            body["link"] = {"type": "REPLY", "mid": reply_to}

        max_retries = 3
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    delay = 2.0 * (2 ** (attempt - 1))  # 2s, 4s, 6s
                    await asyncio.sleep(delay)

                resp = await self._http_client.post(f"{MAX_API_BASE}/messages", params=params, json=body)
                resp.raise_for_status()
                d = resp.json()
                mid = str((d.get("message", {}).get("body", {}) or {}).get("mid", ""))
                return SendResult(success=True, message_id=mid, raw_response=d)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 400:
                    try:
                        err_body = e.response.json()
                        code = err_body.get("code", "")
                        if code == "attachment.not.ready" and attempt + 1 < max_retries:
                            logger.info("MAX: upload not ready (attempt %d/%d), retrying…", attempt + 1, max_retries)
                            continue
                    except (json.JSONDecodeError, TypeError):
                        pass
                logger.error("MAX: _upload_send failed: %s", e)
                return SendResult(success=False, error="Upload-send failed (see logs)", retryable=True)
            except Exception as e:
                logger.error("MAX: _upload_send failed: %s", e)
                return SendResult(success=False, error="Upload-send failed (see logs)", retryable=True)

        return SendResult(success=False, error="Upload-send failed: attachment still not ready after retries", retryable=True)

    async def _upload(self, file_path: str, media_type: str) -> str | None:
        """Two-step upload: get upload URL -> POST file (multipart) -> return token."""
        import aiohttp as _aiohttp

        fp = Path(file_path)
        if not fp.exists() or fp.stat().st_size > MAX_FILE_SIZE:
            return None

        try:
            # Step 1: get upload URL
            resp = await self._http_client.post(f"{MAX_API_BASE}/uploads", params={"type": media_type})
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
                logger.warning(
                    "MAX: upload URL rejected (not in Max domain): %s",
                    _safe_url_for_log(upload_url),
                )
                return None

            # Step 2: upload file to the URL (use aiohttp for multipart)
            async with _aiohttp.ClientSession(timeout=_aiohttp.ClientTimeout(total=120)) as session:
                with open(fp, "rb") as f:
                    form = _aiohttp.FormData()
                    form.add_field("data", f, filename=fp.name)
                    async with session.post(upload_url, data=form) as r:
                        if r.status != 200:
                            logger.warning(
                                "MAX: CDN upload failed for %s (status %d, type=%s)",
                                fp, r.status, media_type,
                            )
                            if media_type in ("audio", "video") and upload_token:
                                logger.info("MAX: audio/video CDN failed but we have token from /uploads, still trying")
                            else:
                                return None

                        # For audio/video: token already obtained from /uploads response
                        if upload_token:
                            return upload_token

                        # For file/image: parse CDN JSON response for token
                        try:
                            upload_data = await r.json()
                        except Exception:
                            logger.warning(
                                "MAX: CDN returned non-JSON for %s (type=%s)",
                                fp, media_type,
                            )
                            if media_type in ("audio", "video"):
                                return await self._upload(str(fp), "file")
                            return None
                        token = upload_data.get("token")
                        if not token and "photos" in upload_data:
                            photos = upload_data["photos"]
                            if isinstance(photos, dict):
                                first = next(iter(photos.values()), {})
                                token = first.get("token") if isinstance(first, dict) else None
                        if not token:
                            logger.warning(
                                "MAX: CDN response missing token for %s (type=%s)",
                                fp.name, media_type,
                            )
                            if media_type in ("audio", "video"):
                                return await self._upload(str(fp), "file")
                            return None
                        return token
        except Exception as e:
            logger.error("MAX: upload error: %s", e)
            return None
