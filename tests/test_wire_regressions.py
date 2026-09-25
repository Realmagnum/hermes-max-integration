"""Wire-level regression tests for the MAX adapter (BUILD-04).

These tests replace `MagicMock`/`AsyncMock` HTTP doubles with a real
`httpx.AsyncClient` over `httpx.MockTransport`, and drive the adapter with
*p Captured* MAX Bot API update payloads (`tests/conftest.py`).  The point is to
assert on the bytes the adapter actually sends — query parameters and JSON
bodies — and on the absence of side effects, not merely that "a call happened".

Known defects are pinned with ``xfail(strict=True)`` so the suite stays honest:
a test marked this way documents current, wrong behaviour; it must be tightened
to a plain assertion as soon as the referenced backlog item is fixed (strict
mode turns a silent pass into a failure, forcing the marker's removal).
"""

import asyncio
import re
import socket

import httpx
import pytest

from tests.conftest import (
    BOT_USER_ID,
    DIALOG_CHAT_ID,
    DIALOG_USER_ID,
    bot_started_update,
    dm_message_created,
    group_message_created,
    message_callback,
)

GROUP_CHAT_ID = -559969187
ACCEPT_AFFIX = re.compile(r"^\(\d+/\d+\)\n")

# ═════════════════════════════════════════════════════════════════════════
# Inbound routing
# ═════════════════════════════════════════════════════════════════════════

class TestInboundRouting:
    """`_build_event` must classify a dialog as a DM and a chat as a group."""

    async def test_captured_dialog_routes_to_dm(self, make_adapter):
        """A captured dialog carries recipient.chat_id *and* chat_type=dialog.

        The document's normalisation table maps a dialog to
        ``recipient.user_id`` — the service ``chat_id`` must not turn it into a
        group.
        """
        a = make_adapter()
        event = await a._build_event(dm_message_created())

        assert event is not None
        assert event.source.chat_type == "dm"
        assert event.source.chat_id == f"user:{DIALOG_USER_ID}"
        assert event.source.user_id == str(DIALOG_USER_ID)

    async def test_dialog_without_chat_id_routes_to_dm(self, make_adapter):
        """A dialog recipient without chat_id (repo's own fixture shape)."""
        a = make_adapter()
        payload = dm_message_created()
        payload["message"]["recipient"] = {"chat_type": "dialog"}

        event = await a._build_event(payload)

        assert event is not None
        assert event.source.chat_type == "dm"
        assert event.source.chat_id == f"user:{DIALOG_USER_ID}"

    async def test_dialog_chat_type_wins_over_stray_chat_id(self, make_adapter):
        """Mixed payload: a `dialog` hint outranks an id from the chat object."""
        a = make_adapter()
        payload = dm_message_created()
        payload["message"]["recipient"] = {"chat_type": "dialog", "user_id": BOT_USER_ID}
        payload["chat"] = {"chat_id": DIALOG_CHAT_ID, "type": "chat"}

        event = await a._build_event(payload)

        assert event is not None
        assert event.source.chat_type == "dm"
        assert event.source.chat_id == f"user:{DIALOG_USER_ID}"

    async def test_missing_chat_fields_keep_the_dm_fallback(self, make_adapter):
        a = make_adapter()
        payload = dm_message_created()
        payload["message"]["recipient"] = {}
        payload["message"].pop("chat_id", None)

        event = await a._build_event(payload)

        assert event is not None
        assert event.source.chat_type == "dm"
        assert event.source.chat_id == f"user:{DIALOG_USER_ID}"

    async def test_group_update_routes_to_group(self, make_adapter):
        a = make_adapter(extra={"group_policy": "open"})
        event = await a._build_event(group_message_created())

        assert event is not None
        assert event.source.chat_type == "group"
        assert event.source.chat_id == f"chat:{GROUP_CHAT_ID}"

    async def test_bot_started_remembers_dm_mapping(self, make_adapter):
        a = make_adapter()
        event = await a._build_event(bot_started_update(payload="c42"))

        assert event is not None
        assert event.text == "/start c42"
        assert event.source.chat_id == f"user:{DIALOG_USER_ID}"
        assert a._dm_user_ids[str(DIALOG_CHAT_ID)] == str(DIALOG_USER_ID)

    async def test_blocked_user_produces_no_side_effects(self, make_adapter, max_api):
        """A non-allowlisted sender is dropped before any HTTP/media work."""
        a = make_adapter(extra={"allowed_users": ["99999"]})

        event = await a._build_event(dm_message_created())

        assert event is None
        assert max_api.requests == []

    async def test_duplicate_mid_is_deduped(self, make_adapter):
        a = make_adapter()
        first = await a._build_event(dm_message_created(mid="mid.dup"))
        second = await a._build_event(dm_message_created(mid="mid.dup"))

        assert first is not None
        assert second is None


