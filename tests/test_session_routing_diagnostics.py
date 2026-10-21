"""Routing readiness and install checks must not expose history or secrets."""

import importlib.util
import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from tests.test_session_list_policy import make_adapter, update

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("routing_check", ROOT / "scripts/check-session-routing.py")
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in list(os.environ):
        if key.startswith("MAX_"):
            monkeypatch.delenv(key)


@pytest.mark.parametrize("settings,user,reason,handler", [
    ({"cross_session": False}, "42", "feature_disabled", "core"),
    ({"allow_all_users": True, "allowed_users": []}, "42", "owners_missing", "core"),
    ({}, "7", "caller_not_owner", "core"),
    ({}, "42", "owner_picker_ready", "plugin"),
    ({}, None, "owner_picker_ready", "plugin"),
])
def test_status_and_startup_log(settings, user, reason, handler, caplog):
    with caplog.at_level(logging.INFO):
        a = make_adapter(**settings)
    result = a.session_routing_status(user)
    assert (result["reason"], result["handler"]) == (reason, handler)
    assert result["limit"] == 10 and result["default_scope"] == "max"
    assert "session routing handler=" in caplog.text
    assert "user_id" not in json.dumps(result)


@pytest.mark.asyncio
async def test_dispatch_logging_has_no_identifiers_or_query(caplog):
    a = make_adapter(cross_session=False)
    with caplog.at_level(logging.INFO):
        event = await a._on_message_created(update("/sessions search private-query-marker"))
    assert event.text.endswith("private-query-marker")
    routing_logs = "\n".join(r.message for r in caplog.records if "session command routing" in r.message)
    assert "handler=core reason=feature_disabled" in routing_logs
    assert "private-query-marker" not in routing_logs
    assert "42" not in routing_logs


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled,handler", [(True, "plugin"), (False, "core")])
async def test_probe_uses_real_dispatch_without_store_or_delivery(enabled, handler):
    a = make_adapter(cross_session=enabled)
    def forbidden(*args, **kwargs):
        pytest.fail("diagnostic accessed history or delivery")
    a._query_sessions = forbidden
    a.send = forbidden
    result = await CHECK.probe_adapter(a, "42")
    assert result["handler"] == handler
    assert result["dispatch_matches_policy"]
    assert result["commands_checked"] == 4


def test_main_redacts_runtime_errors(monkeypatch, capsys):
    def broken(_load_env):
        raise RuntimeError("private-owner-marker private-token-marker")
    monkeypatch.setattr(CHECK, "load_adapter", broken)
    assert CHECK.main(["--user-id", "private-owner-marker"]) == 1
    captured = capsys.readouterr()
    assert "private-owner-marker" not in captured.out + captured.err
    assert "private-token-marker" not in captured.out + captured.err
    assert json.loads(captured.out)["reason"] == "configuration_or_runtime_error"


def test_main_fails_when_dispatch_does_not_match_policy(monkeypatch, capsys):
    from unittest.mock import AsyncMock

    a = make_adapter()
    a._on_message_created = AsyncMock(return_value=None)
    monkeypatch.setattr(CHECK, "load_adapter", lambda _load_env: a)
    assert CHECK.main(["--user-id", "42"]) == 1
    assert json.loads(capsys.readouterr().out)["dispatch_matches_policy"] is False


def test_installed_profile_cli_matrix(tmp_path):
    home = tmp_path / "home"
    plugin = home / "plugins/max-platform"
    shutil.copytree(ROOT, plugin, ignore=shutil.ignore_patterns(
        ".git", ".venv*", "__pycache__", ".pytest_cache", ".hermes", "tests", "docs", "_rel_body.txt",
    ))
    (home / "empty-bundled").mkdir()
    env = {k: v for k, v in os.environ.items() if not k.startswith(("MAX_", "HERMES_"))}
    env.update(HERMES_HOME=str(home), HERMES_BUNDLED_PLUGINS=str(home / "empty-bundled"),
               HERMES_ENABLE_PROJECT_PLUGINS="0")
    cases = [
        ({"cross_session": False}, {}, False, "feature_disabled", 1),
        ({"cross_session": True, "allow_all_users": True}, {}, False, "owners_missing", 1),
        ({"cross_session": True, "cross_session_users": ["84"]}, {}, False, "caller_not_owner", 1),
        ({"cross_session": True, "cross_session_users": ["42"]}, {}, False, "owner_picker_ready", 0),
        ({"cross_session": False, "cross_session_users": ["42"]},
         {"MAX_CROSS_SESSION": "true"}, False, "owner_picker_ready", 0),
        ({"cross_session_users": ["42"]}, {}, True, "owner_picker_ready", 0),
    ]
    token = "private-token-output-marker"
    for extra, overrides, load_env, reason, code in cases:
        config = {"plugins": {"enabled": ["max-platform"]},
                  "platforms": {"max": {"enabled": True, "token": token, "extra": {"allowed_users": ["42"], **extra}}}}
        config_file = home / "config.yaml"
        config_file.write_text(yaml.safe_dump(config), encoding="utf-8")
        (home / ".env").write_text("MAX_CROSS_SESSION=true\nOTHER_SECRET=private-secret-marker\n", encoding="utf-8")
        before = config_file.read_bytes()
        args = [sys.executable, str(plugin / "scripts/check-session-routing.py"), "--user-id", "42"]
        if load_env:
            args.append("--load-profile-env")
        result = subprocess.run(args, env={**env, **overrides}, capture_output=True, text=True, timeout=30, check=False)
        assert result.returncode == code, result.stdout + result.stderr
        assert result.stdout, result.stderr
        report = json.loads(result.stdout)
        assert report["reason"] == reason, report
        assert report["dispatch_matches_policy"], report
        assert token not in result.stdout + result.stderr
        assert "private-secret-marker" not in result.stdout + result.stderr
        assert config_file.read_bytes() == before
