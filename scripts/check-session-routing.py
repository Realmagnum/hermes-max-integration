#!/usr/bin/env python3
"""Read-only owner routing check in the gateway's Python/profile environment."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import io
import json
import logging
import os
import socket
from unittest.mock import AsyncMock, patch


async def probe_adapter(adapter, user_id: str) -> dict:
    """Exercise dispatch, replacing the handler before any history or network access."""
    status = adapter.session_routing_status(user_id)
    commands = ("/sessions", "/sessions all", "/sessions search routing-probe", "/resume")
    results = []
    with patch.object(adapter, "_handle_cross_sessions", new_callable=AsyncMock) as handler:
        for index, command in enumerate(commands):
            handler.reset_mock()
            update = {"update_type": "message_created", "message": {
                "sender": {"user_id": user_id}, "recipient": {"chat_type": "dialog"},
                "body": {"mid": f"offline-routing-{index}", "text": command},
            }}
            event = await adapter._on_message_created(update)
            routed = "plugin" if event is None and handler.await_count == 1 else "core" if event is not None else "rejected"
            results.append(routed)
    return {**status, "dispatch_matches_policy": all(r == status["handler"] for r in results),
            "commands_checked": len(results)}


def _deny_network(*_args, **_kwargs):
    raise RuntimeError("network disabled in session routing diagnostic")


def load_adapter(load_profile_env: bool):
    """Use Core's real profile loader/registry, not a parallel YAML interpretation."""
    if load_profile_env:
        from hermes_cli.config import load_env

        for key, value in load_env().items():
            os.environ.setdefault(key, value)
    from hermes_cli.plugins import discover_plugins

    discover_plugins()
    from gateway.config import load_gateway_config
    from gateway.platform_registry import platform_registry

    config = load_gateway_config()
    entry = platform_registry.get("max")
    if entry is None:
        raise RuntimeError("MAX platform unavailable")
    platform_config = next((v for k, v in config.platforms.items() if k.value == "max"), None)
    if platform_config is None or not platform_config.enabled:
        raise RuntimeError("MAX platform not enabled")
    return entry.adapter_factory(platform_config)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", required=True, help="Owner to check; never echoed in output")
    parser.add_argument("--load-profile-env", action="store_true",
                        help="Explicitly load the active Hermes profile .env via Core; shell values retain priority")
    args = parser.parse_args(argv)
    # Suppress incidental dependency/plugin logs and error details, which could
    # contain identifiers, URLs or secrets. Emit only the fixed diagnostic schema.
    previous_level = logging.root.manager.disable
    try:
        logging.disable(logging.CRITICAL)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()), asyncio.Runner() as runner:
            # Windows creates a local socketpair when the event loop starts.
            # Initialize that internal transport before blocking network calls.
            runner.get_loop()
            with patch.object(socket.socket, "connect", _deny_network), \
                    patch.object(socket.socket, "connect_ex", _deny_network), \
                    patch.object(socket, "create_connection", _deny_network):
                adapter = load_adapter(args.load_profile_env)
                result = runner.run(probe_adapter(adapter, args.user_id))
    except Exception:  # noqa: BLE001 — never expose credential-bearing exception details
        result = {"handler": "unknown", "reason": "configuration_or_runtime_error", "dispatch_matches_policy": False}
    finally:
        logging.disable(previous_level)
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("handler") == "plugin" and result.get("dispatch_matches_policy") else 1


if __name__ == "__main__":
    raise SystemExit(main())
