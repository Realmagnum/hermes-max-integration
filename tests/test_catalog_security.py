"""Catalog review regressions: safe access, profile credentials and Core hooks."""

import sys
from types import ModuleType
from unittest.mock import AsyncMock

import pytest
from gateway.config import PlatformConfig
from gateway.platforms.base import BasePlatformAdapter, SendResult
from max.credential_support import get_max_secret

import adapter


def make_adapter(**extra):
    return adapter.MaxAdapter(PlatformConfig(enabled=True, token="fixture-token", extra=extra))


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("MAX_ALLOWED_USERS", "MAX_ALLOW_ALL_USERS", "MAX_BOT_TOKEN", "MAX_WEBHOOK_SECRET"):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.asyncio
@pytest.mark.parametrize("recipient", [{"chat_type": "dialog"}, {"chat_id": 777}])
@pytest.mark.parametrize("users", [[], ["99"]])
async def test_closed_access_stops_attachment_and_command_processing(recipient, users):
    a = make_adapter(allowed_users=users, group_policy="open")
    a._extract_inbound_media = AsyncMock(return_value=([], []))
    a._handle_cross_sessions = AsyncMock()
    payload = {"update_type": "message_created", "message": {"sender": {"user_id": 42}, "recipient": recipient,
                           "body": {"mid": "deny", "text": "/sessions",
                                    "attachments": [{"type": "file", "payload": {"url": "https://example.com/file"}}]}}}
    assert await a._build_event(payload) is None
    a._extract_inbound_media.assert_not_called()
    a._handle_cross_sessions.assert_not_called()


@pytest.mark.asyncio
async def test_empty_closed_access_blocks_callback_before_dispatch():
    a = make_adapter()
    a._handle_exec_callback = AsyncMock()
    await a._on_callback({"callback": {"user": {"user_id": 42}, "payload": "exec:once:pending"}})
    a._handle_exec_callback.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("update_type", ["bot_started", "bot_added"])
async def test_start_events_do_not_bypass_closed_access(update_type):
    a = make_adapter(group_policy="open")
    assert await a._build_event({"update_type": update_type, "chat_id": 777,
                                 "user": {"user_id": 42}}) is None


@pytest.mark.parametrize("allow_all", [False, True])
def test_setup_defaults_closed_and_preserves_allowlist(monkeypatch, allow_all):
    from hermes_cli import setup
    saved = {"MAX_ALLOWED_USERS": "42,99"}
    questions = []
    def prompt_yes_no(question, default):
        questions.append((question, default))
        return allow_all if question.startswith("Allow all") else False
    def prompt(question, default="", **kwargs):
        return "fixture-token" if question.startswith("Bot token") else default
    for name in ("print_header", "print_info", "print_success", "print_warning"):
        monkeypatch.setattr(setup, name, lambda *args: None)
    monkeypatch.setattr(setup, "get_env_value", lambda name: saved.get(name, ""))
    monkeypatch.setattr(setup, "save_env_value", lambda name, value: saved.update({name: value}))
    monkeypatch.setattr(setup, "prompt_yes_no", prompt_yes_no)
    monkeypatch.setattr(setup, "prompt", prompt)
    adapter.interactive_setup()
    assert ("Allow all Max users to talk to the bot?", False) in questions
    assert saved["MAX_ALLOW_ALL_USERS"] == str(allow_all).lower()
    assert saved["MAX_ALLOWED_USERS"] == ("" if allow_all else "42,99")


def install_scope(monkeypatch, mapping, failure=None):
    module = ModuleType("agent.secret_scope")
    class UnscopedSecretError(RuntimeError):
        pass
    module.UnscopedSecretError = UnscopedSecretError
    module.current_secret_scope = lambda: mapping
    def get_secret(name):
        if failure:
            raise failure
    module.get_secret = get_secret
    monkeypatch.setitem(sys.modules, "agent.secret_scope", module)
    return module


