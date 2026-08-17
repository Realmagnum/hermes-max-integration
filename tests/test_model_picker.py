"""Tests for model picker interactive buttons."""

from unittest.mock import AsyncMock, MagicMock

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
            "provider_msg_id": "mid-001",
            "providers": [
                {"slug": "deepseek", "name": "DeepSeek", "models": ["deepseek-v3"], "is_current": False},
            ],
            "session_key": "test",
            "on_model_selected": on_selected,
            "current_model": "gpt-4",
            "current_provider": "openrouter",
        }

        # Simulate _post_interactive (sends new message with models)
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
        # _post_interactive should have been called (sends new message with models)
        a._http_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_model_pick_callback(self):
        a = self._make_adapter()

        async def on_selected(chat_id, model_id, provider_slug):
            return f"✅ Switched to `{model_id}` via {provider_slug}"

        a._model_picker_state["user:42"] = {
            "provider_msg_id": "mid-provider",
            "model_msg_id": "mid-models",
            "providers": [],
            "session_key": "test",
            "on_model_selected": on_selected,
            "current_model": "gpt-4",
            "current_provider": "openrouter",
        }

        a.send = AsyncMock()
        a.delete_message = AsyncMock(return_value=MagicMock(success=True))

        payload = {
            "update_type": "message_callback",
            "callback": {
                "payload": "model:pick:deepseek-v3:deepseek",
                "user": {"user_id": 42},
            },
        }
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

        a._model_picker_state["user:42"] = {
            "provider_msg_id": "mid-provider",
            "model_msg_id": "mid-models",
            "providers": [
                {"slug": "openrouter", "name": "OpenRouter", "models": [], "is_current": True},
            ],
            "session_key": "test",
            "on_model_selected": None,
            "current_model": "gpt-4",
            "current_provider": "openrouter",
        }

        a.delete_message = AsyncMock(return_value=MagicMock(success=True))
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": {"body": {"mid": "mid-provider-new"}}}
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
        payload = {
            "update_type": "message_callback",
            "callback": {
                "payload": "model:unknown:stuff",
                "user": {"user_id": 42},
            },
        }
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

        a._model_picker_state["user:42"] = {
            "provider_msg_id": "mid-001",
            "providers": providers,
            "session_key": "test",
            "on_model_selected": on_selected,
            "current_model": "model-00",
            "current_provider": "bigprovider",
        }

        a.edit_message = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": {"body": {"mid": "mid-models"}}}
        a._http_client.post = AsyncMock(return_value=mock_resp)

        # Select provider
        payload = {
            "update_type": "message_callback",
            "callback": {
                "payload": "model:provider:bigprovider",
                "user": {"user_id": 42},
            },
        }
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

        a._model_picker_state["user:42"] = {
            "provider_msg_id": "mid-provider",
            "model_msg_id": "mid-models",
            "providers": providers,
            "session_key": "test",
            "on_model_selected": on_selected,
            "current_model": "model-00",
            "current_provider": "bigprovider",
        }

        a.delete_message = AsyncMock(return_value=MagicMock(success=True))
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": {"body": {"mid": "mid-models-new"}}}
        a._http_client.post = AsyncMock(return_value=mock_resp)

        # Navigate to page 2
        payload = {
            "update_type": "message_callback",
            "callback": {
                "payload": "model:page:bigprovider:1",
                "user": {"user_id": 42},
            },
        }
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
