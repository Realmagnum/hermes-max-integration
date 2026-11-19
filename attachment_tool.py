"""MAX attachment tool: fixed current-session destination, closed payload grammar."""
from __future__ import annotations

import asyncio
import ipaddress
import json
import math
import os
import re
import stat
from urllib.parse import urlsplit

import httpx
from gateway.config import PlatformConfig
from gateway.session_context import get_session_env

from .credential_support import get_max_secret
from .ssl_support import get_max_ssl_context

MEDIA = {"image", "video", "audio", "file"}
TYPES = MEDIA | {"sticker", "contact", "inline_keyboard", "location", "share"}
BUTTONS = {"callback", "link", "request_geo_location", "request_contact", "open_app", "message", "clipboard"}


def fields(obj, allowed, required=()):
    if not isinstance(obj, dict) or set(obj) - set(allowed) or set(required) - set(obj):
        raise ValueError("Invalid or unknown attachment fields")


def string(value, maximum=4096, minimum=1):
    if not isinstance(value, str) or not minimum <= len(value) <= maximum:
        raise ValueError("Invalid string length")


def url(value):
    string(value, 2048)
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Expected public HTTPS URL without credentials")
    host = parsed.hostname.lower().rstrip(".")
    if host == "localhost" or host.endswith((".localhost", ".local")) or "." not in host:
        raise ValueError("Private URL rejected")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return
    if not address.is_global:
        raise ValueError("Private URL rejected")