def _group_callback(
    payload: str,
    *,
    chat_id: int = GROUP_CHAT_ID,
    user_id: int = DIALOG_USER_ID,
    mid: str = "mid.group.1",
) -> dict:
    """Captured `message_callback` shape, rewritten for a group chat.

    No live capture for the group variant exists; per the documented schema a
    chat/channel carries `chat_id` in `message.recipient` and no
    `chat_type: "dialog"`.
    """
    update = message_callback(payload, mid=mid, user_id=user_id)
    update["message"]["recipient"] = {
        "chat_id": chat_id,
        "type": "chat",
        "title": "Test Group",
    }
    return update


class TestCallbackRouting:
    """Button presses resolve against captured `message_callback` payloads."""

    async def test_unknown_prefix_is_ignored_without_side_effects(
        self, make_adapter, max_api
    ):
        a = make_adapter()

        result = await a._on_callback(message_callback("utm_view_6"))

        assert result is None
        assert max_api.requests == []

    async def test_callback_without_payload_is_ignored(self, make_adapter, max_api):
        a = make_adapter()
        payload = message_callback("")
        payload["callback"].pop("payload")

        assert await a._on_callback(payload) is None
        assert max_api.requests == []

    async def test_callback_without_user_is_ignored(self, make_adapter, max_api):
        a = make_adapter()
        payload = message_callback("model:pick:x:y")
        payload["callback"].pop("user")

        assert await a._on_callback(payload) is None
        assert max_api.requests == []

    async def test_captured_dialog_callback_replies_to_the_dialog(
        self, make_adapter, max_api, monkeypatch
    ):
        """An approval pressed in a captured dialog is acked in that dialog.

        `message.recipient.chat_id` here is the dialog's service id, not a
        group: the ack must address `user_id` and never a chat.
        """
        import tools.approval as approval_mod

        monkeypatch.setattr(approval_mod, "has_blocking_approval", lambda key: True)
        monkeypatch.setattr(
            approval_mod, "resolve_gateway_approval", lambda key, choice: 1
        )

        a = make_adapter()
        await a.send_exec_approval(
            f"user:{DIALOG_USER_ID}", command="rm -rf /", session_key="sess-1"
        )
        approval_id = _flat_button_payloads(
            max_api.json_body(max_api.calls("POST", "/messages")[0])
        )[0].split(":")[2]
        max_api.requests.clear()

        await a._on_callback(
            message_callback(f"exec:once:{approval_id}", mid="mid.bot.1")
        )

        ack = max_api.calls("POST", "/messages")[-1]
        assert max_api.params(ack) == {"user_id": str(DIALOG_USER_ID)}
        assert "chat_id" not in max_api.params(ack)
        assert "Approved (once)" in max_api.json_body(ack)["text"]

    async def test_captured_group_callback_replies_to_the_group(
        self, make_adapter, max_api, monkeypatch
    ):
        """The group counterpart: scope is chat:<id>, addressed by chat_id."""
        import tools.approval as approval_mod

        monkeypatch.setattr(approval_mod, "has_blocking_approval", lambda key: True)
        monkeypatch.setattr(
            approval_mod, "resolve_gateway_approval", lambda key, choice: 1
        )

        a = make_adapter()
        a._remember_interaction_owner(
            session_key="sess-1",
            chat_id=f"chat:{GROUP_CHAT_ID}",
            user_id=str(DIALOG_USER_ID),
        )
        result = await a.send_exec_approval(
            f"chat:{GROUP_CHAT_ID}", command="rm -rf /", session_key="sess-1"
        )
        assert result.success is True
        approval_id = _flat_button_payloads(
            max_api.json_body(max_api.calls("POST", "/messages")[0])
        )[0].split(":")[2]
        max_api.requests.clear()

        await a._on_callback(
            _group_callback(f"exec:once:{approval_id}", mid="mid.bot.1")
        )

        ack = max_api.calls("POST", "/messages")[-1]
        assert max_api.params(ack) == {"chat_id": str(GROUP_CHAT_ID)}

    async def test_captured_dialog_model_callback_reaches_picker_state(
        self, make_adapter, max_api
    ):
        """A dialog callback keys the picker state exactly as the sender stored it."""
        a = make_adapter()

        async def on_selected(chat_id, model_id, provider_slug):
            return "ok"

        a._model_picker_state[f"user:{DIALOG_USER_ID}"] = {
            "provider_msg_id": "mid-provider",
            "owner_user_id": str(DIALOG_USER_ID),
            "models": ["deepseek-v3"],
            "providers": [
                {"slug": "deepseek", "name": "DeepSeek", "models": ["deepseek-v3"]},
            ],
            "session_key": "test",
            "on_model_selected": on_selected,
            "current_model": "gpt-4",
            "current_provider": "openrouter",
        }

        await a._on_callback(
            message_callback("model:provider:deepseek", mid="mid-provider")
        )

        posts = max_api.calls("POST", "/messages")
        assert posts, "a dialog callback must reach the picker"
        assert max_api.params(posts[-1]) == {"user_id": str(DIALOG_USER_ID)}
        assert "chat_id" not in max_api.params(posts[-1])

    async def test_captured_group_model_callback_uses_group_scope(
        self, make_adapter, max_api
    ):
        a = make_adapter()

        async def on_selected(chat_id, model_id, provider_slug):
            return "ok"

        a._model_picker_state[f"chat:{GROUP_CHAT_ID}"] = {
            "provider_msg_id": "mid-provider",
            "owner_user_id": str(DIALOG_USER_ID),
            "models": ["deepseek-v3"],
            "providers": [
                {"slug": "deepseek", "name": "DeepSeek", "models": ["deepseek-v3"]},
            ],
            "session_key": "test",
            "on_model_selected": on_selected,
            "current_model": "gpt-4",
            "current_provider": "openrouter",
        }

        await a._on_callback(
            _group_callback("model:provider:deepseek", mid="mid-provider")
        )

        posts = max_api.calls("POST", "/messages")
        assert posts, "the group callback must reach the picker"
        assert max_api.params(posts[-1]) == {"chat_id": str(GROUP_CHAT_ID)}


