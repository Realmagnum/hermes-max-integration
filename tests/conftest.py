"""Shared test fixtures for Max platform plugin."""

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

# The plugin is a *package* whose modules use relative imports
# (`adapter.py` does `from .mixins.media_upload import ...`), while the tests
# import it as a plain top-level module (`import adapter`). Bootstrap it here
# by directory path so the suite works in every checkout layout.
#
# Two things a path-based bootstrap must not assume:
#
# * The checkout directory name. Hermes installs a directory plugin under the
#   sanitized `plugin.yaml` name (`plugins/max-platform/`), a `git clone` of
#   the repo lands as `hermes-max-integration/`, and CI checks out
#   `hermes-max-integration/`. None of those is `max`, so importing
#   `max.adapter` fails everywhere.
# * The absolute location of the plugin root, so the parent directory must
#   never be added to `sys.path` — that would shadow unrelated top-level
#   modules.
#
# Load `__init__.py` under a fixed private namespace instead, then alias the
# resulting `adapter` submodule to the top-level name the tests expect.
_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
_NAMESPACE = "hermes_max_plugin_under_test"

if _NAMESPACE not in sys.modules:
    _spec = importlib.util.spec_from_file_location(
        _NAMESPACE,
        _PLUGIN_ROOT / "__init__.py",
        submodule_search_locations=[str(_PLUGIN_ROOT)],
    )
    if _spec is None or _spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"Cannot load plugin package from {_PLUGIN_ROOT}")
    _plugin = importlib.util.module_from_spec(_spec)
    _plugin.__package__ = _NAMESPACE
    _plugin.__path__ = [str(_PLUGIN_ROOT)]
    sys.modules[_NAMESPACE] = _plugin
    _spec.loader.exec_module(_plugin)

adapter = importlib.import_module(f"{_NAMESPACE}.adapter")
# Register under the flat name the tests use, and expose the plugin package
# under `max` so `from max.mixins...` imports keep resolving.
sys.modules.setdefault("adapter", adapter)
sys.modules.setdefault("max", sys.modules[_NAMESPACE])
sys.modules.setdefault("max.adapter", adapter)

# Register already-loaded plugin submodules under the legacy `max.` namespace
# too. Otherwise a test importing `max.mixins.*` executes a duplicate module.
if sys.modules.get("max") is sys.modules[_NAMESPACE]:
    _PREFIX = _NAMESPACE + "."
    for _name, _module in list(sys.modules.items()):
        if _name.startswith(_PREFIX) and _module is not None:
            sys.modules["max." + _name[len(_PREFIX):]] = _module


@pytest.fixture
def max_config():
    """Create a PlatformConfig for testing."""
    from gateway.config import PlatformConfig

    return PlatformConfig(
        enabled=True,
        token="test-token",
        extra={
            "token": "test-token",
        },
    )


@pytest.fixture
def max_config_no_stt():
    """PlatformConfig with STT disabled."""
    from gateway.config import PlatformConfig

    return PlatformConfig(
        enabled=True,
        token="test-token",
        extra={
            "token": "test-token",
            "stt_enabled": False,
        },
    )


@pytest.fixture
def sample_dm_update():
    """Sample direct message update from Max."""
    return {
        "update_type": "message_created",
        "message": {
            "sender": {"user_id": 42, "name": "Test User"},
            "recipient": {"chat_type": "dialog"},
            "body": {"mid": "mid-001", "text": "Hello!"},
        },
    }


@pytest.fixture
def sample_group_update():
    """Sample group chat update from Max."""
    return {
        "update_type": "message_created",
        "chat": {"chat_id": 777, "title": "Test Group"},
        "message": {
            "sender": {"user_id": 42, "name": "Test User"},
            "recipient": {"chat_id": 777},
            "body": {"mid": "mid-002", "text": "Hello group!"},
        },
    }


