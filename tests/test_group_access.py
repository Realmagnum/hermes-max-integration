"""SEC-06 — group allowlist semantics.

The pre-fix implementation (``adapter.py:645-654``) combined the two group
allowlists with OR and treated an empty list as "allow all":

    user_allowed = (not self._group_allow_from) or user_id in self._group_allow_from
    chat_allowed = (not self._group_allow_chats) or chat_id_str in self._group_allow_chats
    if not user_allowed and not chat_allowed:  # OR → either match admits
        return None

That admitted every group message when both lists were empty, and a user in
the user-allowlist was admitted into *any* group, neutralizing the chat
allowlist. Acceptance for SEC-06: define the OR/AND policy, make empty lists
non-opening, and cover the empty/set × user/chat × open/closed/allowlist
matrix including direct messages/commands.

Effective policy under test:

* ``open``      — every group message accepted (explicit opt-in).
* ``closed``    — no group message accepted.
* ``allowlist`` — every *configured* list must match (AND); an empty list is
  not a permission, and when both lists are empty nothing is accepted.
"""

import pytest

import adapter

GROUP_CHAT_ID = "777"
GROUP_CHAT_SCOPED = "chat:777"
OTHER_CHAT_ID = "888"
USER_ID = "42"
OTHER_USER_ID = "99"


# ── helpers ──────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clean_group_env(monkeypatch):
    """Keep the matrix hermetic — no ambient MAX_* allowlists leak in."""
    for var in (
        "MAX_GROUP_POLICY",
        "MAX_GROUP_ALLOWED_USERS",
        "MAX_GROUP_ALLOWED_CHATS",
        "MAX_ALLOWED_USERS",
        "MAX_ALLOW_ALL_USERS",
    ):
        monkeypatch.delenv(var, raising=False)


def make_adapter(**extra):
    """Build an adapter whose PlatformConfig.extra carries the given keys."""
    from gateway.config import PlatformConfig

    cfg = PlatformConfig(
        enabled=True,
        token="test-token",
        extra={"token": "test-token", "allow_all_users": True, **extra},
    )
    return adapter.MaxAdapter(cfg)


def group_payload(user_id=USER_ID, chat_id=GROUP_CHAT_ID, text="hello", mid="g-mid"):
    """A group ``message_created`` update as MAX delivers it."""
    return {
        "update_type": "message_created",
        "chat": {"chat_id": int(chat_id), "title": "Test Group"},
        "message": {
            "sender": {"user_id": int(user_id), "name": "Test User"},
            "recipient": {"chat_id": int(chat_id)},
            "body": {"mid": mid, "text": text},
        },
    }


def dm_payload(user_id=USER_ID, text="hello", mid="d-mid"):
    """A direct (dialog) ``message_created`` update — no chat_id, so the
    adapter classifies it as ``dm`` and the group policy must not apply."""
    return {
        "update_type": "message_created",
        "message": {
            "sender": {"user_id": int(user_id), "name": "Test User"},
            "recipient": {"chat_type": "dialog"},
            "body": {"mid": mid, "text": text},
        },
    }


async def admitted(a, payload):
    """True when the update survives access control (an event is produced)."""
    event = await a._build_event(payload)
    return event is not None


# ── config normalization ─────────────────────────────────────────────────


class TestGroupConfigNormalization:
    def test_policy_is_case_and_space_insensitive(self, monkeypatch):
        monkeypatch.setenv("MAX_GROUP_POLICY", "  Open ")
        a = make_adapter()
        assert a.group_policy == "open"

    def test_unknown_policy_fails_closed(self, caplog):
        # A typo must not behave like "open" (the old code had no explicit
        # "open" branch, so anything not "closed"/"allowlist" allowed all).
        a = make_adapter(group_policy="Close", group_allow_from="42")
        assert a.group_policy == "closed"
        # …and it must not silently fall back to allowlist either: a user that
        # *is* allowlisted stays blocked until the policy value is fixed.
        assert a._group_message_allowed(USER_ID, GROUP_CHAT_ID) is False

    def test_yaml_list_allowlists_are_parsed(self):
        # ``str([1, 2])`` used to become the literal "['1', '2']" — a junk
        # single entry that could never match a real id.
        a = make_adapter(group_allow_from=[1, 2], group_allow_chats=[-100500])
        assert a.group_allow_from == ["1", "2"]
        assert a.group_allow_chats == ["-100500"]

    def test_env_comma_list_is_parsed(self, monkeypatch):
        monkeypatch.setenv("MAX_GROUP_ALLOWED_USERS", "42, 99")
        monkeypatch.setenv("MAX_GROUP_ALLOWED_CHATS", "-100500")
        a = make_adapter()
        assert a.group_allow_from == ["42", "99"]
        assert a.group_allow_chats == ["-100500"]

    def test_env_overrides_yaml(self, monkeypatch):
        monkeypatch.setenv("MAX_GROUP_ALLOWED_USERS", "7")
        a = make_adapter(group_allow_from=["42"])
        assert a.group_allow_from == ["7"]

    def test_empty_env_falls_back_to_yaml(self, monkeypatch):
        monkeypatch.setenv("MAX_GROUP_ALLOWED_USERS", "")
        a = make_adapter(group_allow_from=["42"])
        assert a.group_allow_from == ["42"]


