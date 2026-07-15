"""Tests for model picker interactive buttons."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import adapter


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
        return a

    @pytest.mark.asyncio
    async def test_provider_selection_callback(self):
        a = self._make_adapter()

        async def on_selected(chat_id, model_id, provider_slug):
            return f"OK {model_id}"

        a._model_picker_state["user:42"] = {
            "msg_id": "mid-001",
            "providers": [
                {"slug": "deepseek", "name": "DeepSeek", "models": ["deepseek-v3"], "is_current": False},
            ],
            "session_key": "test",
            "on_model_selected": on_selected,
            "current_model": "gpt-4",
            "current_provider": "openrouter",
        }

        # Simulate edit_message and _post_interactive
        a.edit_message = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": {"body": {"mid": "mid-models"}}}
        a._http_client.post = AsyncMock(return_value=mock_resp)

        payload = {
            "update_type": "message_callback",
            "callback": {
                "payload": "model:provider:deepseek",
                "user": {"user_id": 42},
            },
        }
        result = await a._on_callback(payload)
        # Provider selection just shows models, returns None (no text response)
        assert result is None
        # edit_message should have been called
        a.edit_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_model_pick_callback(self):
        a = self._make_adapter()

        async def on_selected(chat_id, model_id, provider_slug):
            return f"✅ Switched to `{model_id}` via {provider_slug}"

        a._model_picker_state["user:42"] = {
            "msg_id": "mid-001",
            "providers": [],
            "session_key": "test",
            "on_model_selected": on_selected,
            "current_model": "gpt-4",
            "current_provider": "openrouter",
        }

        payload = {
            "update_type": "message_callback",
            "callback": {
                "payload": "model:pick:deepseek-v3:deepseek",
                "user": {"user_id": 42},
            },
        }
        result = await a._on_callback(payload)
        assert result is not None
        assert "deepseek-v3" in result.text
        assert "deepseek" in result.text

        # State should be cleared
        assert "user:42" not in a._model_picker_state

    @pytest.mark.asyncio
    async def test_back_callback(self):
        a = self._make_adapter()

        a._model_picker_state["user:42"] = {
            "msg_id": "mid-001",
            "providers": [
                {"slug": "openrouter", "name": "OpenRouter", "models": [], "is_current": True},
            ],
            "session_key": "test",
            "on_model_selected": None,
            "current_model": "gpt-4",
            "current_provider": "openrouter",
        }

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": {"body": {"mid": "mid-back"}}}
        a._http_client.post = AsyncMock(return_value=mock_resp)

        payload = {
            "update_type": "message_callback",
            "callback": {
                "payload": "model:back",
                "user": {"user_id": 42},
            },
        }
        result = await a._on_callback(payload)
        assert result is None
        # Should have sent a new interactive message
        assert a._http_client.post.called

    @pytest.mark.asyncio
    async def test_unknown_model_callback(self):
        a = self._make_adapter()
        payload = {
            "update_type": "message_callback",
            "callback": {
                "payload": "model:unknown:stuff",
                "user": {"user_id": 42},
            },
        }
        result = await a._on_callback(payload)
        assert result is None
