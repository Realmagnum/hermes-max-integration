"""Unit tests for interactive session picker (SESS-001..SESS-006).

Verifies the interactive /sessions picker: formatting with bold numbers and
platform emojis, 5-per-row button layout, SEC-01 fail-closed authorization,
message deletion on cancel/pick, context preview, and /resume --all event dispatch.
"""

from __future__ import annotations

import types
from typing import ClassVar
from unittest.mock import AsyncMock

import pytest
from gateway.platforms.base import SendResult

import adapter

OWNER_CFG = {"cross_session": True, "allowed_users": [42]}


def make_adapter(extra=None):
    from gateway.config import PlatformConfig

    cfg = PlatformConfig(enabled=True, token="test-token", extra=extra or {})
    return adapter.MaxAdapter(cfg)


class FakeSessionDB:
    rows: ClassVar[list[dict]] = []
    messages: ClassVar[dict[str, list[dict]]] = {}

    def __init__(self):
        pass

    def close(self):
        pass

    def list_sessions_rich(self, **kwargs):
        rows = [row for row in FakeSessionDB.rows if not kwargs.get("source") or row["source"] == kwargs["source"]]
        return rows[:kwargs["limit"]]

    def get_messages(self, session_id: str, include_ancestors: bool = True, **kwargs):
        return list(FakeSessionDB.messages.get(session_id, []))


@pytest.fixture(autouse=True)
def _patch_session_db(monkeypatch):
    FakeSessionDB.rows = [
        {
            "id": "sess-cli-1234567890",
            "source": "cli",
            "title": "CLI Terminal Work",
            "preview": "Initial user command for CLI",
            "last_active": "2026-10-14T10:30:00Z",
            "message_count": 8,
        },
        {
            "id": "sess-tg-0987654321",
            "source": "telegram",
            "title": "Telegram Bot Chat",
            "preview": "Deploy Traefik reverse proxy",
            "last_active": "2026-10-15T14:15:00Z",
            "message_count": 14,
        },
        {
            "id": "sess-max-1122334455",
            "source": "max",
            "title": "MAX Bot Discussion",
            "preview": "Review micro-spec pipeline",
            "last_active": "2026-10-16T09:00:00Z",
            "message_count": 5,
        },
    ]
    FakeSessionDB.messages = {
        "sess-tg-0987654321": [
            {"role": "user", "content": "Deploy Traefik reverse proxy with ACME TLS certificates"},
            {"role": "assistant", "content": "Starting Traefik configuration on gateway host..."},
            {"role": "user", "content": "Check port 443 binding and reload"},
            {"role": "assistant", "content": "Traefik deployed and running healthy on port 443."},
        ]
    }
    mod = types.ModuleType("hermes_state")
    mod.SessionDB = FakeSessionDB
    monkeypatch.setitem(pytest.importorskip("sys").modules, "hermes_state", mod)
    return FakeSessionDB