# ── decision matrix ──────────────────────────────────────────────────────
#
# rows: policy × (user allowlist, chat allowlist) × (user, chat) membership


class TestGroupPolicyMatrix:
    # ── open ────────────────────────────────────────────────────────────
    @pytest.mark.parametrize(
        "users,chats",
        [(None, None), (["42"], None), (None, ["999"]), (["7"], ["999"])],
    )
    def test_open_allows_everything(self, users, chats):
        a = make_adapter(
            group_policy="open",
            **({"group_allow_from": users} if users else {}),
            **({"group_allow_chats": chats} if chats else {}),
        )
        assert a._group_message_allowed(USER_ID, GROUP_CHAT_ID) is True
        assert a._group_message_allowed(OTHER_USER_ID, OTHER_CHAT_ID) is True

    # ── closed ──────────────────────────────────────────────────────────
    @pytest.mark.parametrize(
        "users,chats",
        [(None, None), (["42"], ["777"]), (["42"], None), (None, ["777"])],
    )
    def test_closed_denies_matching_config_too(self, users, chats):
        a = make_adapter(
            group_policy="closed",
            **({"group_allow_from": users} if users else {}),
            **({"group_allow_chats": chats} if chats else {}),
        )
        assert a._group_message_allowed(USER_ID, GROUP_CHAT_ID) is False

    # ── allowlist, both lists empty ⇒ nothing is allowed ────────────────
    @pytest.mark.parametrize("policy", ["allowlist", None])
    def test_allowlist_empty_lists_fail_closed(self, policy):
        extra = {"group_policy": policy} if policy else {}
        a = make_adapter(**extra)  # default policy is "allowlist"
        assert a.group_allow_from == []
        assert a.group_allow_chats == []
        assert a._group_message_allowed(USER_ID, GROUP_CHAT_ID) is False

    # ── allowlist, only the user dimension configured ───────────────────
    def test_allowlist_users_only(self):
        a = make_adapter(group_allow_from=["42"])
        # matching user → accepted in any group chat
        assert a._group_message_allowed(USER_ID, GROUP_CHAT_ID) is True
        assert a._group_message_allowed(USER_ID, OTHER_CHAT_ID) is True
        # non-matching user → denied
        assert a._group_message_allowed(OTHER_USER_ID, GROUP_CHAT_ID) is False

    # ── allowlist, only the chat dimension configured ───────────────────
    def test_allowlist_chats_only(self):
        a = make_adapter(group_allow_chats=["777"])
        # matching chat → accepted for any user
        assert a._group_message_allowed(USER_ID, GROUP_CHAT_ID) is True
        assert a._group_message_allowed(OTHER_USER_ID, GROUP_CHAT_ID) is True
        # non-matching chat → denied
        assert a._group_message_allowed(USER_ID, OTHER_CHAT_ID) is False

    # ── allowlist, both dimensions ⇒ AND, not OR ────────────────────────
    def test_allowlist_both_must_match(self):
        a = make_adapter(group_allow_from=["42"], group_allow_chats=["777"])
        # both match → accepted
        assert a._group_message_allowed(USER_ID, GROUP_CHAT_ID) is True
        # user matches, chat does not → denied (OR used to admit this)
        assert a._group_message_allowed(USER_ID, OTHER_CHAT_ID) is False
        # chat matches, user does not → denied (OR used to admit this)
        assert a._group_message_allowed(OTHER_USER_ID, GROUP_CHAT_ID) is False
        # neither matches → denied
        assert a._group_message_allowed(OTHER_USER_ID, OTHER_CHAT_ID) is False


# ── end-to-end through the inbound path ──────────────────────────────────


