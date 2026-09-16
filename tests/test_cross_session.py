"""SEC-05 regression tests: access to global (cross-platform) sessions.

The adapter's ``/sessions`` / ``/resume`` interceptor bypasses the core
gateway's per-platform session scoping and can expose titles, previews and IDs
of sessions belonging to *every* platform. It must therefore be:

* OFF by default (explicit opt-in required), and
* owner-only — restricted to explicitly configured user IDs,
* authorised BEFORE any side effect (session-store query, outbound message,
  ``/resume --all`` rewrite).
"""

import sys
import types
from typing import ClassVar
from unittest.mock import AsyncMock

import pytest

import adapter

# Env names that must not leak from the ambient test environment.
_ENV_VARS = (
    "MAX_CROSS_SESSION",
    "MAX_CROSS_SESSION_USERS",
    "MAX_ALLOWED_USERS",
    "MAX_ALLOW_ALL_USERS",
    "MAX_GROUP_ALLOWED_USERS",
    "MAX_GROUP_ALLOWED_CHATS",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in _ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def make_adapter(extra=None):
    from gateway.config import PlatformConfig

    cfg = PlatformConfig(enabled=True, token="test-token", extra=extra or {})
    return adapter.MaxAdapter(cfg)


def dm_update(text, user_id=42, mid="mid-cross-1", name="Owner"):
    """Minimal DM update as MAX delivers it (no recipient.chat_id => dm)."""
    return {
        "update_type": "message_created",
        "message": {
            "sender": {"user_id": user_id, "name": name},
            "recipient": {"chat_type": "dialog"},
            "body": {"mid": mid, "text": text},
        },
    }


class FakeSessionDB:
    """Stand-in for hermes_state.SessionDB that records every interaction."""

    rows: ClassVar[list[dict]] = []
    init_calls = 0
    query_calls: ClassVar[list[dict]] = []

    def __init__(self):
        FakeSessionDB.init_calls += 1

    def list_sessions_rich(self, **kwargs):
        FakeSessionDB.query_calls.append(kwargs)
        return list(FakeSessionDB.rows)


@pytest.fixture
def fake_state(monkeypatch):
    FakeSessionDB.rows = []
    FakeSessionDB.init_calls = 0
    FakeSessionDB.query_calls = []
    mod = types.ModuleType("hermes_state")
    mod.SessionDB = FakeSessionDB
    monkeypatch.setitem(sys.modules, "hermes_state", mod)
    return FakeSessionDB


# ── Configuration / authorization ────────────────────────────────────────


class TestCrossSessionAuthorization:
    def test_disabled_by_default(self):
        a = make_adapter()
        assert a._cross_session is False
        assert a._cross_session_allowed("42") is False

    def test_allow_all_users_alone_never_grants_cross_platform_access(self):
        a = make_adapter({"allow_all_users": True})
        assert a._cross_session_users == set()
        assert a._cross_session_allowed("42") is False

    def test_open_chat_with_cross_session_enabled_still_denies(self):
        """Empty allowlist + allow_all_users=True must not open cross-session."""
        a = make_adapter({"cross_session": True, "allow_all_users": True})
        assert a._cross_session_allowed("42") is False

    def test_empty_allowlist_with_feature_enabled_denies(self):
        a = make_adapter({"cross_session": True})
        assert a._cross_session_allowed("42") is False

    def test_allowlist_acts_as_owner_set(self):
        a = make_adapter({"cross_session": True, "allowed_users": [42]})
        assert a._cross_session_allowed("42") is True
        assert a._cross_session_allowed("7") is False

    def test_explicit_owner_list_wins_over_allow_all_users(self):
        a = make_adapter({
            "cross_session": True,
            "allow_all_users": True,
            "cross_session_users": ["42"],
        })
        assert a._cross_session_allowed("42") is True
        assert a._cross_session_allowed("7") is False

    def test_env_configuration(self, monkeypatch):
        monkeypatch.setenv("MAX_CROSS_SESSION", "true")
        monkeypatch.setenv("MAX_CROSS_SESSION_USERS", "42, 43")
        a = make_adapter()
        assert a._cross_session_allowed("42") is True
        assert a._cross_session_allowed("43") is True
        assert a._cross_session_allowed("7") is False

    def test_feature_enabled_by_env_with_allowlist_owner(self, monkeypatch):
        monkeypatch.setenv("MAX_CROSS_SESSION", "1")
        monkeypatch.setenv("MAX_ALLOWED_USERS", "42")
        a = make_adapter()
        assert a._cross_session_allowed("42") is True

    def test_empty_user_id_is_denied(self):
        a = make_adapter({"cross_session": True, "allowed_users": [42]})
        assert a._cross_session_allowed("") is False
        assert a._cross_session_allowed(None) is False


# ── Command routing in _on_message_created ───────────────────────────────


OWNER_CFG = {"cross_session": True, "allowed_users": [42]}
# allow_all_users lets the "other" user reach the cross-session block, so the
# owner check is what denies them.
OTHER_USER_CFG = {
    "cross_session": True,
    "allow_all_users": True,
    "cross_session_users": ["42"],
}


class TestCrossSessionRouting:
    @pytest.mark.asyncio
    async def test_default_config_passes_sessions_through_to_core(self):
        a = make_adapter()
        a._handle_cross_sessions = AsyncMock()
        event = await a._on_message_created(dm_update("/sessions"))
        a._handle_cross_sessions.assert_not_called()
        assert event is not None and event.text == "/sessions"

    @pytest.mark.asyncio
    async def test_default_config_passes_resume_target_without_all(self):
        a = make_adapter()
        event = await a._on_message_created(dm_update("/resume abc123"))
        assert event is not None
        assert event.text == "/resume abc123"
        assert "--all" not in event.text

    @pytest.mark.asyncio
    async def test_default_config_passes_sessions_target_without_all(self):
        a = make_adapter()
        event = await a._on_message_created(dm_update("/sessions abc123"))
        assert event is not None
        assert event.text == "/sessions abc123"
        assert "--all" not in event.text

    @pytest.mark.asyncio
    async def test_owner_plain_sessions_uses_handler(self):
        a = make_adapter(OWNER_CFG)
        a._handle_cross_sessions = AsyncMock()
        event = await a._on_message_created(dm_update("/sessions"))
        a._handle_cross_sessions.assert_called_once_with("/sessions", "user:42", "42")
        assert event is None

    @pytest.mark.asyncio
    async def test_owner_sessions_search_uses_handler(self):
        a = make_adapter(OWNER_CFG)
        a._handle_cross_sessions = AsyncMock()
        event = await a._on_message_created(dm_update("/sessions search zabbix"))
        a._handle_cross_sessions.assert_called_once_with(
            "/sessions search zabbix", "user:42", "42"
        )
        assert event is None

    @pytest.mark.asyncio
    async def test_owner_resume_without_args_uses_handler(self):
        a = make_adapter(OWNER_CFG)
        a._handle_cross_sessions = AsyncMock()
        event = await a._on_message_created(dm_update("/resume"))
        a._handle_cross_sessions.assert_called_once_with("/sessions", "user:42", "42")
        assert event is None

    @pytest.mark.asyncio
    async def test_owner_sessions_target_rewritten_for_core(self):
        a = make_adapter(OWNER_CFG)
        a._handle_cross_sessions = AsyncMock()
        event = await a._on_message_created(dm_update("/sessions abc123"))
        a._handle_cross_sessions.assert_not_called()
        assert event is not None and event.text == "/resume --all abc123"

    @pytest.mark.asyncio
    async def test_owner_resume_target_rewritten_for_core(self):
        a = make_adapter(OWNER_CFG)
        event = await a._on_message_created(dm_update("/resume abc123"))
        assert event is not None and event.text == "/resume --all abc123"

    @pytest.mark.asyncio
    async def test_owner_explicit_all_is_left_alone(self):
        a = make_adapter(OWNER_CFG)
        event = await a._on_message_created(dm_update("/resume --all abc123"))
        assert event is not None and event.text == "/resume --all abc123"

    @pytest.mark.asyncio
    async def test_non_owner_plain_sessions_not_intercepted(self):
        a = make_adapter(OTHER_USER_CFG)
        a._handle_cross_sessions = AsyncMock()
        event = await a._on_message_created(
            dm_update("/sessions", user_id=7, mid="mid-cross-7")
        )
        a._handle_cross_sessions.assert_not_called()
        assert event is not None and event.text == "/sessions"

    @pytest.mark.asyncio
    async def test_non_owner_sessions_search_not_intercepted(self):
        a = make_adapter(OTHER_USER_CFG)
        a._handle_cross_sessions = AsyncMock()
        event = await a._on_message_created(
            dm_update("/sessions search zabbix", user_id=7, mid="mid-cross-8")
        )
        a._handle_cross_sessions.assert_not_called()
        assert event is not None and event.text == "/sessions search zabbix"

    @pytest.mark.asyncio
    async def test_non_owner_resume_without_args_not_intercepted(self):
        a = make_adapter(OTHER_USER_CFG)
        a._handle_cross_sessions = AsyncMock()
        event = await a._on_message_created(
            dm_update("/resume", user_id=7, mid="mid-cross-9")
        )
        a._handle_cross_sessions.assert_not_called()
        assert event is not None and event.text == "/resume"

    @pytest.mark.asyncio
    async def test_non_owner_never_gets_all_rewrite(self):
        a = make_adapter(OTHER_USER_CFG)
        for mid, text in (("mid-cross-a", "/resume abc123"),
                          ("mid-cross-b", "/sessions abc123")):
            event = await a._on_message_created(
                dm_update(text, user_id=7, mid=mid)
            )
            assert event is not None
            assert event.text == text
            assert "--all" not in event.text

    @pytest.mark.asyncio
    async def test_denied_path_has_no_side_effects(self, fake_state):
        """Denied callers must not reach the session store or send anything."""
        a = make_adapter(OTHER_USER_CFG)
        a.send = AsyncMock()
        event = await a._on_message_created(
            dm_update("/sessions search secret", user_id=7, mid="mid-cross-c")
        )
        assert fake_state.init_calls == 0
        assert fake_state.query_calls == []
        a.send.assert_not_called()
        assert event is not None and event.text == "/sessions search secret"


# ── Handler-level guard (defence in depth) ───────────────────────────────


class TestCrossSessionHandlerGuard:
    @pytest.mark.asyncio
    async def test_handler_denies_unknown_user(self, fake_state):
        a = make_adapter(OWNER_CFG)
        a.send = AsyncMock()
        await a._handle_cross_sessions("/sessions", "user:7", "7")
        assert fake_state.init_calls == 0
        assert fake_state.query_calls == []
        a.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_handler_denies_when_feature_disabled(self, fake_state):
        a = make_adapter({"allowed_users": [42]})
        a.send = AsyncMock()
        await a._handle_cross_sessions("/sessions", "user:42", "42")
        assert fake_state.init_calls == 0
        a.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_handler_denies_missing_user_id(self, fake_state):
        a = make_adapter(OWNER_CFG)
        a.send = AsyncMock()
        await a._handle_cross_sessions("/sessions", "user:42")
        assert fake_state.init_calls == 0
        a.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_handler_lists_sessions_for_owner(self, fake_state):
        fake_state.rows = [
            {
                "id": "abcdef1234567890",
                "source": "cli",
                "title": "Zabbix deploy",
                "preview": "line one\nline two",
            },
            {
                "id": "ffffffff00000000",
                "source": "telegram",
                "title": "Traefik",
                "preview": "",
            },
        ]
        a = make_adapter(OWNER_CFG)
        a.send = AsyncMock()

        await a._handle_cross_sessions("/sessions", "user:42", "42")

        assert fake_state.init_calls == 1
        assert fake_state.query_calls == [
            {"limit": 15, "include_archived": False, "order_by_last_active": True}
        ]
        assert a.send.await_count == 2
        listing = a.send.await_args_list[0].args[1]
        assert "all platforms" in listing
        assert "Zabbix deploy" in listing
        assert "abcdef123456" in listing
        assert "Traefik" in listing

    @pytest.mark.asyncio
    async def test_handler_search_passes_query_and_denies_nothing(self, fake_state):
        fake_state.rows = [
            {"id": "abcdef1234567890", "source": "cli", "title": "Traefik", "preview": ""}
        ]
        a = make_adapter(OWNER_CFG)
        a.send = AsyncMock()

        await a._handle_cross_sessions("/sessions search traefik", "user:42", "42")

        assert fake_state.query_calls == [
            {
                "limit": 20,
                "include_archived": False,
                "order_by_last_active": True,
                "search_query": "traefik",
            }
        ]
        listing = a.send.await_args_list[0].args[1]
        assert "traefik" in listing

    @pytest.mark.asyncio
    async def test_handler_reports_empty_result(self, fake_state):
        fake_state.rows = []
        a = make_adapter(OWNER_CFG)
        a.send = AsyncMock()

        await a._handle_cross_sessions("/sessions", "user:42", "42")

        assert a.send.await_count == 1
        assert "No sessions" in a.send.await_args_list[0].args[1]

    @pytest.mark.asyncio
    async def test_handler_usage_error_on_empty_search(self, fake_state):
        a = make_adapter(OWNER_CFG)
        a.send = AsyncMock()

        await a._handle_cross_sessions("/sessions search", "user:42", "42")

        assert fake_state.init_calls == 0  # usage error never opens the store
        assert fake_state.query_calls == []
        assert "Usage" in a.send.await_args_list[0].args[1]

    @pytest.mark.asyncio
    async def test_bare_search_keyword_uses_handler_not_resume(self):
        """`/sessions search` (no query) must not become `/resume --all search`."""
        a = make_adapter(OWNER_CFG)
        a._handle_cross_sessions = AsyncMock()
        event = await a._on_message_created(dm_update("/sessions search"))

        a._handle_cross_sessions.assert_called_once_with(
            "/sessions search", "user:42", "42"
        )
        assert event is None