# ═════════════════════════════════════════════════════════════════════════
# Outbound wire format
# ═════════════════════════════════════════════════════════════════════════

class TestSendWireFormat:
    """`send()` must address the right target and build the documented body."""

    async def test_dm_send_uses_user_id_param(self, make_adapter, max_api):
        a = make_adapter()

        result = await a.send(f"user:{DIALOG_USER_ID}", "hello")

        assert result.success is True
        assert result.message_id == "mid.bot.1"
        req = max_api.calls("POST", "/messages")[0]
        assert max_api.params(req) == {"user_id": str(DIALOG_USER_ID)}
        assert max_api.json_body(req) == {
            "text": "hello",
            "format": "markdown",
            "notify": True,
        }
        assert max_api.methods() == [("POST", "/messages")]

    async def test_group_send_uses_chat_id_param(self, make_adapter, max_api):
        a = make_adapter()

        await a.send(f"chat:{GROUP_CHAT_ID}", "hi group")

        req = max_api.calls("POST", "/messages")[0]
        assert max_api.params(req) == {"chat_id": str(GROUP_CHAT_ID)}
        assert "user_id" not in max_api.params(req)

    async def test_negative_plain_id_is_treated_as_group(self, make_adapter, max_api):
        a = make_adapter()

        await a.send(f"{GROUP_CHAT_ID}", "plain id")

        assert max_api.params(max_api.calls("POST", "/messages")[0]) == {
            "chat_id": str(GROUP_CHAT_ID)
        }

    async def test_dm_chat_id_is_mapped_to_user_id(self, make_adapter, max_api):
        """A remembered dialog ids map (chat_id → user_id) is honoured."""
        a = make_adapter()
        a._dm_user_ids["user:777"] = str(DIALOG_USER_ID)

        await a.send("user:777", "mapped")

        assert max_api.params(max_api.calls("POST", "/messages")[0]) == {
            "user_id": str(DIALOG_USER_ID)
        }

    async def test_reply_link_payload(self, make_adapter, max_api):
        a = make_adapter()

        await a.send(f"user:{DIALOG_USER_ID}", "re", reply_to="mid.42")

        assert max_api.json_body(max_api.calls("POST", "/messages")[0])["link"] == {
            "type": "REPLY",
            "mid": "mid.42",
        }

    async def test_markdown_table_is_converted_not_sent_raw(self, make_adapter, max_api):
        a = make_adapter()

        await a.send(f"user:{DIALOG_USER_ID}", "| A | B |\n|---|---|\n| 1 | 2 |")

        text = max_api.json_body(max_api.calls("POST", "/messages")[0])["text"]
        assert "|---|---|" not in text       # separator must not survive
        assert "<pre>" not in text          # no HTML tags
        assert "```" not in text            # no code fences
        assert "`| A   | B   |`" in text    # cell content is preserved
        assert "`| 1   | 2   |`" in text

    async def test_send_without_client_reports_error(self, make_adapter, max_api):
        a = make_adapter()
        a._http_client = None

        result = await a.send(f"user:{DIALOG_USER_ID}", "hello")

        assert result.success is False
        assert result.error == "Not connected"
        assert max_api.requests == []

    async def test_http_error_returns_failure_without_raising(self, make_adapter, max_api):
        max_api.route("POST", "/messages", 500, {"message": "boom"})
        a = make_adapter()

        result = await a.send(f"user:{DIALOG_USER_ID}", "hello")

        assert result.success is False
        assert result.error == "Send failed (see logs)"

    async def test_chunked_send_addresses_same_target_per_chunk(
        self, make_adapter, max_api
    ):
        a = make_adapter()

        result = await a.send(f"user:{DIALOG_USER_ID}", "a" * 7000)

        reqs = max_api.calls("POST", "/messages")
        assert len(reqs) == 2
        assert result.success is True
        for req in reqs:
            assert max_api.params(req) == {"user_id": str(DIALOG_USER_ID)}
            assert len(max_api.json_body(req)["text"]) <= 4000