class TestGroupPolicyEndToEnd:
    """Exercise ``_build_event`` — the single entry point shared by polling
    (``_poll_loop``) and the webhook handler."""

    @pytest.mark.asyncio
    async def test_group_message_blocked_when_lists_empty(self):
        a = make_adapter()
        assert await admitted(a, group_payload()) is False

    @pytest.mark.asyncio
    async def test_group_message_blocked_for_other_chat(self):
        a = make_adapter(group_allow_from=["42"], group_allow_chats=["777"])
        assert await admitted(a, group_payload(chat_id=OTHER_CHAT_ID)) is False

    @pytest.mark.asyncio
    async def test_group_message_allowed_when_both_match(self):
        a = make_adapter(group_allow_from=["42"], group_allow_chats=["777"])
        event = await a._build_event(group_payload())
        assert event is not None
        assert event.source.chat_id == GROUP_CHAT_SCOPED
        assert event.source.chat_type == "group"

    @pytest.mark.asyncio
    async def test_group_slash_command_cannot_bypass_policy(self):
        # A command is an ordinary inbound message: the policy is applied
        # before dispatch, so a blocked user cannot drive the bot via /start.
        a = make_adapter(group_policy="closed")
        assert await admitted(a, group_payload(text="/start")) is False

    @pytest.mark.asyncio
    async def test_group_command_allowed_when_allowlisted(self):
        a = make_adapter(group_allow_from=["42"], group_allow_chats=["777"])
        assert await admitted(a, group_payload(text="/start", mid="cmd-1")) is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize("policy", ["open", "closed", "allowlist"])
    async def test_direct_message_unaffected_by_group_policy(self, policy):
        # "including direct commands": DMs are not group traffic, so no group
        # policy may block them — even a fully closed group policy.
        a = make_adapter(group_policy=policy)
        event = await a._build_event(dm_payload(text="/start", mid=f"dm-{policy}"))
        assert event is not None
        assert event.source.chat_type == "dm"
        assert event.source.chat_id == f"user:{USER_ID}"

    @pytest.mark.asyncio
    async def test_direct_message_carries_no_chat_scope(self):
        a = make_adapter(group_policy="closed")
        event = await a._build_event(dm_payload(text="hi", mid="dm-scope"))
        assert event.source.chat_id == f"user:{USER_ID}"
        assert GROUP_CHAT_SCOPED not in event.source.chat_id


class TestYamlConfigMapping:
    """``config.yaml`` must be able to express the same policy as env vars."""

    def test_group_allowlists_map_from_yaml(self):
        extra = adapter._apply_yaml_config(
            {},
            {
                "group_policy": "allowlist",
                "group_allow_from": ["42"],
                "group_allow_chats": ["777"],
            },
        )
        assert extra["group_allow_from"] == ["42"]
        assert extra["group_allow_chats"] == ["777"]
        a = make_adapter(**extra)
        assert a._group_message_allowed("42", "777") is True
        assert a._group_message_allowed("42", "888") is False

    def test_group_policy_maps_from_yaml(self):
        extra = adapter._apply_yaml_config({}, {"group_policy": "open"})
        assert extra["group_policy"] == "open"
        a = make_adapter(**extra)
        assert a.group_policy == "open"
        assert a._group_message_allowed("1", "2") is True


class TestIngressPathsShareAccessControl:
    """Both ingress paths must funnel through ``_build_event``, the single
    choke point where the group policy is evaluated."""

    def test_poll_loop_routes_through_build_event(self):
        import inspect

        src = inspect.getsource(adapter.MaxAdapter._poll_loop)
        assert "_build_event" in src

    def test_webhook_handler_routes_through_build_event(self):
        import inspect

        from max.mixins.webhook import WebhookMixin

        src = inspect.getsource(WebhookMixin)
        assert "_build_event" in src


class TestOrRegression:
    """Behavioral guards against the two pre-fix defects.

    Old expression: ``if not user_allowed and not chat_allowed: return None``
    with ``user_allowed = (not list) or user in list``.
    """

    def test_user_match_does_not_neutralize_chat_allowlist(self):
        # Pre-fix: user 42 ∈ users ⇒ admitted into group 888 despite the
        # chat allowlist listing only 777.
        a = make_adapter(group_allow_from=["42"], group_allow_chats=["777"])
        assert a._group_message_allowed("42", "888") is False

    def test_chat_match_does_not_neutralize_user_allowlist(self):
        # Pre-fix: chat 777 ∈ chats ⇒ any user admitted.
        a = make_adapter(group_allow_from=["42"], group_allow_chats=["777"])
        assert a._group_message_allowed("99", "777") is False

    def test_empty_allowlists_do_not_admit(self):
        # Pre-fix: both lists empty ⇒ user_allowed=chat_allowed=True ⇒ admit.
        a = make_adapter()
        assert a._group_message_allowed("42", "777") is False
        assert a._group_message_allowed("99", "888") is False


