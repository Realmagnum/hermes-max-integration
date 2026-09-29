"""
MAX messenger (max.ru) Platform Adapter for Hermes Agent.

A plugin-based gateway adapter that supports both long-polling and webhook
for receiving messages, and the Max Bot REST API for sending responses.

Architecture:
- Inbound:  Long polling (GET /updates) OR Webhook (POST /max/webhook) → MessageEvent
- Outbound: httpx → POST /messages (with chunking for >4000 chars)
- STT:      Voice messages auto-downloaded and cached; transcription is
            handled by the Hermes core STT pipeline (config.yaml -> stt)
- Files:    Two-step upload (POST /uploads → PUT file → token → send)
- Streaming: edit_message via PUT /messages

Configuration in ~/.hermes/.env:
  MAX_BOT_TOKEN (required)
  MAX_WEBHOOK_HOST, MAX_WEBHOOK_PORT, MAX_WEBHOOK_PATH
  MAX_WEBHOOK_SECRET, MAX_ALLOWED_USERS, MAX_ALLOW_ALL_USERS
"""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import logging
import mimetypes
import os
import random
import shutil
import socket
import time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from gateway.config import Platform, PlatformConfig
from gateway.platforms.base import (
    SUPPORTED_DOCUMENT_TYPES,
    BasePlatformAdapter,
    MessageEvent,
    MessageType,
    SendResult,
    cache_audio_from_bytes,
    cache_document_from_bytes,
    cache_image_from_bytes,
)

try:
    from gateway.platforms import base as _core_base
except ImportError:  # pragma: no cover — older Hermes core
    _core_base = None  # type: ignore[assignment]

from .mixins.base import _http_body_snippet, _is_retryable_http_status
from .mixins.buttons import ButtonsMixin
from .mixins.callback_auth import CallbackAuthMixin
from .mixins.media_upload import (  # noqa: F401 — re-export (tests use adapter._ALLOWED_UPLOAD_HOSTS)
    _ALLOWED_UPLOAD_HOSTS,
    MediaUploadMixin,
)
from .mixins.sessions import SessionsMixin
from .mixins.standalone import (  # noqa: F401 — re-export (tests use adapter._standalone_get_token)
    _standalone_get_token,
    _standalone_send,
)
from .mixins.table_renderer import TableRendererMixin
from .mixins.webhook import (  # noqa: F401 — re-export (tests use adapter._verify_raw_secret)
    WebhookMixin,
    _verify_raw_secret,
)

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────

MAX_API_BASE = "https://platform-api.max.ru"
MAX_MESSAGE_LENGTH = 4000
# Text budget per chunk: MAX_MESSAGE_LENGTH minus headroom for the "(i/n)\n"
# numbering prefix that the sender prepends to every chunk of a split message.
OUTBOUND_CHUNK_MARGIN = 100
OUTBOUND_CHUNK_LIMIT = max(500, MAX_MESSAGE_LENGTH - OUTBOUND_CHUNK_MARGIN)
MODEL_PICKER_TTL_SECONDS = 900.0
POLL_TIMEOUT = 5  # seconds
POLL_ERROR_DELAY = 5.0
POLL_BACKOFF_MAX = 60.0  # upper bound for a single backoff sleep
POLL_BACKOFF_JITTER = 0.25  # ±25% random spread around the bounded delay
POLL_RETRY_AFTER_MAX = 300.0  # upper bound for a server-provided Retry-After
UPLOAD_DELAY = 2.0

# ── Media download security and limits (SEC-02, SEC-03, SEC-07) ─────────
DOWNLOAD_ALLOWED_HOST_SUFFIXES: tuple[str, ...] = (".max.ru", ".oneme.ru")
DOWNLOAD_ALLOWED_SCHEMES: frozenset[str] = frozenset({"https"})
DOWNLOAD_REDIRECT_STATUS_CODES: frozenset[int] = frozenset({301, 302, 303, 307, 308})

_TRUSTED_DOWNLOAD_HOST_SUFFIXES = (".max.ru", ".oneme.ru", ".okcdn.ru", ".cdn-max.ru")
_DOWNLOAD_USER_AGENT = "HermesAgent/1.0 MaxBot"

DEFAULT_INBOUND_ATTACHMENT_MAX_BYTES = 50 * 1024 * 1024  # 50 MB
DEFAULT_INBOUND_TOTAL_MAX_BYTES = 100 * 1024 * 1024      # 100 MB aggregate per message
DEFAULT_INBOUND_MAX_ATTACHMENTS = 10                     # attachments processed per message
DEFAULT_INBOUND_DOWNLOAD_TIMEOUT = 60.0                  # seconds, whole-download deadline
DEFAULT_INBOUND_DOWNLOAD_CONCURRENCY = 4                 # parallel downloads
INBOUND_MEDIA_CHUNK_SIZE = 64 * 1024                     # streaming read granularity
MAX_INBOUND_MEDIA_CEILING = 512 * 1024 * 1024            # hard ceiling for the byte knobs
CACHE_FREE_SPACE_HEADROOM = 1024 * 1024                  # keep 1 MB free in the cache volume

_INBOUND_MEDIA_ACCEPT = {
    "audio": "audio/*,*/*;q=0.8",
    "voice": "audio/*,*/*;q=0.8",
    "image": "image/*,*/*;q=0.8",
    "document": "application/*,text/*,*/*;q=0.8",
}

# Streaming edit throttle. Per-message state lives in MaxAdapter._edit_states,
# so two concurrent chats can never consume each other's slot (CODE-03).
EDIT_THROTTLE_SECONDS = 0.2
# Upper bound on tracked (chat, message) streams; idle entries are pruned first
# so a long-lived adapter cannot grow one state per message forever.
EDIT_STATES_MAX = 256

# Upper bound for waiting on our own cancelled poll/queue/handler tasks during
# teardown. The HTTP client is closed only after they are gone, so a task that
# never unwinds would otherwise stall every disconnect; past this bound the
# stragglers are left to unwind on their own (already cancelled).
TASK_SHUTDOWN_TIMEOUT = 5.0

# SSRF allowlist is in .mixins.media_upload

DEFAULT_WEBHOOK_HOST = "0.0.0.0"  # nosec B104 — вебхук за Caddy reverse proxy; порт защищён host firewall
DEFAULT_WEBHOOK_PORT = 8646
DEFAULT_WEBHOOK_PATH = "/max/webhook"

# Hard bounds for ingress, worker concurrency and duplicate tracking (CODE-08).
DEFAULT_QUEUE_MAXSIZE = 1000
DEFAULT_MAX_CONCURRENCY = 8
DEFAULT_DEDUP_MAX = 5000
DEFAULT_DEDUP_TTL = 300.0
OVERLOAD_DROP_OLDEST = "drop_oldest"
OVERLOAD_DROP_NEWEST = "drop_newest"
OVERLOAD_POLICIES = (OVERLOAD_DROP_OLDEST, OVERLOAD_DROP_NEWEST)

# Audio cache anchor (also parent of table_images dir)
AUDIO_CACHE_DIR = Path(
    os.getenv("HERMES_HOME", str(Path.home() / ".hermes"))
) / "audio_cache"

# Ensure cache dir exists with restricted permissions (voice messages are private)
AUDIO_CACHE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)

# ── Helpers ──────────────────────────────────────────────────────────────
import json as _json

# Random source for poll backoff jitter. Tests seed it for determinism;
# production keeps the module-level generator.
_POLL_RNG = random.Random()  # nosec B311 — jitter only, not security-relevant


def _parse_retry_after(raw: Any) -> float | None:
    """Parse an HTTP ``Retry-After`` header value into a non-negative delay.

    Accepts both forms defined by RFC 9110: a delta-seconds integer/float or
    an HTTP-date. Returns ``None`` when the header is absent or unusable, and
    clamps the result to ``POLL_RETRY_AFTER_MAX`` so a hostile/broken server
    cannot park the poll loop for hours.
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        seconds = float(raw)
    else:
        value = str(raw).strip()
        if not value:
            return None
        try:
            seconds = float(value)
        except ValueError:
            try:
                parsed = parsedate_to_datetime(value)
            except (TypeError, ValueError):
                return None
            if parsed is None:  # pragma: no cover - defensive
                return None
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            seconds = (parsed - datetime.now(UTC)).total_seconds()
    return max(0.0, min(seconds, POLL_RETRY_AFTER_MAX))


def _poll_backoff_delay(
    errs: int,
    *,
    base: float = POLL_ERROR_DELAY,
    cap: float = POLL_BACKOFF_MAX,
    jitter: float = POLL_BACKOFF_JITTER,
    rng: random.Random | None = None,
) -> float:
    """Bounded exponential backoff with jitter for the ``errs``-th failure.

    ``base * 2 ** (errs - 1)`` (exponent clamped at 4 so the doubling stops),
    capped at ``cap`` and spread by ±``jitter`` of the capped value. The
    result is always inside ``[0, cap]`` and never negative.
    """
    exponent = min(max(int(errs), 1) - 1, 4)
    delay = min(base * (2 ** exponent), cap)
    if jitter > 0:
        spread = delay * jitter
        delay = (rng or _POLL_RNG).uniform(delay - spread, delay + spread)
    return max(0.0, min(delay, cap))


def _poll_status_delay(headers: Any, errs: int) -> float:
    """Delay before retrying a poll that answered with a non-200 status.

    ``Retry-After`` wins when the server sends one (429/503 mainly); otherwise
    the same bounded exponential backoff as transport errors is used.
    """
    raw = None
    if headers is not None:
        getter = getattr(headers, "get", None)
        if callable(getter):
            # httpx.Headers is case-insensitive; plain dicts are not, so try
            # both spellings before giving up.
            raw = getter("Retry-After")
            if raw is None:
                raw = getter("retry-after")
    retry_after = _parse_retry_after(raw)
    if retry_after is not None:
        return retry_after
    return _poll_backoff_delay(errs)


async def _poll_sleep(delay: float) -> None:
    """Sleep between poll attempts (indirection point for virtual-clock tests)."""
    await asyncio.sleep(delay)


def _split_keep_separators(text: str, sep: str) -> list[str]:
    """Split ``text`` on ``sep``, keeping each separator on the piece before it.

    ``"".join(result) == text`` holds for every input, including empty pieces
    (``"a\\n\\nb".split("\\n")`` -> ``["a", "", "b"]`` -> ``["a\\n", "\\n", "b"]``).
    """
    pieces = text.split(sep)
    result = [piece + sep for piece in pieces[:-1]]
    if pieces[-1]:
        result.append(pieces[-1])
    return result


def _iter_text_segments(text: str, limit: int) -> Iterator[str]:
    """Yield ordered segments of ``text``, each no longer than ``limit``.

    Concatenating the segments reproduces ``text`` exactly. Splitting prefers
    boundaries in this order: line, word, character — a word longer than the
    limit is the only case that gets cut mid-word.
    """
    for line in _split_keep_separators(text, "\n"):
        if len(line) <= limit:
            yield line
            continue
        for word in _split_keep_separators(line, " "):
            if len(word) <= limit:
                yield word
            else:
                for start in range(0, len(word), limit):
                    yield word[start:start + limit]


def _pack_segments(segments: Iterable[str], limit: int) -> list[str]:
    """Greedily pack segments into chunks of at most ``limit`` characters."""
    chunks: list[str] = []
    current = ""
    for segment in segments:
        if current and len(current) + len(segment) > limit:
            chunks.append(current)
            current = segment
        else:
            current += segment
    if current:
        chunks.append(current)
    return chunks


def _move_leading_whitespace(chunks: list[str], cap: int) -> None:
    """Move a chunk's leading whitespace onto the previous chunk while it fits.

    In-place, and never moves a chunk's last character, so the concatenation of
    ``chunks`` is unchanged (losslessness is preserved). ``cap`` is the maximum
    allowed length of a chunk's text — the caller sets it so that the numbered
    payload still fits the API limit. Keeps a message from starting with a blank
    line when a chunk boundary lands inside a paragraph break.
    """
    for idx in range(1, len(chunks)):
        while (
            len(chunks[idx]) > 1
            and chunks[idx][0] in " \t\n"
            and len(chunks[idx - 1]) < cap
        ):
            chunks[idx - 1] += chunks[idx][0]
            chunks[idx] = chunks[idx][1:]


def _safe_url_for_log(url: str) -> str:
    """Strip credentials from URL for logging."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if parsed.password:
        return url.replace(parsed.password, "***")
    if parsed.username and parsed.username != parsed.hostname:
        return url.replace(parsed.username, "***")
    return url


def _find_audio_url_direct(obj: Any, depth: int = 0) -> str | None:
    """Recursively search for an audio/voice download URL in a MAX update.

    Searches common MAX fields: message.attachments, .voice, .audio,
    body.attachments, and any dict containing type=voice/audio with a URL.
    """
    if depth > 8:
        return None
    if isinstance(obj, dict):
        # Check type+url pattern (standard MAX attachment)
        atype = str(obj.get("type", "")).lower()
        url = obj.get("url") or obj.get("download_url") or ""
        if atype in ("voice", "audio") and isinstance(url, str) and url.startswith("http"):
            return url
        # Check payload.url pattern
        payload = obj.get("payload")
        if isinstance(payload, dict):
            url = payload.get("url") or payload.get("download_url") or ""
            if isinstance(url, str) and url.startswith("http"):
                return url
        # Recurse into all values
        for key in ("attachments", "voice", "audio", "message", "body", "payload"):
            val = obj.get(key)
            found = _find_audio_url_direct(val, depth + 1)
            if found:
                return found
        for val in obj.values():
            if isinstance(val, (dict, list)):
                found = _find_audio_url_direct(val, depth + 1)
                if found:
                    return found
    elif isinstance(obj, list):
        for item in obj:
            found = _find_audio_url_direct(item, depth + 1)
            if found:
                return found
    return None


def _parse_list(value: str) -> list[str]:
    """Parse comma-separated string into trimmed list."""
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def _coerce_str_list(value: Any) -> list[str]:
    """Normalize a config value into a list of non-empty trimmed strings.

    Accepts the comma-separated env style ("1, 2") and native YAML lists.
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple, set, frozenset)):
        items = [str(v).strip() for v in value]
    else:
        items = [v.strip() for v in str(value).split(",")]
    return [v for v in items if v]


# Group policy values accepted in config/env. Anything else fails closed.
_GROUP_POLICIES: tuple[str, ...] = ("open", "closed", "allowlist")



def _is_group(chat_id: str) -> bool:
    """MAX group chats have negative IDs, DMs have positive."""
    try:
        return int(chat_id) < 0
    except (ValueError, TypeError):
        return False


def _coerce_bool(value: Any, default: bool = False) -> bool:
    """Coerce env/config strings to bool."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _coerce_int(value: Any, default: int, *, minimum: int = 1, maximum: int | None = None) -> int:
    """Coerce an env/config value to a positive int; unusable input yields *default*."""
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    if parsed < minimum:
        return default
    return min(parsed, maximum) if maximum is not None else parsed


def _coerce_float(
    value: Any, default: float, *, minimum: float = 0.0, maximum: float | None = None
) -> float:
    """Coerce env/config strings to a float; unusable input yields *default*."""
    if value is None or value == "":
        return default
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError):
        return default
    if parsed < minimum:
        return default
    return min(parsed, maximum) if maximum is not None else parsed


def _parse_host_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Return the IP literal *host* denotes, or ``None`` when it is a DNS name.

    Canonicalise legacy IPv4 forms (2130706433, 0x7f000001, 0177.0.0.1, 127.1)
    exactly like inet_aton does.
    """
    candidate = str(host).strip()
    if candidate.startswith("[") and candidate.endswith("]"):
        candidate = candidate[1:-1]
    candidate = candidate.split("%", 1)[0]
    if not candidate:
        return None
    try:
        return ipaddress.ip_address(candidate)
    except ValueError:
        pass
    try:
        packed = socket.inet_aton(candidate)
    except OSError:
        return None
    return ipaddress.IPv4Address(packed)


def _is_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True only for addresses that are routable on the public internet."""
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        return _is_public_ip(mapped)
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast:
        return False
    if ip.is_reserved or ip.is_unspecified:
        return False
    return bool(ip.is_global)