class TestChunkingPreservation:
    """Every character of a chunk must survive the per-chunk prefixing step."""

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "CODE-02: `text[:3900 - len(prefix)]` truncates the tail of any "
            "chunk that is exactly at the split limit; 7800 input chars → 7788 "
            "chars on the wire. Fix in the CODE-02 task, then drop this marker."
        ),
    )
    async def test_prefixing_does_not_drop_chunk_content(self, make_adapter, max_api):
        a = make_adapter()
        content = "a" * 7800
        chunks = a._split_outbound_text(content)

        await a.send(f"user:{DIALOG_USER_ID}", content)

        on_wire = [max_api.json_body(r)["text"] for r in max_api.calls("POST", "/messages")]
        assert len(on_wire) == len(chunks)
        stripped = [ACCEPT_AFFIX.sub("", text) for text in on_wire]
        assert "".join(stripped) == "".join(chunks)

    async def test_chunk_count_and_limits(self, make_adapter, max_api):
        a = make_adapter()
        content = "\n\n".join(["x" * 3000, "y" * 3000])

        await a.send(f"user:{DIALOG_USER_ID}", content)

        on_wire = [max_api.json_body(r)["text"] for r in max_api.calls("POST", "/messages")]
        assert len(on_wire) == 2
        assert all(len(text) <= 4000 for text in on_wire)
        assert all(ACCEPT_AFFIX.match(text) for text in on_wire)

    async def test_short_content_is_sent_verbatim(self, make_adapter, max_api):
        a = make_adapter()

        await a.send(f"user:{DIALOG_USER_ID}", "just one line")

        assert len(max_api.calls("POST", "/messages")) == 1
        assert (
            max_api.json_body(max_api.calls("POST", "/messages")[0])["text"]
            == "just one line"
        )


# ═════════════════════════════════════════════════════════════════════════
# Streaming / edit throttling
# ═════════════════════════════════════════════════════════════════════════

class TestStreamingThrottleWire:
    """`edit_message` PUT payload, typing renewal and pending-edit handling."""

    async def test_edit_put_payload_and_typing_renewal(self, make_adapter, max_api):
        a = make_adapter()

        result = await a.edit_message(f"user:{DIALOG_USER_ID}", "mid-1", "hello")

        assert result.success is True
        put = max_api.calls("PUT", "/messages")[0]
        assert max_api.params(put) == {"message_id": "mid-1"}
        assert max_api.json_body(put) == {"text": "hello", "format": "markdown"}
        # MAX clears the typing indicator on edit — the adapter must renew it.
        assert ("POST", f"/chats/{DIALOG_USER_ID}/actions") in max_api.methods()

    async def test_second_rapid_edit_is_throttled_and_queued(self, make_adapter, max_api):
        a = make_adapter()

        await a.edit_message(f"user:{DIALOG_USER_ID}", "mid-1", "first")
        result = await a.edit_message(f"user:{DIALOG_USER_ID}", "mid-1", "second")

        assert result.success is True
        assert len(max_api.calls("PUT", "/messages")) == 1
        state = a._edit_states[a._edit_state_key(f"user:{DIALOG_USER_ID}", "mid-1")]
        assert state.pending_text == "second"

    async def test_finalize_always_reaches_the_wire(self, make_adapter, max_api):
        a = make_adapter()

        await a.edit_message(f"user:{DIALOG_USER_ID}", "mid-1", "first")
        await a.edit_message(f"user:{DIALOG_USER_ID}", "mid-1", "interim")
        result = await a.edit_message(
            f"user:{DIALOG_USER_ID}", "mid-1", "final", finalize=True
        )

        assert result.success is True
        puts = max_api.calls("PUT", "/messages")
        assert len(puts) == 2
        assert max_api.json_body(puts[-1])["text"] == "final"
        assert a._edit_state_key(f"user:{DIALOG_USER_ID}", "mid-1") not in a._edit_states

    async def test_throttled_edit_is_flushed_after_window(self, make_adapter, max_api):
        a = make_adapter()

        await a.edit_message(f"user:{DIALOG_USER_ID}", "mid-1", "first")
        await a.edit_message(f"user:{DIALOG_USER_ID}", "mid-1", "second")
        assert len(max_api.calls("PUT", "/messages")) == 1

        await asyncio.sleep(0.3)  # throttle window is 200 ms

        puts = max_api.calls("PUT", "/messages")
        assert len(puts) == 2
        assert max_api.json_body(puts[-1])["text"] == "second"

    async def test_edit_error_does_not_renew_typing(self, make_adapter, max_api):
        max_api.route("PUT", "/messages", 500, {"message": "boom"})
        a = make_adapter()

        result = await a.edit_message(f"user:{DIALOG_USER_ID}", "mid-1", "fail")

        assert result.success is False
        assert ("POST", f"/chats/{DIALOG_USER_ID}/actions") not in max_api.methods()


