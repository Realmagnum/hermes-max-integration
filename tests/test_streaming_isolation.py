"""CODE-03: streaming edit isolation and flush.

Regression suite for the adapter-wide streaming throttle. On the audit base
(`b004c573`) `_last_edit_at`/`_pending_edit` lived on the adapter, so:

* two chats streaming at the same time shared one slot — the first PUT of chat
  B was swallowed because chat A had just edited (one PUT for two chats), and
* a throttled edit was stored but never delivered, because nothing flushed it.

These tests pin the acceptance criteria from BACKLOG.md CODE-03: per-message
state, guaranteed flush/finalize, correct timer cancellation, and the
concurrent-chat / last-throttled-edit cases.
"""

import asyncio
import contextlib
from unittest.mock import AsyncMock, MagicMock

import pytest

import adapter

THROTTLE = 0.05


def _make_adapter(throttle: float | None = THROTTLE):
    """Adapter with a mocked HTTP client and a short, deterministic throttle."""
    from gateway.config import PlatformConfig

    cfg = PlatformConfig(enabled=True, token="test-token", extra={"token": "test-token"})
    a = adapter.MaxAdapter(cfg)
    if throttle is not None:
        a._edit_throttle = throttle
    a._http_client = AsyncMock()
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {}
    a._http_client.put = AsyncMock(return_value=resp)
    a.send_typing = AsyncMock()
    return a


@pytest.fixture
async def adapters():
    """Track adapters built by a test and join/cancel their flush timers."""
    created: list = []
    yield created

    for a in created:
        tasks = [
            st.flush_task
            for st in a._edit_states.values()
            if st.flush_task is not None and not st.flush_task.done()
        ]
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        a._edit_states.clear()


def _build(registry) -> "adapter.MaxAdapter":
    a = _make_adapter()
    registry.append(a)
    return a


def _put_message_ids(client) -> list[str]:
    """message_id params of every PUT the adapter performed, in order."""
    return [call.kwargs["params"]["message_id"] for call in client.put.call_args_list]


def _put_texts(client) -> list[str]:
    return [call.kwargs["json"]["text"] for call in client.put.call_args_list]


class TestConcurrentChats:
    """State is per (chat_id, message_id), not per adapter."""

    @pytest.mark.asyncio
    async def test_two_concurrent_chats_each_get_a_put(self, adapters):
        """The regression: chat B's first edit must not consume chat A's slot."""
        a = _build(adapters)

        r1 = await a.edit_message("user:1", "mid-A", "chat A start")
        r2 = await a.edit_message("user:2", "mid-B", "chat B start")

        assert r1.success is True and r2.success is True
        assert a._http_client.put.call_count == 2, "each chat needs its own PUT"
        assert _put_message_ids(a._http_client) == ["mid-A", "mid-B"]

    @pytest.mark.asyncio
    async def test_interleaved_streams_do_not_suppress_each_other(self, adapters):
        a = _build(adapters)

        # Both chats stream in the same 50ms window, alternating.
        for text in ("A1", "B1", "A2", "B2"):
            chat, mid = ("user:1", "mid-A") if text.startswith("A") else ("user:2", "mid-B")
            result = await a.edit_message(chat, mid, text)
            assert result.success is True

        # Two immediate PUTs (one per chat) + two throttled calls queued.
        assert a._http_client.put.call_count == 2
        assert _put_message_ids(a._http_client) == ["mid-A", "mid-B"]

        # Both queued edits are delivered by their own timers.
        await asyncio.sleep(THROTTLE * 3)
        assert a._http_client.put.call_count == 4
        assert sorted(_put_texts(a._http_client)) == ["A1", "A2", "B1", "B2"]

    @pytest.mark.asyncio
    async def test_typing_renewed_for_the_owning_chat_only(self, adapters):
        a = _build(adapters)
        await a.edit_message("user:1", "mid-A", "A")
        await a.edit_message("user:2", "mid-B", "B")
        assert [c.args[0] for c in a.send_typing.call_args_list] == ["user:1", "user:2"]

    @pytest.mark.asyncio
    async def test_two_messages_in_one_chat_are_independent(self, adapters):
        a = _build(adapters)
        await a.edit_message("user:1", "mid-1", "first")
        await a.edit_message("user:1", "mid-2", "second")
        assert _put_message_ids(a._http_client) == ["mid-1", "mid-2"]