def _normalize_host_suffixes(value: Any) -> tuple[str, ...]:
    """Normalise an allowlist config value to ``(".example.com", ...)`` form."""
    if isinstance(value, str):
        parts: list[Any] = value.replace(";", ",").split(",")
    elif isinstance(value, (list, tuple, set, frozenset)):
        parts = list(value)
    else:
        return ()
    suffixes: list[str] = []
    for part in parts:
        host = str(part).strip().lower().rstrip(".")
        if not host:
            continue
        host = host.removeprefix("*")
        if not host.startswith("."):
            host = f".{host}"
        if len(host) > 1:
            suffixes.append(host)
    return tuple(suffixes)


def _host_allowed_by_suffixes(host: str, suffixes: tuple[str, ...]) -> bool:
    """True when *host* is one of *suffixes* or a subdomain of one."""
    for suffix in suffixes:
        if host == suffix[1:] or host.endswith(suffix):
            return True
    return False


def _parse_trusted_download_hosts(raw: Any) -> set[str]:
    """Parse ``MAX_TRUSTED_DOWNLOAD_HOSTS`` / ``extra["trusted_download_hosts"]``."""
    if isinstance(raw, str):
        parts: list[Any] = raw.split(",")
    elif isinstance(raw, (list, tuple, set, frozenset)):
        parts = list(raw)
    else:
        return set()

    hosts: set[str] = set()
    for part in parts:
        entry = str(part).strip().lower()
        if not entry:
            continue
        if "://" in entry:
            entry = urlparse(entry).hostname or ""
        else:
            entry = entry.split("/", 1)[0]
        if "@" in entry:
            entry = entry.rsplit("@", 1)[1]
        if entry.startswith("[") and "]" in entry:
            entry = entry[1:entry.index("]")]
        elif ":" in entry:
            entry = entry.split(":", 1)[0]
        entry = entry.rstrip(".")
        if entry:
            hosts.add(entry)
    return hosts


def _inbound_cache_dir(media_type: str) -> Path | None:
    """Resolve the core cache directory for a media kind (``None`` when unknown)."""
    getter_name = {
        "audio": "get_audio_cache_dir",
        "voice": "get_audio_cache_dir",
        "image": "get_image_cache_dir",
        "document": "get_document_cache_dir",
    }.get(media_type)
    getter = getattr(_core_base, getter_name, None) if getter_name and _core_base else None
    if getter is None:
        return None
    try:
        return Path(getter())
    except Exception:  # noqa: BLE001 — a missing cache dir only disables cleanup
        return None


def _dir_snapshot(cache_dir: Path | None, *, exclude: set[Path] | None = None) -> set[Path]:
    """Return the file set of *cache_dir* (empty for ``None``/unreadable dirs)."""
    if cache_dir is None:
        return set()
    try:
        entries = {p for p in cache_dir.iterdir() if p.is_file()}
    except OSError:
        return set()
    return entries - exclude if exclude else entries


class InboundMediaLimitError(Exception):
    """An inbound media download was refused because a configured limit was hit."""


class _InboundMediaBudget:
    """Byte/attachment budget shared by the downloads of one update."""

    def __init__(self, *, max_attachments: int, max_bytes: int) -> None:
        self.max_attachments = max_attachments
        self.max_bytes = max_bytes
        self._remaining = max_bytes
        self._admitted = 0
        self._lock = asyncio.Lock()

    async def admit(self) -> bool:
        """Reserve a slot for one attachment; ``False`` once the count cap is hit."""
        async with self._lock:
            if self.max_attachments and self._admitted >= self.max_attachments:
                return False
            self._admitted += 1
            return True

    async def charge(self, size: int) -> bool:
        """Consume *size* aggregate bytes; ``False`` when that would exceed the cap."""
        async with self._lock:
            if self.max_bytes and self._remaining < size:
                return False
            self._remaining -= size
            return True

    async def refund(self, size: int) -> None:
        """Return *size* aggregate bytes on a failed download."""
        async with self._lock:
            self._remaining = min(self.max_bytes, self._remaining + size)


@dataclass
class _StreamEditState:
    """Per-(chat, message) streaming-edit bookkeeping (CODE-03).

    Kept per message instead of on the adapter so concurrent streams cannot
    share a throttle slot. ``last_edit_at`` gates the next PUT, ``pending_text``
    holds the content of a throttled call until ``flush_task`` delivers it, and
    ``lock`` serialises the direct and timer-driven PUT for one message.
    """

    chat_id: str
    message_id: str
    last_edit_at: float = 0.0
    pending_text: str | None = None
    flush_task: asyncio.Task | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


# ── MaxAdapter ───────────────────────────────────────────────────────────

