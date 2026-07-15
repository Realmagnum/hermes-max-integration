"""Tests for interactive buttons (approval, slash-confirm, clarify)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import adapter


class TestPostInteractive:
    """Tests for _post_interactive."""

    def _make_adapter(self):
        from gateway.config import PlatformConfig
        cfg = PlatformConfig(enabled=True, token="test-token", extra={"token": "test-token"})
        a = adapter.MaxAdapter(cfg)
        a._http_client = AsyncMock()
        return a

    @pytest.mark.asyncio
    async def test_post_interactive_dm(self):
        a = self._make_adapter()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": {"body": {"mid": "mid-123"}}}
        a._http_client.post = AsyncMock(return_value=mock_resp)

        buttons = [[
            {"type": "callback", "text": "Btn", "payload": "btn:1"},
        ]]

        result = await a._post_interactive("user:42", "Test message", buttons)
        assert result.success is True
        assert result.message_id == "mid-123"

        # Verify the request body
        call_args = a._http_client.post.call_args
        body = call_args[1]["json"]
        assert body["text"] == "Test message"
        assert body["attachments"][0]["type"] == "inline_keyboard"
        assert body["attachments"][0]["payload"]["buttons"] == buttons

    @pytest.mark.asyncio
    async def test_post_interactive_no_client(self):
        from gateway.config import PlatformConfig
        cfg = PlatformConfig(enabled=True, token="test-token")
        a = adapter.MaxAdapter(cfg)
        a._http_client = None
        result = await a._post_interactive("user:42", "Test", [])
        assert result.success is False


class TestSendExecApproval:
    """Tests for send_exec_approval."""

    def _make_adapter(self):
        from gateway.config import PlatformConfig
        cfg = PlatformConfig(enabled=True, token="test-token", extra={"token": "test-token"})
        a = adapter.MaxAdapter(cfg)
        a._http_client = AsyncMock()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": {"body": {"mid": "mid-456"}}}
        a._http_client.post = AsyncMock(return_value=mock_resp)
        return a

    @pytest.mark.asyncio
    async def test_sends_buttons_and_stores_state(self):
        a = self._make_adapter()
        result = await a.send_exec_approval(
            chat_id="user:42",
            command="rm -rf /test",
            session_key="test-session",
            description="test command",
        )
        assert result.success is True
        # State should be stored
        assert len(a._exec_approval_state) == 1
        approval_id = list(a._exec_approval_state.keys())[0]
        assert a._exec_approval_state[approval_id] == "test-session"

        # Verify buttons
        call_args = a._http_client.post.call_args
        body = call_args[1]["json"]
        buttons = body["attachments"][0]["payload"]["buttons"]
        assert len(buttons) == 2  # 2 rows
        assert buttons[0][0]["text"] == "✅ Approve Once"
        assert buttons[0][1]["text"] == "🔄 Session"
        assert buttons[1][0]["text"] == "🔒 Always"
        assert buttons[1][1]["text"] == "❌ Deny"


class TestSendSlashConfirm:
    """Tests for send_slash_confirm."""

    def _make_adapter(self):
        from gateway.config import PlatformConfig
        cfg = PlatformConfig(enabled=True, token="test-token", extra={"token": "test-token"})
        a = adapter.MaxAdapter(cfg)
        a._http_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": {"body": {"mid": "mid-789"}}}
        a._http_client.post = AsyncMock(return_value=mock_resp)
        return a

    @pytest.mark.asyncio
    async def test_sends_three_buttons_and_stores_state(self):
        a = self._make_adapter()
        result = await a.send_slash_confirm(
            chat_id="user:42",
            title="Test Confirm",
            message="Are you sure?",
            session_key="test-session",
            confirm_id="c001",
        )
        assert result.success is True
        assert a._slash_confirm_state["c001"] == "test-session"

        call_args = a._http_client.post.call_args
        body = call_args[1]["json"]
        buttons = body["attachments"][0]["payload"]["buttons"]
        assert len(buttons) == 1  # 1 row of 3
        assert buttons[0][0]["text"] == "✅ Approve Once"
        assert buttons[0][1]["text"] == "🔒 Always"
        assert buttons[0][2]["text"] == "❌ Cancel"


class TestOnCallback:
    """Tests for _on_callback message_callback handling."""

    def _make_adapter(self):
        from gateway.config import PlatformConfig
        cfg = PlatformConfig(enabled=True, token="test-token", extra={"token": "test-token"})
        return adapter.MaxAdapter(cfg)

    @pytest.mark.asyncio
    async def test_exec_callback(self):
        a = self._make_adapter()
        a._exec_approval_state["apr001"] = "test-session"

        from tools.approval import _ApprovalEntry, _gateway_queues
        _gateway_queues["test-session"] = [_ApprovalEntry({"command": "test"})]

        try:
            payload = {
                "update_type": "message_callback",
                "callback": {
                    "payload": "exec:session:apr001",
                    "user": {"user_id": 42, "name": "Test"},
                },
            }
            result = await a._on_callback(payload)
            assert result is not None
            assert "Approved" in result.text or "session" in result.text.lower()
        finally:
            _gateway_queues.pop("test-session", None)

    @pytest.mark.asyncio
    async def test_exec_callback_unknown_id(self):
        a = self._make_adapter()
        payload = {
            "update_type": "message_callback",
            "callback": {
                "payload": "exec:once:unknown_id",
                "user": {"user_id": 42},
            },
        }
        result = await a._on_callback(payload)
        assert result is None  # Unknown ID → no event

    @pytest.mark.asyncio
    async def test_unknown_prefix(self):
        a = self._make_adapter()
        payload = {
            "update_type": "message_callback",
            "callback": {
                "payload": "unknown:data:here",
                "user": {"user_id": 42},
            },
        }
        result = await a._on_callback(payload)
        assert result is None

    @pytest.mark.asyncio
    async def test_no_payload(self):
        a = self._make_adapter()
        payload = {
            "update_type": "message_callback",
            "callback": {
                "user": {"user_id": 42},
            },
        }
        result = await a._on_callback(payload)
        assert result is None

    @pytest.mark.asyncio
    async def test_callback_clears_state(self):
        a = self._make_adapter()
        a._exec_approval_state["apr002"] = "test-session-2"

        from tools.approval import _ApprovalEntry, _gateway_queues
        _gateway_queues["test-session-2"] = [_ApprovalEntry({"command": "test"})]

        try:
            payload = {
                "update_type": "message_callback",
                "callback": {
                    "payload": "exec:once:apr002",
                    "user": {"user_id": 42},
                },
            }
            await a._on_callback(payload)
            # State should be cleared
            assert "apr002" not in a._exec_approval_state
        finally:
            _gateway_queues.pop("test-session-2", None)