class TestInteractiveSessionPicker:
    def test_sess_001_card_formatting(self):
        """SESS-001: bold numbers, source emojis, quotes, mono date, message count."""
        a = make_adapter(OWNER_CFG)
        card_text, _keyboard = a._session_picker_card(FakeSessionDB.rows, interaction_id="test123")

        assert "📋 **Выбор сессии** (все платформы" in card_text
        assert "**1.** 💻 **cli** — CLI Terminal Work" in card_text
        assert "_«Initial user command for CLI»_" in card_text
        assert "🕒 `2026/10/14" in card_text
        assert "💬 8 сообщ." in card_text
        assert "**2.** 📱 **telegram** — Telegram Bot Chat" in card_text
        assert "_«Deploy Traefik reverse proxy»_" in card_text
        assert "💬 14 сообщ." in card_text
        assert "sess-cli-123" in card_text

    def test_sess_002_keyboard_layout_and_action_row(self):
        """SESS-002: 5 buttons per row + bottom action row with refresh and cancel."""
        a = make_adapter(OWNER_CFG)
        # Create 12 fake sessions to test row grouping
        fake_12 = [
            {"id": f"s-{i}", "source": "cli", "title": f"Task {i}", "preview": ""}
            for i in range(1, 13)
        ]
        _, keyboard = a._session_picker_card(fake_12, interaction_id="act789", limit=12)

        # Row 1: 5 buttons
        assert len(keyboard[0]) == 5
        assert keyboard[0][0]["text"] == "💻 1"
        assert keyboard[0][0]["payload"] == "session:act789:pick:1"
        assert keyboard[0][4]["text"] == "💻 5"

        # Row 2: 5 buttons
        assert len(keyboard[1]) == 5
        assert keyboard[1][0]["text"] == "💻 6"

        # Row 3: 2 remaining buttons
        assert len(keyboard[2]) == 2
        assert keyboard[2][1]["text"] == "💻 12"

        # Row 4: Action row (Refresh & Cancel)
        assert len(keyboard[3]) == 2
        assert keyboard[3][0]["text"] == "🔄 Обновить"
        assert keyboard[3][0]["payload"] == "session:act789:refresh"
        assert keyboard[3][1]["text"] == "❌ Отмена"
        assert keyboard[3][1]["payload"] == "session:act789:cancel"

    @pytest.mark.asyncio
    async def test_sess_003_callback_authorization_fail_closed(self):
        """SESS-003: reject foreign users, mismatched message ID, and expired states."""
        a = make_adapter(OWNER_CFG)
        a.delete_message = AsyncMock(return_value=SendResult(success=True))

        # Register a pending interaction for owner 42
        interaction_id = "sec01sess"
        mid = "mid-picker-1"
        chat = "user:42"
        record = a._register_interaction(
            "session", interaction_id,
            owner_user_id="42", chat_id=chat, message_id=mid, ttl=100.0,
        )
        record["rows"] = FakeSessionDB.rows
        a._session_picker_state[interaction_id] = record

        # 1. Foreign user (99) attempts to pick session 1 -> REJECTED
        res = await a._handle_session_callback(
            f"session:{interaction_id}:pick:1", user_id="99", scoped_chat=chat, message_id=mid,
        )
        assert res is None
        a.delete_message.assert_not_called()
        assert interaction_id in a._session_picker_state  # State left intact for owner

        # 2. Wrong message_id -> REJECTED
        res = await a._handle_session_callback(
            f"session:{interaction_id}:pick:1", user_id="42", scoped_chat=chat, message_id="wrong-mid",
        )
        assert res is None
        a.delete_message.assert_not_called()

        # 3. Expired interaction -> REJECTED & popped
        record["expires_at"] = 0.0
        res = await a._handle_session_callback(
            f"session:{interaction_id}:pick:1", user_id="42", scoped_chat=chat, message_id=mid,
        )
        assert res is None

    @pytest.mark.asyncio
    async def test_sess_004_cancel_action(self):
        """SESS-004: cancel deletes the message, removes state, and does not switch session."""
        a = make_adapter(OWNER_CFG)
        a.delete_message = AsyncMock(return_value=SendResult(success=True))

        interaction_id = "cancelsess"
        mid = "mid-picker-cancel"
        chat = "user:42"
        record = a._register_interaction(
            "session", interaction_id,
            owner_user_id="42", chat_id=chat, message_id=mid, ttl=100.0,
        )
        record["rows"] = FakeSessionDB.rows
        a._session_picker_state[interaction_id] = record

        res = await a._handle_session_callback(
            f"session:{interaction_id}:cancel", user_id="42", scoped_chat=chat, message_id=mid,
        )
        assert res is None
        a.delete_message.assert_called_once_with(chat, mid)
        assert interaction_id not in a._session_picker_state

    @pytest.mark.asyncio
    async def test_sess_005_refresh_action(self):
        """SESS-005: refresh deletes old message and posts a fresh picker."""
        a = make_adapter(OWNER_CFG)
        a.delete_message = AsyncMock(return_value=SendResult(success=True))
        a._post_session_picker = AsyncMock()

        interaction_id = "refreshsess"
        mid = "mid-picker-refresh"
        chat = "user:42"
        record = a._register_interaction(
            "session", interaction_id,
            owner_user_id="42", chat_id=chat, message_id=mid, ttl=100.0,
        )
        record["rows"] = FakeSessionDB.rows
        record["search"] = None
        a._session_picker_state[interaction_id] = record

        res = await a._handle_session_callback(
            f"session:{interaction_id}:refresh", user_id="42", scoped_chat=chat, message_id=mid,
        )
        assert res is None
        a.delete_message.assert_called_once_with(chat, mid)
        assert a._post_session_picker.called
        assert interaction_id not in a._session_picker_state

    @pytest.mark.asyncio
    async def test_sess_006_pick_session_success(self):
        """SESS-006: pick deletes picker message, sends context card, returns /resume --all event."""
        a = make_adapter(OWNER_CFG)
        a.delete_message = AsyncMock(return_value=SendResult(success=True))
        a.send = AsyncMock(return_value=SendResult(success=True))

        interaction_id = "picksess"
        mid = "mid-picker-pick"
        chat = "user:42"
        record = a._register_interaction(
            "session", interaction_id,
            owner_user_id="42", chat_id=chat, message_id=mid, ttl=100.0,
        )
        record["rows"] = FakeSessionDB.rows
        a._session_picker_state[interaction_id] = record

        # Pick session 2 (sess-tg-0987654321)
        event = await a._handle_session_callback(
            f"session:{interaction_id}:pick:2", user_id="42", scoped_chat=chat, message_id=mid,
        )

        # 1. Message deleted
        a.delete_message.assert_called_once_with(chat, mid)

        # 2. Context confirmation card sent (or registered via post-delivery hook)
        sk = a._source_session_key(event.source)
        post_cb = a.pop_post_delivery_callback(sk)
        if post_cb:
            await post_cb()
        assert a.send.called
        card_text = a.send.await_args_list[0].args[1]
        assert "✅ **Активная сессия:** 📱 Telegram Bot Chat" in card_text
        assert "📌 **Задача:** _«Deploy Traefik reverse proxy with ACME TLS certificates»_" in card_text
        assert "🤖 **Последнее:** _«Traefik deployed and running healthy on port 443.»_" in card_text

        # 3. MessageEvent created to switch session in core gateway
        assert event is not None
        assert event.text == "/resume --all sess-tg-0987654321"
        assert event.source.user_id == "42"

    def test_sess_007_context_extraction(self):
        """Test extraction of first user prompt and latest message exchange."""
        a = make_adapter(OWNER_CFG)
        first, last, role = a._session_context("sess-tg-0987654321")
        assert "Deploy Traefik" in first
        assert "Traefik deployed" in last
        assert role == "assistant"
