"""Tests for model picker interactive buttons."""

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

import adapter


def _picker_state(**overrides) -> dict:
    """A live picker session shaped exactly like ``send_model_picker`` writes it."""
    now = time.monotonic()
    state = {
        "provider_msg_id": "mid-provider",
        "providers": [],
        "session_key": "test",
        "on_model_selected": None,
        "current_model": "gpt-4",
        "current_provider": "openrouter",
        "owner_user_id": "42",
        "created_at": now,
        "updated_at": now,
    }
    state.update(overrides)
    return state


def _callback(payload: str, *, user_id=42, mid=None, chat_id=None) -> dict:
    """MAX ``message_callback`` update for a button tap.

    *mid* is the id of the message the button is attached to (MAX sends it in
    ``message.body.mid``); *chat_id* makes the tap look like a group tap.
    """
    update: dict = {
        "update_type": "message_callback",
        "callback": {"payload": payload, "user": {"user_id": user_id}},
    }
    if mid is not None or chat_id is not None:
        message: dict = {}
        if chat_id is not None:
            message["recipient"] = {"chat_id": chat_id}
        if mid is not None:
            message["body"] = {"mid": mid}
        update["message"] = message
    return update


class TestSendModelPicker:
    """Tests for send_model_picker."""

    def _make_adapter(self):
        from gateway.config import PlatformConfig
        cfg = PlatformConfig(enabled=True, token="test-token", extra={"token": "test-token"})
        a = adapter.MaxAdapter(cfg)
        a._http_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": {"body": {"mid": "mid-picker"}}}
        a._http_client.post = AsyncMock(return_value=mock_resp)
        return a

    @pytest.mark.asyncio
    async def test_sends_provider_buttons(self):
        a = self._make_adapter()
        providers = [
            {"slug": "openrouter", "name": "OpenRouter", "models": ["gpt-4", "claude-3"], "is_current": True},
            {"slug": "deepseek", "name": "DeepSeek", "models": ["deepseek-v3"], "is_current": False},
        ]

        async def on_selected(chat_id, model_id, provider_slug):
            return f"Switched to {model_id}"

        result = await a.send_model_picker(
            chat_id="user:42",
            providers=providers,
            current_model="gpt-4",
            current_provider="openrouter",
            session_key="test-session",
            on_model_selected=on_selected,
        )
        assert result.success is True
        assert "user:42" in a._model_picker_state

        state = a._model_picker_state["user:42"]
        assert state["providers"] == providers
        assert state["session_key"] == "test-session"

        # Verify buttons
        call_args = a._http_client.post.call_args
        body = call_args[1]["json"]
        buttons = body["attachments"][0]["payload"]["buttons"]
        # OpenRouter + DeepSeek = 2 providers, 2 per row → 1 row
        assert len(buttons) == 1
        assert buttons[0][0]["text"] == "OpenRouter ✅"
        assert buttons[0][1]["text"] == "DeepSeek"

    @pytest.mark.asyncio
    async def test_session_bound_to_owner_and_message(self):
        """A new session records its owner, its message and a live timestamp."""
        a = self._make_adapter()

        async def on_selected(chat_id, model_id, provider_slug):
            return "ok"

        await a.send_model_picker(
            chat_id="user:42", providers=[{"slug": "p", "name": "P", "models": []}],
            current_model="m", current_provider="p", session_key="s",
            on_model_selected=on_selected, metadata={"reply_to_message_id": "mid-reply"},
        )

        state = a._model_picker_state["user:42"]
        assert state["provider_msg_id"] == "mid-picker"
        assert state["owner_user_id"] == "42"  # derived from the DM chat id
        assert state["updated_at"] == state["created_at"]

    @pytest.mark.asyncio
    async def test_group_session_owner_from_metadata(self):
        """Core metadata wins when it carries an identity; a group id alone carries none."""
        a = self._make_adapter()

        async def on_selected(chat_id, model_id, provider_slug):
            return "ok"

        await a.send_model_picker(
            chat_id="chat:777", providers=[], current_model="m", current_provider="p",
            session_key="s", on_model_selected=on_selected, metadata={"user_id": 7},
        )
        assert a._model_picker_state["chat:777"]["owner_user_id"] == "7"

        await a.send_model_picker(
            chat_id="chat:777", providers=[], current_model="m", current_provider="p",
            session_key="s", on_model_selected=on_selected,
        )
        # No identity available up front in a group — bound on the first tap.
        assert a._model_picker_state["chat:777"]["owner_user_id"] == ""

    @pytest.mark.asyncio
    async def test_no_client(self):
        from gateway.config import PlatformConfig
        cfg = PlatformConfig(enabled=True, token="test-token")
        a = adapter.MaxAdapter(cfg)
        a._http_client = None
        result = await a.send_model_picker(
            chat_id="user:42", providers=[], current_model="",
            current_provider="", session_key="", on_model_selected=None,
        )
        assert result.success is False


