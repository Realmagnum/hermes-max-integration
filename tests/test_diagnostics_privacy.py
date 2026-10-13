"""Run diagnostics against local command fixtures, without network or credentials."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def _run_diagnostics(tmp_path, monkeypatch, token=None, response=None):
    bash = shutil.which("bash")
    if sys.platform == "win32":
        bash = r"C:\Program Files\Git\bin\bash.exe"
    if not bash or not Path(bash).exists():
        pytest.skip("Bash is required for shell diagnostics")
    home = tmp_path / "home"
    commands = tmp_path / "bin"
    commands.mkdir()
    (home / "logs").mkdir(parents=True)
    (home / ".env").write_text(
        "MAX_BOT_TOKEN=file-token-must-not-be-used\nOTHER_SERVICE_SECRET=unrelated-marker\n",
        encoding="utf-8",
    )
    marker = token or "file-token-must-not-be-used"
    (home / "logs" / "gateway.log").write_text(
        f"MAX: connected {marker}\nMAX: poll ok {marker}\n", encoding="utf-8"
    )
    trace = tmp_path / "requests"
    curl = commands / "curl"
    curl.write_text(
        '#!/usr/bin/env bash\n'
        'printf "%s\\n" "$*" >> "$TRACE"\n'
        'printf "other=%s\\n" "${OTHER_SERVICE_SECRET:-}" >> "$TRACE"\n'
        'if [[ "$*" == *"--config -"* ]]; then cat >/dev/null; fi\n'
        'printf "%s" "$MOCK_RESPONSE"\n',
        encoding="utf-8",
    )
    (commands / "hermes").write_text(
        '#!/usr/bin/env bash\nprintf "max-platform enabled\\n"\n', encoding="utf-8"
    )
    (commands / "python3").write_text(
        f'#!/usr/bin/env bash\nexec "{Path(sys.executable).as_posix()}" "$@"\n',
        encoding="utf-8",
    )
    for command in commands.iterdir():
        command.chmod(0o755)
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("MAX_") or key == "OTHER_SERVICE_SECRET":
            del env[key]
    env.update(
        HERMES_HOME=home.as_posix(), TRACE=trace.as_posix(),
        MOCK_RESPONSE=response or '{"subscriptions":[],"username":"test_bot"}',
    )
    if token:
        env["MAX_BOT_TOKEN"] = token
    command_path = commands.as_posix()
    if sys.platform == "win32":
        command_path = "/" + command_path[0].lower() + command_path[2:]
        env["MOCK_COMMANDS"] = command_path
    else:
        env["PATH"] = command_path + os.pathsep + env["PATH"]
    script = Path(__file__).resolve().parents[1] / "scripts" / "diagnose.sh"
    args = [bash, script.as_posix()]
    if sys.platform == "win32":
        env["DIAG_SCRIPT"] = script.as_posix()
        args = [bash, "-c", 'export PATH="$MOCK_COMMANDS:/usr/bin:/bin"; exec bash "$DIAG_SCRIPT"']
    result = subprocess.run(args, env=env, text=True, capture_output=True, timeout=20, check=False)
    return result, trace.read_text(encoding="utf-8") if trace.exists() else ""


def test_diagnostics_does_not_load_credential_file(tmp_path, monkeypatch):
    result, trace = _run_diagnostics(tmp_path, monkeypatch)
    assert not trace, "No API request is allowed without a supplied environment token"
    assert "MAX_BOT_TOKEN not found" in result.stdout


def test_diagnostics_keeps_secret_out_of_output_and_process_args(tmp_path, monkeypatch):
    token = "test-environment-token-marker"
    result, trace = _run_diagnostics(tmp_path, monkeypatch, token)
    assert "Bot token valid" in result.stdout, result.stderr
    assert token not in result.stdout + result.stderr
    assert token not in trace
    assert "file-token-must-not-be-used" not in trace
    assert "unrelated-marker" not in trace
    assert "--config -" in trace


def test_invalid_subscription_response_cannot_pass_diagnostics(tmp_path, monkeypatch):
    token = "test-environment-token-marker"
    result, _ = _run_diagnostics(tmp_path, monkeypatch, token, response=token)
    assert result.returncode == 1
    assert "invalid API response" in result.stdout
    assert "no stale subscriptions" not in result.stdout
    assert token not in result.stdout + result.stderr