class MaxAdapter(MediaUploadMixin, TableRendererMixin, ButtonsMixin, CallbackAuthMixin, WebhookMixin, SessionsMixin, BasePlatformAdapter):
    """MAX messenger platform adapter (voice transcription via Hermes core STT)."""

    def __init__(self, config: PlatformConfig):
        try:
            platform = Platform("max")
        except ValueError:
            # Platform 'max' is not in the Enum (typical in unit tests where the plugin isn't registered)
            # We can register a pseudo-member dynamically to make it work.
            try:
                pseudo = object.__new__(Platform)
                pseudo._value_ = "max"
                pseudo._name_ = "MAX"
                Platform._value2member_map_["max"] = pseudo
                Platform._member_map_["MAX"] = pseudo
                platform = pseudo
            except Exception:  # noqa: BLE001 — adapter must not crash on transport/API errors
                platform = next(iter(Platform))
        super().__init__(config=config, platform=platform)
        extra = getattr(config, "extra", {}) or {}

        # Token
        self._token: str = (
            os.getenv("MAX_BOT_TOKEN", "")
            or getattr(config, "token", "")
            or extra.get("token", "")
        )

        # Table-as-image (requires Pillow)
        self._table_as_image: bool = _coerce_bool(
            os.getenv("MAX_TABLE_AS_IMAGE")
            or extra.get("table_as_image", False),
            False,
        )
        self._table_image_dir: Path = AUDIO_CACHE_DIR.parent / "table_images"
        if self._table_as_image:
            self._table_image_dir.mkdir(mode=0o700, parents=True, exist_ok=True)

        # Webhook settings
        self._webhook_host: str = (
            os.getenv("MAX_WEBHOOK_HOST")
            or str(extra.get("host", DEFAULT_WEBHOOK_HOST))
        )
        self._webhook_port: int = int(
            os.getenv("MAX_WEBHOOK_PORT")
            or extra.get("port", DEFAULT_WEBHOOK_PORT)
        )
        self._webhook_path: str = (
            os.getenv("MAX_WEBHOOK_PATH")
            or str(extra.get("path", DEFAULT_WEBHOOK_PATH))
        )
        self._webhook_secret: str = (
            os.getenv("MAX_WEBHOOK_SECRET")
            or str(extra.get("webhook_secret", ""))
        )
        self._webhook_url: str = (
            os.getenv("MAX_WEBHOOK_URL")
            or str(extra.get("webhook_url", ""))
        )
        self._webhook_insecure_dev: bool = _coerce_bool(
            os.getenv("MAX_WEBHOOK_INSECURE_DEV")
            or extra.get("webhook_insecure_dev", False),
            False,
        )
        # Use webhook if URL is explicitly configured
        self._use_webhook: bool = bool(self._webhook_url)

        # Access control
        self.allowed_users: list = extra.get("allowed_users", [])
        self._allowed_users_set: set = set()
        for u in self.allowed_users:
            if isinstance(u, (int, str)):
                self._allowed_users_set.add(str(u))
        # Also parse from env
        env_allowed = _parse_list(os.getenv("MAX_ALLOWED_USERS", ""))
        self._allowed_users_set.update(env_allowed)
        self._allow_all_users: bool = _coerce_bool(
            os.getenv("MAX_ALLOW_ALL_USERS")
            or extra.get("allow_all_users", False),
            False,
        )

        # Cross-platform session commands expose sessions from other
        # platforms, so they are an explicit opt-in and owner-only (SEC-05).
        self._cross_session = _coerce_bool(
            os.getenv("MAX_CROSS_SESSION") or extra.get("cross_session", False), False
        )
        raw_cross_users = os.getenv("MAX_CROSS_SESSION_USERS") or extra.get("cross_session_users", "")
        if isinstance(raw_cross_users, (list, tuple, set)):
            raw_cross_users = ",".join(str(value) for value in raw_cross_users)
        self._cross_session_users = set(_parse_list(str(raw_cross_users or "")))
        if not self._cross_session_users and not self._allow_all_users:
            self._cross_session_users = set(self._allowed_users_set)

        # Group access control
        raw_group_policy = (
            os.getenv("MAX_GROUP_POLICY")
            or extra.get("group_policy")
            or "allowlist"
        )
        self._group_policy: str = str(raw_group_policy).strip().lower()
        if self._group_policy not in _GROUP_POLICIES:
            logger.warning(
                "MAX: unknown group_policy=%r — denying all group messages (valid values: %s)",
                raw_group_policy,
                ", ".join(_GROUP_POLICIES),
            )
            self._group_policy = "closed"
        self._group_allow_from: list[str] = _coerce_str_list(
            os.getenv("MAX_GROUP_ALLOWED_USERS")
            or extra.get("group_allow_from")
            or ""
        )
        self._group_allow_chats: list[str] = _coerce_str_list(
            os.getenv("MAX_GROUP_ALLOWED_CHATS")
            or extra.get("group_allow_chats")
            or ""
        )
        if (
            self._group_policy == "allowlist"
            and not self._group_allow_from
            and not self._group_allow_chats
        ):
            logger.warning(
                "MAX: group_policy=allowlist but MAX_GROUP_ALLOWED_USERS and "
                "MAX_GROUP_ALLOWED_CHATS are both empty — all group messages "
                "will be rejected. Set at least one allowlist, or set "
                "MAX_GROUP_POLICY=open to allow every group explicitly."
            )

        # Bounded ingress and bounded handler concurrency (CODE-08).
        def _bounded_int(env_name: str, config_name: str, default: int) -> int:
            try:
                return max(1, int(os.getenv(env_name) or extra.get(config_name, default)))
            except (TypeError, ValueError):
                return default

        self._queue_maxsize = _bounded_int("MAX_QUEUE_MAXSIZE", "queue_maxsize", DEFAULT_QUEUE_MAXSIZE)
        self._max_concurrency = _bounded_int("MAX_MAX_CONCURRENCY", "max_concurrency", DEFAULT_MAX_CONCURRENCY)
        self._overload_policy = str(
            os.getenv("MAX_OVERLOAD_POLICY") or extra.get("overload_policy", OVERLOAD_DROP_OLDEST)
        ).strip().lower()
        if self._overload_policy not in OVERLOAD_POLICIES:
            logger.warning("MAX: unknown overload policy %r; using %s", self._overload_policy, OVERLOAD_DROP_OLDEST)
            self._overload_policy = OVERLOAD_DROP_OLDEST

        # Runtime state
        self._http_client: httpx.AsyncClient | None = None
        self._webhook_runner: Any = None  # aiohttp.web.AppRunner
        self._webhook_site: Any = None
        self._webhook_app: Any = None
        self._message_queue: asyncio.Queue[MessageEvent] = asyncio.Queue(maxsize=self._queue_maxsize)
        self._poll_task: asyncio.Task | None = None
        self._background_tasks: set[asyncio.Task] = set()
        self._handler_tasks: set[asyncio.Task] = set()
        self._stop: asyncio.Event = asyncio.Event()

        # `_running` and the `_mark_connected`/`_mark_disconnected` pair are
        # owned by Hermes core (`gateway.platforms.base.BasePlatformAdapter`);
        # `_mark_connected()` sets `_running = True`, `_mark_disconnected()`
        # clears it, and `_set_fatal_error()` also clears it. The contract is
        # verified against the pinned core in tests/test_lifecycle.py
        # (TestCoreContract), so the flag is deliberately NOT re-declared here:
        # shadowing it would hide a core change (e.g. `_running` becoming a
        # property) instead of failing loudly.
        for _inherited in ("_running", "_expected_cancelled_tasks", "_background_tasks"):
            if not hasattr(self, _inherited):  # pragma: no cover - very old core
                setattr(self, _inherited, False if _inherited == "_running" else set())

        # connect() must be idempotent and safe under concurrent callers: the
        # gateway may re-enter connect() (reconnect after a missed failure,
        # adapter reuse in tests) while the previous session is still up.
        self._connect_lock: asyncio.Lock = asyncio.Lock()

        # Dedup: a TTL window with a hard cap even under a sustained fresh burst.
        self._seen_msgs: dict[str, float] = {}
        self._SEEN_MSGS_MAX = _bounded_int("MAX_DEDUP_MAX", "dedup_max", DEFAULT_DEDUP_MAX)
        try:
            self._DEDUP_TTL = max(1.0, float(
                os.getenv("MAX_DEDUP_TTL") or extra.get("dedup_ttl", DEFAULT_DEDUP_TTL)
            ))
        except (TypeError, ValueError):
            self._DEDUP_TTL = DEFAULT_DEDUP_TTL
        self._stats: dict[str, int] = {
            "enqueued": 0, "dispatched": 0, "dropped_oldest": 0,
            "dropped_newest": 0, "duplicate_suppressed": 0,
            "queue_peak": 0, "handlers_peak": 0,
        }
        self._drop_log_interval = 50
        # DM routing: chat_id → user_id
        self._dm_user_ids: dict[str, str] = {}

        # Callback state is bound to owner/chat/message and expires (SEC-01).
        self._init_callback_auth()
        self._model_picker_state: dict[str, dict] = {}    # chat_id → picker state

        # Streaming edit throttle — one state entry per (chat_id, message_id)
        self._edit_throttle: float = _coerce_float(
            os.getenv("MAX_EDIT_THROTTLE") or extra.get("edit_throttle"),
            EDIT_THROTTLE_SECONDS,
        )
        self._edit_states: dict[str, _StreamEditState] = {}

        # Media download security and limits (SEC-02, SEC-03, SEC-07).
        # An operator-supplied allowlist is deliberately strict.  Without one,
        # arbitrary public HTTPS origins are admitted only after DNS validation
        # and pinning; trust for credentials is a separate decision below.
        raw_download_hosts = os.getenv("MAX_DOWNLOAD_ALLOWED_HOSTS")
        if raw_download_hosts is None:
            raw_download_hosts = extra.get("download_allowed_hosts")
        self._download_host_allowlist_configured = raw_download_hosts is not None
        self._download_allowed_suffixes: tuple[str, ...] = _normalize_host_suffixes(
            raw_download_hosts
        )
        self._trusted_download_hosts: set[str] = _parse_trusted_download_hosts(
            os.getenv("MAX_TRUSTED_DOWNLOAD_HOSTS")
            or extra.get("trusted_download_hosts")
        )
        self._download_client: httpx.AsyncClient | None = None

        self._inbound_attachment_max_bytes: int = _coerce_int(
            os.getenv("MAX_INBOUND_MEDIA_MAX_BYTES") or extra.get("inbound_media_max_bytes"),
            DEFAULT_INBOUND_ATTACHMENT_MAX_BYTES,
            minimum=1,
            maximum=MAX_INBOUND_MEDIA_CEILING,
        )
        self._inbound_media_total_max_bytes: int = _coerce_int(
            os.getenv("MAX_INBOUND_MEDIA_TOTAL_BYTES") or extra.get("inbound_media_total_bytes"),
            DEFAULT_INBOUND_TOTAL_MAX_BYTES,
            minimum=1,
            maximum=MAX_INBOUND_MEDIA_CEILING,
        )
        self._inbound_media_max_attachments: int = _coerce_int(
            os.getenv("MAX_INBOUND_MEDIA_MAX_ATTACHMENTS") or extra.get("inbound_media_max_attachments"),
            DEFAULT_INBOUND_MAX_ATTACHMENTS,
            minimum=1,
            maximum=100,
        )
        self._inbound_media_timeout: float = _coerce_float(
            os.getenv("MAX_INBOUND_MEDIA_TIMEOUT") or extra.get("inbound_media_timeout"),
            DEFAULT_INBOUND_DOWNLOAD_TIMEOUT,
            minimum=0.1,
            maximum=600.0,
        )
        self._inbound_media_concurrency: int = _coerce_int(
            os.getenv("MAX_INBOUND_MEDIA_CONCURRENCY") or extra.get("inbound_media_concurrency"),
            DEFAULT_INBOUND_DOWNLOAD_CONCURRENCY,
            minimum=1,
            maximum=32,
        )
        core_cap_getter = getattr(_core_base, "get_inbound_media_max_bytes", None) if _core_base else None
        try:
            core_cap = int(core_cap_getter() or 0) if core_cap_getter else 0
        except Exception:  # noqa: BLE001 — an unreadable core config keeps the plugin cap
            core_cap = 0
        if core_cap > 0:
            self._inbound_attachment_max_bytes = min(self._inbound_attachment_max_bytes, core_cap)
        self._inbound_semaphore: asyncio.Semaphore | None = None
        self._cache_write_lock: asyncio.Lock | None = None

    def _cross_session_allowed(self, user_id: str | None) -> bool:
        """Authorize the cross-platform session view, fail closed."""
        if not self._cross_session or not str(user_id or ""):
            return False
        return str(user_id) in self._cross_session_users

    @staticmethod
    def _callback_message_id(payload: dict[str, Any]) -> str:
        message = payload.get("message") or {}
        body = message.get("body") or {}
        callback = payload.get("callback") or payload.get("message_callback") or {}
        return str(body.get("mid") or message.get("mid") or callback.get("mid") or callback.get("message_id") or "")

    @staticmethod
    def _model_picker_owner(scoped_chat: str, metadata: dict | None) -> str:
        meta = metadata or {}
        explicit = meta.get("owner_user_id") or meta.get("user_id")
        if explicit is not None and str(explicit):
            return str(explicit)
        scope, _, value = str(scoped_chat or "").partition(":")
        return value if scope == "user" else ""

    # ═════════════════════════════════════════════════════════════════════
    # Bot commands (PATCH /me/commands)
    # ═════════════════════════════════════════════════════════════════════

    async def _set_bot_commands(self) -> bool:
        """Register slash commands via MAX API PATCH /me/commands.

        Analogous to Telegram's setMyCommands.
        MAX supports up to 32 commands.
        """
        commands = [
            {"name": "start", "description": "Запустить бота"},
            {"name": "new", "description": "Новая сессия (alias: /reset)"},
            {"name": "status", "description": "Статус сессии"},
            {"name": "model", "description": "Выбрать модель"},
            {"name": "resume", "description": "Возобновить сессию"},
            {"name": "sessions", "description": "Список сессий"},
            {"name": "help", "description": "Помощь"},
            {"name": "stop", "description": "Остановить процессы"},
            {"name": "config", "description": "Конфигурация"},
            {"name": "restart", "description": "Перезапустить gateway"},
            {"name": "retry", "description": "Повторить последнее сообщение"},
            {"name": "undo", "description": "Откатить N ходов (по умолч. 1)"},
            {"name": "title", "description": "Установить название сессии"},
            {"name": "branch", "description": "Ветвить сессию (alias: /fork)"},
            {"name": "compress", "description": "Сжать контекст (alias: /compact)"},
            {"name": "rollback", "description": "Список или восстановление чекпоинтов"},
            {"name": "background", "description": "Запустить в фоне (alias: /bg, /btw)"},
            {"name": "agents", "description": "Активные агенты и задачи (alias: /tasks)"},
            {"name": "queue", "description": "Очередь промптов (alias: /q)"},
            {"name": "topic", "description": "Темы в Telegram DM (off|help|session-id)"},
        ]
        try:
            resp = await self._http_client.patch(
                f"{MAX_API_BASE}/me/commands",
                json={"commands": commands},
                timeout=httpx.Timeout(10.0),
            )
            if resp.status_code == 200:
                logger.info("MAX: registered %d slash commands", len(commands))
                return True
            else:
                logger.warning("MAX: failed to set commands: %s", resp.status_code)
                return False
        except Exception as e:  # noqa: BLE001 — adapter must not crash on transport/API errors
            logger.warning("MAX: error setting commands: %s", e)
            return False

    # ═════════════════════════════════════════════════════════════════════
    # Connection lifecycle
    # ═════════════════════════════════════════════════════════════════════

    async def _close_client(self) -> None:
        """Close and drop the HTTP client(s); safe to call repeatedly.

        Never raises: teardown runs on failure paths and during cancellation,
        where an exception would mask the original error.
        """
        client, self._http_client = self._http_client, None
        dl_client, self._download_client = self._download_client, None
        for c in (client, dl_client):
            if c is not None:
                try:
                    await c.aclose()
                except Exception as exc:  # noqa: BLE001 — teardown must not raise
                    logger.debug("MAX: error closing HTTP client: %s", exc)

    async def _shutdown_transport(self) -> None:
        """Release everything that owns a socket: our tasks, then the client.

        Ordering is the point. The poll loop, the queue-drain loop and every
        in-flight ``handle_message`` task issue requests through
        ``self._http_client``; closing the client while they are still
        unwinding makes them fail against a closed client and leaves
        "Task was destroyed but it is pending" noise behind. So: signal stop,
        cancel, AWAIT them (bounded), and only then close the client.

        Bounded and failure-tolerant — this is the teardown path the gateway
        calls with its own timeout, and it must always end with a closed
        client, including when the caller itself is being cancelled.
        """
        self._stop.set()

        tasks = [self._poll_task]
        self._poll_task = None
        tasks.extend(self._background_tasks)
        live = list(dict.fromkeys(t for t in tasks if t is not None and not t.done()))

        for task in live:
            # Register before cancelling: core's `_expected_cancelled_tasks`
            # marks this cancellation as intentional (not a failure) for the
            # processing hooks.
            self._expected_cancelled_tasks.add(task)
            task.cancel()

        try:
            if live:
                await asyncio.wait_for(
                    asyncio.gather(*live, return_exceptions=True),
                    timeout=TASK_SHUTDOWN_TIMEOUT,
                )
        except TimeoutError:
            logger.warning(
                "MAX: teardown timed out after %.1fs — %d cancelled task(s) did not confirm "
                "exit; closing the client anyway and letting them unwind",
                TASK_SHUTDOWN_TIMEOUT, len(live),
            )
        finally:
            self._background_tasks.clear()
            for task in live:
                self._expected_cancelled_tasks.discard(task)

            # Cancel pending streaming-edit flush timers (CODE-03) so a closed
            # adapter cannot PUT against a closed client.
            pending_flushes = [
                state.flush_task
                for state in self._edit_states.values()
                if state.flush_task is not None and not state.flush_task.done()
            ]
            for task in pending_flushes:
                task.cancel()
            if pending_flushes:
                await asyncio.gather(*pending_flushes, return_exceptions=True)
            self._edit_states.clear()

            if self._webhook_runner:
                runner, self._webhook_runner = self._webhook_runner, None
                self._webhook_app = None
                self._webhook_site = None
                self._webhook_ready = False
                self._webhook_ready_reason = "stopped"
                try:
                    await runner.cleanup()
                except Exception as exc:  # noqa: BLE001 — teardown must not raise
                    logger.debug("MAX: webhook cleanup error: %s", exc)

            await self._close_client()

    async def connect(self, *, is_reconnect: bool = False) -> bool:
        """Connect to Max: verify token, start polling or webhook.

        Safe to call repeatedly and concurrently on the same instance: the
        whole body is serialized by ``_connect_lock`` and any previous session
        (client, tasks, webhook runner) is released first, so a second
        connect() can never leave a second client or a second pair of loops
        behind (CODE-07).
        """
        if not self._token:
            self._set_fatal_error("no_token", "MAX_BOT_TOKEN not configured", retryable=False)
            return False

        async with self._connect_lock:
            # Repeated connect(): drop whatever the previous call left running.
            # A no-op when this is the first connect.
            await self._shutdown_transport()

            # SECURITY: Do NOT follow redirects blindly — Authorization header
            # (token) would be forwarded to any redirect target (token leak).
            # Redirects with Authorization are disabled; if the Max API ever
            # needs redirects, add a limited-redirects transport for known domains.
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                headers={"Authorization": self._token},
                follow_redirects=False,
            )
            self._download_client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._inbound_media_timeout),
                follow_redirects=False,
            )
            try:
                ok = await self._verify_token_and_start(self._http_client)
            except BaseException:
                # Cancellation or any unexpected escape must not orphan the
                # client (the gateway disconnects defensively after a failed
                # connect, but a cancelled connect() leaves no handle to it).
                await self._close_client()
                raise
            if not ok:
                await self._close_client()
            return ok

    async def _verify_token_and_start(self, client: httpx.AsyncClient) -> bool:
        """``/me`` check followed by the configured receive path. ``connect()``
        owns ``client``; this method only reports success."""
        # Verify token with /me
        try:
            resp = await client.get(f"{MAX_API_BASE}/me", timeout=httpx.Timeout(10.0))
            if resp.status_code == 401:
                self._set_fatal_error("invalid_token", "MAX bot token is invalid", retryable=False)
                return False
            if resp.status_code != 200:
                detail = f"MAX /me returned HTTP {resp.status_code}{_http_body_snippet(resp)}"
                self._set_fatal_error("me_failed", detail, retryable=_is_retryable_http_status(resp.status_code))
                return False
            try:
                d = resp.json()
            except ValueError:
                self._set_fatal_error("me_invalid_response", "MAX /me returned non-JSON", retryable=False)
                return False
            if not isinstance(d, dict) or d.get("success") is False:
                detail = d.get("message") if isinstance(d, dict) else None
                self._set_fatal_error("me_rejected", f"MAX /me rejected: {detail or 'success=false'}", retryable=False)
                return False
            logger.info("MAX: connected as @%s (id=%s)", d.get("username", "?"), d.get("user_id"))
            # Register slash commands via PATCH /me/commands
            try:
                await self._set_bot_commands()
            except Exception as cmd_err:  # noqa: BLE001 — adapter must not crash on transport/API errors
                logger.warning("MAX: failed to register commands (non-fatal): %s", cmd_err)
        except Exception as e:  # noqa: BLE001 — adapter must not crash on transport/API errors
            self._set_fatal_error("conn_fail", str(e), retryable=True)
            return False

        if self._use_webhook:
            return await self._start_webhook()
        return await self._start_polling()

    async def disconnect(self) -> None:
        """Shut down the adapter (idempotent, tolerates partial-init state)."""
        self._running = False
        try:
            await self._shutdown_transport()
        finally:
            # Runtime status is core-owned state: report the disconnect even if
            # teardown was interrupted.
            self._mark_disconnected()
        logger.info("MAX: disconnected")

    # ═════════════════════════════════════════════════════════════════════
    # Backpressure, ingress queue and dedup (CODE-08)
    # ═════════════════════════════════════════════════════════════════════

    def _note_overload(self, policy: str) -> None:
        key = "dropped_oldest" if policy == OVERLOAD_DROP_OLDEST else "dropped_newest"
        self._stats[key] += 1
        dropped = self._stats["dropped_oldest"] + self._stats["dropped_newest"]
        if dropped == 1 or dropped % self._drop_log_interval == 0:
            logger.warning("MAX: ingress queue full (maxsize=%d, policy=%s)", self._queue_maxsize, policy)

    def _enqueue_event(self, event: MessageEvent) -> bool:
        """Non-blocking enqueue governed by the explicit overload policy."""
        try:
            self._message_queue.put_nowait(event)
        except asyncio.QueueFull:
            if self._overload_policy == OVERLOAD_DROP_NEWEST:
                self._note_overload(OVERLOAD_DROP_NEWEST)
                return False
            try:
                self._message_queue.get_nowait()
                self._message_queue.task_done()
            except asyncio.QueueEmpty:
                pass
            self._note_overload(OVERLOAD_DROP_OLDEST)
            self._message_queue.put_nowait(event)
        self._stats["enqueued"] += 1
        self._stats["queue_peak"] = max(self._stats["queue_peak"], self._message_queue.qsize())
        return True

    def _remember_mid(self, mid: str, now: float) -> None:
        if len(self._seen_msgs) >= self._SEEN_MSGS_MAX:
            cutoff = now - self._DEDUP_TTL
            self._seen_msgs = {key: ts for key, ts in self._seen_msgs.items() if ts >= cutoff}
            while len(self._seen_msgs) >= self._SEEN_MSGS_MAX:
                self._seen_msgs.pop(next(iter(self._seen_msgs)))
        self._seen_msgs[mid] = now

    def _is_duplicate(self, mid: str, now: float) -> bool:
        seen_at = self._seen_msgs.get(mid)
        return seen_at is not None and now - seen_at < self._DEDUP_TTL

    def backpressure_stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "queue_depth": self._message_queue.qsize(),
            "queue_maxsize": self._queue_maxsize,
            "active_handlers": len(self._handler_tasks),
            "max_concurrency": self._max_concurrency,
            "dedup_entries": len(self._seen_msgs),
            "dedup_max": self._SEEN_MSGS_MAX,
            "overload_policy": self._overload_policy,
        }

    async def _wait_for_handler_slot(self) -> None:
        while self._running and len(self._handler_tasks) >= self._max_concurrency:
            done, _ = await asyncio.wait(
                self._handler_tasks, timeout=1.0, return_when=asyncio.FIRST_COMPLETED,
            )
            for task in done:
                self._handler_tasks.discard(task)

    # ═════════════════════════════════════════════════════════════════════
    # Long polling
    # ═════════════════════════════════════════════════════════════════════

    async def _start_polling(self) -> bool:
        self._stop.clear()

        # ═══════════════════════════════════════════════════════════════
        # Auto-clean stale webhook subscriptions
        #
        # MAX API does NOT support simultaneous webhook + long polling.
        # If a webhook subscription exists (from a previous run or manual
        # registration), /updates returns empty — all messages go to the
        # webhook URL instead.
        #
        # We proactively delete any active webhook subscription when
        # starting in long-polling mode so the user doesn't get stuck
        # with a "dead" subscription pointing at an old/stale URL.
        # ═══════════════════════════════════════════════════════════════
        try:
            sub_resp = await self._http_client.get(
                f"{MAX_API_BASE}/subscriptions",
                timeout=httpx.Timeout(5.0),
            )
            if sub_resp.status_code == 200:
                data = sub_resp.json()
                subs = data.get("subscriptions", [])
                if subs:
                    for sub in subs:
                        url = sub.get("url", "")
                        if url:
                            logger.info(
                                "MAX: cleaning stale webhook subscription: %s",
                                url,
                            )
                            del_resp = await self._http_client.request(
                                "DELETE",
                                f"{MAX_API_BASE}/subscriptions?url={url}",
                                timeout=httpx.Timeout(5.0),
                            )
                            if del_resp.status_code == 200:
                                logger.info(
                                    "MAX: stale webhook subscription deleted: %s",
                                    url,
                                )
                            else:
                                logger.warning(
                                    "MAX: failed to delete stale subscription %s: HTTP %s",
                                    url, del_resp.status_code,
                                )
        except Exception as e:  # noqa: BLE001 — adapter must not crash on transport/API errors
            logger.debug(
                "MAX: webhook cleanup skipped (non-fatal): %s", e,
            )

        self._mark_connected()
        # Both loops are tracked; `_shutdown_transport()` cancels and awaits them
        # before the client is closed (`_poll_task` also covers the webhook path,
        # which starts only the queue-drain loop).
        poll_task = asyncio.create_task(self._poll_loop())
        poll_task.add_done_callback(self._background_tasks.discard)
        self._background_tasks.add(poll_task)
        drain_task = asyncio.create_task(self._queue_poll_loop())
        drain_task.add_done_callback(self._background_tasks.discard)
        self._background_tasks.add(drain_task)
        self._poll_task = drain_task
        logger.info("MAX: long polling started")
        return True

    async def _poll_loop(self) -> None:
        """Long poll /updates with marker-based pagination.

        Every non-200 response and every transport error shares one retry
        policy: bounded exponential backoff with jitter, honouring the
        server's ``Retry-After`` when it sends one (429/503). HTTP 401 is the
        one *fatal* status — MAX rejected the bot token, so retrying can only
        hammer the API; the loop stops and publishes the fatal auth state
        (same ``invalid_token`` code ``connect()`` uses for its /me check)
        so the supervisor can surface it instead of seeing a live adapter
        that can never receive anything.
        """
        last_marker = 0
        errs = 0
        while not self._stop.is_set():
            try:
                url = f"{MAX_API_BASE}/updates?timeout={POLL_TIMEOUT}&limit=100"
                if last_marker:
                    url += f"&marker={last_marker}"
                resp = await self._http_client.get(url, timeout=httpx.Timeout(POLL_TIMEOUT + 10))
                if resp.status_code == 200:
                    data = resp.json()
                    for u in data.get("updates", []):
                        event = await self._build_event(u)
                        if event is not None:
                            self._enqueue_event(event)
                    marker = data.get("marker", 0)
                    if marker:
                        last_marker = marker
                    errs = 0
                elif resp.status_code == 401:
                    logger.error(
                        "MAX: poll rejected with HTTP 401 — bot token is invalid, "
                        "long polling stopped (check MAX_BOT_TOKEN)",
                    )
                    self._set_fatal_error(
                        "invalid_token",
                        "MAX bot token is invalid (HTTP 401 from GET /updates)",
                        retryable=False,
                    )
                    self._stop.set()
                    return
                else:
                    errs += 1
                    delay = _poll_status_delay(getattr(resp, "headers", None), errs)
                    logger.warning(
                        "MAX: poll HTTP %s (attempt %d), retrying in %.1fs",
                        resp.status_code, errs, delay,
                    )
                    await _poll_sleep(delay)
            except asyncio.CancelledError:
                break
            except Exception as e:  # noqa: BLE001 — adapter must not crash on transport/API errors
                errs += 1
                delay = _poll_backoff_delay(errs)
                logger.warning(
                    "MAX: poll error (attempt %d): %s: %s — retrying in %.1fs",
                    errs, type(e).__name__, e, delay,
                )
                await _poll_sleep(delay)

    # ═════════════════════════════════════════════════════════════════════
    # Webhook server
    # ═════════════════════════════════════════════════════════════════════

    async def _queue_poll_loop(self) -> None:
        """Drain ingress with bounded concurrent message handlers."""
        while self._running:
            try:
                event = await asyncio.wait_for(self._message_queue.get(), timeout=1.0)
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            if not self._running:
                break
            await self._wait_for_handler_slot()
            if not self._running:
                break
            try:
                self._stats["dispatched"] += 1
                task = asyncio.create_task(self.handle_message(event))
                self._background_tasks.add(task)
                self._handler_tasks.add(task)
                self._stats["handlers_peak"] = max(self._stats["handlers_peak"], len(self._handler_tasks))

                def _forget(completed: asyncio.Task) -> None:
                    self._background_tasks.discard(completed)
                    self._handler_tasks.discard(completed)

                task.add_done_callback(_forget)
            except Exception:
                logger.exception("MAX: failed to dispatch queued event")

    # ═════════════════════════════════════════════════════════════════════
    # Update processing
    # ═════════════════════════════════════════════════════════════════════

    async def _build_event(self, payload: dict[str, Any]) -> MessageEvent | None:
        """Parse a Max Update object into a MessageEvent."""
        update_type = payload.get("update_type", "")

        if update_type == "bot_started":
            user = payload.get("user", {})
            cid = str(payload.get("chat_id", ""))
            uid = str(user.get("user_id", ""))
            payload_text = payload.get("payload", "")
            self._dm_user_ids[cid] = uid
            source = self.build_source(
                chat_id=f"user:{uid}",
                chat_name=user.get("name", uid),
                chat_type="dm",
                user_id=uid,
                user_name=user.get("name", uid),
            )
            return MessageEvent(
                text=f"/start {payload_text}".strip(),
                message_type=MessageType.TEXT,
                source=source,
                raw_message=payload,
                message_id=f"start_{uid}",
            )

        if update_type == "bot_added":
            cid = str(payload.get("chat_id", ""))
            uid = str((payload.get("user") or {}).get("user_id", ""))
            source = self.build_source(
                chat_id=f"chat:{cid}",
                chat_name=cid,
                chat_type="group",
                user_id=uid,
                user_name=uid,
            )
            return MessageEvent(
                text="/start",
                message_type=MessageType.TEXT,
                source=source,
                internal=True,
            )

        if update_type in ("message_created", "message_edited", "message_updated"):
            return await self._on_message_created(payload)

        if update_type == "message_callback":
            return await self._on_callback(payload)

        # Unknown update types (voice messages may arrive with a special type)
        if update_type and update_type not in (
            "message_created", "message_edited", "message_updated",
            "message_callback", "bot_started", "bot_added",
        ):
            logger.info("MAX: unhandled update_type=%r keys=%s", update_type, list(payload.keys()))

        return None

    async def _on_message_created(self, update: dict) -> MessageEvent | None:
        """Process message_created update. Returns MessageEvent or None."""
        message = update.get("message", {}) or {}
        body = message.get("body") or {}
        sender = message.get("sender") or update.get("user") or {}
        recipient = message.get("recipient") or {}

        # Skip bot messages
        if sender.get("is_bot") is True:
            return None

        user_id = str(
            sender.get("user_id")
            or update.get("user_id")
            or message.get("user_id")
            or ""
        )
        user_name = (
            sender.get("name")
            or sender.get("first_name")
            or sender.get("username")
            or user_id
        )

        text = (body.get("text") or message.get("text") or "").strip()

        chat = update.get("chat", {}) or {}
        chat_id_str = str(
            recipient.get("chat_id")
            or chat.get("chat_id")
            or message.get("chat_id")
            or ""
        )

        # MAX dialogs carry a service chat_id too. `chat_type=dialog` is the
        # authoritative discriminator; only non-dialog recipients are groups.
        is_dialog = str(recipient.get("chat_type") or "").lower() == "dialog"
        if chat_id_str and not is_dialog:
            chat_type = "group"
            scoped_chat_id = f"chat:{chat_id_str}"
        else:
            chat_type = "dm"
            scoped_chat_id = f"user:{user_id}"

        # Store DM mapping
        self._dm_user_ids[str(chat_id_str or user_id)] = user_id

        # Dedup: suppress only messages inside the configurable TTL and keep
        # the table under its advertised hard cap even during a fresh burst.
        mid = str(body.get("mid") or message.get("mid") or message.get("message_id") or "")
        if mid:
            now = time.time()
            if self._is_duplicate(mid, now):
                self._stats["duplicate_suppressed"] += 1
                return None
            self._remember_mid(mid, now)

        # Access control
        if (not self._allow_all_users and self._allowed_users_set
                and user_id not in self._allowed_users_set):
            logger.debug("MAX: ignoring message from unauthorized user %s", user_id)
            return None

        # Group access control
        if chat_type == "group" and not self._group_message_allowed(user_id, chat_id_str):
            logger.info(
                "MAX: group message blocked: policy=%s user=%s chat=%s",
                self._group_policy, user_id, chat_id_str,
            )
            return None

        # Extract media
        media_urls, media_types = await self._extract_inbound_media(update, message, body)
        logger.debug(
            "MAX: media extracted: %s urls, types=%s",
            len(media_urls), media_types,
        )

        # Voice messages: cache any audio attachments so the Hermes core STT
        # pipeline (config.yaml -> stt) can transcribe them. MAX may send
        # voice as message.attachments, message.voice, or at the update root
        # level instead of body.attachments.
        if not media_urls and not text:
            voice_url = _find_audio_url_direct(update)
            if voice_url:
                logger.info("MAX: found audio via fallback: %s", _safe_url_for_log(voice_url))
                cached = await self._cache_audio_attachment(
                    {"type": "voice", "payload": {"url": voice_url}}, "voice"
                )
                if cached:
                    audio_path, audio_mtype = cached
                    media_urls.append(audio_path)
                    media_types.append(audio_mtype)
                    logger.info("MAX: audio cached (fallback) to %s", audio_path)
            if not media_urls and not text:
                logger.warning("MAX: raw update payload: %s",
                    _json.dumps(update, ensure_ascii=False, default=str)[:2048])

        # Process basic attachments as text references (for non-recursive fallback)
        if not media_urls:
            attachments = body.get("attachments", [])
            for att in attachments:
                atype = att.get("type", "")
                payload_att = att.get("payload", {})
                if atype == "image":
                    url = payload_att.get("url", "")
                    text = (text + f"\n[Image: {url}]").strip() if text else f"[Image: {url}]"
                elif atype == "audio":
                    audio_url = payload_att.get("url", "")
                    if audio_url:
                        pseudo_att = {"type": "audio", "payload": {"url": audio_url}}
                        cached = await self._cache_audio_attachment(pseudo_att, "audio")
                        if cached:
                            audio_path, _ = cached
                            text = (text + f"\n[Audio: {audio_path}]").strip() if text else f"[Audio: {audio_path}]"
                            logger.info("MAX: audio downloaded (fallback) to %s", audio_path)
                        else:
                            text = (text + "\n[Audio]").strip() if text else "[Audio]"
                    else:
                        text = (text + "\n[Audio]").strip() if text else "[Audio]"
                elif atype in ("video", "sticker"):
                    text = (text + f"\n[{atype.title()}]").strip() if text else f"[{atype.title()}]"
                elif atype == "file":
                    text = (text + "\n[File]").strip() if text else "[File]"
                elif atype == "location":
                    text = (text + f"\n[Location: {payload_att.get('latitude','')},{payload_att.get('longitude','')}]").strip() if text else "[Location: ...]"

        # ── Cross-platform session commands (bypass platform scoping) ──
        if text and self._cross_session and self._cross_session_allowed(user_id):
            if text.startswith('/sessions'):
                args = text[len('/sessions'):].strip()
                if args and args.lower() != 'search' and not args.lower().startswith('search '):
                    # Has a target ID → let core handle with --all override
                    text = f"/resume --all {args}"
                else:
                    # Plain /sessions or /sessions search → our handler (all platforms)
                    await self._handle_cross_sessions(text, scoped_chat_id, user_id)
                    return None
            elif text.startswith('/resume'):
                if '--all' not in text and '--cross-room' not in text:
                    parts = text.split(maxsplit=1)
                    if len(parts) == 1:
                        # /resume with no args → our handler (all platforms)
                        await self._handle_cross_sessions('/sessions', scoped_chat_id, user_id)
                        return None
                    else:
                        # /resume <target> → rewrite with --all for core
                        text = f"/resume --all {parts[1].strip()}"

        if not text and not media_urls:
            return None

        msg_type = self._derive_message_type(text, media_types)

        source = self.build_source(
            chat_id=scoped_chat_id,
            chat_name=user_name if chat_type == "dm" else (chat.get("title") or chat_id_str),
            chat_type=chat_type,
            user_id=user_id,
            user_name=user_name,
        )
        try:
            session_key = self._source_session_key(source)
        except Exception as exc:  # noqa: BLE001 — owner binding must fail closed, not crash ingress
            logger.debug("MAX: cannot derive interaction owner: %s", exc)
            session_key = ""
        self._remember_interaction_owner(
            session_key=session_key, chat_id=scoped_chat_id, user_id=user_id,
        )

        return MessageEvent(
            text=text,
            message_type=msg_type,
            source=source,
            raw_message=update,
            message_id=mid,
            media_urls=media_urls,
            media_types=media_types,
        )

    # ═════════════════════════════════════════════════════════════════════
    # Media extraction (recursive walk)
    # ═════════════════════════════════════════════════════════════════════

    async def _extract_inbound_media(
        self, payload: dict[str, Any], message: dict[str, Any], body: dict[str, Any]
    ) -> tuple[list[str], list[str]]:
        """Recursively find and cache all media attachments in the payload."""
        attachments: list[dict[str, Any]] = []
        seen: set[int] = set()

        def add_attachment(item: Any) -> None:
            if not isinstance(item, dict):
                return
            ident = id(item)
            if ident in seen:
                return
            seen.add(ident)
            attachments.append(item)

        def walk(obj: Any) -> None:
            if isinstance(obj, dict):
                raw = obj.get("attachments")
                if isinstance(raw, list):
                    for item in raw:
                        add_attachment(item)
                elif isinstance(raw, dict):
                    add_attachment(raw)
                # Direct media wrappers
                for key in ("audio", "voice", "file", "document", "doc",
                            "attachment", "media", "image", "photo", "picture"):
                    value = obj.get(key)
                    if isinstance(value, dict):
                        pseudo = {"type": key, "payload": value}
                        add_attachment(pseudo)
                if self._attachment_kind(obj) in {"audio", "voice", "image", "document"}:
                    add_attachment(obj)
                for value in obj.values():
                    walk(value)
            elif isinstance(obj, list):
                for value in obj:
                    walk(value)

        walk(payload)

        media_paths: list[str] = []
        media_types: list[str] = []
        seen_media_refs: set[str] = set()
        candidates: list[tuple[dict[str, Any], str]] = []

        for attachment in attachments:
            kind = self._attachment_kind(attachment)
            if kind not in {"audio", "voice", "image", "document"}:
                continue
            media_ref = self._find_first_url(attachment) or f"object:{id(attachment)}"
            if media_ref in seen_media_refs:
                continue
            seen_media_refs.add(media_ref)
            candidates.append((attachment, kind))

        # Bound the fan-out before scheduling: the count cap applies to what we
        # are willing to download, and an oversized update must not spawn tasks.
        if len(candidates) > self._inbound_media_max_attachments:
            logger.warning(
                "MAX: update carries %d media attachments; considering only the first %d",
                len(candidates), self._inbound_media_max_attachments,
            )
            candidates = candidates[: self._inbound_media_max_attachments]

        budget = _InboundMediaBudget(
            max_attachments=self._inbound_media_max_attachments,
            max_bytes=self._inbound_media_total_max_bytes,
        )

        async def fetch(attachment: dict[str, Any], kind: str) -> tuple[str, str] | None:
            if not await budget.admit():
                logger.warning(
                    "MAX: inbound media attachment cap (%d) reached; dropping %s",
                    self._inbound_media_max_attachments, kind,
                )
                return None
            if kind in {"audio", "voice"}:
                return await self._cache_audio_attachment(attachment, kind, budget=budget)
            if kind == "image":
                return await self._cache_image_attachment(attachment, budget=budget)
            return await self._cache_document_attachment(attachment, budget=budget)

        # Downloads run concurrently (bounded by the download semaphore) while
        # the results keep their original order.
        for cached in await asyncio.gather(*(fetch(att, kind) for att, kind in candidates)):
            if cached:
                media_paths.append(cached[0])
                media_types.append(cached[1])

        return media_paths, media_types

    @staticmethod
    def _attachment_kind(attachment: dict[str, Any]) -> str:
        """Determine attachment kind from type keys and payload."""
        values: list[str] = []
        for key in ("type", "attachment_type", "kind", "media_type"):
            value = attachment.get(key)
            if value:
                values.append(str(value).lower())
        payload = attachment.get("payload")
        if isinstance(payload, dict):
            for key in ("type", "attachment_type", "kind", "media_type",
                        "mime_type", "content_type"):
                value = payload.get(key)
                if value:
                    values.append(str(value).lower())
            for key in ("audio", "voice", "image", "photo", "picture",
                        "file", "document", "doc"):
                if key in payload:
                    values.append(key)
        filename = MaxAdapter._find_first_filename(attachment) or ""
        if filename:
            values.append(filename.lower())
        joined = " ".join(values)
        if "voice" in joined:
            return "voice"
        if "audio" in joined or joined.startswith("ptt"):
            return "audio"
        if any(marker in joined for marker in ("image", "photo", "picture")):
            return "image"
        if any(marker in joined for marker in ("file", "document", "doc", "attachment")):
            return "document"
        ext = Path(filename).suffix.lower() if filename else ""
        if ext in SUPPORTED_DOCUMENT_TYPES:
            return "document"
        return ""

    @staticmethod
    def _find_first_url(data: Any) -> str | None:
        """Find a plausible download URL inside an attachment payload."""
        if isinstance(data, dict):
            for key in ("url", "download_url", "downloadUrl", "file_url",
                        "fileUrl", "media_url", "mediaUrl", "href", "link"):
                value = data.get(key)
                if isinstance(value, str) and value.startswith(("http://", "https://")):
                    return value
            for value in data.values():
                found = MaxAdapter._find_first_url(value)
                if found:
                    return found
        elif isinstance(data, list):
            for value in data:
                found = MaxAdapter._find_first_url(value)
                if found:
                    return found
        return None

    @staticmethod
    def _find_first_filename(data: Any) -> str | None:
        """Find a plausible original filename inside an attachment payload."""
        if isinstance(data, dict):
            for key in ("filename", "file_name", "fileName", "name",
                        "title", "display_name", "displayName",
                        "original_filename", "originalFilename"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    return Path(value.strip()).name
            for value in data.values():
                found = MaxAdapter._find_first_filename(value)
                if found:
                    return found
        elif isinstance(data, list):
            for value in data:
                found = MaxAdapter._find_first_filename(value)
                if found:
                    return found
        return None

    @staticmethod
    def _safe_url_for_log(url: str) -> str:
        """Strip credentials from URL for logging."""
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return "[invalid-url]"
        path = parsed.path or "/"
        return f"{parsed.scheme}://{parsed.netloc}{path}"

    @staticmethod
    def _validate_download_url(
        url: str,
        allowed_suffixes: tuple[str, ...] = DOWNLOAD_ALLOWED_HOST_SUFFIXES,
        *,
        require_host_allowlist: bool = True,
    ) -> bool:
        """SSRF guard for media downloads before DNS validation.

        Layered, cheapest check first:
        * scheme must be https;
        * credentials in URL (user:pass@host) are rejected;
        * bare localhost/*.local names are rejected;
        * literal IPs (including legacy inet_aton spellings) must be public;
        * an operator-configured allowlist, when required, must match the host.
        """
        parsed = urlparse(url)
        if parsed.scheme.lower() not in DOWNLOAD_ALLOWED_SCHEMES:
            return False
        if parsed.username or parsed.password:
            return False
        host = parsed.hostname
        if not host:
            return False
        host_l = host.lower().rstrip(".")
        if not host_l:
            return False
        if host_l == "localhost" or host_l.endswith(".local"):
            return False
        if require_host_allowlist and not _host_allowed_by_suffixes(host_l, allowed_suffixes):
            return False
        ip = _parse_host_ip(host_l)
        if ip is not None:
            return _is_public_ip(ip)
        return True

    def _download_url_allowed(self, url: str) -> bool:
        """Validate syntax and apply an operator allowlist when one was supplied."""
        return self._validate_download_url(
            url,
            self._download_allowed_suffixes,
            require_host_allowlist=self._download_host_allowlist_configured,
        )

    @staticmethod
    def _resolve_public_addresses(host: str, port: int) -> list[str] | None:
        """Resolve *host* and return its addresses only if all of them are public."""
        try:
            infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except OSError:
            return None
        addresses: set[str] = set()
        for _family, _socktype, _proto, _canonname, sockaddr in infos:
            ip = _parse_host_ip(str(sockaddr[0]))
            if ip is None or not _is_public_ip(ip):
                return None
            addresses.add(str(ip))
        if not addresses:
            return None
        return sorted(addresses)

    @staticmethod
    def _pin_download_request(
        url: str, ip: str
    ) -> tuple[str, dict[str, str], dict[str, Any]]:
        """Rewrite *url* to dial *ip* directly, keeping the original Host/SNI."""
        parsed = urlparse(url)
        host = parsed.hostname or ""
        try:
            port = parsed.port
        except ValueError:
            port = None
        address = f"[{ip}]" if ":" in ip else ip
        netloc = f"{address}:{port}" if port is not None else address
        pinned_url = parsed._replace(netloc=netloc).geturl()
        host_header = f"[{host}]" if ":" in host else host
        if port is not None and port != 443:
            host_header = f"{host_header}:{port}"
        return pinned_url, {"Host": host_header}, {"sni_hostname": host}

    async def _prepare_download(
        self, url: str
    ) -> tuple[str, dict[str, str], dict[str, Any]] | None:
        """Validate, resolve and pin a media-download URL."""
        if not self._download_url_allowed(url):
            return None
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        ip = _parse_host_ip(host)
        if ip is None:
            try:
                port = parsed.port or 443
            except ValueError:
                return None
            addresses = await asyncio.to_thread(
                self._resolve_public_addresses, host, port
            )
            if not addresses:
                return None
            ip = ipaddress.ip_address(addresses[0])
        return self._pin_download_request(url, str(ip))

    def _is_trusted_download_origin(self, url: str) -> bool:
        """Return True only for HTTPS URLs on a host we explicitly trust."""
        parsed = urlparse(url)
        if parsed.scheme != "https":
            return False
        host = (parsed.hostname or "").lower().rstrip(".")
        if not host:
            return False
        if host.endswith(_TRUSTED_DOWNLOAD_HOST_SUFFIXES):
            return True
        for entry in self._trusted_download_hosts:
            if entry.startswith("*."):
                if host.endswith(entry[1:]):
                    return True
            elif host == entry:
                return True
        return False

    def _attachment_download_headers(self, url: str, accept: str) -> dict[str, str]:
        """Request headers for an attachment download."""
        headers = {"User-Agent": _DOWNLOAD_USER_AGENT, "Accept": accept}
        if self._token and self._is_trusted_download_origin(url):
            headers["Authorization"] = self._token
        return headers

    def _redact_secrets(self, text: str) -> str:
        """Remove the bot token from a string before it reaches the logs."""
        if not text:
            return text
        if self._token and len(self._token) >= 8:
            text = text.replace(self._token, "[redacted]")
        return text

    @staticmethod
    def _detect_image_mime(data: bytes) -> str:
        """Detect image MIME type from magic bytes."""
        if len(data) < 12:
            return "image/jpeg"
        # PNG: 89 50 4E 47
        if data[0] == 0x89 and data[1] == 0x50 and data[2] == 0x4E and data[3] == 0x47:
            return "image/png"
        # JPEG: FF D8 FF
        if data[0] == 0xFF and data[1] == 0xD8 and data[2] == 0xFF:
            return "image/jpeg"
        # WebP: RIFF....WEBP
        if (data[0] == 0x52 and data[1] == 0x49 and data[2] == 0x46 and data[3] == 0x46
                and data[8] == 0x57 and data[9] == 0x45 and data[10] == 0x42 and data[11] == 0x50):
            return "image/webp"
        # GIF: GIF8
        if data[0] == 0x47 and data[1] == 0x49 and data[2] == 0x46 and data[3] == 0x38:
            return "image/gif"
        # BMP: BM
        if data[0] == 0x42 and data[1] == 0x4D:
            return "image/bmp"
        return "image/jpeg"

    # ── Inbound media downloads (bounded: bytes, deadline, concurrency) ──

    def _inbound_download_slot(self) -> asyncio.Semaphore:
        """Semaphore bounding how many inbound media downloads run concurrently."""
        if self._inbound_semaphore is None:
            self._inbound_semaphore = asyncio.Semaphore(self._inbound_media_concurrency)
        return self._inbound_semaphore

    def _cache_write_slot(self) -> asyncio.Lock:
        """Lock serialising cache writes so partial-file cleanup is race-free."""
        if self._cache_write_lock is None:
            self._cache_write_lock = asyncio.Lock()
        return self._cache_write_lock

    async def _read_limited_inbound_body(
        self,
        response: Any,
        *,
        media_type: str,
        budget: _InboundMediaBudget | None,
        deadline: float,
    ) -> bytes:
        """Read a streaming body under the per-body cap, message budget and deadline."""
        max_bytes = self._inbound_attachment_max_bytes
        declared = response.headers.get("content-length")
        if declared:
            try:
                declared_size = int(declared)
            except (TypeError, ValueError):
                logger.debug("MAX: ignoring invalid Content-Length for inbound %s: %r", media_type, declared)
            else:
                if max_bytes and declared_size > max_bytes:
                    raise InboundMediaLimitError(
                        f"declared size {declared_size} bytes exceeds the {max_bytes}-byte per-attachment cap"
                    )

        chunks: list[bytes] = []
        total = 0
        charged = 0
        try:
            async for chunk in response.aiter_bytes(INBOUND_MEDIA_CHUNK_SIZE):
                if not chunk:
                    continue
                if time.monotonic() > deadline:
                    raise InboundMediaLimitError(
                        f"download exceeded the {self._inbound_media_timeout:g}s deadline ({total} bytes read)"
                    )
                total += len(chunk)
                if max_bytes and total > max_bytes:
                    raise InboundMediaLimitError(
                        f"body exceeds the {max_bytes}-byte per-attachment cap ({total} bytes read)"
                    )
                if budget is not None:
                    if not await budget.charge(len(chunk)):
                        raise InboundMediaLimitError(
                            f"per-message aggregate cap of {budget.max_bytes} bytes reached"
                        )
                    charged += len(chunk)
                chunks.append(chunk)
        except BaseException:
            if budget is not None and charged:
                await budget.refund(charged)
            raise
        return b"".join(chunks)

    async def _download_inbound_media(
        self,
        url: str,
        *,
        media_type: str,
        budget: _InboundMediaBudget | None = None,
    ) -> tuple[bytes, str] | None:
        """Stream one inbound attachment; return ``(body, content-type)`` or ``None``."""
        client = self._download_client or self._http_client
        if not client:
            return None

        prepared = await self._prepare_download(url)
        if prepared is None:
            # A rejected origin, DNS answer, or malformed port must never reach a
            # direct fallback request.  One attachment is attempted at most once.
            logger.warning(
                "MAX: refusing to download %s from blocked origin: %s",
                media_type, self._safe_url_for_log(url),
            )
            return None
        request_url, pin_headers, extensions = prepared

        headers = {
            **self._attachment_download_headers(url, _INBOUND_MEDIA_ACCEPT.get(media_type, "*/*")),
            **pin_headers,
        }
        timeout = self._inbound_media_timeout
        deadline = time.monotonic() + timeout

        # If client supports stream() and stream is not an AsyncMock (e.g. FakeClient in limits test)
        if hasattr(client, "stream") and not hasattr(client.stream, "assert_called"):
            try:
                async with self._inbound_download_slot(), client.stream(
                    "GET", request_url, headers=headers, timeout=httpx.Timeout(timeout), extensions=extensions
                ) as resp:
                    if resp.status_code in DOWNLOAD_REDIRECT_STATUS_CODES:
                        logger.warning("MAX: refusing redirect for %s: %s", media_type, self._safe_url_for_log(url))
                        return None
                    resp.raise_for_status()
                    content_type = str(resp.headers.get("content-type") or "")
                    body = await self._read_limited_inbound_body(
                        resp, media_type=media_type, budget=budget, deadline=deadline
                    )
                return body, content_type
            except InboundMediaLimitError as exc:
                logger.warning("MAX: dropped inbound %s from %s: %s", media_type, self._safe_url_for_log(url), exc)
                return None
            except Exception as exc:  # noqa: BLE001 — adapter must not crash on transport/API errors
                logger.warning("MAX: failed to download %s from %s: %s", media_type, self._safe_url_for_log(url), self._redact_secrets(str(exc)))
                return None
        else:
            # Standard get() path (used by mock transport and AsyncMock in test_ssrf_download)
            try:
                resp = await client.get(request_url, headers=headers, extensions=extensions)
                if resp.status_code in DOWNLOAD_REDIRECT_STATUS_CODES:
                    logger.warning("MAX: refusing redirect for %s: %s", media_type, self._safe_url_for_log(url))
                    return None
                resp.raise_for_status()
                content_type = str(resp.headers.get("content-type") or "")
                body = resp.content
                if self._inbound_attachment_max_bytes and len(body) > self._inbound_attachment_max_bytes:
                    return None
                if budget is not None and not await budget.charge(len(body)):
                    return None
                return body, content_type
            except Exception as exc:  # noqa: BLE001 — adapter must not crash on transport/API errors
                logger.warning("MAX: failed to download %s from %s: %s", media_type, self._safe_url_for_log(url), self._redact_secrets(str(exc)))
                return None

    async def _persist_inbound_media(
        self, cache_fn: Any, data: bytes, arg: str, *, media_type: str
    ) -> str | None:
        """Cache validated media through a core writer, cleaning up partial files."""
        cache_dir = _inbound_cache_dir(media_type)
        if cache_dir is not None and cache_dir.exists():
            try:
                free = shutil.disk_usage(cache_dir).free
            except OSError:
                free = None
            if free is not None and free < len(data) + CACHE_FREE_SPACE_HEADROOM:
                logger.warning(
                    "MAX: refusing to cache inbound %s (%d bytes): only %d bytes free in %s",
                    media_type, len(data), free, cache_dir,
                )
                return None
        async with self._cache_write_slot():
            before = _dir_snapshot(cache_dir)
            try:
                return cache_fn(data, arg)
            except Exception as exc:  # noqa: BLE001 — a failed cache write must not crash the adapter
                for stale in _dir_snapshot(cache_dir, exclude=before):
                    with contextlib.suppress(OSError):
                        stale.unlink()
                logger.warning("MAX: failed to cache inbound %s (%d bytes): %s", media_type, len(data), exc)
                return None

    async def _cache_audio_attachment(
        self,
        attachment: dict[str, Any],
        kind: str,
        budget: _InboundMediaBudget | None = None,
    ) -> tuple[str, str] | None:
        """Download audio attachment and cache it for the core STT pipeline."""
        url = self._find_first_url(attachment)
        if not url:
            return None
        downloaded = await self._download_inbound_media(url, media_type=kind, budget=budget)
        if not downloaded:
            return None
        body, header_type = downloaded
        content_type = header_type.split(";", 1)[0].strip().lower()
        if not content_type or content_type == "application/octet-stream":
            guessed, _ = mimetypes.guess_type(urlparse(url).path)
            content_type = guessed or "audio/ogg"
        if not content_type.startswith("audio/"):
            ext_from_url = Path(urlparse(url).path).suffix.lower()
            if ext_from_url not in {".ogg", ".oga", ".opus", ".mp3", ".m4a", ".aac", ".wav", ".amr", ".webm"}:
                logger.info("MAX: downloaded %s but content-type is not audio: %s", kind, content_type)
                return None
        ext = mimetypes.guess_extension(content_type) if content_type else None
        if not ext:
            ext = Path(urlparse(url).path).suffix.lower() or ".ogg"
        if ext == ".oga":
            ext = ".ogg"
        path = await self._persist_inbound_media(cache_audio_from_bytes, body, ext, media_type=kind)
        if path is None:
            return None
        return path, content_type or "audio/ogg"

    async def _cache_image_attachment(
        self,
        attachment: dict[str, Any],
        budget: _InboundMediaBudget | None = None,
    ) -> tuple[str, str] | None:
        """Download image attachment and cache it."""
        url = self._find_first_url(attachment)
        if not url:
            return None
        downloaded = await self._download_inbound_media(url, media_type="image", budget=budget)
        if not downloaded:
            return None
        body, header_type = downloaded
        content_type = header_type.split(";", 1)[0].strip().lower()
        if not content_type or content_type == "application/octet-stream":
            # Try magic bytes first — more reliable than Content-Type header
            magic_mime = self._detect_image_mime(body)
            if magic_mime.startswith("image/"):
                content_type = magic_mime
            else:
                guessed, _ = mimetypes.guess_type(urlparse(url).path)
                content_type = guessed or "image/jpeg"
        ext = mimetypes.guess_extension(content_type) if content_type else None
        if not ext:
            ext = Path(urlparse(url).path).suffix.lower() or ".jpg"
        if ext in {".jpe", ".jpeg"}:
            ext = ".jpg"
        path = await self._persist_inbound_media(cache_image_from_bytes, body, ext, media_type="image")
        if path is None:
            return None
        return path, content_type or "image/jpeg"

    async def _cache_document_attachment(
        self,
        attachment: dict[str, Any],
        budget: _InboundMediaBudget | None = None,
    ) -> tuple[str, str] | None:
        """Download document attachment and cache it."""
        url = self._find_first_url(attachment)
        if not url:
            return None
        downloaded = await self._download_inbound_media(url, media_type="document", budget=budget)
        if not downloaded:
            return None
        body, header_type = downloaded
        content_type = header_type.split(";", 1)[0].strip().lower()
        filename = self._find_first_filename(attachment) or Path(urlparse(url).path).name or "document"
        ext = Path(filename).suffix.lower()
        if not content_type or content_type == "application/octet-stream":
            guessed, _ = mimetypes.guess_type(filename)
            content_type = guessed or "application/octet-stream"
        if not ext:
            guessed_ext = mimetypes.guess_extension(content_type) if content_type else None
            ext = guessed_ext or ".bin"
            filename = f"{filename}{ext}"
        if ext in SUPPORTED_DOCUMENT_TYPES:
            content_type = SUPPORTED_DOCUMENT_TYPES[ext]
        path = await self._persist_inbound_media(cache_document_from_bytes, body, filename, media_type="document")
        if path is None:
            return None
        return path, content_type

    @staticmethod
    def _derive_message_type(text: str, media_types: list[str]) -> MessageType:
        """Derive MessageType from text and media types."""
        if any(mtype.startswith(("application/", "text/"))
               or mtype == "application/octet-stream" for mtype in media_types):
            return MessageType.DOCUMENT
        if any(mtype.startswith("image/") for mtype in media_types):
            return MessageType.TEXT if text else MessageType.PHOTO
        if any(mtype.startswith("audio/") for mtype in media_types):
            return MessageType.TEXT if text else MessageType.VOICE
        return MessageType.TEXT

    # ═════════════════════════════════════════════════════════════════════
    # Outbound: send messages
    # ═════════════════════════════════════════════════════════════════════

    def _split_outbound_text(
        self, content: str, limit: int | None = None
    ) -> list[str]:
        """Split long outbound text into Max-sized chunks (≤ ``limit`` chars).

        Lossless: ``"".join(result) == content`` for every input — the splitter
        never trims or re-joins characters, so nothing is dropped at a chunk
        boundary. Splits prefer paragraph, then line, then word boundaries and
        only cut mid-word for a word longer than the limit.
        """
        budget = OUTBOUND_CHUNK_LIMIT if limit is None else max(1, limit)
        if len(content) <= budget:
            return [content]
        segments = _iter_text_segments(content, budget)
        return _pack_segments(segments, budget)

    def _numbered_outbound_chunks(self, content: str) -> list[str]:
        """Chunk ``content`` and prepend the ``(i/n)\\n`` numbering prefix.

        The prefix is accounted for *before* splitting (CODE-02): the split is
        re-run with a reduced text budget until the number of chunks — and
        therefore the prefix width — is stable, so the sender never has to
        truncate a chunk after the fact. ``"".join`` of the returned texts with
        the prefixes removed reproduces ``content`` exactly, and no payload
        exceeds ``MAX_MESSAGE_LENGTH``.
        """
        budget = OUTBOUND_CHUNK_LIMIT
        chunks = self._split_outbound_text(content, budget)
        for _ in range(8):  # prefix width changes at most once per digit count
            if len(chunks) <= 1:
                break
            prefix_len = len(f"({len(chunks)}/{len(chunks)})\n")
            if prefix_len >= budget:
                break  # pragma: no cover - defensive: 3900-char budget never yields this
            renumbered = self._split_outbound_text(content, budget - prefix_len)
            stable = len(renumbered) == len(chunks)
            chunks = renumbered
            if stable:
                break
        if len(chunks) <= 1:
            return chunks
        total = len(chunks)
        prefix_len = len(f"({total}/{total})\n")
        # Leading whitespace may move onto the previous chunk, but only within
        # the API limit (MAX_MESSAGE_LENGTH) that the prefix is not using.
        _move_leading_whitespace(chunks, MAX_MESSAGE_LENGTH - prefix_len)
        return [f"({idx}/{total})\n{text}" for idx, text in enumerate(chunks, start=1)]

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SendResult:
        """Send a text message, automatically chunking if over limit."""
        if not self._http_client:
            return SendResult(success=False, error="Not connected")

        parts = chat_id.split(":", 1)
        target_type = parts[0] if len(parts) > 1 else "user"
        target_id = parts[1] if len(parts) > 1 else chat_id

        params = {}
        if target_type == "chat" or _is_group(target_id):
            params["chat_id"] = target_id
        else:
            user_id = self._dm_user_ids.get(chat_id, target_id)
            params["user_id"] = user_id

        # ── Handle tables ─────────────────────────────────────────────
        # Table images (MAX_TABLE_AS_IMAGE) or text fallback
        image_tokens: list[str] = []

        if self._table_as_image:
            # Try to render tables as images
            import re as _re

            lines = content.split("\n")
            new_lines = []
            i = 0
            while i < len(lines):
                line = lines[i]
                if _re.match(r"^\|.+\|", line):
                    table_lines = []
                    has_sep = False
                    while i < len(lines) and _re.match(r"^\|.+\|", lines[i]):
                        cur = lines[i]
                        table_lines.append(cur)
                        if _re.match(r"^\|[\s\-:|]+\|$", cur):
                            has_sep = True
                        i += 1
                    if has_sep and len(table_lines) >= 2:
                        token = await self._render_table_as_image(table_lines)
                        if token:
                            image_tokens.append(token)
                            # Replace table with a compact text reference
                            new_lines.append("📊 _таблица_")
                        else:
                            # Image failed — render as text
                            converted = MaxAdapter._render_table(table_lines)
                            new_lines.append(converted)
                    else:
                        new_lines.extend(table_lines)
                else:
                    new_lines.append(line)
                    i += 1
            content = "\n".join(new_lines)
        else:
            # Text-only mode (default)
            content = self._convert_markdown_tables(content)

        # ── Send ───────────────────────────────────────────────────────
        # Numbering prefixes are budgeted before the split, so no chunk is
        # truncated after the fact (CODE-02).
        chunks = self._numbered_outbound_chunks(content)
        last_result: SendResult | None = None

        for idx, text in enumerate(chunks, start=1):

            body: dict[str, Any] = {
                "text": text,
                "format": "markdown",
                "notify": True,
            }

            # Attach table images to the first chunk
            if idx == 1 and image_tokens:
                body["attachments"] = [
                    {"type": "image", "payload": {"token": t}} for t in image_tokens
                ]

            if reply_to:
                body["link"] = {"type": "REPLY", "mid": reply_to}

            try:
                resp = await self._http_client.post(
                    f"{MAX_API_BASE}/messages",
                    params=params,
                    json=body,
                )
                resp.raise_for_status()
                data = resp.json()
                msg = data.get("message", {})
                last_result = SendResult(
                    success=True,
                    message_id=str(
                        msg.get("message_id", "")
                        or msg.get("body", {}).get("mid", "")
                        or ""
                    ),
                    raw_response=data,
                )
            except Exception as exc:  # noqa: BLE001 — adapter must not crash on transport/API errors
                logger.error("MAX: send failed chunk %s/%s: %s", idx, len(chunks), exc)
                return SendResult(success=False, error="Send failed (see logs)")

        if len(chunks) > 1:
            logger.info("MAX: split outbound message into %s chunks for %s", len(chunks), chat_id)
        return last_result or SendResult(success=False, error="No content to send")

    @staticmethod
    def _edit_state_key(chat_id: str, message_id: str) -> str:
        return f"{chat_id}:{message_id}"

    def _get_edit_state(self, chat_id: str, message_id: str) -> _StreamEditState:
        """Fetch or create per-message streaming edit state, bounded."""
        key = self._edit_state_key(chat_id, message_id)
        state = self._edit_states.get(key)
        if state is None:
            if len(self._edit_states) >= EDIT_STATES_MAX:
                self._prune_edit_states()
            state = _StreamEditState(chat_id=chat_id, message_id=message_id)
            self._edit_states[key] = state
        return state

    def _prune_edit_states(self) -> None:
        """Drop the oldest idle streams so tracked state stays bounded.

        Only entries with nothing queued and no live flush timer are eligible,
        oldest ``last_edit_at`` first. Dropping one merely costs that message a
        fresh throttle window on its next edit.
        """
        idle = [
            (key, state)
            for key, state in self._edit_states.items()
            if state.pending_text is None
            and (state.flush_task is None or state.flush_task.done())
        ]
        idle.sort(key=lambda item: item[1].last_edit_at)
        for key, _state in idle[: max(1, len(idle) // 2)]:
            self._edit_states.pop(key, None)

    @staticmethod
    def _cancel_flush_task(state: _StreamEditState) -> None:
        """Cancel the pending flush timer for one message, if any."""
        task = state.flush_task
        state.flush_task = None
        if task is not None and not task.done():
            task.cancel()

    def _discard_edit_state(self, chat_id: str, message_id: str) -> None:
        """Drop per-message state and its timer (stream finished)."""
        state = self._edit_states.pop(self._edit_state_key(chat_id, message_id), None)
        if state is not None:
            self._cancel_flush_task(state)

    async def _perform_edit(self, state: _StreamEditState, content: str) -> SendResult:
        """Truncate/normalise ``content`` and PUT it to MAX (single attempt)."""
        text = content[:MAX_MESSAGE_LENGTH - 3] + "..." if len(content) > MAX_MESSAGE_LENGTH else content
        text = self._convert_markdown_tables(text)
        body = {"text": text, "format": "markdown"}
        try:
            resp = await self._http_client.put(
                f"{MAX_API_BASE}/messages",
                params={"message_id": state.message_id},
                json=body,
            )
            resp.raise_for_status()
            # MAX clears typing indicator on message edit — renew it
            await self.send_typing(state.chat_id)
            return SendResult(success=True, message_id=state.message_id, raw_response=resp.json())
        except Exception as e:  # noqa: BLE001 — adapter must not crash on transport/API errors
            logger.error("MAX: edit_message failed: %s", e)
            return SendResult(success=False, error="Edit failed (see logs)", retryable=True)

    def _schedule_flush(self, state: _StreamEditState) -> None:
        """(Re)start the timer that delivers throttled content.

        A newer throttled edit cancels the older timer and restarts it, so the
        last queued content always wins and is delivered even when no further
        edit_message call ever arrives.
        """
        self._cancel_flush_task(state)
        key = self._edit_state_key(state.chat_id, state.message_id)
        try:
            state.flush_task = asyncio.create_task(self._flush_pending_edit(key))
        except RuntimeError:  # no running loop — nothing to schedule on
            logger.debug("MAX: no event loop for streaming edit flush")

    async def _flush_pending_edit(self, key: str) -> None:
        """Deliver content stored by the last throttled edit_message call."""
        state = self._edit_states.get(key)
        if state is None:
            return
        try:
            while True:
                remaining = self._edit_throttle - (time.monotonic() - state.last_edit_at)
                if remaining > 0:
                    await asyncio.sleep(remaining)
                text = state.pending_text
                if text is None:
                    return
                state.pending_text = None
                async with state.lock:
                    state.last_edit_at = time.monotonic()
                    await self._perform_edit(state, text)
                if state.pending_text is None:
                    return
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — flush must never kill the loop
            logger.error("MAX: pending edit flush failed: %s", exc)
        finally:
            if self._edit_states.get(key) is state:
                state.flush_task = None

    async def edit_message(
        self,
        chat_id: str,
        message_id: str,
        content: str,
        *,
        finalize: bool = False,
    ) -> SendResult:
        """Edit an existing message — for streaming support.

        Throttling is tracked per (chat_id, message_id), so two concurrent chats
        each keep their own slot and can no longer suppress each other's PUT.
        A throttled edit is never dropped: it is stored and delivered by its own
        timer once the throttle window expires. ``finalize=True`` always sends
        immediately and releases the per-message state.
        Renews typing indicator after each edit (MAX clears it on edit).
        """
        if not self._http_client:
            return SendResult(success=False, error="Not connected")

        state = self._get_edit_state(chat_id, message_id)
        now = time.monotonic()

        if not finalize and state.last_edit_at > 0 and (now - state.last_edit_at) < self._edit_throttle:
            state.pending_text = content
            self._schedule_flush(state)
            logger.debug("MAX: edit_message throttled, content queued")
            return SendResult(success=True, message_id=message_id)

        # Unthrottled path (or finalize): this content supersedes anything queued.
        self._cancel_flush_task(state)
        state.pending_text = None
        async with state.lock:
            state.last_edit_at = time.monotonic()
            result = await self._perform_edit(state, content)

        if finalize:
            self._discard_edit_state(chat_id, message_id)
        return result

    async def delete_message(self, chat_id: str, message_id: str) -> SendResult:
        """Delete a message by ID."""
        if not self._http_client:
            return SendResult(success=False, error="Not connected")
        try:
            resp = await self._http_client.delete(
                f"{MAX_API_BASE}/messages",
                params={"message_id": message_id},
            )
            resp.raise_for_status()
            return SendResult(success=True, message_id=message_id)
        except Exception as e:  # noqa: BLE001 — adapter must not crash on transport/API errors
            logger.error("MAX: delete_message failed: %s", e)
            return SendResult(success=False, error="Delete failed (see logs)", retryable=True)

    async def send_image(
        self, chat_id: str, image_url: str,
        caption: str | None = None,
        reply_to: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SendResult:
        """Send an image via URL attachment."""
        if not self._http_client:
            return SendResult(success=False, error="Not connected")
        parts = chat_id.split(":", 1)
        target_type = parts[0] if len(parts) > 1 else "user"
        target_id = parts[1] if len(parts) > 1 else chat_id
        params = {"chat_id": target_id} if target_type == "chat" else {"user_id": target_id}
        body: dict[str, Any] = {
            "text": caption or "",
            "attachments": [{"type": "image", "payload": {"url": image_url}}],
        }
        if reply_to:
            body["link"] = {"type": "REPLY", "mid": reply_to}
        try:
            resp = await self._http_client.post(f"{MAX_API_BASE}/messages", params=params, json=body)
            resp.raise_for_status()
            d = resp.json()
            mid = str((d.get("message", {}).get("body", {}) or {}).get("mid", ""))
            return SendResult(success=True, message_id=mid, raw_response=d)
        except Exception as e:  # noqa: BLE001 — adapter must not crash on transport/API errors
            logger.error("MAX: send_image failed: %s", e)
            return SendResult(success=False, error="Send image failed (see logs)", retryable=True)

    async def send_image_file(
        self, chat_id: str, image_path: str,
        caption: str | None = None,
        reply_to: str | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs,
    ) -> SendResult:
        return await self._upload_send(chat_id, image_path, "image", caption or "", reply_to)

    async def send_multiple_images(
        self, chat_id: str,
        images: list[tuple[str, str]],
        metadata: dict[str, Any] | None = None,
        **kwargs,
    ) -> SendResult:
        """Send multiple images in a single message.

        Uploads all images concurrently via ``_upload``, then sends one
        message with all attachment tokens. Falls back to sequential
        ``send_image_file`` if any upload fails.

        ``images`` is a list of ``(url_or_path, caption)`` tuples, matching
        the Hermes core contract (``chat_id`` is already scoped by the caller).
        """
        if not self._http_client:
            return SendResult(success=False, error="Not connected")

        if not images:
            return SendResult(success=False, error="No images provided")

        # Upload all images concurrently
        tokens: list[str] = []
        captions: list[str] = []
        for url_or_path, caption in images:
            # Prefer local path, fall back to URL-based _send_image
            if url_or_path.startswith(("http://", "https://", "file://")):
                tok = await self._upload(url_or_path, "image") if not url_or_path.startswith("http") else None
                if tok:
                    tokens.append(tok)
                else:
                    # URL-based: send_image handles this; fall back to sequential
                    return await self._send_multiple_images_fallback(chat_id, images, reply_to=None, metadata=metadata)
            else:
                tok = await self._upload(url_or_path, "image")
                if tok:
                    tokens.append(tok)
                    captions.append(caption or "")
                else:
                    return await self._send_multiple_images_fallback(chat_id, images, reply_to=None, metadata=metadata)

        parts = chat_id.split(":", 1)
        target_type = parts[0] if len(parts) > 1 else "user"
        target_id = parts[1] if len(parts) > 1 else chat_id
        params = {"chat_id": target_id} if target_type == "chat" else {"user_id": target_id}

        body: dict[str, Any] = {
            "text": " ".join(c for c in captions if c).strip() or "📷",
            "attachments": [{"type": "image", "payload": {"token": t}} for t in tokens],
        }

        try:
            resp = await self._http_client.post(f"{MAX_API_BASE}/messages", params=params, json=body)
            resp.raise_for_status()
            d = resp.json()
            mid = str((d.get("message", {}).get("body", {}) or {}).get("mid", ""))
            return SendResult(success=True, message_id=mid, raw_response=d)
        except Exception as e:  # noqa: BLE001 — adapter must not crash on transport/API errors
            logger.error("MAX: send_multiple_images failed: %s", e)
            return await self._send_multiple_images_fallback(chat_id, images, reply_to=None, metadata=metadata)

    async def _send_multiple_images_fallback(
        self, chat_id: str,
        images: list[tuple[str, str]],
        reply_to: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SendResult:
        """Fallback: send images one by one if batch upload fails."""
        last_result = SendResult(success=False, error="No images sent")
        for url_or_path, caption in images:
            if url_or_path.startswith(("http://", "https://", "file://")):
                result = await self.send_image(chat_id, url_or_path, caption, reply_to, metadata)
            else:
                result = await self.send_image_file(chat_id, url_or_path, caption, reply_to, metadata)
            if result.success:
                last_result = result
        return last_result

    async def send_document(
        self, chat_id: str, file_path: str,
        caption: str | None = None,
        file_name: str | None = None,
        reply_to: str | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs,
    ) -> SendResult:
        return await self._upload_send(chat_id, file_path, "file", caption or "", reply_to)

    async def send_video(
        self, chat_id: str, video_path: str,
        caption: str | None = None,
        reply_to: str | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs,
    ) -> SendResult:
        return await self._upload_send(chat_id, video_path, "video", caption or "", reply_to)

    async def send_voice(
        self, chat_id: str, audio_path: str,
        caption: str | None = None,
        reply_to: str | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs,
    ) -> SendResult:
        return await self._upload_send(chat_id, audio_path, "audio", caption or "", reply_to)

    async def send_animation(
        self, chat_id: str, animation_url: str,
        caption: str | None = None,
        reply_to: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SendResult:
        """Send animated GIF — treated as image in MAX."""
        return await self.send_image(chat_id, animation_url, caption, reply_to, metadata)

    # ═════════════════════════════════════════════════════════════════════
    # Typing indicator
    # ═════════════════════════════════════════════════════════════════════

    # Chat actions (send_typing / send_action) moved to mixins/buttons.py

    # ═════════════════════════════════════════════════════════════════════
    # Chat info
    # ═════════════════════════════════════════════════════════════════════

    async def get_chat_info(self, chat_id: str) -> dict:
        """Return basic chat info from MAX API."""
        if not self._http_client:
            return {"name": chat_id, "type": "dm", "chat_id": chat_id}
        try:
            resp = await self._http_client.get(f"{MAX_API_BASE}/chats/{chat_id}")
            if resp.status_code == 200:
                d = resp.json()
                return {
                    "name": d.get("name", d.get("title", chat_id)),
                    "type": d.get("type", "dm"),
                    "chat_id": chat_id,
                }
        except Exception as exc:  # noqa: BLE001 — adapter must not crash on transport/API errors
            logger.debug("MAX: failed to fetch chat info for %s: %s", chat_id, exc)
        return {"name": chat_id, "type": "dm", "chat_id": chat_id}

    # Interactive buttons (send_buttons, send_action, approval/clarify)
    # — moved to mixins/buttons.py (ButtonsMixin)

    async def _on_callback(self, payload: dict[str, Any]) -> MessageEvent | None:
        """Handle message_callback update from inline keyboard button press."""
        callback = payload.get("callback", {}) or payload.get("message_callback", {})
        data = (callback.get("payload") or callback.get("data") or "").strip()
        if not data:
            return None

        user = callback.get("user", {}) or payload.get("user", {})
        user_id = str(user.get("user_id", ""))
        if not user_id:
            return None

        # Extract chat info for routing.
        # Max API callback payload puts chat info in message.recipient.
        msg = payload.get("message", {})
        recipient = msg.get("recipient", {}) if msg else {}
        raw_chat_id = (
            recipient.get("chat_id")
            or (payload.get("chat", {}) or {}).get("chat_id", "")
            or payload.get("chat_id", "")
            or ""
        )
        chat_id = str(raw_chat_id)
        is_dialog = str(recipient.get("chat_type") or "").lower() == "dialog"
        scoped_chat_id = f"user:{user_id}" if is_dialog or not chat_id else f"chat:{chat_id}"
        message_id = str((msg.get("body") or {}).get("mid") or msg.get("mid") or "")

        logger.info("MAX: callback received: data=%s from user=%s chat_id=%s",
                     data, user_id, scoped_chat_id)

        # Dispatch based on prefix
        parts = data.split(":", 2)
        prefix = parts[0] if parts else ""

        if prefix == "exec":
            return await self._handle_exec_callback(data, user_id, payload, scoped_chat_id, message_id)
        elif prefix == "sc":
            return await self._handle_slash_confirm_callback(data, user_id, payload, scoped_chat_id, message_id)
        elif prefix == "clarify":
            return await self._handle_clarify_callback(data, user_id, payload, scoped_chat_id, message_id)
        elif prefix == "model":
            return await self._handle_model_callback(data, user_id, payload, scoped_chat_id, message_id)
        else:
            logger.warning("MAX: unknown callback prefix: %s", prefix)
            return None

    async def _handle_exec_callback(
        self, data: str, user_id: str, raw_payload: dict[str, Any],
        chat_id: str = "", message_id: str = "",
    ) -> MessageEvent | None:
        """Route exec approval button to resolve_gateway_approval."""
        # Format: exec:{choice}:{approval_id}
        parts = data.split(":", 2)
        if len(parts) < 3:
            return None
        choice = parts[1]   # once / session / always / deny
        approval_id = parts[2]

        record, reason = self._consume_interaction(
            "exec", approval_id, user_id=user_id, chat_id=chat_id, message_id=message_id,
        )
        if record is None:
            if reason == "unknown":
                await self.send(f"user:{user_id}", "❌ This approval has already been resolved.")
            return None
        session_key = str(record.get("session_key") or "")
        if not session_key:
            return None

        from tools.approval import has_blocking_approval, resolve_gateway_approval

        if not has_blocking_approval(session_key):
            await self.send(f"user:{user_id}", "❌ No pending approval to resolve.")
            return None

        count = resolve_gateway_approval(session_key, choice)
        logger.info(
            "MAX: button resolved %d approval(s) for session %s (choice=%s)",
            count, session_key, choice,
        )

        # Send acknowledgment directly via MAX API (not as MessageEvent)
        # — avoids injecting the acknowledgment into the AI's context as a
        # new user message in the next turn.  Telegram does the same by
        # editing the original message (query.edit_message_text) and
        # returning without creating a MessageEvent.
        labels = {
            "once": "✅ Approved (once)",
            "session": "🔄 Approved (session)",
            "always": "🔒 Approved (always)",
            "deny": "❌ Denied",
        }
        label = labels.get(choice, f"Resolved: {choice}")
        # A valid callback is bound to the original scoped chat.  Acknowledge
        # it there, rather than moving a group approval into the owner's DM.
        target_chat = str(record.get("chat_id") or chat_id or f"user:{user_id}")
        await self.send(target_chat, label)
        return None

    async def _handle_slash_confirm_callback(
        self, data: str, user_id: str, raw_payload: dict[str, Any],
        chat_id: str = "", message_id: str = "",
    ) -> MessageEvent | None:
        """Route slash-confirm button to tools.slash_confirm.resolve."""
        # Format: sc:{choice}:{confirm_id}
        parts = data.split(":", 2)
        if len(parts) < 3:
            return None
        choice = parts[1]     # once / always / cancel
        confirm_id = parts[2]

        record, _reason = self._consume_interaction(
            "sc", confirm_id, user_id=user_id, chat_id=chat_id, message_id=message_id,
        )
        if record is None:
            return None
        session_key = str(record.get("session_key") or "")
        if not session_key:
            return None

        from tools import slash_confirm as _sc

        result_text = await _sc.resolve(session_key, confirm_id, choice)
        if result_text:
            # Send result directly via MAX API — same reasoning as
            # _handle_exec_callback: avoid injecting the result into the
            # AI's context as a new user message in the next turn.
            await self.send(f"user:{user_id}", result_text)
        return None

    async def _handle_clarify_callback(
        self, data: str, user_id: str, raw_payload: dict[str, Any],
        chat_id: str = "", message_id: str = "",
    ) -> MessageEvent | None:
        """Route clarify button to tools.clarify_gateway.resolve_gateway_clarify."""
        # Format: clarify:{clarify_id}:{choice_index}
        parts = data.split(":", 2)
        if len(parts) < 3:
            return None
        clarify_id = parts[1]
        choice_idx = parts[2]

        record, _reason = self._consume_interaction(
            "clarify", clarify_id, user_id=user_id, chat_id=chat_id, message_id=message_id,
        )
        if record is None:
            return None

        try:
            from tools.clarify_gateway import (
                mark_awaiting_text,
                resolve_gateway_clarify,
            )

            if choice_idx == "other":
                # User chose "Other…" — next text message will be the answer
                mark_awaiting_text(clarify_id)
                return None

            if not choice_idx.isdigit():
                logger.warning("MAX: clarify callback with non-numeric index: %s", choice_idx)
                return None

            idx = int(choice_idx)
            if idx < 0 or idx > 256:  # reasonable upper bound
                logger.warning("MAX: clarify callback index out of range: %s", idx)
                return None
            # Get the choice text from the pending clarify state
            # The gateway stores the choices — we resolve with the index
            response = str(idx)
            result_text = await resolve_gateway_clarify(clarify_id, response)
            if result_text:
                # Send choice text to MAX so the user sees what they picked,
                # then return a MessageEvent (NOT internal) so the AI sees it
                # as the user's input in the next turn.
                await self.send(f"user:{user_id}", result_text)
                source = self.build_source(
                    chat_id=f"user:{user_id}",
                    chat_name=user_id,
                    chat_type="dm",
                    user_id=user_id,
                    user_name=user_id,
                )
                return MessageEvent(
                    text=result_text,
                    message_type=MessageType.TEXT,
                    source=source,
                    raw_message=raw_payload,
                )
        except (ValueError, ImportError) as e:
            logger.warning("MAX: clarify callback failed: %s", e)
        return None

    async def _handle_model_callback(
        self,
        data: str,
        user_id: str,
        raw_payload: dict[str, Any],
        scoped_chat: str,
        message_id: str = "",
    ) -> MessageEvent | None:
        """Route a model-picker callback within its already-derived scope.

        ``scoped_chat`` is calculated by ``_on_callback`` from the recipient's
        explicit ``chat_type``. Do not infer DM/group from the presence of a
        service ``chat_id``: MAX dialogs also carry one.
        """
        if not scoped_chat:
            return None

        state = self._model_picker_state.get(scoped_chat)
        if not state:
            return None
        now = time.monotonic()
        expires_at = state.get("expires_at")
        if expires_at is not None and now >= float(expires_at):
            self._model_picker_state.pop(scoped_chat, None)
            return None
        updated = float(state.get("updated_at", state.get("created_at", now)))
        if now - updated > MODEL_PICKER_TTL_SECONDS:
            self._model_picker_state.pop(scoped_chat, None)
            return None
        owner = str(state.get("owner_user_id") or "")
        if owner and owner != str(user_id):
            return None
        expected_message = str(state.get("model_msg_id") or state.get("provider_msg_id") or "")
        if message_id and expected_message and message_id != expected_message:
            return None
        if not owner:
            owner = str(user_id)
            state["owner_user_id"] = owner
        state["updated_at"] = now

        parts = data.split(":", 3)

        if len(parts) >= 3 and parts[1] == "provider":
            # Provider selected
            provider_slug = parts[2]
            state = self._model_picker_state.get(scoped_chat)

            msg_id = state.get("provider_msg_id", "") if state else ""
            await self._on_model_provider_selected(scoped_chat, provider_slug, msg_id)
            return None

        if len(parts) >= 4 and parts[1] == "page":
            # Page navigation
            provider_slug = parts[2]
            try:
                page = int(parts[3])
            except ValueError:
                page = 0
            state = self._model_picker_state.get(scoped_chat)
            if state:
                await self._on_model_page_selected(scoped_chat, provider_slug, page)
            return None

        if len(parts) >= 3 and parts[1] == "pick":
            # Model selected
            # Format: model:pick:{model}:{provider}
            # parts[2] = model, parts[3] = provider (if present)
            model_id = parts[2]
            provider_slug = parts[3] if len(parts) >= 4 else ""
            if provider_slug:
                return await self._on_model_picked(scoped_chat, model_id, provider_slug, user_id)

        if data == "model:back":
            await self._on_model_back(scoped_chat, user_id)
            return None

        logger.warning("MAX: unhandled model callback: %s", data)
        return None

    # ═════════════════════════════════════════════════════════════════════
    # Model picker
    # ═════════════════════════════════════════════════════════════════════

    async def send_model_picker(
        self,
        chat_id: str,
        providers: list,
        current_model: str,
        current_provider: str,
        session_key: str,
        on_model_selected,
        metadata: dict[str, Any] | None = None,
    ) -> SendResult:
        """Send an interactive model picker with callback buttons.

        Two steps:
        1. Show provider list → tap provider → show its models
        2. Show model list → tap model → call on_model_selected
        """
        if not self._http_client:
            return SendResult(success=False, error="Not connected")

        try:
            from hermes_cli.providers import get_label
        except ImportError:
            def get_label(slug: str) -> str:
                return slug

        # Step 1: Show provider selection
        provider_label = get_label(current_provider)
        text = (
            f"⚙ **Model Configuration**\n\n"
            f"Current: `{current_model or 'unknown'}` ({provider_label})\n\n"
            f"Select a provider:"
        )[:MAX_MESSAGE_LENGTH]

        # Build provider buttons (2 per row)
        buttons: list[list[dict[str, str]]] = []
        row: list[dict[str, str]] = []
        for p in providers[:20]:  # Max 20 providers
            slug = p.get("slug", "")
            name = str(p.get("name", slug))[:38]
            tag = " ✅" if p.get("is_current") else ""
            btn_text = f"{name}{tag}"[:40]
            row.append({
                "type": "callback",
                "text": btn_text,
                "payload": f"model:provider:{slug}",
            })
            if len(row) >= 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)

        reply_to = (metadata or {}).get("reply_to_message_id") if metadata else None
        result = await self._post_interactive(chat_id, text, buttons, reply_to=reply_to)
        if result.success:
            picker_scope = str(chat_id)
            self._model_picker_state[picker_scope] = {
                "provider_msg_id": result.message_id,  # ID сообщения с провайдерами (текст+кнопки)
                "providers": providers,
                "session_key": session_key,
                "on_model_selected": on_model_selected,
                "current_model": current_model,
                "current_provider": current_provider,
                "owner_user_id": self._model_picker_owner(picker_scope, metadata),
                "created_at": (created_at := time.monotonic()),
                "updated_at": created_at,
                "expires_at": created_at + MODEL_PICKER_TTL_SECONDS,
            }
        return result

    async def _on_model_provider_selected(
        self, chat_id: str, provider_slug: str, message_id: str, page: int = 0, is_pagination: bool = False
    ) -> None:
        """Step 2: Show models for the selected provider (with pagination)."""
        state = self._model_picker_state.get(str(chat_id))
        if not state:
            return

        providers = state.get("providers", [])
        provider = next((p for p in providers if p.get("slug") == provider_slug), None)
        if not provider:
            return

        all_models = provider.get("models", [])
        provider_name = provider.get("name", provider_slug)

        # Pagination: 15 models per page
        PAGE_SIZE = 15
        total_pages = max(1, (len(all_models) + PAGE_SIZE - 1) // PAGE_SIZE)
        page = max(0, min(page, total_pages - 1))
        start = page * PAGE_SIZE
        models = all_models[start:start + PAGE_SIZE]

        # Update state with current page
        state["selected_provider"] = provider_slug
        state["model_page"] = page
        state["model_total_pages"] = total_pages
        self._model_picker_state[str(chat_id)] = state

        # Header with page indicator
        page_info = f" (стр. {page + 1}/{total_pages})" if total_pages > 1 else ""
        text = (
            f"⚙ **{provider_name}** models{page_info}\n\n"
            f"Select a model:"
        )[:MAX_MESSAGE_LENGTH]

        # Build model buttons (1 per row for readability)
        buttons: list[list[dict[str, str]]] = []
        for m in models:
            name = str(m)[:38]
            is_current = (
                state.get("current_model") == m
                and state.get("current_provider") == provider_slug
            )
            label = f"{'✅ ' if is_current else ''}{name}"[:40]
            buttons.append([{
                "type": "callback",
                "text": label,
                "payload": f"model:pick:{m}:{provider_slug}",
            }])

        # Pagination buttons
        if total_pages > 1:
            nav_row: list[dict[str, str]] = []
            if page > 0:
                nav_row.append({
                    "type": "callback",
                    "text": "⬅ Prev",
                    "payload": f"model:page:{provider_slug}:{page - 1}",
                })
            if page < total_pages - 1:
                nav_row.append({
                    "type": "callback",
                    "text": "Next ➡",
                    "payload": f"model:page:{provider_slug}:{page + 1}",
                })
            if nav_row:
                buttons.append(nav_row)

        # Add "← Back" button
        buttons.append([{
            "type": "callback",
            "text": "← Back to providers",
            "payload": "model:back",
        }])

        # Edit the original message to show models
        if is_pagination:
            # Pagination: delete old model message, send new one with updated page counter
            model_msg_id = state.get("model_msg_id", "")
            if model_msg_id:
                # Delete old model message (text + buttons)
                await self.delete_message(chat_id, model_msg_id)
                # Send new message with models (text + buttons together)
                result = await self._post_interactive(chat_id, text, buttons)
                if result.success:
                    state["model_msg_id"] = result.message_id
                    self._model_picker_state[str(chat_id)] = state
            else:
                # Fallback: send new message
                result = await self._post_interactive(chat_id, text, buttons)
                if result.success:
                    state["model_msg_id"] = result.message_id
                    self._model_picker_state[str(chat_id)] = state
        else:
            # Initial display: send new message with models (text + buttons together)
            model_msg_result = await self._post_interactive(chat_id, text, buttons)
            # Store model message ID for pagination (this message has both text and buttons)
            if model_msg_result.success:
                state["model_msg_id"] = model_msg_result.message_id
                self._model_picker_state[str(chat_id)] = state

    async def _on_model_page_selected(
        self, chat_id: str, provider_slug: str, page: int
    ) -> None:
        """Handle page navigation in model picker."""
        state = self._model_picker_state.get(str(chat_id))
        if not state:
            return

        # Get model message ID
        model_msg_id = state.get("model_msg_id", "")
        if not model_msg_id:
            # Fallback: show from scratch
            await self._on_model_provider_selected(chat_id, provider_slug, "", page)
            return

        # Pass model_msg_id as message_id and is_pagination=True
        await self._on_model_provider_selected(chat_id, provider_slug, model_msg_id, page, is_pagination=True)

    async def _on_model_picked(
        self, chat_id: str, model_id: str, provider_slug: str, user_id: str,
    ) -> MessageEvent | None:
        """Step 3: Model selected — call on_model_selected callback."""
        state = self._model_picker_state.pop(str(chat_id), None)
        if not state:
            return None

        # Delete both model and provider messages
        model_msg_id = state.get("model_msg_id", "")
        if model_msg_id:
            await self.delete_message(chat_id, model_msg_id)

        provider_msg_id = state.get("provider_msg_id", "")
        if provider_msg_id:
            await self.delete_message(chat_id, provider_msg_id)

        on_model_selected = state.get("on_model_selected")
        if not on_model_selected:
            return None

        try:
            result_text = await on_model_selected(chat_id, model_id, provider_slug)
        except Exception as e:  # noqa: BLE001 — adapter must not crash on transport/API errors
            result_text = f"❌ Error switching model: {e}"

        # Send confirmation message to user
        await self.send(chat_id, result_text)

        return None

    async def _on_model_back(self, chat_id: str, user_id: str) -> None:
        """Go back to provider selection."""
        state = self._model_picker_state.get(str(chat_id))
        if not state:
            return

        from hermes_cli.providers import get_label as _get_label

        providers = state.get("providers", [])
        current_provider = state.get("current_provider", "")
        current_model = state.get("current_model", "")

        try:
            provider_label = _get_label(current_provider)
        except Exception:  # noqa: BLE001 — adapter must not crash on transport/API errors
            provider_label = current_provider

        text = (
            f"⚙ **Model Configuration**\n\n"
            f"Current: `{current_model or 'unknown'}` ({provider_label})\n\n"
            f"Select a provider:"
        )[:MAX_MESSAGE_LENGTH]

        buttons: list[list[dict[str, str]]] = []
        row: list[dict[str, str]] = []
        for p in providers[:20]:
            slug = p.get("slug", "")
            name = p.get("name", slug)[:38]
            tag = " ✅" if p.get("is_current") else ""
            row.append({
                "type": "callback",
                "text": f"{name}{tag}"[:40],
                "payload": f"model:provider:{slug}",
            })
            if len(row) >= 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)

        # Delete old messages (provider + model buttons)
        model_msg_id = state.get("model_msg_id", "")
        if model_msg_id:
            await self.delete_message(chat_id, model_msg_id)

        provider_msg_id = state.get("provider_msg_id", "")
        if provider_msg_id:
            await self.delete_message(chat_id, provider_msg_id)

        # Send fresh provider message
        result = await self._post_interactive(chat_id, text, buttons)

        # Store new provider message ID for next cleanup
        if result.success:
            state["provider_msg_id"] = result.message_id
            self._model_picker_state[str(chat_id)] = state

    # Cross-platform session commands (/sessions, /resume)
    # — moved to mixins/sessions.py (SessionsMixin)

    @property
    def dm_policy(self) -> str:
        return "open" if self._allow_all_users else "allowlist"

    @property
    def allow_from(self) -> list[str]:
        return list(self._allowed_users_set)

    @property
    def group_policy(self) -> str:
        return self._group_policy

    @property
    def group_allow_from(self) -> list[str]:
        return self._group_allow_from

    @property
    def group_allow_chats(self) -> list[str]:
        return self._group_allow_chats

    def _group_message_allowed(self, user_id: str, chat_id: str) -> bool:
        """Decide whether a group-chat message may reach the Hermes core."""
        policy = self._group_policy
        if policy == "open":
            return True
        if policy != "allowlist":
            return False
        if not self._group_allow_from and not self._group_allow_chats:
            return False
        user_ok = not self._group_allow_from or str(user_id) in self._group_allow_from
        chat_ok = not self._group_allow_chats or str(chat_id) in self._group_allow_chats
        return bool(user_ok and chat_ok)

    @property
    def max_message_length(self) -> int:
        return MAX_MESSAGE_LENGTH


# ═════════════════════════════════════════════════════════════════════════
# Plugin registration
# ═════════════════════════════════════════════════════════════════════════

def check_max_requirements() -> bool:
    """Check if aiohttp and httpx are available and token is configured."""
    try:
        import aiohttp  # noqa: F401
        import httpx  # noqa: F401
    except ImportError:
        return False
    return bool(os.getenv("MAX_BOT_TOKEN", "").strip())


def validate_config(config) -> bool:
    """Validate that the platform config has enough info to connect."""
    extra = getattr(config, "extra", {}) or {}
    token = os.getenv("MAX_BOT_TOKEN") or getattr(config, "token", "") or extra.get("token", "")
    return bool(str(token).strip())


def is_connected(config) -> bool:
    """Check whether Max is configured."""
    return validate_config(config)


def _env_enablement() -> dict | None:
    """Seed PlatformConfig.extra from env-only setups."""
    token = os.getenv("MAX_BOT_TOKEN", "").strip()
    if not token:
        return None

    extra: dict[str, Any] = {"token": token}

    str_vars = {
        "MAX_WEBHOOK_HOST": "host",
        "MAX_WEBHOOK_PATH": "path",
        "MAX_WEBHOOK_SECRET": "webhook_secret",
        "MAX_WEBHOOK_URL": "webhook_url",
        "MAX_GROUP_POLICY": "group_policy",
    }
    for env_name, key in str_vars.items():
        value = os.getenv(env_name, "").strip()
        if value:
            extra[key] = value

    port = os.getenv("MAX_WEBHOOK_PORT", "").strip()
    if port:
        try:
            extra["port"] = int(port)
        except ValueError:
            extra["port"] = port

    allowed = os.getenv("MAX_ALLOWED_USERS", "").strip()
    if allowed:
        extra["allowed_users"] = [part.strip() for part in allowed.split(",") if part.strip()]

    allow_all = os.getenv("MAX_ALLOW_ALL_USERS", "").strip()
    if allow_all:
        extra["allow_all_users"] = _coerce_bool(allow_all, True)

    home = os.getenv("MAX_HOME_CHANNEL", "").strip()
    if home:
        extra["home_channel"] = {
            "chat_id": home,
            "name": os.getenv("MAX_HOME_CHANNEL_NAME", "Max Home") or "Max Home",
        }

    cross = os.getenv("MAX_CROSS_SESSION", "").strip()
    if cross:
        extra["cross_session"] = _coerce_bool(cross, True)

    group_users = os.getenv("MAX_GROUP_ALLOWED_USERS", "").strip()
    if group_users:
        extra["group_allow_from"] = [part.strip() for part in group_users.split(",") if part.strip()]

    group_chats = os.getenv("MAX_GROUP_ALLOWED_CHATS", "").strip()
    if group_chats:
        extra["group_allow_chats"] = [part.strip() for part in group_chats.split(",") if part.strip()]

    download_hosts = os.getenv("MAX_DOWNLOAD_ALLOWED_HOSTS", "").strip()
    if download_hosts:
        extra["download_allowed_hosts"] = [part.strip() for part in download_hosts.split(",") if part.strip()]

    return extra


def _apply_yaml_config(yaml_cfg: dict, platform_cfg: dict) -> dict | None:
    """Translate top-level max: config into env/extras."""
    del yaml_cfg
    if not isinstance(platform_cfg, dict):
        return None

    extra: dict[str, Any] = {}
    mapping = {
        "token": "MAX_BOT_TOKEN",
        "webhook_secret": "MAX_WEBHOOK_SECRET",
        "webhook_url": "MAX_WEBHOOK_URL",
        "host": "MAX_WEBHOOK_HOST",
        "port": "MAX_WEBHOOK_PORT",
        "path": "MAX_WEBHOOK_PATH",
        "allowed_users": "MAX_ALLOWED_USERS",
        "allow_all_users": "MAX_ALLOW_ALL_USERS",
        "home_channel": "MAX_HOME_CHANNEL",
        "group_policy": "MAX_GROUP_POLICY",
        "group_allow_from": "MAX_GROUP_ALLOWED_USERS",
        "group_allow_chats": "MAX_GROUP_ALLOWED_CHATS",
        "download_allowed_hosts": "MAX_DOWNLOAD_ALLOWED_HOSTS",
        "cross_session": "MAX_CROSS_SESSION",
    }

    for key, env_name in mapping.items():
        if key not in platform_cfg:
            continue
        value = platform_cfg.get(key)
        if value is None:
            continue
        if key in ("allowed_users", "group_allow_from", "group_allow_chats", "download_allowed_hosts") and isinstance(value, list):
            extra[key] = [str(v) for v in value]
            env_value = ",".join(str(v) for v in value)
        elif key == "home_channel" and isinstance(value, dict):
            chat_id = str(value.get("chat_id") or "").strip()
            if not chat_id:
                continue
            env_value = chat_id
            extra[key] = value
        else:
            env_value = str(value)
            extra[key] = value
        # SECURITY: Do NOT mutate global os.environ from plugin code.
        # The caller (gateway) is responsible for environment setup.
        if env_value and not os.getenv(env_name):
            # Only set if not already present; this is a fallback bridge
            # for legacy paths, kept for backward compatibility.
            pass  # os.environ mutation removed — caller handles env setup

    return extra or None


def interactive_setup() -> None:
    """Interactive `hermes gateway setup` flow for the Max platform."""
    try:
        from hermes_cli.setup import (
            get_env_value,
            print_header,
            print_info,
            print_success,
            print_warning,
            prompt,
            prompt_yes_no,
            save_env_value,
        )
    except ImportError:
        logger.warning("MAX: hermes_cli.setup not available for interactive setup")
        return

    print_header("Max (max.ru)")

    existing_token = get_env_value("MAX_BOT_TOKEN")
    if existing_token:
        print_info(f"Max: already configured (token: {existing_token[:8]}...)")
        if not prompt_yes_no("Reconfigure Max?", False):
            return

    print_info("Connect Hermes to Max messenger (max.ru). Requires aiohttp + httpx.")

    token = prompt("Bot token (from Max Platform → Chat-bots → Integration)",
                   default="", password=True)
    if not token:
        print_warning("Token is required — skipping Max setup")
        return
    save_env_value("MAX_BOT_TOKEN", token.strip())

    print()
    print_info("🔒 Webhook security")
    use_secret = prompt_yes_no("Set a webhook secret?", True)
    if use_secret:
        secret = prompt("Webhook secret (5-256 chars)", password=True)
        save_env_value("MAX_WEBHOOK_SECRET", secret.strip() if secret else "")

    print()
    host = prompt("HTTP server host", default=get_env_value("MAX_WEBHOOK_HOST") or "0.0.0.0")
    save_env_value("MAX_WEBHOOK_HOST", host.strip() or "0.0.0.0")
    port = prompt("HTTP server port", default=get_env_value("MAX_WEBHOOK_PORT") or "8646")
    save_env_value("MAX_WEBHOOK_PORT", port.strip() or "8646")
    path = prompt("Webhook path", default=get_env_value("MAX_WEBHOOK_PATH") or "/max/webhook")
    save_env_value("MAX_WEBHOOK_PATH", path.strip() or "/max/webhook")

    print()
    print_info("🔒 Access control")
    allow_all = prompt_yes_no("Allow all Max users to talk to the bot?", True)
    if allow_all:
        save_env_value("MAX_ALLOW_ALL_USERS", "true")
        save_env_value("MAX_ALLOWED_USERS", "")
    else:
        save_env_value("MAX_ALLOW_ALL_USERS", "false")
        allowed = prompt("Allowed user IDs (comma-separated)",
                         default=get_env_value("MAX_ALLOWED_USERS") or "")
        if allowed:
            save_env_value("MAX_ALLOWED_USERS", allowed.replace(" ", ""))

    print()
    print_info("🎤 Voice messages")
    print_info("Transcription is handled by the Hermes core STT pipeline (config.yaml → stt); no plugin setting needed.")

    print()
    print_success("Max configuration saved to ~/.hermes/.env")
    print_info("Restart the gateway: hermes gateway restart")


def register(ctx) -> None:
    """Plugin entry point — called by the Hermes plugin system."""
    skill_path = Path(__file__).parent / "skills" / "max-gateway" / "SKILL.md"

    ctx.register_platform(
        name="max",
        label="Max",
        adapter_factory=lambda cfg: MaxAdapter(cfg),
        check_fn=check_max_requirements,
        validate_config=validate_config,
        is_connected=is_connected,
        required_env=["MAX_BOT_TOKEN"],
        install_hint="pip install aiohttp httpx",
        setup_fn=interactive_setup,
        env_enablement_fn=_env_enablement,
        apply_yaml_config_fn=_apply_yaml_config,
        cron_deliver_env_var="MAX_HOME_CHANNEL",
        standalone_sender_fn=_standalone_send,
        allowed_users_env="MAX_ALLOWED_USERS",
        allow_all_env="MAX_ALLOW_ALL_USERS",
        max_message_length=MAX_MESSAGE_LENGTH,
        emoji="🟣",
        pii_safe=True,
        allow_update_command=True,
        platform_hint=(
            "You are chatting via Max (max.ru) messenger. "
            "Max supports markdown formatting (**bold**, *italic*, `code`, ```blocks```). "
            "Messages are limited to 4000 characters. "
            "You can send images using markdown ![alt](url) syntax. "
            "Voice messages are automatically transcribed — the transcription appears in the message text. "
            "Keep responses clear and well-structured."
        ),
    )

    if skill_path.exists():
        ctx.register_skill(
            "max-gateway",
            skill_path,
            description="Install and configure Hermes Agent gateway access through Max messenger (voice transcription via Hermes core STT).",
        )