# GRP-001/002: the group gate applies before every callback dispatcher.
@pytest.mark.asyncio
@pytest.mark.parametrize("prefix,handler", [
    ("exec", "_handle_exec_callback"),
    ("sc", "_handle_slash_confirm_callback"),
    ("clarify", "_handle_clarify_callback"),
    ("model", "_handle_model_callback"),
    ("session", "_handle_session_callback"),
])
@pytest.mark.parametrize("extra,allowed", [
    ({"group_policy": "closed"}, False),
    ({"group_policy": "allowlist"}, False),
    ({"group_policy": "allowlist", "group_allow_from": [USER_ID], "group_allow_chats": [OTHER_CHAT_ID]}, False),
    ({"group_policy": "allowlist", "group_allow_from": [OTHER_USER_ID], "group_allow_chats": [GROUP_CHAT_ID]}, False),
    ({"group_policy": "allowlist", "group_allow_from": [USER_ID], "group_allow_chats": [GROUP_CHAT_ID]}, True),
    ({"group_policy": "open"}, True),
    ({"group_policy": "open", "allow_all_users": False, "allowed_users": [OTHER_USER_ID]}, False),
])
async def test_group_callback_policy_before_dispatch(prefix, handler, extra, allowed):
    from unittest.mock import AsyncMock, Mock
    a = make_adapter(**extra)
    dispatch = AsyncMock(return_value=None)
    setattr(a, handler, dispatch)
    a._remember_dm = Mock()
    payload = {"callback": {"user": {"user_id": int(USER_ID)}, "payload": f"{prefix}:probe:cancel"},
               "message": {"recipient": {"chat_id": int(GROUP_CHAT_ID), "chat_type": "chat"}, "body": {"mid": "mid"}}}
    await a._on_callback(payload)
    assert dispatch.await_count == int(allowed)
    if not allowed:
        a._remember_dm.assert_not_called()


@pytest.mark.asyncio
async def test_group_callback_denial_keeps_pending_until_policy_allows_owner():
    from unittest.mock import AsyncMock

    from gateway.platforms.base import SendResult
    a = make_adapter(group_policy="closed", cross_session=True, cross_session_users=[USER_ID])
    a.delete_message = AsyncMock(return_value=SendResult(success=True))
    a.send = AsyncMock()
    record = a._register_interaction("session", "group-probe", owner_user_id=USER_ID,
                                     chat_id=GROUP_CHAT_SCOPED, message_id="mid", ttl=100)
    record["rows"] = [{"id": "synthetic-session", "source": "max"}]
    payload = {"callback": {"payload": "session:group-probe:cancel", "user": {"user_id": int(USER_ID)}},
               "message": {"recipient": {"chat_id": int(GROUP_CHAT_ID), "chat_type": "chat"}, "body": {"mid": "mid"}}}
    await a._on_callback(payload)
    a.delete_message.assert_not_awaited()
    a.send.assert_not_awaited()
    a._group_policy = "open"
    await a._on_callback(payload)
    a.delete_message.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("fallback", ["recipient", "chat", "chat_id"])
async def test_callback_group_chat_id_fallback_is_gated(fallback):
    from unittest.mock import AsyncMock
    a = make_adapter(group_policy="closed")
    a._handle_model_callback = AsyncMock()
    payload = {"callback": {"payload": "model:probe:cancel", "user": {"user_id": int(USER_ID)}}}
    if fallback == "recipient":
        payload["message"] = {"recipient": {"chat_id": int(GROUP_CHAT_ID)}}
    elif fallback == "chat":
        payload["chat"] = {"chat_id": int(GROUP_CHAT_ID)}
    else:
        payload["chat_id"] = int(GROUP_CHAT_ID)
    await a._on_callback(payload)
    a._handle_model_callback.assert_not_called()


@pytest.mark.asyncio
async def test_dialog_callback_service_chat_id_ignores_group_policy():
    from unittest.mock import AsyncMock
    a = make_adapter(group_policy="closed")
    a._handle_model_callback = AsyncMock()
    await a._on_callback({"callback": {"payload": "model:probe:cancel", "user": {"user_id": int(USER_ID)}},
                          "message": {"recipient": {"chat_type": "dialog", "chat_id": int(GROUP_CHAT_ID)}}})
    a._handle_model_callback.assert_awaited_once()
    assert a._handle_model_callback.call_args.args[3] == f"user:{USER_ID}"


def test_fresh_adapter_access_and_session_defaults(monkeypatch):
    for name in ("MAX_CROSS_SESSION", "MAX_CROSS_SESSION_USERS", "MAX_SESSIONS_LIMIT", "MAX_SESSIONS_DEFAULT_ALL"):
        monkeypatch.delenv(name, raising=False)
    a = make_adapter(allow_all_users=False)
    assert not a._allow_all_users
    assert not a._allowed_users_set
    assert a._group_policy == "allowlist"
    assert not a._group_message_allowed(USER_ID, GROUP_CHAT_ID)
    status = a.session_routing_status(USER_ID)
    assert status["reason"] == "feature_disabled"
    assert status["limit"] == 10
    assert status["default_scope"] == "max"
