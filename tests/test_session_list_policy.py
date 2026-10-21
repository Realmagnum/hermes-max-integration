"""SLP regressions through the command entry point and real Core database."""

from unittest.mock import AsyncMock

import pytest
from gateway.config import PlatformConfig
from gateway.platforms.base import SendResult

import adapter


@pytest.fixture(autouse=True)
def clean_policy_env(monkeypatch):
    for name in ("MAX_SESSIONS_LIMIT", "MAX_SESSIONS_DEFAULT_ALL", "MAX_CROSS_SESSION",
                 "MAX_ALLOWED_USERS", "MAX_CROSS_SESSION_USERS", "MAX_ALLOW_ALL_USERS"):
        monkeypatch.delenv(name, raising=False)


def make_adapter(**settings):
    return adapter.MaxAdapter(PlatformConfig(
        enabled=True, token="test-token",
        extra={"cross_session": True, "allowed_users": [42], **settings},
    ))


def update(text):
    return {"update_type": "message_created", "message": {
        "sender": {"user_id": 42}, "recipient": {"chat_type": "dialog"},
        "body": {"mid": "policy-test", "text": text},
    }}


@pytest.mark.parametrize("value,expected", [(1, 1), (10, 10), (20, 20), (0, 10),
                                            (-1, 10), (21, 10), ("bad", 10), (True, 10), (1.5, 10)])
def test_limit_validation(value, expected):
    assert make_adapter(sessions_limit=value)._sessions_limit == expected


def test_defaults_and_environment_precedence(monkeypatch):
    a = make_adapter()
    assert (a._sessions_limit, a._sessions_default_all) == (10, False)
    monkeypatch.setenv("MAX_SESSIONS_LIMIT", "7")
    monkeypatch.setenv("MAX_SESSIONS_DEFAULT_ALL", "false")
    a = make_adapter(sessions_limit=3, sessions_default_all=True)
    assert (a._sessions_limit, a._sessions_default_all) == (7, False)


@pytest.mark.asyncio
@pytest.mark.parametrize("command,default_all,expected_all,query", [
    ("/sessions", False, False, None), ("/sessions", True, True, None),
    ("/sessions all", False, True, None), ("/sessions max", True, False, None),
    ("/resume", False, False, None), ("/resume", True, True, None),
    ("/sessions search MiXeD Text", False, True, "MiXeD Text"),
    ("/sessions search MiXeD Text", True, True, "MiXeD Text"),
])
async def test_entry_point_modes(command, default_all, expected_all, query):
    a = make_adapter(sessions_limit=3, sessions_default_all=default_all)
    a._query_sessions = lambda *args, **kwargs: [{"id": "one", "source": "max"}]
    a._post_session_picker = AsyncMock()
    assert await a._on_message_created(update(command)) is None
    args = a._post_session_picker.await_args
    assert args.args[3] == query
    assert args.kwargs == {"include_all": expected_all, "limit": 3}


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["/sessions nonsense", "/sessions searchfoo", "/sessions search", "/sessions all junk", "/sessions max junk"])
async def test_invalid_arguments_do_not_resume_or_query(text):
    a = make_adapter()
    a._query_sessions = lambda *args, **kwargs: pytest.fail("invalid command queried DB")
    a.send = AsyncMock()
    assert await a._on_message_created(update(text)) is None
    assert "Usage:" in a.send.await_args.args[1]


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["/sessionsXYZ", "/resumeXYZ"])
async def test_command_prefixes_are_not_intercepted(text):
    a = make_adapter()
    event = await a._on_message_created(update(text))
    assert event.text == text


def test_max_filter_precedes_limit_in_real_database(tmp_path, monkeypatch):
    import hermes_state

    db = hermes_state.SessionDB(db_path=tmp_path / "sessions.db")
    try:
        for i in range(10):
            db.create_session(f"max-{i}", source="max")
            db.set_session_title(f"max-{i}", f"Needle max {i}")
        for i in range(25):
            db.create_session(f"cli-{i}", source="cli")
            db.set_session_title(f"cli-{i}", f"Needle {i}")
        db.create_session("archived-max", source="max")
        db.set_session_archived("archived-max", True)
        real_db = hermes_state.SessionDB
        monkeypatch.setattr(hermes_state, "SessionDB", lambda: real_db(db_path=tmp_path / "sessions.db"))
        a = make_adapter()
        rows = a._query_sessions(None, include_all=False, limit=10)
        assert len(rows) == 10 and {r["source"] for r in rows} == {"max"}
        assert "archived-max" not in {r["id"] for r in rows}
        assert len(a._query_sessions(None, include_all=True, limit=7)) == 7
        rows = a._query_sessions("Needle", include_all=True, limit=20)
        assert len(rows) == 20
        assert a._query_sessions("no-match", include_all=True, limit=10) == []
    finally:
        db.close()


