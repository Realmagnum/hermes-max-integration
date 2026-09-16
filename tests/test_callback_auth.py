"""Regression tests for SEC-01 — callback authorization.

Base: audit commit b004c573 (BACKLOG.md / BACKLOG_EN.md, SEC-01).
Before the fix a callback only needed a nonempty ``user_id``: any member of a
group could press "Approve Always" on somebody else's dangerous-command card
and the handler resolved the *owner's* session (``_exec_approval_state`` held
nothing but a session key).

These tests exercise the real dispatch path (``_on_callback``) with mocked
gateway resolvers, so "the resolver was/was not called" is what is asserted —
not an intermediate helper.
"""

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

import adapter


def _make_adapter(allowed_users=None, allow_all=True):
    from gateway.config import PlatformConfig

    extra = {"token": "test-token", "allow_all_users": allow_all}
    if allowed_users is not None:
        extra["allowed_users"] = allowed_users
    a = adapter.MaxAdapter(
        PlatformConfig(enabled=True, token="test-token", extra=extra)
    )
    a._http_client = AsyncMock()
    a.send = AsyncMock()
    return a


def _callback(data, user_id, chat_id=None, mid=None):
    """Build a message_callback update the way MAX delivers it."""
    payload = {
        "update_type": "message_callback",
        "callback": {"payload": data, "user": {"user_id": user_id}},
    }
    message = {}
    if chat_id is not None:
        message["recipient"] = {"chat_id": chat_id}
    if mid is not None:
        message["body"] = {"mid": mid}
    if message:
        payload["message"] = message
    return payload


@pytest.fixture
def approval_tools(monkeypatch):
    """Mock the exec-approval resolver; returns the two mock handles."""
    from tools import approval

    has_pending = MagicMock(return_value=True)
    resolve = MagicMock(return_value=1)
    monkeypatch.setattr(approval, "has_blocking_approval", has_pending)
    monkeypatch.setattr(approval, "resolve_gateway_approval", resolve)
    return has_pending, resolve


def _bind_exec(a, *, approval_id="ap1", owner="42", chat="chat:777",
               mid="mid-prompt", session_key="max:group:sk-owner"):
    return a._register_interaction(
        "exec", approval_id,
        session_key=session_key,
        owner_user_id=owner,
        chat_id=chat,
        message_id=mid,
    )


class TestExecApprovalAuthorization:
    @pytest.mark.asyncio
    async def test_owner_press_resolves_and_consumes_state(self, approval_tools):
        has_pending, resolve = approval_tools
        a = _make_adapter()
        _bind_exec(a)

        await a._on_callback(
            _callback("exec:once:ap1", 42, chat_id=777, mid="mid-prompt")
        )

        has_pending.assert_called_once_with("max:group:sk-owner")
        resolve.assert_called_once_with("max:group:sk-owner", "once")
        assert "ap1" not in a._exec_approval_state

    @pytest.mark.asyncio
    async def test_group_member_cannot_approve_someone_elses_command(self, approval_tools):
        """The audit scenario: another participant presses Approve Always."""
        _, resolve = approval_tools
        a = _make_adapter()
        _bind_exec(a)

        await a._on_callback(
            _callback("exec:always:ap1", 99, chat_id=777, mid="mid-prompt")
        )

        resolve.assert_not_called()
        # The owner's pending approval must survive a stranger's press.
        assert "ap1" in a._exec_approval_state

    @pytest.mark.asyncio
    async def test_press_from_another_chat_is_refused(self, approval_tools):
        _, resolve = approval_tools
        a = _make_adapter()
        _bind_exec(a)

        await a._on_callback(
            _callback("exec:once:ap1", 42, chat_id=888, mid="mid-prompt")
        )

        resolve.assert_not_called()
        assert "ap1" in a._exec_approval_state

    @pytest.mark.asyncio
    async def test_press_on_a_stale_prompt_message_is_refused(self, approval_tools):
        _, resolve = approval_tools
        a = _make_adapter()
        _bind_exec(a)

        await a._on_callback(
            _callback("exec:once:ap1", 42, chat_id=777, mid="mid-another-card")
        )

        resolve.assert_not_called()
        assert "ap1" in a._exec_approval_state

    @pytest.mark.asyncio
    async def test_press_after_ttl_is_refused_and_state_dropped(self, approval_tools):
        _, resolve = approval_tools
        a = _make_adapter()
        _bind_exec(a)
        # Only the deadline moves — the record itself is untouched.
        a._exec_approval_state["ap1"]["expires_at"] = time.monotonic() - 1

        await a._on_callback(
            _callback("exec:once:ap1", 42, chat_id=777, mid="mid-prompt")
        )

        resolve.assert_not_called()
        assert "ap1" not in a._exec_approval_state

    @pytest.mark.asyncio
    async def test_disallowed_user_is_refused_before_any_dispatch(self, approval_tools):
        """A forbidden user must not reach the resolver even with a valid id."""
        _, resolve = approval_tools
        a = _make_adapter(allowed_users=["42"], allow_all=False)
        _bind_exec(a)

        await a._on_callback(
            _callback("exec:always:ap1", 666, chat_id=777, mid="mid-prompt")
        )

        resolve.assert_not_called()
        assert "ap1" in a._exec_approval_state

    @pytest.mark.asyncio
    async def test_unknown_approval_id_never_reaches_the_resolver(self, approval_tools):
        _, resolve = approval_tools
        a = _make_adapter()

        await a._on_callback(_callback("exec:once:nope", 42))

        resolve.assert_not_called()

    @pytest.mark.asyncio
    async def test_new_prompt_supersedes_the_previous_pending_buttons(self, approval_tools):
        """A newer approval for the same owner+chat kills the older card."""
        _, resolve = approval_tools
        a = _make_adapter()
        _bind_exec(a, approval_id="old")
        _bind_exec(a, approval_id="new")

        assert "old" not in a._exec_approval_state
        await a._on_callback(
            _callback("exec:once:old", 42, chat_id=777, mid="mid-prompt")
        )
        resolve.assert_not_called()

    @pytest.mark.asyncio
    async def test_unbound_approval_is_refused_by_default(self, approval_tools):
        """Owner unknown → fail closed, and the resolver is never called."""
        _, resolve = approval_tools
        a = _make_adapter()
        a._exec_approval_state["ap1"] = {
            "kind": "exec",
            "session_key": "max:group:sk-owner",
            "owner_user_id": "",
            "chat_id": "",
            "message_id": "",
            "created_at": time.monotonic(),
            "expires_at": time.monotonic() + 300,
        }

        await a._on_callback(_callback("exec:once:ap1", 42))

        resolve.assert_not_called()
        assert "ap1" in a._exec_approval_state