def keyboard(payload):
    fields(payload, {"buttons"}, {"buttons"})
    rows = payload["buttons"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 30:
        raise ValueError("Keyboard requires 1..30 rows")
    for row in rows:
        if not isinstance(row, list) or not 1 <= len(row) <= 7:
            raise ValueError("Keyboard requires 1..7 buttons per row")
        if any(isinstance(b, dict) and b.get("type") in {"link", "open_app", "request_geo_location", "request_contact"} for b in row) and len(row) > 3:
            raise ValueError("Special button row maximum is 3")
        for b in row:
            if not isinstance(b, dict) or b.get("type") not in BUTTONS:
                raise ValueError("Unknown button type")
            kind = b["type"]
            extra = {"callback": {"payload"}, "link": {"url"},
                     "request_geo_location": {"quick"}, "request_contact": set(),
                     "open_app": {"web_app", "contact_id", "payload"}, "message": set(),
                     "clipboard": {"payload"}}[kind]
            fields(b, {"type", "text"} | extra, {"type", "text"})
            string(b["text"], 128)
            if kind in {"callback", "clipboard"}:
                string(b.get("payload"), 1024, 0)
            if kind == "link":
                url(b.get("url"))

            if "quick" in b and not isinstance(b["quick"], bool):
                raise ValueError("quick must be boolean")
            if kind == "open_app":
                if not (b.get("web_app") or b.get("contact_id")):
                    raise ValueError("open_app requires web_app or contact_id")
                if "web_app" in b:
                    string(b["web_app"], 2048)
                if "contact_id" in b and (type(b["contact_id"]) is not int or b["contact_id"] <= 0):
                    raise ValueError("Invalid contact_id")
                if "payload" in b:
                    string(b["payload"], 1024, 0)


def validate(args):
    fields(args, {"text", "attachments", "format", "notify", "link"}, {"attachments"})
    if len(json.dumps(args, ensure_ascii=False).encode()) > 65536:
        raise ValueError("Attachment request exceeds 64 KiB")
    args = json.loads(json.dumps(args))
    for key in ("text", "format", "link"):
        if args.get(key, False) is None:
            args.pop(key)
    if "text" in args:
        string(args["text"], 4000, 0)
    if "format" in args and args["format"] not in {"markdown", "html"}:
        raise ValueError("Unknown text format")
    if "notify" in args and type(args["notify"]) is not bool:
        raise ValueError("notify must be boolean")
    if "link" in args:
        fields(args["link"], {"type", "mid"}, {"type", "mid"})
        if args["link"]["type"] not in {"reply", "forward"}:
            raise ValueError("Invalid message link")
        string(args["link"]["mid"], 1024)
    attachments = args["attachments"]
    if not isinstance(attachments, list) or not 1 <= len(attachments) <= 12:
        raise ValueError("Expected 1..12 attachments")
    kinds = []
    for a in attachments:
        if not isinstance(a, dict) or a.get("type") not in TYPES:
            raise ValueError("Unknown attachment type")
        kind = a["type"]
        kinds.append(kind)
        if kind == "location":
            fields(a, {"type", "latitude", "longitude"}, {"type", "latitude", "longitude"})
            for key, limit in (("latitude", 90), ("longitude", 180)):
                v = a[key]
                if type(v) not in (int, float) or not math.isfinite(v) or abs(v) > limit:
                    raise ValueError("Invalid location coordinate")
            continue
        if "path" in a:
            fields(a, {"type", "path"}, {"type", "path"})
            if kind not in MEDIA:
                raise ValueError("Only media may have a local path")
            string(a["path"])
            if not os.path.isabs(a["path"]):
                raise ValueError("Local media path must be absolute")
            continue
        fields(a, {"type", "payload"}, {"type", "payload"})
        p = a["payload"]
        if isinstance(p, dict):
            nullable = {"image": {"url", "token", "photos"},
                        "share": {"url", "token"},
                        "contact": {"name", "contact_id", "vcf_info"}}.get(kind, set())
            for key in nullable:
                if p.get(key, False) is None:
                    p.pop(key)
        if kind == "inline_keyboard":
            keyboard(p)
        elif kind == "contact":
            fields(p, {"name", "contact_id", "vcf_info"})
            if ("contact_id" in p) == ("vcf_info" in p):
                raise ValueError("Contact requires exactly one of contact_id/vcf_info")
            if "name" in p:
                string(p["name"], 1024)
            if "contact_id" in p and (type(p["contact_id"]) is not int or p["contact_id"] <= 0):
                raise ValueError("Invalid contact_id")
            if "vcf_info" in p:
                string(p["vcf_info"], 16384)
        else:
            allowed = {"image": {"url", "token", "photos"}, "share": {"url", "token"},
                       "sticker": {"code", "url"}}.get(kind, {"token"})
            fields(p, allowed)
            if len(p) != 1:
                raise ValueError("Expected exactly one payload variant")
            key, value = next(iter(p.items()))
            if key == "url":
                url(value)
            elif key == "photos":
                if not isinstance(value, dict) or not 1 <= len(value) <= 12:
                    raise ValueError("Invalid photos")
                for photo in value.values():
                    fields(photo, {"token"}, {"token"})
                    string(photo["token"])
            else:
                string(value)
    if kinds.count("inline_keyboard") > 1:
        raise ValueError("Only one keyboard is allowed")
    content = [k for k in kinds if k != "inline_keyboard"]
    if "sticker" in kinds and len(kinds) != 1:
        raise ValueError("Sticker must be the only attachment")
    if content and not set(content) <= {"image", "video"}:
        if len(content) != 1:
            raise ValueError("This attachment cannot be combined with other content")
        if content[0] in {"location", "share"} and len(kinds) > 1:
            raise ValueError("Undocumented combination rejected")
    return json.loads(json.dumps(args))


async def send_attachments(args, **kwargs):
    """Agent tool. No destination parameter or arbitrary endpoint is accepted."""
    try:
        body = validate(args)
        if get_session_env("HERMES_SESSION_PLATFORM") != "max":
            raise ValueError("Tool is limited to the current MAX session; use send_message for other destinations")
        target = get_session_env("HERMES_SESSION_CHAT_ID")
        if not isinstance(target, str) or not re.fullmatch(r"(?:(?:chat|user):)?-?[0-9]{1,20}", target):
            raise ValueError("No valid current MAX destination")
        token = get_max_secret("MAX_BOT_TOKEN")
        if not token:
            raise ValueError("MAX credentials unavailable")
        return await send_to_resolved(body, target, token)
    except (ValueError, TypeError, OSError) as exc:
        return json.dumps({"error": str(exc), "retryable": False})
    except Exception as exc:  # noqa: BLE001 — context/credential failures fail closed
        return json.dumps({"error": f"Attachment send failed ({type(exc).__name__})", "retryable": False})


async def send_to_resolved(body, target, token):
    """Plugin-local sender; host callback supplies the already-authorized recipient."""
    try:
        body = validate(body)
        if not isinstance(target, str) or not re.fullmatch(r"(?:(?:chat|user):)?-?[0-9]{1,20}", target):
            raise ValueError("Invalid resolved MAX recipient")
        # Lazy import prevents a registration import cycle. No connection/polling.
        from .adapter import MaxAdapter

        # Validate every local file before any upload side effect.
        for item in body["attachments"]:
            if "path" in item:
                from agent.file_safety import raise_if_read_blocked
                raise_if_read_blocked(item["path"])
                info = await asyncio.to_thread(os.stat, item["path"])
                if not stat.S_ISREG(info.st_mode) or info.st_size <= 0:
                    raise ValueError("Expected a non-empty regular local file")
        instance = MaxAdapter(PlatformConfig(enabled=True, token=token, extra={}))
        async with httpx.AsyncClient(headers={"Authorization": token}, timeout=30, verify=get_max_ssl_context(), follow_redirects=False) as client:
            instance._http_client = client
            if body.get("notify") is False:
                # user: is an API recipient contract, not an inferred chat sign.
                from .mixins.base import _message_recipient_params
                recipient = _message_recipient_params(target)
                if "chat_id" in recipient:
                    response = await client.get(f"https://platform-api2.max.ru/chats/{recipient['chat_id']}")
                    response.raise_for_status()
                    metadata = response.json()
                    if metadata.get("type") not in {"chat", "group", "dialog", "dm"}:
                        raise ValueError("notify=false requires confirmed DM/group; channel or unknown target refused")
            for i, item in enumerate(body["attachments"]):
                if "path" in item:
                    uploaded = await instance._upload(item["path"], item["type"])
                    if not uploaded:
                        return json.dumps({"error": "Upload failed; message not sent", "retryable": False})
                    body["attachments"][i] = {"type": item["type"], "payload": {"token": uploaded}}
            result = await instance._send_attachment_body(target, body)
        return json.dumps({"success": result.success, "message_id": result.message_id,
                           "error": result.error, "retryable": False})
    except (ValueError, TypeError, OSError) as exc:
        return json.dumps({"error": str(exc), "retryable": False})
    except Exception as exc:  # noqa: BLE001 — no credentials or response text in errors
        return json.dumps({"error": f"Attachment send failed ({type(exc).__name__}); do not resend automatically", "retryable": False})


SCHEMA = {
    "name": "max_send_attachments",
    "description": "Send validated MAX Bot API attachments ONLY to the current MAX conversation. Types: image/video/audio/file (payload token or local absolute path; image also URL/photos), sticker, contact, inline_keyboard, location, share. No arbitrary destination/API. See plugin docs attachments.md for field variants and combinations. Never automatically resend an uncertain failure.",
    "parameters": {"type": "object", "additionalProperties": False, "required": ["attachments"],
                   "properties": {"text": {"type": ["string", "null"], "maxLength": 4000},
                                  "attachments": {"type": "array", "minItems": 1, "maxItems": 12, "items": {"type": "object", "additionalProperties": False, "required": ["type"], "properties": {"type": {"type": "string", "enum": sorted(TYPES)}, "payload": {"type": "object", "description": "token for media/share; URL alternatively for image/share/sticker; code for sticker; name plus contact_id or vcf_info for contact; buttons: array of button rows for inline_keyboard."}, "path": {"type": "string", "description": "Absolute local media path instead of payload; file safety enforced."}, "latitude": {"type": "number", "minimum": -90, "maximum": 90}, "longitude": {"type": "number", "minimum": -180, "maximum": 180}}}},
                                  "format": {"type": ["string", "null"], "enum": ["markdown", "html", None]},
                                  "notify": {"type": "boolean"},
                                  "link": {"type": ["object", "null"]}}},
}
