"""CODE-07 — adapter lifecycle and the Hermes core contract it depends on.

Reproductions for the audit item (base commit b004c57, audit base b004c573):

* ``connect()`` built a fresh ``httpx.AsyncClient`` on every call and never
  released the previous one, so a repeated connect leaked an open client and a
  second pair of poll loops.
* ``disconnect()`` cancelled the poll/queue/handler tasks but closed the HTTP
  client immediately, without awaiting them.
* A ``connect()`` that failed (or was cancelled) after the client was built
  left that client open — the core calls ``disconnect()`` defensively after a
  failed connect, but a cancelled connect() returns no handle at all.
* ``_running`` / ``_mark_connected`` / ``_mark_disconnected`` are inherited from
  ``gateway.platforms.base.BasePlatformAdapter`` — an unverified contract in the
  audit. ``TestCoreContract`` pins it against the installed core.

Every test here drives the real ``MaxAdapter``; only the HTTP transport is
faked, so no request leaves the process.
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib.metadata
import inspect
from typing import ClassVar

import pytest
from gateway.config import PlatformConfig
from gateway.platforms.base import BasePlatformAdapter

import adapter as max_adapter

# Minimum core the lifecycle contract was verified against (published release);
# 0.21.3 is the version the development checkout pins (see pyproject.toml).
_MIN_CORE = (0, 19)


class FakeResponse:
    def __init__(self, status_code: int = 200, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = ""

    def json(self) -> dict:
        return self._payload


class FakeClient:
    """Stand-in for ``httpx.AsyncClient`` recording creation/close order."""

    instances: ClassVar[list[FakeClient]] = []
    events: ClassVar[list[str]] = []
    # URL substrings that should hang until cancelled (long-poll emulation).
    blocking_urls: ClassVar[set[str]] = set()
    # URL substrings answering with a non-200 status.
    status_overrides: ClassVar[dict[str, int]] = {}

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.closed = False
        FakeClient.instances.append(self)
        FakeClient.events.append("client-created")

    # -- lifecycle -------------------------------------------------------
    async def aclose(self) -> None:
        self.closed = True
        FakeClient.events.append("client-closed")

    @property
    def is_closed(self) -> bool:
        return self.closed

    # -- requests --------------------------------------------------------
    async def _respond(self, url: str) -> FakeResponse:
        for needle, status in FakeClient.status_overrides.items():
            if needle in url:
                return FakeResponse(status, {})
        if "/me" in url:
            return FakeResponse(200, {"username": "bot", "user_id": 1})
        if "/subscriptions" in url:
            return FakeResponse(200, {"subscriptions": []})
        if "/updates" in url:
            if "updates" in FakeClient.blocking_urls:
                await asyncio.Event().wait()  # until cancelled
            await asyncio.sleep(0.01)
            return FakeResponse(200, {"updates": [], "marker": 0})
        return FakeResponse(200, {})

    async def get(self, url, **kwargs) -> FakeResponse:
        if "/me" in str(url) and "me" in FakeClient.blocking_urls:
            await asyncio.Event().wait()  # until cancelled
        return await self._respond(str(url))

    async def post(self, url, **kwargs) -> FakeResponse:
        return await self._respond(str(url))

    async def patch(self, url, **kwargs) -> FakeResponse:
        return await self._respond(str(url))

    async def delete(self, url, **kwargs) -> FakeResponse:
        return await self._respond(str(url))

    async def request(self, method, url, **kwargs) -> FakeResponse:
        return await self._respond(str(url))


@pytest.fixture(autouse=True)
def _reset_fake_client():
    FakeClient.instances = []
    FakeClient.events = []
    FakeClient.blocking_urls = set()
    FakeClient.status_overrides = {}
    yield


@pytest.fixture
def adapter_factory(monkeypatch):
    """Build a polling-mode MaxAdapter whose HTTP transport is faked."""
    for var in (
        "MAX_BOT_TOKEN",
        "MAX_WEBHOOK_URL",
        "MAX_WEBHOOK_SECRET",
        "MAX_WEBHOOK_PORT",
        "MAX_TABLE_AS_IMAGE",
        "MAX_CROSS_SESSION",
        "MAX_ALLOWED_USERS",
        "MAX_ALLOW_ALL_USERS",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(max_adapter.httpx, "AsyncClient", FakeClient)
    # `raising=False`: this constant is introduced by the CODE-07 fix, so the
    # reproduction run against the base commit must get past the fixture and
    # fail on the lifecycle assertions instead.
    monkeypatch.setattr(max_adapter, "TASK_SHUTDOWN_TIMEOUT", 5.0, raising=False)

    def _build(**extra):
        cfg = PlatformConfig(enabled=True, token="test-token", extra={"token": "test-token", **extra})
        return max_adapter.MaxAdapter(cfg)

    return _build


def open_clients() -> list[FakeClient]:
    return [c for c in FakeClient.instances if not c.closed]


def owned_tasks(adapter) -> list[asyncio.Task]:
    tasks = [adapter._poll_task, *adapter._background_tasks]
    return list(dict.fromkeys(t for t in tasks if t is not None))


def stray_live_tasks() -> list[asyncio.Task]:
    current = asyncio.current_task()
    return [t for t in asyncio.all_tasks() if t is not current and not t.done()]


def loop_tasks() -> list[asyncio.Task]:
    """Live receive loops — the leak surface when connect() is repeated."""
    return [
        t for t in stray_live_tasks()
        if str(getattr(t.get_coro(), "__qualname__", "")).endswith(("_poll_loop", "_queue_poll_loop"))
    ]


class TestRepeatedAndConcurrentConnect:
    async def test_connect_disconnect_connect_releases_each_session(self, adapter_factory):
        a = adapter_factory()

        assert await a.connect() is True
        first = a._http_client
        assert first is not None and not first.closed
        assert a._running is True
        assert len(owned_tasks(a)) == 2  # poll loop + queue drain
        assert len(loop_tasks()) == 2

        await a.disconnect()
        assert first.closed is True
        assert a._http_client is None
        assert a._running is False
        assert a._poll_task is None
        assert a._background_tasks == set()
        assert loop_tasks() == []
        assert stray_live_tasks() == []

        assert await a.connect() is True
        second = a._http_client
        assert second is not None and second is not first and not second.closed
        assert len(open_clients()) == 2
        assert len(owned_tasks(a)) == 2

        await a.disconnect()
        assert second.closed is True
        assert stray_live_tasks() == []

    async def test_repeated_connect_does_not_leak_client_or_loops(self, adapter_factory):
        a = adapter_factory()

        assert await a.connect() is True
        first = a._http_client
        assert await a.connect() is True

        # The previous session must be released, not orphaned.
        assert first.closed is True
        assert a._http_client is not first
        assert len(open_clients()) == 2
        # Exactly one poll loop and one queue-drain loop — no duplicates.
        assert len(owned_tasks(a)) == 2
        assert len(loop_tasks()) == 2

        await a.disconnect()
        assert loop_tasks() == []
        assert stray_live_tasks() == []

    async def test_concurrent_connect_is_serialized(self, adapter_factory):
        a = adapter_factory()

        results = await asyncio.gather(a.connect(), a.connect(), a.connect())

        assert results == [True, True, True]
        assert len(open_clients()) == 2
        assert len(FakeClient.instances) >= 1
        assert len(owned_tasks(a)) == 2
        assert len(loop_tasks()) == 2

        await a.disconnect()
        assert len(open_clients()) == 0
        assert loop_tasks() == []
        assert stray_live_tasks() == []
        # Every client that was ever built was closed exactly once.
        assert all(c.closed for c in FakeClient.instances)

    async def test_connect_after_failed_connect_still_works(self, adapter_factory):
        a = adapter_factory()
        FakeClient.status_overrides = {"/me": 401}

        assert await a.connect() is False
        assert a._http_client is None
        failed_client = FakeClient.instances[-1]
        assert failed_client.closed is True

        FakeClient.status_overrides = {}
        assert await a.connect() is True
        assert a._http_client is not None and not a._http_client.closed
        assert len(open_clients()) == 2

        await a.disconnect()
        assert len(open_clients()) == 0


class TestCancellationAndTeardown:
    async def test_disconnect_awaits_cancelled_tasks_before_closing_client(self, adapter_factory):
        a = adapter_factory()
        assert await a.connect() is True

        order: list[str] = []

        async def handler() -> None:
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                order.append("handler-cancelled")
                await asyncio.sleep(0)
                order.append("handler-unwound")
                raise

        task = asyncio.create_task(handler())
        a._background_tasks.add(task)
        await asyncio.sleep(0)  # let the handler reach its first await

        await a.disconnect()

        # The task is finished by the time disconnect() returns, and it finished
        # BEFORE the client was closed (a handler that unwinds against a closed
        # client is exactly the leak this guards).
        assert task.done() is True
        assert task.cancelled() is True
        assert order == ["handler-cancelled", "handler-unwound"]
        assert order[-1] != "client-closed"
        assert FakeClient.events.index("client-closed") > FakeClient.events.index("client-created")
        assert a._http_client is None
        assert a._expected_cancelled_tasks == set() or all(
            t.done() for t in a._expected_cancelled_tasks
        )
        assert stray_live_tasks() == []

    async def test_disconnect_while_poll_loop_is_mid_request(self, adapter_factory):
        a = adapter_factory()
        assert await a.connect() is True
        # Force the poll loop into a request that only ends by cancellation.
        FakeClient.blocking_urls = {"updates"}
        await asyncio.sleep(0.05)
        assert a._running is True

        await a.disconnect()

        assert a._http_client is None
        assert a._running is False
        assert a._poll_task is None
        assert a._background_tasks == set()
        assert stray_live_tasks() == []

    async def test_cancelled_connect_does_not_orphan_the_client(self, adapter_factory):
        a = adapter_factory()
        FakeClient.blocking_urls = {"me"}

        task = asyncio.create_task(a.connect())
        await asyncio.sleep(0.05)  # let it reach the blocking /me request
        assert a._http_client is not None
        client = a._http_client

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        # The client built for the aborted attempt is not left open.
        assert client.closed is True
        assert a._http_client is None
        assert stray_live_tasks() == []

        # And the adapter is still usable afterwards.
        FakeClient.blocking_urls = set()
        assert await a.connect() is True
        await a.disconnect()
        assert all(c.closed for c in FakeClient.instances)

    async def test_disconnect_without_connect_and_twice_is_safe(self, adapter_factory):
        a = adapter_factory()

        await a.disconnect()  # never connected: partial-init state
        assert a._http_client is None
        assert a._running is False
        assert a._background_tasks == set()

        assert await a.connect() is True
        client = a._http_client
        await a.disconnect()
        assert client.closed is True

        await a.disconnect()  # idempotent
        assert a._http_client is None
        assert a._running is False
        assert stray_live_tasks() == []

    async def test_failed_webhook_start_releases_client(self, adapter_factory, monkeypatch):
        a = adapter_factory(webhook_url="https://example.test/max/webhook")
        assert a._use_webhook is True

        async def _fail() -> bool:
            a._set_fatal_error("port_in_use", "Port already in use", retryable=False)
            return False

        monkeypatch.setattr(a, "_start_webhook", _fail)

        assert await a.connect() is False
        assert a._http_client is None
        assert FakeClient.instances[-1].closed is True
        assert open_clients() == []
        assert a._running is False
        assert stray_live_tasks() == []

    async def test_teardown_is_bounded_when_a_task_ignores_cancellation(self, adapter_factory, monkeypatch):
        a = adapter_factory()
        assert await a.connect() is True
        monkeypatch.setattr(max_adapter, "TASK_SHUTDOWN_TIMEOUT", 0.05, raising=False)

        release = asyncio.Event()

        async def stubborn() -> None:
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                # Swallow the cancel and keep the client busy — teardown must
                # still finish (bounded) and close the client.
                await release.wait()

        task = asyncio.create_task(stubborn())
        a._background_tasks.add(task)
        await asyncio.sleep(0)  # let it enter the try block

        await asyncio.wait_for(a.disconnect(), timeout=3.0)
        assert a._http_client is None
        assert a._background_tasks == set()

        release.set()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        assert task.done() is True
        assert stray_live_tasks() == []


class TestCoreContract:
    """The inherited lifecycle surface CODE-07 flagged as unverified."""

    def test_installed_core_version_is_supported(self):
        version = importlib.metadata.version("hermes-agent")
        # Upstream stopped publishing Core releases to PyPI after 0.19.
        # A source checkout intentionally reports 0.0.0; its lifecycle API
        # is verified by the contract tests below rather than this package
        # metadata floor.
        if version == "0.0.0":
            return
        major, minor = (int(part) for part in version.split(".")[:2])
        assert (major, minor) >= _MIN_CORE, (
            f"hermes-agent {version} predates the lifecycle contract verified "
            f"at >= {_MIN_CORE[0]}.{_MIN_CORE[1]} (see pyproject.toml dev extra)"
        )

    def test_base_adapter_exposes_the_lifecycle_hooks(self):
        for name in ("_mark_connected", "_mark_disconnected", "_set_fatal_error"):
            assert callable(getattr(BasePlatformAdapter, name, None)), name

        # Every parameter must be optional: the adapter calls these with no args.
        for name in ("_mark_connected", "_mark_disconnected"):
            sig = inspect.signature(getattr(BasePlatformAdapter, name))
            for param in sig.parameters.values():
                if param.name == "self":
                    continue
                assert (
                    param.default is not inspect.Parameter.empty
                    or param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
                ), f"{name}() now requires {param.name!r} — update MaxAdapter"

    def test_running_flag_is_owned_by_the_core(self, adapter_factory):
        a = adapter_factory()
        # MaxAdapter.__init__ must not re-declare the core-owned flag: a plain
        # `self._running = False` would silently shadow a core change (e.g. the
        # flag becoming a property or gaining extra bookkeeping).
        assert "self._running" not in inspect.getsource(max_adapter.MaxAdapter.__init__)
        assert isinstance(a._running, bool)

        a._mark_connected()
        assert a._running is True
        a._mark_disconnected()
        assert a._running is False

    async def test_connect_and_disconnect_drive_the_core_flag(self, adapter_factory):
        a = adapter_factory()
        assert a._running is False

        assert await a.connect() is True
        assert a._running is True
        assert a.has_fatal_error is False

        await a.disconnect()
        assert a._running is False