class TestSlashConfirmAuthorization:
    @pytest.fixture
    def slash_tools(self, monkeypatch):
        import tools.slash_confirm as sc

        resolve = AsyncMock(return_value="done")
        monkeypatch.setattr(sc, "resolve", resolve)
        return resolve

    @pytest.mark.asyncio
    async def test_owner_can_confirm(self, slash_tools):
        a = _make_adapter()
        a._register_interaction(
            "sc", "c1", session_key="sk", owner_user_id="42",
            chat_id="chat:777", message_id="mid-c1",
        )

        await a._on_callback(_callback("sc:once:c1", 42, chat_id=777, mid="mid-c1"))

        slash_tools.assert_awaited_once_with("sk", "c1", "once")

    @pytest.mark.asyncio
    async def test_other_member_cannot_confirm(self, slash_tools):
        a = _make_adapter()
        a._register_interaction(
            "sc", "c1", session_key="sk", owner_user_id="42",
            chat_id="chat:777", message_id="mid-c1",
        )

        await a._on_callback(_callback("sc:always:c1", 99, chat_id=777, mid="mid-c1"))

        slash_tools.assert_not_awaited()
        assert "c1" in a._slash_confirm_state


class TestClarifyAuthorization:
    @pytest.fixture
    def clarify_tools(self, monkeypatch):
        import tools.clarify_gateway as cg

        resolve = AsyncMock(return_value="chosen")
        mark = MagicMock(return_value=None)
        monkeypatch.setattr(cg, "resolve_gateway_clarify", resolve)
        monkeypatch.setattr(cg, "mark_awaiting_text", mark)
        return resolve, mark

    @pytest.mark.asyncio
    async def test_owner_can_answer(self, clarify_tools):
        resolve, _ = clarify_tools
        a = _make_adapter()
        a._register_interaction(
            "clarify", "q1", session_key="sk", owner_user_id="42",
            chat_id="chat:777", message_id="mid-q1",
        )

        await a._on_callback(_callback("clarify:q1:0", 42, chat_id=777, mid="mid-q1"))

        resolve.assert_awaited_once_with("q1", "0")

    @pytest.mark.asyncio
    async def test_other_member_cannot_answer(self, clarify_tools):
        resolve, mark = clarify_tools
        a = _make_adapter()
        a._register_interaction(
            "clarify", "q1", session_key="sk", owner_user_id="42",
            chat_id="chat:777", message_id="mid-q1",
        )

        await a._on_callback(_callback("clarify:q1:other", 99, chat_id=777, mid="mid-q1"))

        resolve.assert_not_awaited()
        mark.assert_not_called()
        assert "q1" in a._clarify_state