@pytest.fixture
def sample_audio_attachment():
    """Sample audio attachment payload."""
    return {
        "type": "audio",
        "payload": {
            "url": "https://cdn.max.ru/audio/test.ogg",
            "token": "aud-token-123",
            "id": "aud-001",
        },
    }


@pytest.fixture
def sample_bot_started():
    """Sample bot_started update."""
    return {
        "update_type": "bot_started",
        "chat_id": "12345",
        "user": {"user_id": 42, "name": "Test User"},
        "payload": "",
    }


@pytest.fixture
def mock_httpx_client():
    """Create a mock httpx.AsyncClient."""
    client = AsyncMock()
    client.aclose = AsyncMock()
    return client


# ═════════════════════════════════════════════════════════════════════════
# Wire-level fixtures (BUILD-04)
#
# The fixtures below replace `AsyncMock`-per-method doubles with a real
# `httpx.AsyncClient` driven by `httpx.MockTransport`, so tests can assert on
# the actual bytes the adapter puts on the wire (query params + JSON body)
# instead of merely asserting that "some call happened".
# ═════════════════════════════════════════════════════════════════════════

MAX_API_HOST = "https://platform-api.max.ru"

# Bound before any test can monkeypatch `httpx.AsyncClient` (see the
# `http_client_factory` fixture) so building the double cannot recurse.
_REAL_ASYNC_CLIENT = httpx.AsyncClient

# Payload shapes below are copied from payloads captured from the live MAX Bot
# API on 2026-02-10, published in the official MAX client repository:
#   github.com/max-messenger/max-bot-api-client-go
#   -> schemes/MAX_API_Real_Payloads_2026.md   (§2.1 text DM, §2.3 callback)
#
# Routing-relevant detail: `message.recipient` of a *dialog* carries
#   {"chat_id": <id>, "chat_type": "dialog", "user_id": <id>}
# i.e. a DM update DOES contain recipient.chat_id — the same source document
# maps a dialog to `recipient.user_id`, not to `recipient.chat_id`
# (normalization table, §3).
DIALOG_CHAT_ID = -100000000
DIALOG_USER_ID = 54321
BOT_USER_ID = 12345

MAX_ENV_VARS = (
    "MAX_BOT_TOKEN",
    "MAX_WEBHOOK_HOST",
    "MAX_WEBHOOK_PORT",
    "MAX_WEBHOOK_PATH",
    "MAX_WEBHOOK_SECRET",
    "MAX_WEBHOOK_URL",
    "MAX_ALLOWED_USERS",
    "MAX_ALLOW_ALL_USERS",
    "MAX_GROUP_ALLOWED_USERS",
    "MAX_GROUP_ALLOWED_CHATS",
    "MAX_CROSS_SESSION",
    "MAX_TABLE_AS_IMAGE",
)


def dm_message_created(
    text: str = "Привет",
    mid: str = "mid.dm.1",
    chat_id: Any = DIALOG_CHAT_ID,
    user_id: Any = DIALOG_USER_ID,
) -> dict:
    """`message_created` update for a dialog (DM) — verbatim captured shape."""
    return {
        "timestamp": 1739184000000,
        "message": {
            "recipient": {
                "chat_id": chat_id,
                "chat_type": "dialog",
                "user_id": BOT_USER_ID,
            },
            "timestamp": 1739184000000,
            "body": {"mid": mid, "seq": 0, "text": text},
            "sender": {
                "user_id": user_id,
                "first_name": "User_Name",
                "last_name": "",
                "is_bot": False,
                "last_activity_time": 1739184000000,
                "name": "User_Name",
            },
        },
        "user_locale": "ru",
        "update_type": "message_created",
    }


