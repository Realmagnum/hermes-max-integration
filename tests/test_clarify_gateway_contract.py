"""Native MAX clarify callbacks against the installed Core gateway registry."""

import inspect
from unittest.mock import AsyncMock, MagicMock

import pytest
from tools import clarify_gateway as core
from tools.clarify_tool import clarify_tool

import adapter


def make_adapter():
    from gateway.config import PlatformConfig

    a = adapter.MaxAdapter(PlatformConfig(
        enabled=True, token="test-token", extra={"token": "test-token", "allow_all_users": True, "group_policy": "open"},
    ))
    a._http_client = AsyncMock()
    response = MagicMock(status_code=200)
    response.json.return_value = {"message": {"body": {"mid": "card-1"}}}
    a._http_client.post = AsyncMock(return_value=response)
    a.send = AsyncMock()
    return a


def callback(option, *, user=42, mid="card-1", chat=777, clarify_id="q-a"):
    return {
        "update_type": "message_callback",
        "callback": {"payload": f"clarify:{clarify_id}:{option}", "user": {"user_id": user}},
        "message": {"recipient": {"chat_id": chat, "chat_type": "chat"}, "body": {"mid": mid}},
    }


@pytest.fixture(autouse=True)
def clean_core_queue():
    for session in ("session-a", "session-b"):
        core.clear_session(session)
    yield
    for session in ("session-a", "session-b"):
        core.clear_session(session)


@pytest.mark.asyncio
async def test_offered_label_resolves_once_in_own_session_without_second_turn():
    a = make_adapter()
    core.register("q-a", "session-a", "Choose", ["Alpha (Recommended)", "Beta"])
    core.register("q-b", "session-b", "Choose", ["Other session"])
    result = await a.send_clarify("chat:777", "Choose", ["Alpha (Recommended)", "Beta"],
                                  "q-a", "session-a", metadata={"user_id": "42"})
    assert result.success and a._clarify_state["q-a"]["message_id"] == "card-1"
    buttons = a._http_client.post.call_args.kwargs["json"]["attachments"][0]["payload"]["buttons"]
    assert [len(row) for row in buttons] == [1, 1, 1]
    assert [b["payload"] for row in buttons for b in row] == [
        "clarify:q-a:0", "clarify:q-a:1", "clarify:q-a:other",
    ]
    for rejected in (callback("1", user=99), callback("1", chat=778),
                     callback("1", mid="old"), callback("99"), callback("garbage")):
        assert await a._on_callback(rejected) is None
        assert core.get_pending_for_session("session-a", include_choice_prompts=True).response is None
    assert await a._on_callback(callback("1")) is None
    assert core.wait_for_response("q-a", 0.01) == "Beta"
    assert core.get_pending_for_session("session-b", include_choice_prompts=True).response is None
    assert await a._on_callback(callback("0")) is None
    a.send.assert_not_awaited()
    assert "q-a" not in a._clarify_state


@pytest.mark.asyncio
async def test_other_arms_core_text_interception_and_replay_does_not_resolve():
    a = make_adapter()
    core.register("q-a", "session-a", "Choose", ["Alpha"])
    await a.send_clarify("chat:777", "Choose", ["Alpha"], "q-a", "session-a",
                         metadata={"user_id": "42"})
    await a._on_callback(callback("other", user=99))
    assert not core.get_pending_for_session("session-a", include_choice_prompts=True).awaiting_text
    await a._on_callback(callback("other"))
    assert core.get_pending_for_session("session-a").awaiting_text
    await a._on_callback(callback("0"))
    assert core.get_pending_for_session("session-a").response is None
    assert core.attempt_text_response_for_session("session-b", "custom") == core.TEXT_NO_PENDING
    assert core.attempt_text_response_for_session("session-a", "custom") == core.TEXT_RESOLVED
    assert core.wait_for_response("q-a", 0.01) == "custom"


@pytest.mark.asyncio
async def test_expired_core_question_and_failed_send_cannot_resolve_card():
    a = make_adapter()
    core.register("q-a", "session-a", "Choose", ["Alpha"])
    await a.send_clarify("chat:777", "Choose", ["Alpha"], "q-a", "session-a",
                         metadata={"user_id": "42"})
    assert core.wait_for_response("q-a", 0.01) is None
    await a._on_callback(callback("0"))
    assert "q-a" not in a._clarify_state

    a._http_client.post.side_effect = RuntimeError("send failed")
    core.register("q-b", "session-b", "Choose", ["Alpha"])
    result = await a.send_clarify("chat:777", "Choose", ["Alpha"], "q-b", "session-b",
                                  metadata={"user_id": "42"})
    assert not result.success
    assert "q-b" not in a._clarify_state


@pytest.mark.asyncio
async def test_open_ended_uses_core_text_queue_and_tool_result():
    a = make_adapter()
    core.register("q-a", "session-a", "Where?", None)
    await a.send_clarify("chat:777", "Where?", None, "q-a", "session-a",
                         metadata={"user_id": "42"})
    assert "q-a" not in a._clarify_state
    assert core.get_pending_for_session("session-a").awaiting_text
    assert core.attempt_text_response_for_session("session-a", "at home") == core.TEXT_RESOLVED
    assert core.wait_for_response("q-a", 0.01) == "at home"
    if "question" in inspect.signature(clarify_tool).parameters:
        # Released minimum/baseline Core accepts one question and a string result.
        result = clarify_tool("Pick", choices=["One", "Two"],
                              callback=lambda question, choices, **kwargs: "Two")
    else:
        # Later Core accepts a question batch and its structured answer envelope.
        result = clarify_tool([{"question": "Pick", "choices": ["One", "Two"]}],
                              callback=lambda questions: {"answers": {"q0": "Two"}, "outcome": "submitted"})
    assert '"user_response": "Two"' in result