# ═════════════════════════════════════════════════════════════════════════
# Approval / confirmation callbacks
# ═════════════════════════════════════════════════════════════════════════

def _flat_button_payloads(body: dict) -> list[str]:
    return [
        button["payload"]
        for row in body["attachments"][0]["payload"]["buttons"]
        for button in row
    ]


class TestExecApproval:
    """Dangerous-command approval buttons route to tools.approval."""

    async def test_prompt_carries_four_exec_choices(self, make_adapter, max_api):
        a = make_adapter()

        result = await a.send_exec_approval(
            f"user:{DIALOG_USER_ID}",
            command="rm -rf /",
            session_key="sess-1",
            description="dangerous command",
        )

        assert result.success is True
        req = max_api.calls("POST", "/messages")[0]
        assert max_api.params(req) == {"user_id": str(DIALOG_USER_ID)}
        body = max_api.json_body(req)
        payloads = _flat_button_payloads(body)
        assert len(payloads) == 4
        approval_id = payloads[0].split(":")[2]
        assert {p.split(":")[1] for p in payloads} == {"once", "session", "always", "deny"}
        assert all(p.split(":")[2] == approval_id for p in payloads)
        record = a._exec_approval_state[approval_id]
        assert record["session_key"] == "sess-1"
        assert record["owner_user_id"] == str(DIALOG_USER_ID)
        assert record["chat_id"] == f"user:{DIALOG_USER_ID}"
        assert record["message_id"] == "mid.bot.1"

    async def test_owner_press_resolves_and_acks_on_the_wire(
        self, make_adapter, max_api, monkeypatch
    ):
        import tools.approval as approval_mod

        resolved: list[tuple[str, str]] = []
        monkeypatch.setattr(approval_mod, "has_blocking_approval", lambda key: True)
        monkeypatch.setattr(
            approval_mod,
            "resolve_gateway_approval",
            lambda key, choice: resolved.append((key, choice)) or 1,
        )

        a = make_adapter()
        await a.send_exec_approval(
            f"user:{DIALOG_USER_ID}", command="rm -rf /", session_key="sess-1"
        )
        approval_id = _flat_button_payloads(
            max_api.json_body(max_api.calls("POST", "/messages")[0])
        )[0].split(":")[2]
        max_api.requests.clear()

        event = await a._on_callback(
            message_callback(
                f"exec:once:{approval_id}", user_id=DIALOG_USER_ID, mid="mid.bot.1"
            )
        )

        assert event is None  # ack must not be injected into the AI context
        assert resolved == [("sess-1", "once")]
        assert approval_id not in a._exec_approval_state  # single use
        ack = max_api.calls("POST", "/messages")[-1]
        assert max_api.params(ack) == {"user_id": str(DIALOG_USER_ID)}
        assert "Approved (once)" in max_api.json_body(ack)["text"]

    async def test_unknown_approval_id_is_reported_without_resolving(
        self, make_adapter, max_api, monkeypatch
    ):
        import tools.approval as approval_mod

        called: list[tuple[str, str]] = []
        monkeypatch.setattr(approval_mod, "has_blocking_approval", lambda key: True)
        monkeypatch.setattr(
            approval_mod,
            "resolve_gateway_approval",
            lambda key, choice: called.append((key, choice)) or 1,
        )

        a = make_adapter()

        event = await a._on_callback(
            message_callback(f"exec:once:{'deadbeef'}", user_id=DIALOG_USER_ID)
        )

        assert event is None
        assert called == []
        ack = max_api.calls("POST", "/messages")[0]
        assert "already been resolved" in max_api.json_body(ack)["text"]

    async def test_no_pending_approval_is_reported(
        self, make_adapter, max_api, monkeypatch
    ):
        import tools.approval as approval_mod

        monkeypatch.setattr(approval_mod, "has_blocking_approval", lambda key: False)

        a = make_adapter()
        a._register_interaction(
            "exec", "abc123", session_key="sess-1",
            owner_user_id=str(DIALOG_USER_ID),
            chat_id=f"user:{DIALOG_USER_ID}", message_id="mid.dm.1",
        )

        await a._on_callback(
            message_callback("exec:once:abc123", user_id=DIALOG_USER_ID)
        )

        assert "No pending approval" in max_api.json_body(
            max_api.calls("POST", "/messages")[0]
        )["text"]

    async def test_foreign_user_cannot_resolve_someone_elses_approval(
        self, make_adapter, max_api, monkeypatch
    ):
        import tools.approval as approval_mod

        resolved: list[tuple[str, str]] = []
        monkeypatch.setattr(approval_mod, "has_blocking_approval", lambda key: True)
        monkeypatch.setattr(
            approval_mod,
            "resolve_gateway_approval",
            lambda key, choice: resolved.append((key, choice)) or 1,
        )

        a = make_adapter()
        await a.send_exec_approval(
            f"user:{DIALOG_USER_ID}", command="rm -rf /", session_key="sess-1"
        )
        approval_id = _flat_button_payloads(
            max_api.json_body(max_api.calls("POST", "/messages")[0])
        )[0].split(":")[2]
        max_api.requests.clear()

        await a._on_callback(
            message_callback(f"exec:once:{approval_id}", user_id=99999, mid="mid.bot.1")
        )

        assert resolved == []
        assert a._exec_approval_state[approval_id]["session_key"] == "sess-1"
        assert max_api.calls("POST", "/messages") == []