class TestModelCallback:
    """Tests for model callback dispatch."""

    def _make_adapter(self):
        from gateway.config import PlatformConfig
        cfg = PlatformConfig(enabled=True, token="test-token", extra={"token": "test-token"})
        a = adapter.MaxAdapter(cfg)
        a._http_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": {"body": {"mid": "mid-models"}}}
        a._http_client.post = AsyncMock(return_value=mock_resp)
        return a

    @pytest.mark.asyncio
    async def test_provider_selection_callback(self):
        a = self._make_adapter()

        async def on_selected(chat_id, model_id, provider_slug):
            return f"OK {model_id}"

        a._model_picker_state["user:42"] = _picker_state(
            provider_msg_id="mid-001",
            providers=[
                {"slug": "deepseek", "name": "DeepSeek", "models": ["deepseek-v3"], "is_current": False},
            ],
            on_model_selected=on_selected,
        )

        payload = _callback("model:provider:deepseek", mid="mid-001")
        result = await a._on_callback(payload)
        # Provider selection just shows models, returns None (no text response)
        assert result is None
        # _post_interactive should have been called (sends new message with models)
        a._http_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_model_pick_callback(self):
        a = self._make_adapter()

        async def on_selected(chat_id, model_id, provider_slug):
            return f"✅ Switched to `{model_id}` via {provider_slug}"

        a._model_picker_state["user:42"] = _picker_state(
            provider_msg_id="mid-provider",
            model_msg_id="mid-models",
            providers=[],
            on_model_selected=on_selected,
        )

        a.send = AsyncMock()
        a.delete_message = AsyncMock(return_value=MagicMock(success=True))

        payload = _callback("model:pick:deepseek-v3:deepseek", mid="mid-models")
        result = await a._on_callback(payload)
        assert result is None  # Returns None after sending confirmation
        # Should have sent confirmation message
        a.send.assert_called_once()
        assert "deepseek-v3" in a.send.call_args[0][1]

        # Should have deleted both old messages
        a.delete_message.assert_any_call("user:42", "mid-models")
        a.delete_message.assert_any_call("user:42", "mid-provider")

        # State should be cleared
        assert "user:42" not in a._model_picker_state

    @pytest.mark.asyncio
    async def test_back_callback(self):
        a = self._make_adapter()

        a._model_picker_state["user:42"] = _picker_state(
            provider_msg_id="mid-provider",
            model_msg_id="mid-models",
            providers=[
                {"slug": "openrouter", "name": "OpenRouter", "models": [], "is_current": True},
            ],
            on_model_selected=None,
        )

        a.delete_message = AsyncMock(return_value=MagicMock(success=True))
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": {"body": {"mid": "mid-provider-new"}}}
        a._http_client.post = AsyncMock(return_value=mock_resp)

        payload = _callback("model:back", mid="mid-models")
        result = await a._on_callback(payload)
        assert result is None

        # Should have deleted both old messages
        a.delete_message.assert_any_call("user:42", "mid-models")
        a.delete_message.assert_any_call("user:42", "mid-provider")
        # Should have sent new provider message
        assert a._http_client.post.called
        # State should be preserved with new provider_msg_id
        assert "user:42" in a._model_picker_state
        assert a._model_picker_state["user:42"]["provider_msg_id"] == "mid-provider-new"

    @pytest.mark.asyncio
    async def test_unknown_model_callback(self):
        a = self._make_adapter()
        payload = _callback("model:unknown:stuff")
        result = await a._on_callback(payload)
        assert result is None

    @pytest.mark.asyncio
    async def test_pagination_with_many_models(self):
        """Test that providers with >15 models show pagination buttons."""
        a = self._make_adapter()

        # Create provider with 20 models (should show 2 pages)
        providers = [
            {
                "slug": "bigprovider",
                "name": "BigProvider",
                "models": [f"model-{i:02d}" for i in range(20)],
                "is_current": False,
            },
        ]

        async def on_selected(chat_id, model_id, provider_slug):
            return f"Switched to {model_id}"

        a._model_picker_state["user:42"] = _picker_state(
            provider_msg_id="mid-001", providers=providers, on_model_selected=on_selected,
            current_model="model-00", current_provider="bigprovider",
        )

        a.edit_message = AsyncMock()

        # Select provider
        payload = _callback("model:provider:bigprovider", mid="mid-001")
        result = await a._on_callback(payload)
        assert result is None

        # Get the sent buttons
        post_call = a._http_client.post.call_args
        body = post_call[1]["json"]
        buttons = body["attachments"][0]["payload"]["buttons"]

        # Should have 20 model buttons + Prev/Next + Back
        # First page: 15 models
        model_buttons = [b for row in buttons for b in row if "model:pick" in b.get("payload", "")]
        assert len(model_buttons) == 15  # First page

        # Should have pagination buttons
        nav_buttons = [b for row in buttons for b in row if "model:page" in b.get("payload", "")]
        assert len(nav_buttons) == 1  # Only Next on first page
        assert nav_buttons[0]["payload"] == "model:page:bigprovider:1"

        # Should have Back button
        back_buttons = [b for row in buttons for b in row if b.get("payload") == "model:back"]
        assert len(back_buttons) == 1

    @pytest.mark.asyncio
    async def test_page_navigation(self):
        """Test page navigation buttons."""
        a = self._make_adapter()

        providers = [
            {
                "slug": "bigprovider",
                "name": "BigProvider",
                "models": [f"model-{i:02d}" for i in range(20)],
                "is_current": False,
            },
        ]

        async def on_selected(chat_id, model_id, provider_slug):
            return f"Switched to {model_id}"

        a._model_picker_state["user:42"] = _picker_state(
            provider_msg_id="mid-provider", model_msg_id="mid-models",
            providers=providers, on_model_selected=on_selected,
            current_model="model-00", current_provider="bigprovider",
        )

        a.delete_message = AsyncMock(return_value=MagicMock(success=True))

        # Navigate to page 2
        payload = _callback("model:page:bigprovider:1", mid="mid-models")
        result = await a._on_callback(payload)
        assert result is None

        # Should have deleted old model message
        a.delete_message.assert_called_once_with("user:42", "mid-models")
        # Should have sent new message with models
        a._http_client.post.assert_called_once()

        # Get the sent buttons
        post_call = a._http_client.post.call_args
        body = post_call[1]["json"]
        buttons = body["attachments"][0]["payload"]["buttons"]

        # Second page: models 15-19 (5 models)
        model_buttons = [b for row in buttons for b in row if "model:pick" in b.get("payload", "")]
        assert len(model_buttons) == 5  # Second page has 5 models

        # Should have Prev button (no Next on last page)
        nav_buttons = [b for row in buttons for b in row if "model:page" in b.get("payload", "")]
        assert len(nav_buttons) == 1  # Only Prev
        assert nav_buttons[0]["payload"] == "model:page:bigprovider:0"


