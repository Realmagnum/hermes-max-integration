"""CODE-01: HTTP backoff polling.

The audit (BACKLOG, CODE-01) found that a non-200 poll response only
incremented a counter: ``adapter.py`` slept **only** in the transport-error
branch, so four mocked HTTP 429 replies produced four back-to-back requests
with no pause, 401 never became fatal, and ``Retry-After`` was ignored.

These tests drive the real ``_poll_loop`` with a scripted HTTP client and a
virtual clock (``adapter._poll_sleep`` is replaced by a recorder), so every
assertion is about the number of requests *and* the delays between them.
"""

import asyncio
import random
import time
from email.utils import formatdate

import httpx
import pytest

import adapter

# ── Harness ─────────────────────────────────────────────────────────────


class FakeResponse:
    """Minimal stand-in for ``httpx.Response`` (status + headers + json)."""

    def __init__(self, status_code, *, headers=None, payload=None):
        self.status_code = status_code
        self.headers = headers if headers is not None else {}
        self._payload = payload if payload is not None else {"updates": [], "marker": 0}

    def json(self):
        return self._payload


class ScriptedClient:
    """Returns scripted responses/exceptions, then ends the loop on drain.

    Once the script is exhausted the next ``get`` flips ``_stop`` and returns
    a 200, so the loop finishes on its own without a real timeout.
    """

    def __init__(self, script, ad):
        self.script = list(script)
        self.ad = ad
        self.requests = []

    async def get(self, url, timeout=None):
        self.requests.append(url)
        if not self.script:
            self.ad._stop.set()
            return FakeResponse(200)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class SleepRecorder:
    """Virtual clock: records the delays the poll loop wanted to sleep."""

    def __init__(self):
        self.delays = []

    async def __call__(self, delay):
        self.delays.append(delay)


@pytest.fixture
def ad():
    from gateway.config import PlatformConfig

    return adapter.MaxAdapter(
        PlatformConfig(enabled=True, token="test-token", extra={})
    )


@pytest.fixture
def clock(monkeypatch):
    recorder = SleepRecorder()
    monkeypatch.setattr(adapter, "_poll_sleep", recorder)
    # Deterministic jitter: every delay assertion below is an exact value.
    monkeypatch.setattr(adapter, "_POLL_RNG", random.Random(20260916))
    return recorder


async def run_poll_loop(ad, script):
    client = ScriptedClient(script, ad)
    ad._http_client = client
    await asyncio.wait_for(ad._poll_loop(), timeout=5.0)
    return client


# ── Backoff helper ──────────────────────────────────────────────────────


class TestBackoffDelay:
    def test_exponential_growth_then_cap(self, monkeypatch):
        monkeypatch.setattr(adapter, "_POLL_RNG", random.Random(0))
        delays = [
            adapter._poll_backoff_delay(n, jitter=0.0) for n in range(1, 9)
        ]
        assert delays == [5.0, 10.0, 20.0, 40.0, 60.0, 60.0, 60.0, 60.0]
        assert max(delays) == adapter.POLL_BACKOFF_MAX

    def test_zeroth_error_is_treated_as_first(self):
        assert adapter._poll_backoff_delay(0, jitter=0.0) == adapter.POLL_ERROR_DELAY
        assert adapter._poll_backoff_delay(-3, jitter=0.0) == adapter.POLL_ERROR_DELAY

    def test_jitter_stays_within_band_and_cap(self, monkeypatch):
        monkeypatch.setattr(adapter, "_POLL_RNG", random.Random(7))
        for n in range(1, 12):
            plain = adapter._poll_backoff_delay(n, jitter=0.0)
            jittered = adapter._poll_backoff_delay(n)
            band = plain * adapter.POLL_BACKOFF_JITTER
            assert plain - band - 1e-9 <= jittered <= plain + band + 1e-9
            assert 0.0 <= jittered <= adapter.POLL_BACKOFF_MAX

    def test_non_negative(self, monkeypatch):
        monkeypatch.setattr(adapter, "_POLL_RNG", random.Random(99))
        assert all(adapter._poll_backoff_delay(n) >= 0.0 for n in range(1, 30))