class TestSlashConfirmAndClarify:
    """Unknown ids must be no-ops — no resolve call, no message, no state leak."""

    async def test_unknown_slash_confirm_id_is_noop(self, make_adapter, max_api, monkeypatch):
        from tools import slash_confirm

        resolved: list[tuple] = []

        async def fake_resolve(session_key, confirm_id, choice):
            resolved.append((session_key, confirm_id, choice))
            return "should not happen"

        monkeypatch.setattr(slash_confirm, "resolve", fake_resolve)
        a = make_adapter()

        event = await a._on_callback(message_callback("sc:once:missing-id"))

        assert event is None
        assert resolved == []
        assert max_api.requests == []

    async def test_unknown_clarify_id_is_noop(self, make_adapter, max_api, monkeypatch):
        import tools.clarify_gateway as clarify_mod

        resolved: list[tuple] = []

        async def fake_resolve(clarify_id, response):
            resolved.append((clarify_id, response))
            return "should not happen"

        monkeypatch.setattr(clarify_mod, "resolve_gateway_clarify", fake_resolve)
        a = make_adapter()

        event = await a._on_callback(message_callback("clarify:missing-id:0"))

        assert event is None
        assert resolved == []
        assert max_api.requests == []


# ═════════════════════════════════════════════════════════════════════════
# Cross-platform session commands (/sessions, /resume)
# ═════════════════════════════════════════════════════════════════════════

SESSION_ROWS: list[dict] = [
    {"id": "abc123def456", "source": "cli", "title": "Dev session",
     "preview": "hello"},
    {"id": "999888777666", "source": "telegram", "title": "Other platform",
     "preview": "hi there"},
]


class _FakeSessionDB:
    """Stands in for hermes_state.SessionDB so tests never touch the real DB."""

    def list_sessions_rich(self, **kwargs):
        return list(SESSION_ROWS)


class TestCrossSessionCommands:
    """`/sessions` bypasses the core platform scoping — access must be gated."""

    @pytest.fixture(autouse=True)
    def _fake_session_db(self, monkeypatch):
        import hermes_state

        monkeypatch.setattr(hermes_state, "SessionDB", _FakeSessionDB)

    @staticmethod
    def _dialog_without_chat_id(text: str) -> dict:
        """Dialog update shaped as the repo's own fixture: no recipient.chat_id.

        Routing of the *captured* dialog payload (which does carry chat_id) is
        covered by `TestInboundRouting`; here the focus is access control and
        the reply payload, so the unambiguous dialog shape is used.
        """
        payload = dm_message_created(text=text)
        payload["message"]["recipient"].pop("chat_id")
        return payload

    async def test_allowlisted_user_gets_session_listing(self, make_adapter, max_api):
        a = make_adapter(extra={"allowed_users": [DIALOG_USER_ID], "cross_session": True})

        event = await a._build_event(self._dialog_without_chat_id("/sessions"))

        assert event is None  # handled in-place, not forwarded to the AI
        reqs = max_api.calls("POST", "/messages")
        assert len(reqs) == 2
        listing = max_api.json_body(reqs[0])["text"]
        assert "Recent Sessions" in listing
        assert "**cli**" in listing          # sessions from every platform
        assert "**telegram**" in listing
        assert "abc123def456"[:12] in listing  # session ids are exposed too
        assert max_api.params(reqs[0]) == {"user_id": str(DIALOG_USER_ID)}

    async def test_resume_without_args_lists_sessions(self, make_adapter, max_api):
        a = make_adapter(extra={"allowed_users": [DIALOG_USER_ID], "cross_session": True})

        event = await a._build_event(self._dialog_without_chat_id("/resume"))

        assert event is None
        assert len(max_api.calls("POST", "/messages")) == 2

    async def test_non_allowlisted_user_is_ignored(self, make_adapter, max_api):
        a = make_adapter(extra={"allowed_users": ["99999"]})

        event = await a._build_event(self._dialog_without_chat_id("/sessions"))

        assert event is None
        assert max_api.requests == []

    async def test_cross_session_disabled_ignores_command(self, make_adapter, max_api):
        a = make_adapter(
            extra={"allowed_users": [DIALOG_USER_ID], "cross_session": False}
        )

        event = await a._build_event(self._dialog_without_chat_id("/sessions"))

        assert event is not None
        assert event.text == "/sessions"
        assert max_api.requests == []

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "SEC-05: with allow_all_users=False and an EMPTY allowlist every user "
            "passes the access check, so an arbitrary user can run /sessions and "
            "read title/preview/IDs of sessions from every platform. Fix in the "
            "SEC-05 task, then drop this marker."
        ),
    )
    async def test_empty_allowlist_does_not_expose_all_sessions(
        self, make_adapter, max_api
    ):
        a = make_adapter()  # allow_all_users False, allowed_users []

        event = await a._build_event(self._dialog_without_chat_id("/sessions"))

        assert event is None
        assert max_api.calls("POST", "/messages") == []