@pytest.mark.parametrize("mapping, expected", [({"MAX_BOT_TOKEN": "profile-A"}, "profile-A"), ({}, "")])
def test_profile_scope_never_uses_other_profile_env_or_config(monkeypatch, mapping, expected):
    install_scope(monkeypatch, mapping)
    monkeypatch.setenv("MAX_BOT_TOKEN", "profile-B")
    cfg = PlatformConfig(enabled=True, token="profile-B", extra={"webhook_secret": "profile-B"})
    assert adapter.MaxAdapter(cfg)._token == expected
    assert adapter._standalone_get_token(cfg) == expected
    assert adapter.validate_config(cfg) is bool(expected)
    assert adapter.MaxAdapter(cfg)._webhook_secret == ""


def test_scope_lookup_failure_does_not_fall_back(monkeypatch):
    from gateway.platforms import _shared
    def failure(name):
        raise RuntimeError("scope failure")
    monkeypatch.setattr(_shared, "get_scoped_secret", failure)
    monkeypatch.setenv("MAX_BOT_TOKEN", "profile-B")
    with pytest.raises(RuntimeError, match="scope failure"):
        get_max_secret("MAX_BOT_TOKEN")


@pytest.mark.parametrize("multiplex", [False, True])
def test_real_core_unscoped_read_obeys_multiplex_policy(monkeypatch, multiplex):
    from agent import secret_scope as core_secrets
    monkeypatch.setenv("MAX_BOT_TOKEN", "default-profile")
    cfg = PlatformConfig(enabled=True, token="default-profile")
    scope = core_secrets.set_secret_scope(None)
    previous_active = core_secrets.is_multiplex_active()
    if hasattr(core_secrets, "set_multiplex_context"):
        context = core_secrets.set_multiplex_context(multiplex)
    else:
        core_secrets.set_multiplex_active(multiplex)
        context = None
    try:
        if multiplex:
            # The low-level agent reader rejects this, while the supported
            # platform helper intentionally supports default-profile startup.
            with pytest.raises(core_secrets.UnscopedSecretError):
                core_secrets.get_secret("MAX_BOT_TOKEN")
        for read in (lambda: get_max_secret("MAX_BOT_TOKEN"),
                     lambda: adapter.MaxAdapter(cfg)._token,
                     lambda: adapter._standalone_get_token(cfg),
                     lambda: adapter.validate_config(cfg),
                     adapter._env_enablement):
            assert read()
        assert get_max_secret("MAX_BOT_TOKEN") == "default-profile"
    finally:
        if context is not None:
            core_secrets.reset_multiplex_context(context)
        else:
            core_secrets.set_multiplex_active(previous_active)
        core_secrets.reset_secret_scope(scope)


def test_real_core_passive_probe_and_default_startup_preserve_routed_profile_isolation(monkeypatch):
    from unittest.mock import MagicMock

    from agent import secret_scope as core_secrets
    from gateway import platform_registry as registry_module
    from gateway.config import GatewayConfig, Platform
    from gateway.config_env import _enable_plugin_platform
    from gateway.platform_registry import PlatformEntry, PlatformRegistry

    monkeypatch.setenv("MAX_BOT_TOKEN", "default-profile")
    cfg = PlatformConfig(enabled=True, token="default-profile")
    factory = MagicMock(side_effect=adapter.MaxAdapter)
    secrets = MagicMock(wraps=adapter.get_max_secret)
    monkeypatch.setattr(adapter, "get_max_secret", secrets)
    entry = PlatformEntry(name="max", label="MAX", adapter_factory=factory,
                          check_fn=adapter.check_max_requirements, validate_config=adapter.validate_config)
    registry = PlatformRegistry()
    registry.register(entry)
    monkeypatch.setattr(registry_module, "platform_registry", registry)
    scope = core_secrets.set_secret_scope(None)
    previous_active = core_secrets.is_multiplex_active()
    core_secrets.set_multiplex_active(True)
    try:
        # Real config/status caller: an already enabled platform only needs its
        # libraries checked. Credential discovery is a separate optional hook.
        config = GatewayConfig(platforms={Platform("max"): cfg})
        _enable_plugin_platform(config, entry)
        assert config.platforms[Platform("max")].enabled
        assert entry.check_fn() is True
        secrets.assert_not_called()
        factory.assert_not_called()

        # Default-profile startup is unscoped by Core design. Construct only;
        # this test never connects or sends through a real network client.
        instance = registry.create_adapter("max", cfg)
        assert isinstance(instance, adapter.MaxAdapter)
        assert instance._token == "default-profile"
        factory.assert_called_once_with(cfg)

        # A routed profile's missing token must not borrow default env/config.
        routed_scope = core_secrets.set_secret_scope({})
        factory.reset_mock()
        try:
            assert registry.create_adapter("max", cfg) is None
            factory.assert_not_called()
        finally:
            core_secrets.reset_secret_scope(routed_scope)
    finally:
        core_secrets.set_multiplex_active(previous_active)
        core_secrets.reset_secret_scope(scope)