def message_callback(
    payload: str = "utm_view_6",
    mid: str = "mid.dm.1",
    chat_id: Any = DIALOG_CHAT_ID,
    user_id: Any = DIALOG_USER_ID,
) -> dict:
    """`message_callback` update — verbatim captured shape (§2.3)."""
    return {
        "callback": {
            "timestamp": 1739184000000,
            "callback_id": "CALLBACK_ID",
            "user": {
                "user_id": user_id,
                "first_name": "User_Name",
                "last_name": "",
                "is_bot": False,
                "last_activity_time": 1739184000000,
                "name": "User_Name",
            },
            "payload": payload,
        },
        "message": {
            "recipient": {
                "chat_id": chat_id,
                "chat_type": "dialog",
                "user_id": BOT_USER_ID,
            },
            "timestamp": 1739184000000,
            "body": {"mid": mid, "seq": 0, "text": "Меню бота"},
            "sender": {
                "user_id": BOT_USER_ID,
                "first_name": "Bot_Name",
                "username": "example_bot",
                "is_bot": True,
                "last_activity_time": 1739184000000,
                "name": "Bot_Name",
            },
        },
        "timestamp": 1739184000000,
        "user_locale": "ru",
        "update_type": "message_callback",
    }


def group_message_created(
    text: str = "Hello group!",
    mid: str = "mid.group.1",
    chat_id: Any = -559969187,
    user_id: Any = DIALOG_USER_ID,
) -> dict:
    """`message_created` update for a group chat.

    No live capture for this variant was available, so the payload is built
    from the documented schema: for a chat/channel `message.recipient` is the
    Chat object and therefore carries `chat_id` (and no `chat_type` of
    "dialog").
    """
    return {
        "timestamp": 1739184000000,
        "message": {
            "recipient": {"chat_id": chat_id, "type": "chat", "title": "Test Group"},
            "timestamp": 1739184000000,
            "body": {"mid": mid, "seq": 0, "text": text},
            "sender": {
                "user_id": user_id,
                "first_name": "User_Name",
                "is_bot": False,
                "last_activity_time": 1739184000000,
                "name": "User_Name",
            },
        },
        "user_locale": "ru",
        "update_type": "message_created",
    }


def bot_started_update(chat_id: Any = DIALOG_CHAT_ID, user_id: Any = DIALOG_USER_ID,
                       payload: str = "c42") -> dict:
    """`bot_started` update (deep-link payload in `payload`)."""
    return {
        "update_type": "bot_started",
        "timestamp": 1739184000000,
        "chat_id": chat_id,
        "user": {
            "user_id": user_id,
            "first_name": "User_Name",
            "is_bot": False,
            "last_activity_time": 1739184000000,
            "name": "User_Name",
        },
        "payload": payload,
    }