# ═════════════════════════════════════════════════════════════════════════
# Lifecycle: connect / disconnect / reconnect
# ═════════════════════════════════════════════════════════════════════════

class TestLifecycle:
    """connect() must verify the token, then start polling; disconnect() cleans up."""

    async def test_connect_verifies_token_and_starts_polling(
        self, make_adapter, max_api, http_client_factory
    ):
        a = make_adapter()

        assert await a.connect() is True

        assert a.is_connected is True
        assert a.has_fatal_error is False
        me = max_api.calls("GET", "/me")[0]
        assert me.headers["Authorization"] == "test-token"
        kwargs = http_client_factory.calls[0]
        assert kwargs["headers"] == {"Authorization": "test-token"}
        assert kwargs["follow_redirects"] is False  # no token leak on redirect
        assert len(max_api.calls("PATCH", "/me/commands")) == 1
        assert a._poll_task is not None

        await a.disconnect()

        assert a._http_client is None
        assert a._poll_task is None
        assert a._background_tasks == set()

    async def test_stale_subscription_is_cleaned_in_polling_mode(
        self, make_adapter, max_api, http_client_factory
    ):
        max_api.route(
            "GET", "/subscriptions", 200,
            {"subscriptions": [{"url": "https://old.example.com/max/webhook"}]},
        )
        max_api.route("DELETE", "/subscriptions", 200, {"success": True})
        a = make_adapter()

        assert await a.connect() is True

        deletes = [r for r in max_api.requests if r.method == "DELETE"]
        assert len(deletes) == 1
        assert "old.example.com" in str(deletes[0].url)
        await a.disconnect()

    async def test_invalid_token_is_fatal_and_leaks_no_client(
        self, make_adapter, max_api, http_client_factory
    ):
        max_api.route("GET", "/me", 401, {})
        a = make_adapter()

        assert await a.connect() is False

        assert a.has_fatal_error is True
        assert a.fatal_error_code == "invalid_token"
        assert a.fatal_error_retryable is False
        assert a._http_client is None            # closed, not leaked
        assert max_api.calls("PATCH", "/me/commands") == []
        assert a._poll_task is None

    async def test_transport_failure_is_retryable_and_leaks_no_client(
        self, make_adapter, max_api, http_client_factory
    ):
        max_api.fail("GET", "/me", httpx.ConnectError("boom"))
        a = make_adapter()

        assert await a.connect() is False

        assert a.fatal_error_code == "conn_fail"
        assert a.fatal_error_retryable is True
        assert a._http_client is None

    async def test_connect_disconnect_connect_is_clean(
        self, make_adapter, max_api, http_client_factory
    ):
        a = make_adapter()

        assert await a.connect() is True
        await a.disconnect()
        assert await a.connect() is True

        assert a.is_connected is True
        assert a._http_client is not None
        assert a._poll_task is not None
        assert not a._poll_task.done()
        assert any(not t.done() for t in a._background_tasks)

        await a.disconnect()
        assert a._poll_task is None
        assert a._http_client is None
        assert a._background_tasks == set()


# ═════════════════════════════════════════════════════════════════════════
# Long polling
# ═════════════════════════════════════════════════════════════════════════