def test_real_core_profile_scope_is_authoritative(monkeypatch):
    from agent.secret_scope import reset_secret_scope, set_secret_scope
    monkeypatch.setenv("MAX_BOT_TOKEN", "profile-B")
    cfg = PlatformConfig(enabled=True, token="profile-B")
    for mapping, expected in (({"MAX_BOT_TOKEN": "profile-A"}, "profile-A"), ({}, "")):
        scope = set_secret_scope(mapping)
        try:
            assert adapter.MaxAdapter(cfg)._token == expected
            assert adapter._standalone_get_token(cfg) == expected
            assert adapter.validate_config(cfg) is bool(expected)
        finally:
            reset_secret_scope(scope)


@pytest.mark.asyncio
@pytest.mark.parametrize("smart_denied,allow_session,allow_permanent,expected", [
    (False, True, True, ["once", "session", "always", "deny"]),
    (False, False, False, ["once", "deny"]),
    (True, True, True, ["once", "deny"]),
])
async def test_real_core_approval_entrypoint_respects_policy(smart_denied, allow_session, allow_permanent, expected):
    a = make_adapter(allowed_users=["42"])
    a._http_client = object()
    a._post_interactive = AsyncMock(return_value=SendResult(success=True, message_id="card"))
    assert a.supports_exec_approval_buttons()
    result = await BasePlatformAdapter.send_exec_approval(
        a, "user:42", "rm example", "session-owner", "test reason",
        allow_session=allow_session, allow_permanent=allow_permanent, smart_denied=smart_denied,
    )
    assert result.success
    args = a._post_interactive.call_args.args
    assert args[0] == "user:42"
    choices = [button["payload"].split(":")[1] for row in args[2] for button in row]
    assert choices == expected
    record = next(iter(a._exec_approval_state.values()))
    assert record["owner_user_id"] == "42"
    assert record["message_id"] == "card"
    assert record["allowed_choices"] == expected


@pytest.mark.asyncio
async def test_owner_cannot_submit_choice_core_did_not_offer(monkeypatch):
    from unittest.mock import MagicMock

    from tools import approval
    a = make_adapter(allowed_users=["42"])
    a._http_client = object()
    a._post_interactive = AsyncMock(return_value=SendResult(success=True, message_id="card"))
    await a.send_exec_approval("user:42", "example", "session-owner", allow_permanent=False)
    approval_id = next(iter(a._exec_approval_state))
    resolve = MagicMock(return_value=1)
    monkeypatch.setattr(approval, "has_blocking_approval", lambda session_key: True)
    monkeypatch.setattr(approval, "resolve_gateway_approval", resolve)
    await a._handle_exec_callback(f"exec:always:{approval_id}", "42", {}, "user:42", "card")
    resolve.assert_not_called()
    assert approval_id in a._exec_approval_state
    a.send = AsyncMock(return_value=SendResult(success=True))
    await a._handle_exec_callback(f"exec:once:{approval_id}", "42", {}, "user:42", "card")
    resolve.assert_called_once_with("session-owner", "once")
    assert approval_id not in a._exec_approval_state


@pytest.mark.asyncio
async def test_download_client_uses_standard_tls_trust(monkeypatch):
    sentinel = object()
    clients = []
    def client(**kwargs):
        clients.append(kwargs)
        return AsyncMock()
    monkeypatch.setattr(adapter, "get_max_ssl_context", lambda: sentinel)
    monkeypatch.setattr(adapter.httpx, "AsyncClient", client)
    a = make_adapter()
    a._verify_token_and_start = AsyncMock(return_value=True)
    assert await a.connect()
    assert clients[0]["verify"] is sentinel
    assert clients[1]["verify"] is True
    assert "headers" not in clients[1]
    assert clients[1]["follow_redirects"] is False
    await a.disconnect()
