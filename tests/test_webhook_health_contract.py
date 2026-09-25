"""Tests for R4 · CODE-05: Webhook Health & Telemetry Endpoint Contract.

Pins the exact contracts:
1. Strict base contract for `/health`: returns 200 {"status": "ok"} without unsolicited payload.
2. Query param option for `/health?backpressure=1` or `/health?metrics=1` returns telemetry.
3. Dedicated `/metrics` endpoint returns 200 with backpressure & ingress telemetry.
4. Distinguishable `/ready` contract (readiness vs liveness).
"""

import socket

import httpx
import pytest
from gateway.config import PlatformConfig

from adapter import DEFAULT_DEDUP_MAX, DEFAULT_MAX_CONCURRENCY, MaxAdapter


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _make_adapter(port: int, secret: str = "secret-123", **extra):
    cfg_extra = {
        "token": "tok",
        "host": "127.0.0.1",
        "port": port,
        "path": "/max/webhook",
        "webhook_secret": secret,
        **extra,
    }
    cfg = PlatformConfig(enabled=True, token="tok", extra=cfg_extra)
    adapter = MaxAdapter(cfg)
    adapter._http_client = httpx.AsyncClient()
    adapter._running = True
    return adapter


class TestWebhookHealthEndpointContract:
    """R4 · CODE-05 health contract verification."""

    @pytest.mark.asyncio
    async def test_health_strict_base_contract(self):
        """GET /health must strictly return {"status": "ok"}."""
        port = _free_port()
        adapter = _make_adapter(port)
        try:
            assert await adapter._start_webhook() is True
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"http://127.0.0.1:{port}/health")
                assert resp.status_code == 200
                assert resp.json() == {"status": "ok"}
        finally:
            await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_health_query_param_telemetry(self):
        """GET /health?backpressure=1 or ?metrics=1 returns extended telemetry."""
        port = _free_port()
        adapter = _make_adapter(port, queue_maxsize=50)
        try:
            assert await adapter._start_webhook() is True
            async with httpx.AsyncClient() as client:
                for q in ("backpressure=1", "metrics=1"):
                    resp = await client.get(f"http://127.0.0.1:{port}/health?{q}")
                    assert resp.status_code == 200
                    data = resp.json()
                    assert data["status"] == "ok"
                    assert "backpressure" in data
                    assert data["backpressure"]["queue_maxsize"] == 50
        finally:
            await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_metrics_endpoint_contract(self):
        """GET /metrics returns 200 with complete backpressure stats snapshot."""
        port = _free_port()
        adapter = _make_adapter(port, queue_maxsize=77)
        try:
            assert await adapter._start_webhook() is True
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"http://127.0.0.1:{port}/metrics")
                assert resp.status_code == 200
                data = resp.json()
                assert data["status"] == "ok"
                bp = data["backpressure"]
                assert bp["queue_maxsize"] == 77
                assert bp["max_concurrency"] == DEFAULT_MAX_CONCURRENCY
                assert bp["dedup_max"] == DEFAULT_DEDUP_MAX
        finally:
            await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_ready_endpoint_contract(self):
        """GET /ready returns readiness status and telemetry."""
        port = _free_port()
        adapter = _make_adapter(port)
        try:
            assert await adapter._start_webhook() is True
            # In manual/loopback mode, server listening implies ready
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"http://127.0.0.1:{port}/ready")
                assert resp.status_code == 200
                data = resp.json()
                assert data["status"] == "ready"
                assert "backpressure" in data

                # When not ready, returns 503
                adapter._webhook_ready = False
                adapter._webhook_ready_reason = "registering"
                resp_not_ready = await client.get(f"http://127.0.0.1:{port}/ready")
                assert resp_not_ready.status_code == 503
                body = resp_not_ready.json()
                assert body["status"] == "not_ready"
                assert body["reason"] == "registering"
                assert "backpressure" in body
        finally:
            await adapter.disconnect()