class TestPolling:
    """`_poll_loop` must drain /updates into the internal queue and page by marker."""

    async def test_update_is_queued_with_original_text(self, make_adapter, max_api):
        max_api.route(
            "GET", "/updates", 200,
            {"updates": [dm_message_created(text="hello poll")], "marker": 0},
        )
        a = make_adapter()
        a._stop.clear()

        task = asyncio.create_task(a._poll_loop())
        try:
            event = await asyncio.wait_for(a._message_queue.get(), timeout=2)
        finally:
            a._stop.set()
            await asyncio.wait_for(task, timeout=2)

        assert event.text == "hello poll"
        assert event.message_id == "mid.dm.1"
        params = max_api.params(max_api.calls("GET", "/updates")[0])
        assert params == {"timeout": "5", "limit": "100"}

    async def test_marker_is_sent_on_the_next_page(self, make_adapter, max_api):
        max_api.route(
            "GET", "/updates", 200,
            {"updates": [dm_message_created(text="page one")], "marker": 777},
        )
        a = make_adapter()
        a._stop.clear()

        task = asyncio.create_task(a._poll_loop())
        try:
            await asyncio.wait_for(a._message_queue.get(), timeout=2)
            for _ in range(50):
                if len(max_api.calls("GET", "/updates")) >= 2:
                    break
                await asyncio.sleep(0)
        finally:
            a._stop.set()
            await asyncio.wait_for(task, timeout=2)

        assert len(max_api.calls("GET", "/updates")) >= 2
        assert max_api.params(max_api.calls("GET", "/updates")[1])["marker"] == "777"

    async def test_http_error_does_not_kill_the_loop(self, make_adapter, max_api, monkeypatch):
        import adapter

        async def no_sleep(_delay):
            return None

        monkeypatch.setattr(adapter, "_poll_sleep", no_sleep)
        calls = {"n": 0}

        def flaky(request):
            calls["n"] += 1
            if calls["n"] == 1:
                return 500, {"message": "server error"}
            return 200, {
                "updates": [dm_message_created(text="recovered")],
                "marker": 0,
            }

        max_api.route("GET", "/updates", 500, flaky)
        a = make_adapter()
        a._stop.clear()

        task = asyncio.create_task(a._poll_loop())
        try:
            event = await asyncio.wait_for(a._message_queue.get(), timeout=2)
        finally:
            a._stop.set()
            await asyncio.wait_for(task, timeout=2)

        assert event.text == "recovered"


# ═════════════════════════════════════════════════════════════════════════
# Webhook server
# ═════════════════════════════════════════════════════════════════════════

def _free_loopback_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class TestWebhook:
    """Real aiohttp server on loopback: secret handling and event queueing."""

    @pytest.fixture
    def webhook_adapter(self, make_adapter):
        def _make(secret: str | None = None):
            port = _free_loopback_port()
            extra = {"host": "127.0.0.1", "port": port, "path": "/max/webhook"}
            if secret is not None:
                extra["webhook_secret"] = secret
            a = make_adapter(extra=extra, _running=False)
            a._webhook_port = port

            # The HTTP surface is what's under test here, not the queue pump:
            # neutralise it so events stay in `_message_queue` for assertions
            # (otherwise `handle_message` drains them and needs a gateway).
            async def _no_pump() -> None:
                return None

            a._queue_poll_loop = _no_pump
            return a, port

        return _make

    async def test_valid_secret_accepts_and_queues(self, webhook_adapter):
        a, port = webhook_adapter(secret="s3cr3t")
        assert await a._start_webhook() is True
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"http://127.0.0.1:{port}/max/webhook",
                    json=dm_message_created(text="from webhook"),
                    headers={"X-Max-Bot-Api-Secret": "s3cr3t"},
                )
                assert resp.status_code == 200

                health = await client.get(f"http://127.0.0.1:{port}/health")
                assert health.status_code == 200
                assert health.json() == {"status": "ok"}

            event = await asyncio.wait_for(a._message_queue.get(), timeout=2)
            assert event.text == "from webhook"
            assert event.message_id == "mid.dm.1"
        finally:
            await a.disconnect()

    async def test_wrong_secret_is_rejected_and_not_queued(self, webhook_adapter):
        a, port = webhook_adapter(secret="s3cr3t")
        assert await a._start_webhook() is True
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"http://127.0.0.1:{port}/max/webhook",
                    json=dm_message_created(),
                    headers={"X-Max-Bot-Api-Secret": "wrong"},
                )
                assert resp.status_code == 403
                missing = await client.post(
                    f"http://127.0.0.1:{port}/max/webhook",
                    json=dm_message_created(),
                )
                assert missing.status_code == 403

            assert a._message_queue.empty()
        finally:
            await a.disconnect()

    async def test_invalid_json_is_rejected(self, webhook_adapter):
        a, port = webhook_adapter(secret="s3cr3t")
        assert await a._start_webhook() is True
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"http://127.0.0.1:{port}/max/webhook",
                    content=b"{not json",
                    headers={
                        "X-Max-Bot-Api-Secret": "s3cr3t",
                        "Content-Type": "application/json",
                    },
                )
                assert resp.status_code == 400
            assert a._message_queue.empty()
        finally:
            await a.disconnect()

    async def test_missing_secret_fails_closed(self, webhook_adapter):
        a, port = webhook_adapter(secret=None)
        assert await a._start_webhook() is True
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"http://127.0.0.1:{port}/max/webhook",
                    json=dm_message_created(),
                )
                # A secretless loopback endpoint is development-only and must
                # fail closed for every request; 503 signals misconfiguration.
                assert resp.status_code == 503
            assert a._message_queue.empty()
        finally:
            await a.disconnect()