class MockMaxAPI:
    """In-process stand-in for platform-api.max.ru over httpx.MockTransport.

    Unlike an `AsyncMock` client this goes through httpx' real request
    building, so `api.requests` holds genuine `httpx.Request` objects and
    tests can assert on method + query params + JSON body.
    """

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.routes: dict[tuple[str, str], tuple[Any, Any]] = {}

    # ── setup ────────────────────────────────────────────────────────────
    def route(self, method: str, path: str, status: int = 200,
              json_body: Any | None = None) -> "MockMaxAPI":
        self.routes[(method.upper(), path)] = (status, {} if json_body is None else json_body)
        return self

    def fail(self, method: str, path: str, exc: BaseException) -> "MockMaxAPI":
        """Make one endpoint raise a transport error (connect timeout, reset…)."""
        self.routes[(method.upper(), path)] = (None, exc)
        return self

    def default_response(self, method: str, path: str) -> tuple[int, Any]:
        if (method, path) == ("GET", "/me"):
            return 200, {
                "user_id": BOT_USER_ID, "first_name": "Bot_Name",
                "username": "example_bot", "is_bot": True,
            }
        if (method, path) == ("GET", "/subscriptions"):
            return 200, {"subscriptions": []}
        if (method, path) == ("GET", "/updates"):
            return 200, {"updates": [], "marker": 0}
        if (method, path) == ("POST", "/messages"):
            return 200, {"message": {"body": {"mid": "mid.bot.1"}}}
        if (method, path) == ("PUT", "/messages"):
            return 200, {"success": True, "message": {"body": {"mid": "mid.edited"}}}
        if (method, path) == ("PATCH", "/me/commands"):
            return 200, {"success": True}
        return 200, {}

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = (request.method.upper(), request.url.path)
        entry = self.routes.get(key)
        if entry is None:
            status, body = self.default_response(*key)
        else:
            status, body = entry
        if isinstance(body, BaseException):
            raise body
        if callable(body):
            status, body = body(request)
        return httpx.Response(status, json=body, request=request)

    async def async_handler(self, request: httpx.Request) -> httpx.Response:
        """Async variant that always yields to the event loop.

        Long-poll loops call this back-to-back; a transport that never suspends
        would starve the loop under test (and hang the suite).
        """
        await asyncio.sleep(0)
        return self.handler(request)

    def client(self, *, yield_to_loop: bool = True) -> httpx.AsyncClient:
        transport = httpx.MockTransport(
            self.async_handler if yield_to_loop else self.handler
        )
        return _REAL_ASYNC_CLIENT(
            transport=transport,
            base_url=MAX_API_HOST,
            headers={"Authorization": "test-token"},
        )

    # ── inspection ───────────────────────────────────────────────────────
    def calls(self, method: str, path: str) -> list[httpx.Request]:
        return [
            r for r in self.requests
            if r.method == method.upper() and r.url.path == path
        ]

    def methods(self) -> list[tuple[str, str]]:
        return [(r.method, r.url.path) for r in self.requests]

    @staticmethod
    def json_body(request: httpx.Request) -> dict:
        raw = request.content.decode("utf-8") if request.content else ""
        return json.loads(raw) if raw else {}

    @staticmethod
    def params(request: httpx.Request) -> dict:
        return dict(request.url.params)


@pytest.fixture(autouse=True)
def _hermetic_max_env(monkeypatch):
    """Drop ambient MAX_* config so tests only see what they set themselves."""
    for name in MAX_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def max_api() -> MockMaxAPI:
    """Wire-level double for the MAX REST API."""
    return MockMaxAPI()


@pytest.fixture
def make_adapter(max_api):
    """Factory: a MaxAdapter whose httpx client talks to `max_api`."""
    from gateway.config import PlatformConfig

    def _make(extra: dict | None = None, *, token: str = "test-token", **overrides):
        payload = {"token": token}
        payload.update(extra or {})
        cfg = PlatformConfig(enabled=True, token=token, extra=payload)
        instance = adapter.MaxAdapter(cfg)
        for key, value in overrides.items():
            setattr(instance, key, value)
        instance._http_client = max_api.client()
        instance._running = True
        instance._connected = True
        return instance

    return _make


@pytest.fixture
def http_client_factory(max_api, monkeypatch):
    """Intercept the `httpx.AsyncClient` that `connect()` constructs itself.

    `MaxAdapter.connect()` builds its own client (it must, so the Authorization
    header and `follow_redirects=False` are applied uniformly), so the transport
    double has to be injected at construction time.  `factory.calls` records the
    kwargs the adapter passed (headers, timeouts, redirect policy).
    """
    def factory(*args, **kwargs):
        factory.calls.append(kwargs)
        return max_api.client()

    factory.calls = []
    monkeypatch.setattr(adapter.httpx, "AsyncClient", factory)
    return factory


@pytest.fixture
def dm_update() -> dict:
    """Captured dialog `message_created` update (recipient.chat_id present)."""
    return dm_message_created()


@pytest.fixture
def group_update() -> dict:
    """Group-chat `message_created` update."""
    return group_message_created()


@pytest.fixture
def callback_update() -> dict:
    """Captured `message_callback` update."""
    return message_callback()