class TestModelPickerIsolation:
    """CODE-06: picker sessions are bound to their owner, their message and a TTL."""

    def _make_adapter(self):
        from gateway.config import PlatformConfig
        cfg = PlatformConfig(enabled=True, token="test-token", extra={"token": "test-token"})
        a = adapter.MaxAdapter(cfg)
        a._http_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": {"body": {"mid": "mid-new-models"}}}
        a._http_client.post = AsyncMock(return_value=mock_resp)
        a.send = AsyncMock()
        a.delete_message = AsyncMock(return_value=MagicMock(success=True))
        return a

    @staticmethod
    def _providers() -> list:
        return [{"slug": "deepseek", "name": "DeepSeek", "models": ["deepseek-v3"], "is_current": False}]

    # ── owner binding ────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_second_user_cannot_drive_group_picker(self):
        """Two users in one group: the first tapper owns the session, the second is refused."""
        a = self._make_adapter()
        calls = []

        async def on_selected(chat_id, model_id, provider_slug):
            calls.append((chat_id, model_id, provider_slug))
            return "switched"

        # Nobody known up front in a group: the first tap binds the session.
        a._model_picker_state["chat:777"] = _picker_state(
            owner_user_id="", provider_msg_id="mid-live", model_msg_id="mid-models",
            providers=self._providers(), on_model_selected=on_selected,
        )

        await a._on_callback(_callback("model:pick:deepseek-v3:deepseek", user_id=42, mid="mid-models", chat_id=777))
        assert len(calls) == 1
        assert a._model_picker_state == {}  # the pick consumed the session

        # Same chat, a stranger taps the (fresh) session's buttons.
        a._model_picker_state["chat:777"] = _picker_state(
            owner_user_id="42", provider_msg_id="mid-live", model_msg_id="mid-models",
            providers=self._providers(), on_model_selected=on_selected,
        )
        await a._on_callback(_callback("model:pick:deepseek-v3:deepseek", user_id=99, mid="mid-models", chat_id=777))
        assert len(calls) == 1  # the stranger's tap changed nothing
        assert "chat:777" in a._model_picker_state  # session still live for its owner

        # The owner can still use it.
        await a._on_callback(_callback("model:pick:deepseek-v3:deepseek", user_id=42, mid="mid-models", chat_id=777))
        assert len(calls) == 2

    @pytest.mark.asyncio
    async def test_dm_session_not_reachable_from_another_user(self):
        """A DM session is keyed by its user, so another user's tap finds no session."""
        a = self._make_adapter()
        a._model_picker_state["user:42"] = _picker_state(
            owner_user_id="42", provider_msg_id="mid-live", providers=self._providers(),
        )

        await a._on_callback(_callback("model:provider:deepseek", user_id=99, mid="mid-live"))
        a._http_client.post.assert_not_called()
        assert "user:42" in a._model_picker_state

    # ── message binding ──────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_superseded_message_cannot_apply_new_session(self):
        """A button on an old picker message is inert once a newer picker exists."""
        a = self._make_adapter()
        providers = self._providers()

        # Old picker message (replaced on screen, not necessarily deleted).
        a._model_picker_state["chat:777"] = _picker_state(
            owner_user_id="42", provider_msg_id="mid-old", providers=providers,
        )
        # The user ran /model again: new session, new message id, same chat key.
        a._model_picker_state["chat:777"] = _picker_state(
            owner_user_id="42", provider_msg_id="mid-new", providers=providers,
        )

        await a._on_callback(_callback("model:provider:deepseek", user_id=42, mid="mid-old", chat_id=777))
        a._http_client.post.assert_not_called()  # stale tap ignored

        await a._on_callback(_callback("model:provider:deepseek", user_id=42, mid="mid-new", chat_id=777))
        a._http_client.post.assert_called_once()  # live message still works

    @pytest.mark.asyncio
    async def test_stale_pick_after_model_list_replaced(self):
        """Pagination replaces the model message; taps on the replaced one are ignored."""
        a = self._make_adapter()
        calls = []

        async def on_selected(chat_id, model_id, provider_slug):
            calls.append(model_id)
            return "ok"

        a._model_picker_state["user:42"] = _picker_state(
            owner_user_id="42", provider_msg_id="mid-provider", model_msg_id="mid-page2",
            providers=[{"slug": "p", "name": "P", "models": ["m1"], "is_current": False}],
            on_model_selected=on_selected,
        )

        await a._on_callback(_callback("model:pick:m1:p", user_id=42, mid="mid-page1"))
        assert calls == []
        assert "user:42" in a._model_picker_state

        await a._on_callback(_callback("model:pick:m1:p", user_id=42, mid="mid-page2"))
        assert calls == ["m1"]

    @pytest.mark.asyncio
    async def test_tap_without_message_id_still_honoured(self):
        """Payloads that hide the pressed message keep working (owner binding still applies)."""
        a = self._make_adapter()
        a._model_picker_state["user:42"] = _picker_state(
            owner_user_id="42", provider_msg_id="mid-001", providers=self._providers(),
        )

        await a._on_callback(_callback("model:provider:deepseek", user_id=42))
        a._http_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_stale_tap_does_not_bind_unowned_group_session(self):
        """A stale button must not be able to claim an unowned group session."""
        a = self._make_adapter()
        a._model_picker_state["chat:777"] = _picker_state(
            owner_user_id="", provider_msg_id="mid-live", providers=self._providers(),
        )

        # A stranger taps an old message's button: refused, and nothing is bound.
        await a._on_callback(_callback("model:provider:deepseek", user_id=99, mid="mid-old", chat_id=777))
        assert a._model_picker_state["chat:777"]["owner_user_id"] == ""

        # The owner's tap on the live message binds the session and works.
        await a._on_callback(_callback("model:provider:deepseek", user_id=42, mid="mid-live", chat_id=777))
        assert a._model_picker_state["chat:777"]["owner_user_id"] == "42"
        a._http_client.post.assert_called_once()

    # ── TTL ──────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_expired_session_is_ignored_and_pruned(self):
        a = self._make_adapter()
        a._model_picker_state["chat:777"] = _picker_state(
            owner_user_id="42", provider_msg_id="mid-live", providers=self._providers(),
            updated_at=time.monotonic() - adapter.MODEL_PICKER_TTL_SECONDS - 1,
        )

        await a._on_callback(_callback("model:provider:deepseek", user_id=42, mid="mid-live", chat_id=777))
        a._http_client.post.assert_not_called()
        assert a._model_picker_state == {}  # expired entry dropped

    @pytest.mark.asyncio
    async def test_accepted_tap_refreshes_ttl(self):
        a = self._make_adapter()
        stale_at = time.monotonic() - adapter.MODEL_PICKER_TTL_SECONDS + 30  # still inside the TTL
        a._model_picker_state["user:42"] = _picker_state(
            owner_user_id="42", provider_msg_id="mid-001", providers=self._providers(),
            updated_at=stale_at,
        )

        await a._on_callback(_callback("model:provider:deepseek", user_id=42, mid="mid-001"))
        a._http_client.post.assert_called_once()
        assert a._model_picker_state["user:42"]["updated_at"] > stale_at

    @pytest.mark.asyncio
    async def test_replayed_pick_is_ignored(self):
        """A re-tapped pick button cannot switch the model twice."""
        a = self._make_adapter()
        calls = []

        async def on_selected(chat_id, model_id, provider_slug):
            calls.append(model_id)
            return "switched"

        a._model_picker_state["user:42"] = _picker_state(
            owner_user_id="42", provider_msg_id="mid-provider", model_msg_id="mid-models",
            providers=self._providers(), on_model_selected=on_selected,
        )

        await a._on_callback(_callback("model:pick:deepseek-v3:deepseek", user_id=42, mid="mid-models"))
        await a._on_callback(_callback("model:pick:deepseek-v3:deepseek", user_id=42, mid="mid-models"))

        assert calls == ["deepseek-v3"]
        a.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_tap_without_session_is_inert(self):
        a = self._make_adapter()
        await a._on_callback(_callback("model:pick:deepseek-v3:deepseek", user_id=42, mid="mid-any"))
        a.send.assert_not_called()
        a._http_client.post.assert_not_called()
        assert a._model_picker_state == {}

    # ── payload plumbing ─────────────────────────────────────────────────

    def test_callback_message_id_extraction(self):
        extract = adapter.MaxAdapter._callback_message_id
        assert extract({"message": {"body": {"mid": "m1"}}}) == "m1"
        assert extract({"message": {"mid": "m2"}}) == "m2"
        assert extract({"callback": {"mid": "m3"}}) == "m3"
        assert extract({"callback": {"message_id": "m4"}}) == "m4"
        assert extract({}) == ""

    def test_owner_derivation(self):
        owner_of = adapter.MaxAdapter._model_picker_owner
        assert owner_of("user:42", None) == "42"
        assert owner_of("chat:777", None) == ""            # unknowable up front
        assert owner_of("chat:777", {"user_id": 7}) == "7"
        assert owner_of("user:42", {"owner_user_id": 9}) == "9"