class TestRetryAfter:
    def test_delta_seconds(self):
        assert adapter._parse_retry_after("120") == 120.0
        assert adapter._parse_retry_after("1.5") == 1.5
        assert adapter._parse_retry_after(7) == 7.0

    def test_http_date(self):
        future = time.time() + 30
        value = formatdate(future, usegmt=True)
        parsed = adapter._parse_retry_after(value)
        assert parsed is not None
        assert 25.0 <= parsed <= 40.0

    def test_past_date_is_zero(self):
        past = formatdate(time.time() - 120, usegmt=True)
        assert adapter._parse_retry_after(past) == 0.0

    def test_missing_or_garbage(self):
        assert adapter._parse_retry_after(None) is None
        assert adapter._parse_retry_after("") is None
        assert adapter._parse_retry_after("   ") is None
        assert adapter._parse_retry_after("soon") is None

    def test_negative_clamped_to_zero(self):
        assert adapter._parse_retry_after("-5") == 0.0

    def test_huge_value_clamped(self):
        assert adapter._parse_retry_after("999999") == adapter.POLL_RETRY_AFTER_MAX

    def test_status_delay_prefers_header(self):
        headers = {"Retry-After": "3"}
        assert adapter._poll_status_delay(headers, 5) == 3.0

    def test_status_delay_falls_back_to_backoff(self, monkeypatch):
        monkeypatch.setattr(adapter, "_POLL_RNG", random.Random(3))
        delay = adapter._poll_status_delay({}, 1)
        assert 3.75 <= delay <= 6.25

    def test_status_delay_tolerates_missing_headers(self, monkeypatch):
        monkeypatch.setattr(adapter, "_POLL_RNG", random.Random(3))
        assert adapter._poll_status_delay(None, 1) > 0.0

    def test_status_delay_reads_lowercase_dict_header(self):
        assert adapter._poll_status_delay({"retry-after": "4"}, 1) == 4.0

    def test_status_delay_reads_httpx_headers(self):
        headers = httpx.Headers({"Retry-After": "9"})
        assert adapter._poll_status_delay(headers, 1) == 9.0


# ── Poll loop ───────────────────────────────────────────────────────────