class TestFlush:
    """A throttled edit is queued and later delivered — never silently lost."""

    @pytest.mark.asyncio
    async def test_last_throttled_edit_is_flushed(self, adapters):
        a = _build(adapters)

        await a.edit_message("user:1", "mid-A", "part 1")
        assert a._http_client.put.call_count == 1

        # Three rapid calls inside the window; only the last content matters.
        for text in ("part 2", "part 3", "part 4"):
            await a.edit_message("user:1", "mid-A", text)
        assert a._http_client.put.call_count == 1, "still inside the throttle window"

        await asyncio.sleep(THROTTLE * 2)

        assert a._http_client.put.call_count == 2, "queued content must be flushed"
        assert _put_texts(a._http_client) == ["part 1", "part 4"]

    @pytest.mark.asyncio
    async def test_flush_delivers_pending_once_only(self, adapters):
        a = _build(adapters)
        await a.edit_message("user:1", "mid-A", "first")
        await a.edit_message("user:1", "mid-A", "second")
        await asyncio.sleep(THROTTLE * 3)
        assert a._http_client.put.call_count == 2
        assert a._edit_states[adapter.MaxAdapter._edit_state_key("user:1", "mid-A")].pending_text is None

    @pytest.mark.asyncio
    async def test_flush_retries_while_new_pending_arrives(self, adapters):
        a = _build(adapters)
        await a.edit_message("user:1", "mid-A", "first")
        # Queue, then queue again before the window expires.
        await a.edit_message("user:1", "mid-A", "second")
        await asyncio.sleep(THROTTLE * 0.5)
        await a.edit_message("user:1", "mid-A", "third")
        await asyncio.sleep(THROTTLE * 3)
        # Intermediate content is coalesced — only the newest text is sent.
        assert _put_texts(a._http_client) == ["first", "third"]

    @pytest.mark.asyncio
    async def test_newer_throttled_edit_cancels_previous_timer(self, adapters):
        a = _build(adapters)
        await a.edit_message("user:1", "mid-A", "first")
        await a.edit_message("user:1", "mid-A", "second")
        key = adapter.MaxAdapter._edit_state_key("user:1", "mid-A")
        first_timer = a._edit_states[key].flush_task

        await a.edit_message("user:1", "mid-A", "third")
        await asyncio.sleep(0)  # let the cancellation land
        assert first_timer.cancelled() or first_timer.done()
        assert a._edit_states[key].flush_task is not first_timer

        await asyncio.sleep(THROTTLE * 2)
        assert _put_texts(a._http_client)[-1] == "third"

    @pytest.mark.asyncio
    async def test_no_flush_timer_after_window_has_passed(self, adapters):
        """A call outside the window sends immediately and queues nothing."""
        a = _build(adapters)
        await a.edit_message("user:1", "mid-A", "first")
        await asyncio.sleep(THROTTLE * 2)
        await a.edit_message("user:1", "mid-A", "second")
        assert a._http_client.put.call_count == 2
        key = adapter.MaxAdapter._edit_state_key("user:1", "mid-A")
        assert a._edit_states[key].flush_task is None
        assert a._edit_states[key].pending_text is None