class TestModelPickerAuthorization:
    def _state(self, **overrides):
        state = {
            "provider_msg_id": "mid-provider",
            "providers": [
                {"slug": "deepseek", "name": "DeepSeek", "models": ["deepseek-v3"], "is_current": False},
            ],
            "session_key": "sk",
            "on_model_selected": AsyncMock(return_value="ok"),
            "current_model": "gpt-4",
            "current_provider": "openrouter",
            "owner_user_id": "42",
            "expires_at": time.monotonic() + 300,
        }
        state.update(overrides)
        return state

    @pytest.mark.asyncio
    async def test_other_member_cannot_drive_the_picker(self):
        a = _make_adapter()
        a.send = AsyncMock()
        a._model_picker_state["chat:777"] = self._state()

        await a._on_callback(
            _callback("model:pick:deepseek-v3:deepseek", 99, chat_id=777)
        )

        assert "chat:777" in a._model_picker_state
        a.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_owner_can_drive_the_picker(self):
        a = _make_adapter()
        a.send = AsyncMock()
        a.delete_message = AsyncMock(return_value=MagicMock(success=True))
        a._model_picker_state["chat:777"] = self._state()

        await a._on_callback(
            _callback("model:pick:deepseek-v3:deepseek", 42, chat_id=777)
        )

        assert "chat:777" not in a._model_picker_state
        a.send.assert_awaited()

    @pytest.mark.asyncio
    async def test_stale_picker_message_is_refused(self):
        a = _make_adapter()
        a._model_picker_state["chat:777"] = self._state()

        await a._on_callback(
            _callback("model:back", 42, chat_id=777, mid="mid-ancient-card")
        )

        assert "chat:777" in a._model_picker_state

    @pytest.mark.asyncio
    async def test_expired_picker_state_is_refused_and_dropped(self):
        a = _make_adapter()
        a._model_picker_state["chat:777"] = self._state(
            expires_at=time.monotonic() - 1,
        )

        await a._on_callback(_callback("model:back", 42, chat_id=777))

        assert "chat:777" not in a._model_picker_state


class TestBoundStateShape:
    """The senders must store the binding, not a bare session key."""

    @pytest.mark.asyncio
    async def test_audit_reproduction_intruder_resolves_owner_session(self, approval_tools):
        """The exact audit finding, in the pre-fix state shape.

        Base b004c573: ``_exec_approval_state`` held ``{approval_id: session_key}``
        and any group member's press reached ``resolve_gateway_approval`` with
        the *owner's* session key (the mocked resolver received an
        owner-session from a disallowed user). This test fails on the base
        commit and passes after the fix.
        """
        _, resolve = approval_tools
        a = _make_adapter(allowed_users=["42"], allow_all=False)
        # Legacy shape, written the way the pre-fix sender wrote it.
        a._exec_approval_state["ap1"] = "max:group:sk-owner"

        await a._on_callback(
            _callback("exec:always:ap1", 666, chat_id=777, mid="mid-prompt")
        )

        resolve.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_exec_approval_binds_owner_chat_and_message(self):
        a = _make_adapter()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": {"body": {"mid": "mid-card"}}}
        a._http_client.post = AsyncMock(return_value=mock_resp)
        a._remember_interaction_owner(
            session_key="max:dm:sk", chat_id="user:42", user_id="42",
        )

        result = await a.send_exec_approval(
            chat_id="user:42", command="rm -rf /", session_key="max:dm:sk",
        )
        assert result.success is True

        approval_id = next(iter(a._exec_approval_state))
        record = a._exec_approval_state[approval_id]
        assert record["owner_user_id"] == "42"
        assert record["chat_id"] == "user:42"
        assert record["message_id"] == "mid-card"
        assert record["session_key"] == "max:dm:sk"
        assert record["expires_at"] > record["created_at"]

    @pytest.mark.asyncio
    async def test_send_clarify_binds_owner_and_ttl(self):
        a = _make_adapter()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": {"body": {"mid": "mid-q"}}}
        a._http_client.post = AsyncMock(return_value=mock_resp)

        result = await a.send_clarify(
            chat_id="user:42", question="Pick one", choices=["a", "b"],
            clarify_id="q1", session_key="max:dm:sk",
        )
        assert result.success is True

        record = a._clarify_state["q1"]
        assert record["owner_user_id"] == "42"
        assert record["message_id"] == "mid-q"
        assert record["expires_at"] > time.monotonic()

    @pytest.mark.asyncio
    async def test_send_model_picker_binds_owner(self):
        a = _make_adapter()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": {"body": {"mid": "mid-p"}}}
        a._http_client.post = AsyncMock(return_value=mock_resp)

        result = await a.send_model_picker(
            chat_id="chat:777",
            providers=[{"slug": "deepseek", "name": "DeepSeek", "models": []}],
            current_model="gpt-4",
            current_provider="openrouter",
            session_key="sk",
            on_model_selected=AsyncMock(),
        )
        assert result.success is True

        # Group scope has no user in it — ownership comes from inbound traffic,
        # which is why an unknown owner must fail closed (asserted above).
        state = a._model_picker_state["chat:777"]
        assert state["owner_user_id"] == ""
        assert state["expires_at"] > time.monotonic()