class TestPollLoopBackoff:
    @pytest.mark.asyncio
    async def test_four_429_sleep_before_every_retry(self, ad, clock):
        """Regression: four 429s used to mean four requests with no delays."""
        script = [FakeResponse(429, headers={"Retry-After": "2"}) for _ in range(4)]
        client = await run_poll_loop(ad, script)

        assert len(client.requests) == 5  # 4 rejected + the drain request
        assert clock.delays == [2.0, 2.0, 2.0, 2.0]

    @pytest.mark.asyncio
    async def test_429_without_retry_after_uses_bounded_backoff(self, ad, clock):
        script = [FakeResponse(429) for _ in range(5)]
        await run_poll_loop(ad, script)

        assert len(clock.delays) == 5
        assert 3.75 <= clock.delays[0] <= 6.25
        assert 7.5 <= clock.delays[1] <= 12.5
        assert 15.0 <= clock.delays[2] <= 25.0
        assert 30.0 <= clock.delays[3] <= 50.0
        assert 45.0 <= clock.delays[4] <= adapter.POLL_BACKOFF_MAX
        assert max(clock.delays) <= adapter.POLL_BACKOFF_MAX

    @pytest.mark.asyncio
    async def test_server_retry_after_beats_backoff_and_is_capped(self, ad, clock):
        script = [
            FakeResponse(429, headers={"Retry-After": "0"}),
            FakeResponse(503, headers={"Retry-After": "999999"}),
        ]
        await run_poll_loop(ad, script)

        assert clock.delays == [0.0, adapter.POLL_RETRY_AFTER_MAX]

    @pytest.mark.asyncio
    async def test_5xx_retried_with_increasing_delays(self, ad, clock):
        script = [FakeResponse(500), FakeResponse(502), FakeResponse(503)]
        client = await run_poll_loop(ad, script)

        assert len(client.requests) == 4  # 3 failures + drain
        assert len(clock.delays) == 3
        assert clock.delays == sorted(clock.delays)
        assert clock.delays[0] < clock.delays[2]

    @pytest.mark.asyncio
    async def test_success_resets_the_error_counter(self, ad, clock):
        script = [
            FakeResponse(500),
            FakeResponse(200),
            FakeResponse(500),
        ]
        await run_poll_loop(ad, script)

        assert len(clock.delays) == 2
        # Second failure is a *first* failure again → same backoff band.
        assert 3.75 <= clock.delays[0] <= 6.25
        assert 3.75 <= clock.delays[1] <= 6.25

    @pytest.mark.asyncio
    async def test_network_errors_back_off_exponentially(self, ad, clock):
        script = [
            httpx.ConnectError("connection refused"),
            httpx.ReadTimeout("read timed out"),
            httpx.RemoteProtocolError("server disconnected"),
        ]
        await run_poll_loop(ad, script)

        assert len(clock.delays) == 3
        assert clock.delays == sorted(clock.delays)
        assert 3.75 <= clock.delays[0] <= 6.25
        assert 7.5 <= clock.delays[1] <= 12.5

    @pytest.mark.asyncio
    async def test_status_and_transport_errors_share_one_counter(self, ad, clock):
        script = [
            httpx.ConnectError("boom"),
            FakeResponse(429),
        ]
        await run_poll_loop(ad, script)

        assert len(clock.delays) == 2
        assert 3.75 <= clock.delays[0] <= 6.25
        assert 7.5 <= clock.delays[1] <= 12.5

    @pytest.mark.asyncio
    async def test_no_sleep_while_polls_succeed(self, ad, clock):
        await run_poll_loop(ad, [FakeResponse(200)] * 3)
        assert clock.delays == []

    @pytest.mark.asyncio
    async def test_403_is_retried_not_treated_as_auth_failure(self, ad, clock):
        await run_poll_loop(ad, [FakeResponse(403)])

        assert len(clock.delays) == 1
        assert ad.has_fatal_error is False
        assert ad._running is False  # never marked connected by the loop itself

    @pytest.mark.asyncio
    async def test_marker_pagination_survives_backoff(self, ad, clock):
        script = [
            FakeResponse(429, headers={"Retry-After": "1"}),
            FakeResponse(200, payload={"updates": [], "marker": 4242}),
        ]
        client = await run_poll_loop(ad, script)

        assert clock.delays == [1.0]
        assert len(client.requests) >= 2
        assert "marker=4242" in client.requests[-1]


class TestPollLoopFatalAuth:
    @pytest.mark.asyncio
    async def test_401_stops_polling_with_fatal_auth_state(self, ad, clock):
        script = [FakeResponse(401), FakeResponse(200)]
        client = await run_poll_loop(ad, script)

        assert len(client.requests) == 1  # no retry after a rejected token
        assert clock.delays == []
        assert ad.has_fatal_error is True
        assert ad._fatal_error_code == "invalid_token"
        assert ad._fatal_error_retryable is False
        assert ad._running is False
        assert ad._stop.is_set()

    @pytest.mark.asyncio
    async def test_401_after_backoff_still_fatal(self, ad, clock):
        script = [FakeResponse(500), FakeResponse(401), FakeResponse(200)]
        client = await run_poll_loop(ad, script)

        assert len(client.requests) == 2
        assert len(clock.delays) == 1
        assert ad._fatal_error_code == "invalid_token"

    @pytest.mark.asyncio
    async def test_401_does_not_leave_a_pending_sleep(self, ad, clock):
        """The fatal path returns immediately — no trailing backoff sleep."""
        await run_poll_loop(ad, [FakeResponse(401)])
        assert clock.delays == []