class TestFinalize:
    """finalize=True always sends and releases per-message state."""

    @pytest.mark.asyncio
    async def test_finalize_bypasses_throttle(self, adapters):
        a = _build(adapters)
        await a.edit_message("user:1", "mid-A", "streaming")
        result = await a.edit_message("user:1", "mid-A", "final answer", finalize=True)
        assert result.success is True
        assert a._http_client.put.call_count == 2
        assert _put_texts(a._http_client)[-1] == "final answer"

    @pytest.mark.asyncio
    async def test_finalize_cancels_pending_timer_and_drops_state(self, adapters):
        a = _build(adapters)
        await a.edit_message("user:1", "mid-A", "first")
        await a.edit_message("user:1", "mid-A", "queued")
        key = adapter.MaxAdapter._edit_state_key("user:1", "mid-A")
        timer = a._edit_states[key].flush_task

        await a.edit_message("user:1", "mid-A", "the end", finalize=True)
        await asyncio.sleep(0)  # let the cancellation land

        assert timer.cancelled() or timer.done()
        assert key not in a._edit_states, "finished stream must release its state"
        await asyncio.sleep(THROTTLE * 2)
        assert a._http_client.put.call_count == 2, "queued content must not leak after finalize"

    @pytest.mark.asyncio
    async def test_finalize_does_not_touch_other_chat(self, adapters):
        a = _build(adapters)
        await a.edit_message("user:1", "mid-A", "A")
        await a.edit_message("user:2", "mid-B", "B")
        await a.edit_message("user:1", "mid-A", "A done", finalize=True)

        key_b = adapter.MaxAdapter._edit_state_key("user:2", "mid-B")
        assert key_b in a._edit_states, "chat B's stream is still live"

    @pytest.mark.asyncio
    async def test_edit_after_finalize_starts_a_fresh_stream(self, adapters):
        a = _build(adapters)
        await a.edit_message("user:1", "mid-A", "one", finalize=True)
        # Immediately after finalize the throttle must not block a new stream.
        result = await a.edit_message("user:1", "mid-A", "two")
        assert result.success is True
        assert a._http_client.put.call_count == 2


class TestLifecycle:
    """Timers are cancelled when the adapter shuts down."""

    @pytest.mark.asyncio
    async def test_disconnect_cancels_flush_timers(self, adapters):
        a = _build(adapters)
        a._poll_task = None
        a._webhook_runner = None
        a._http_client.aclose = AsyncMock()
        a._mark_disconnected = MagicMock()

        await a.edit_message("user:1", "mid-A", "first")
        await a.edit_message("user:1", "mid-A", "queued")
        timers = [st.flush_task for st in a._edit_states.values()]
        assert timers and all(t is not None for t in timers)

        await a.disconnect()
        await asyncio.sleep(0)  # let the cancellations land

        assert a._edit_states == {}
        assert all(t.cancelled() or t.done() for t in timers)

    @pytest.mark.asyncio
    async def test_not_connected_is_reported(self, adapters):
        a = _build(adapters)
        a._http_client = None
        result = await a.edit_message("user:1", "mid-A", "x")
        assert result.success is False
        assert a._edit_states == {}


class TestStateBounds:
    """Per-message state cannot grow without bound on a long-lived adapter."""

    @pytest.mark.asyncio
    async def test_state_map_stays_bounded(self, adapters, monkeypatch):
        monkeypatch.setattr(adapter, "EDIT_STATES_MAX", 8)
        a = _build(adapters)
        for i in range(40):
            await a.edit_message("user:1", f"mid-{i}", f"text {i}")
        assert len(a._edit_states) <= 8

    @pytest.mark.asyncio
    async def test_prune_never_drops_queued_content(self, adapters, monkeypatch):
        monkeypatch.setattr(adapter, "EDIT_STATES_MAX", 4)
        a = _build(adapters)
        await a.edit_message("user:1", "live", "first")
        await a.edit_message("user:1", "live", "queued")

        # Churn other messages so pruning runs while "live" has a live timer.
        for i in range(20):
            await a.edit_message("user:1", f"mid-{i}", f"text {i}")

        key = adapter.MaxAdapter._edit_state_key("user:1", "live")
        assert key in a._edit_states
        assert a._edit_states[key].pending_text == "queued"

        await asyncio.sleep(THROTTLE * 3)
        assert "queued" in _put_texts(a._http_client)


class TestThrottleConfig:
    """The window is configurable so deployments can tune API pressure."""

    def test_default_window(self):
        a = _make_adapter(throttle=None)
        assert a._edit_throttle == pytest.approx(adapter.EDIT_THROTTLE_SECONDS)

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("MAX_EDIT_THROTTLE", "1.5")
        a = _make_adapter(throttle=None)
        assert a._edit_throttle == pytest.approx(1.5)

    def test_invalid_env_falls_back(self, monkeypatch):
        monkeypatch.setenv("MAX_EDIT_THROTTLE", "not-a-number")
        a = _make_adapter(throttle=None)
        assert a._edit_throttle == pytest.approx(adapter.EDIT_THROTTLE_SECONDS)
