"""CODE-08 regression tests: backpressure and dedup.

Covers the four acceptance points of CODE-08:
  * bounded ingress queue (hard cap, never blocks the producer)
  * bounded handler concurrency
  * hard-capped dedup table (cap holds even when every entry is fresh)
  * explicit overload policy plus observable metrics
"""

import asyncio
import socket
import time

import pytest

import adapter


def make_adapter(**extra):
    """Build a MaxAdapter with the given `extra` config."""
    from gateway.config import PlatformConfig

    cfg = PlatformConfig(
        enabled=True,
        token="test-token",
        extra={"token": "test-token", **extra},
    )
    return adapter.MaxAdapter(cfg)


def dm_update(mid, text="hi"):
    return {
        "update_type": "message_created",
        "message": {
            "sender": {"user_id": 42, "name": "Test User"},
            "recipient": {"chat_type": "dialog"},
            "body": {"mid": mid, "text": text},
        },
    }


async def wait_until_idle(a, timeout=5.0):
    """Wait until the queue is empty and no handler task is in flight."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if a._message_queue.empty() and not a._background_tasks:
            return True
        await asyncio.sleep(0.005)
    return False


class TestQueueBounds:
    """The ingress queue has a hard, configurable cap."""

    def test_default_cap(self):
        a = make_adapter()
        assert a._message_queue.maxsize == adapter.DEFAULT_QUEUE_MAXSIZE
        assert a.backpressure_stats()["queue_maxsize"] == adapter.DEFAULT_QUEUE_MAXSIZE

    def test_cap_from_extra(self):
        a = make_adapter(queue_maxsize=3)
        assert a._message_queue.maxsize == 3

    def test_cap_from_env(self, monkeypatch):
        monkeypatch.setenv("MAX_QUEUE_MAXSIZE", "7")
        a = make_adapter()
        assert a._message_queue.maxsize == 7

    def test_invalid_cap_falls_back(self):
        a = make_adapter(queue_maxsize="not-a-number")
        assert a._message_queue.maxsize == adapter.DEFAULT_QUEUE_MAXSIZE

    def test_cap_never_below_one(self):
        a = make_adapter(queue_maxsize=0)
        assert a._message_queue.maxsize == 1


class TestOverloadPolicy:
    """Overload is explicit, non-blocking and counted."""

    def test_drop_oldest_keeps_freshest(self):
        a = make_adapter(queue_maxsize=2)
        assert a._overload_policy == adapter.OVERLOAD_DROP_OLDEST

        assert a._enqueue_event("e1") is True
        assert a._enqueue_event("e2") is True
        # Queue full: the oldest event is evicted, the newest is kept.
        assert a._enqueue_event("e3") is True

        assert a._message_queue.qsize() == 2
        assert list(a._message_queue._queue) == ["e2", "e3"]
        stats = a.backpressure_stats()
        assert stats["dropped_oldest"] == 1
        assert stats["dropped_newest"] == 0
        assert stats["enqueued"] == 3
        assert stats["queue_peak"] == 2

    def test_drop_newest_rejects_ingress(self):
        a = make_adapter(queue_maxsize=2, overload_policy="drop_newest")
        assert a._enqueue_event("e1") is True
        assert a._enqueue_event("e2") is True
        # Queue full: the incoming event is rejected, backlog is untouched.
        assert a._enqueue_event("e3") is False

        assert list(a._message_queue._queue) == ["e1", "e2"]
        stats = a.backpressure_stats()
        assert stats["dropped_newest"] == 1
        assert stats["dropped_oldest"] == 0
        assert stats["enqueued"] == 2

    def test_unknown_policy_falls_back_to_drop_oldest(self):
        a = make_adapter(overload_policy="explode")
        assert a._overload_policy == adapter.OVERLOAD_DROP_OLDEST

    def test_sustained_burst_never_exceeds_cap(self):
        a = make_adapter(queue_maxsize=10)
        accepted = sum(a._enqueue_event(f"e{i}") for i in range(1000))

        assert accepted == 1000  # drop_oldest always makes room
        assert a._message_queue.qsize() == 10
        stats = a.backpressure_stats()
        assert stats["dropped_oldest"] == 990
        assert stats["queue_depth"] == 10
        assert stats["queue_peak"] == 10


class TestDedupHardCap:
    """The dedup table is TTL-bounded and hard-capped."""

    def test_fresh_burst_respects_cap(self):
        a = make_adapter(dedup_max=5)
        now = time.time()
        for i in range(200):
            a._remember_mid(f"m{i}", now)  # all entries fresh — no TTL help

        assert len(a._seen_msgs) == 5
        assert a.backpressure_stats()["dedup_entries"] == 5
        assert "m199" in a._seen_msgs
        assert "m0" not in a._seen_msgs  # oldest evicted FIFO

    def test_expired_entries_pruned_first(self):
        a = make_adapter(dedup_max=3)
        old = time.time() - a._DEDUP_TTL - 10
        for i in range(3):
            a._remember_mid(f"old{i}", old)

        a._remember_mid("fresh", time.time())

        assert set(a._seen_msgs) == {"fresh"}

    def test_ttl_window(self):
        a = make_adapter()
        now = time.time()
        a._remember_mid("dup", now)

        assert a._is_duplicate("dup", now + 1) is True
        assert a._is_duplicate("dup", now + a._DEDUP_TTL + 1) is False
        assert a._is_duplicate("unknown", now) is False

    def test_ttl_configurable(self):
        a = make_adapter(dedup_ttl=10)
        now = time.time()
        a._remember_mid("dup", now)
        assert a._is_duplicate("dup", now + 11) is False

    @pytest.mark.asyncio
    async def test_duplicate_update_dropped_and_counted(self):
        a = make_adapter()
        update = dm_update("mid-dup")

        assert await a._build_event(update) is not None
        assert await a._build_event(update) is None
        assert a.backpressure_stats()["duplicate_suppressed"] == 1

    @pytest.mark.asyncio
    async def test_distinct_updates_pass(self):
        a = make_adapter()
        assert await a._build_event(dm_update("mid-a")) is not None
        assert await a._build_event(dm_update("mid-b")) is not None
        assert a.backpressure_stats()["duplicate_suppressed"] == 0


class TestConcurrencyBound:
    """Handler concurrency is capped; the queue drains with that cap."""

    @pytest.mark.asyncio
    async def test_peak_concurrency_respects_cap(self):
        a = make_adapter(max_concurrency=2)
        a._running = True
        state = {"active": 0, "peak": 0, "done": 0}

        async def fake_handle(event):
            state["active"] += 1
            state["peak"] = max(state["peak"], state["active"])
            await asyncio.sleep(0.02)
            state["active"] -= 1
            state["done"] += 1

        a.handle_message = fake_handle
        for i in range(12):
            a._enqueue_event(f"e{i}")

        loop_task = asyncio.create_task(a._queue_poll_loop())
        try:
            assert await wait_until_idle(a) is True
        finally:
            a._running = False
            loop_task.cancel()
            try:
                await loop_task
            except asyncio.CancelledError:
                pass

        assert state["done"] == 12
        assert state["peak"] <= 2
        stats = a.backpressure_stats()
        assert stats["dispatched"] == 12
        assert stats["handlers_peak"] <= 2
        assert stats["active_handlers"] == 0

    @pytest.mark.asyncio
    async def test_burst_with_backpressure_loses_no_undropped_event(self):
        a = make_adapter(queue_maxsize=8, max_concurrency=3)
        a._running = True
        handled = []
        state = {"active": 0, "peak": 0}

        async def fake_handle(event):
            state["active"] += 1
            state["peak"] = max(state["peak"], state["active"])
            await asyncio.sleep(0.005)
            state["active"] -= 1
            handled.append(event)

        a.handle_message = fake_handle
        for i in range(200):
            a._enqueue_event(f"e{i}")

        loop_task = asyncio.create_task(a._queue_poll_loop())
        try:
            assert await wait_until_idle(a) is True
        finally:
            a._running = False
            loop_task.cancel()
            try:
                await loop_task
            except asyncio.CancelledError:
                pass

        stats = a.backpressure_stats()
        # Every event is accounted for: handled, or explicitly dropped.
        assert len(handled) == stats["dispatched"]
        assert stats["dispatched"] + stats["dropped_oldest"] == 200
        assert state["peak"] <= 3
        assert stats["handlers_peak"] <= 3
        assert stats["queue_peak"] <= 8


    @pytest.mark.asyncio
    async def test_poll_loop_task_does_not_consume_handler_slot(self):
        """The long-lived poll loop must not eat a handler slot (max=1)."""
        a = make_adapter(max_concurrency=1)
        a._running = True
        handled = []

        async def fake_handle(event):
            await asyncio.sleep(0.005)
            handled.append(event)

        async def idle_forever():
            await asyncio.sleep(30)

        a.handle_message = fake_handle
        helper = asyncio.create_task(idle_forever())  # stands in for _poll_loop
        a._background_tasks.add(helper)
        a._enqueue_event("e1")
        a._enqueue_event("e2")

        loop_task = asyncio.create_task(a._queue_poll_loop())
        try:
            deadline = time.monotonic() + 5
            while len(handled) < 2 and time.monotonic() < deadline:
                await asyncio.sleep(0.005)
        finally:
            a._running = False
            loop_task.cancel()
            helper.cancel()
            for task in (loop_task, helper):
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        assert handled == ["e1", "e2"]
        assert a.backpressure_stats()["active_handlers"] == 0


class TestPollLoopBurst:
    """A real burst through _poll_loop stays bounded and deduped."""

    @pytest.mark.asyncio
    async def test_updates_page_burst_is_bounded_and_deduped(self):
        import httpx

        a = make_adapter(queue_maxsize=5)

        # 300 updates in a single /updates page: 150 distinct mids, then the
        # same 150 mids repeated (transport retry / duplicate delivery).
        updates = [dm_update(f"m{i}", text=f"m{i}") for i in range(150)]
        updates += [dm_update(f"m{i}", text=f"m{i}") for i in range(150)]

        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(200, json={"updates": updates, "marker": 1})
            a._stop.set()  # stop the loop after the burst is drained
            return httpx.Response(200, json={"updates": [], "marker": 2})

        a._http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        a._stop.clear()
        try:
            await asyncio.wait_for(asyncio.create_task(a._poll_loop()), timeout=5)
        finally:
            await a._http_client.aclose()

        stats = a.backpressure_stats()
        assert stats["duplicate_suppressed"] == 150
        assert stats["enqueued"] == 150
        # Queue cap 5 with no consumer running: the rest is explicitly dropped.
        assert stats["dropped_oldest"] == 145
        assert stats["queue_depth"] == 5
        remaining = [e.text for e in list(a._message_queue._queue)]
        assert remaining == ["m145", "m146", "m147", "m148", "m149"]


class TestMetrics:
    """Metrics are observable and exposed by /health."""

    def test_stats_snapshot_shape(self):
        a = make_adapter()
        stats = a.backpressure_stats()
        for key in (
            "enqueued", "dispatched", "dropped_oldest", "dropped_newest",
            "duplicate_suppressed", "queue_peak", "handlers_peak",
            "queue_depth", "queue_maxsize", "active_handlers",
            "max_concurrency", "dedup_entries", "dedup_max",
        ):
            assert isinstance(stats[key], int), key
        assert stats["overload_policy"] == adapter.OVERLOAD_DROP_OLDEST

    @pytest.mark.asyncio
    async def test_health_endpoint_exposes_backpressure(self):
        import httpx

        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()

        a = make_adapter(host="127.0.0.1", port=port, queue_maxsize=42)
        a._http_client = httpx.AsyncClient()
        a._running = True
        try:
            assert await a._start_webhook() is True
            async with httpx.AsyncClient() as client:
                # Base health contract is strictly {"status": "ok"}
                health = await client.get(f"http://127.0.0.1:{port}/health")
                assert health.status_code == 200
                assert health.json() == {"status": "ok"}

                # Telemetry exposed via query param or dedicated /metrics endpoint
                resp = await client.get(f"http://127.0.0.1:{port}/health?backpressure=1")
                assert resp.status_code == 200
                body = resp.json()
                assert body["status"] == "ok"
                bp = body["backpressure"]
                assert bp["queue_maxsize"] == 42
                assert bp["queue_depth"] == 0
                assert bp["max_concurrency"] == adapter.DEFAULT_MAX_CONCURRENCY
                assert bp["overload_policy"] == adapter.OVERLOAD_DROP_OLDEST
                assert bp["dedup_max"] == adapter.DEFAULT_DEDUP_MAX

                metrics = await client.get(f"http://127.0.0.1:{port}/metrics")
                assert metrics.status_code == 200
                assert metrics.json()["backpressure"]["queue_maxsize"] == 42
        finally:
            a._running = False
            if a._poll_task is not None:
                a._poll_task.cancel()
                try:
                    await a._poll_task
                except asyncio.CancelledError:
                    pass
            if a._webhook_runner is not None:
                await a._webhook_runner.cleanup()
            await a._http_client.aclose()