@pytest.mark.asyncio
async def test_refresh_preserves_scope_limit_and_heading():
    a = make_adapter(sessions_limit=2)
    rows = [{"id": str(i), "source": "max", "title": "Task"} for i in range(5)]
    a._post_interactive = AsyncMock(return_value=SendResult(success=True, message_id="picker"))
    a.delete_message = AsyncMock(return_value=SendResult(success=True))
    record = await a._post_session_picker("user:42", "42", rows, None, include_all=True, limit=2)
    assert len(record["rows"]) == 2
    assert "all platforms" in a._post_interactive.await_args.args[1]
    a._sessions_limit = 1
    a._query_sessions = lambda search, **kw: rows[:kw["limit"]] if kw["include_all"] else []
    await a._handle_session_callback(
        f"session:{next(iter(a._session_picker_state))}:refresh", "42", "user:42", "picker",
    )
    refreshed = next(iter(a._session_picker_state.values()))
    assert len(refreshed["rows"]) == refreshed["limit"] == 2
    assert refreshed["include_all"] is True


@pytest.mark.asyncio
async def test_long_card_keeps_all_buttons_and_rows_visible():
    a = make_adapter(sessions_limit=20)
    rows = [{"id": f"session-{i}", "source": "max", "title": "T" * 100,
             "preview": "Q" * 200, "message_count": 123} for i in range(20)]
    a._post_interactive = AsyncMock(return_value=SendResult(success=True, message_id="picker"))
    record = await a._post_session_picker("user:42", "42", rows, None, limit=20)
    text, keyboard = a._post_interactive.await_args.args[1:]
    assert len(text) <= 3900
    assert len(record["rows"]) == 20
    for i in range(1, 21):
        assert f"**{i}.**" in text
    assert sum(len(row) for row in keyboard[:-1]) == 20


@pytest.mark.parametrize("default_all", [True, False])
def test_yaml_and_standalone_settings(monkeypatch, default_all):
    settings = adapter._apply_yaml_config({}, {"sessions_limit": 4, "sessions_default_all": default_all})
    a = make_adapter(**settings)
    assert (a._sessions_limit, a._sessions_default_all) == (4, default_all)
    monkeypatch.setenv("MAX_BOT_TOKEN", "test-token")
    monkeypatch.setenv("MAX_SESSIONS_LIMIT", "6")
    monkeypatch.setenv("MAX_SESSIONS_DEFAULT_ALL", str(default_all).lower())
    settings = adapter._env_enablement()
    a = make_adapter(**settings)
    assert (a._sessions_limit, a._sessions_default_all) == (6, default_all)


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["refresh:extra", "cancel:extra"])
async def test_malformed_callback_preserves_owner_state(action):
    a = make_adapter()
    a._post_interactive = AsyncMock(return_value=SendResult(success=True, message_id="picker"))
    record = await a._post_session_picker("user:42", "42", [{"id": "one", "source": "max"}], None)
    iid = next(iter(a._session_picker_state))
    assert await a._handle_session_callback(f"session:{iid}:{action}", "42", "user:42", "picker") is None
    assert a._session_picker_state[iid] is record


@pytest.mark.asyncio
async def test_refresh_error_is_distinct_from_empty_result():
    a = make_adapter()
    a._post_interactive = AsyncMock(return_value=SendResult(success=True, message_id="picker"))
    a.delete_message = AsyncMock(return_value=SendResult(success=True))
    a.send = AsyncMock()
    await a._post_session_picker("user:42", "42", [{"id": "one", "source": "max"}], None)
    iid = next(iter(a._session_picker_state))
    def broken(*args, **kwargs):
        raise RuntimeError("store unavailable")
    a._query_sessions = broken
    await a._handle_session_callback(f"session:{iid}:refresh", "42", "user:42", "picker")
    assert "⚠️" in a.send.await_args.args[1]
    assert not a._session_picker_state
