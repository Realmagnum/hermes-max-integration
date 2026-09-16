"""Core adapter tests."""

import adapter


class TestHelpers:
    """Tests for helper functions."""

    def test_parse_list(self):
        assert adapter._parse_list("a, b, c") == ["a", "b", "c"]
        assert adapter._parse_list("") == []
        assert adapter._parse_list("single") == ["single"]

    def test_is_group(self):
        assert adapter._is_group("-100") is True
        assert adapter._is_group("-1") is True
        assert adapter._is_group("42") is False
        assert adapter._is_group("abc") is False

    def test_coerce_bool(self):
        assert adapter._coerce_bool("true") is True
        assert adapter._coerce_bool("1") is True
        assert adapter._coerce_bool("yes") is True
        assert adapter._coerce_bool("false") is False
        assert adapter._coerce_bool("0") is False
        assert adapter._coerce_bool(None) is False
        assert adapter._coerce_bool(True) is True

    def test_verify_secret_matches(self):
        assert adapter._verify_raw_secret(b"{}", "secret-123", "secret-123") is True
        assert adapter._verify_raw_secret(b"{}", "secret-123", "different") is False
        assert adapter._verify_raw_secret(b"{}", "", None) is True
        assert adapter._verify_raw_secret(b"{}", "secret-123", None) is False


class TestEnvEnablement:
    """Tests for _env_enablement."""

    def test_seeds_extra(self, monkeypatch):
        monkeypatch.setenv("MAX_BOT_TOKEN", "tok")
        monkeypatch.setenv("MAX_WEBHOOK_PORT", "8646")
        monkeypatch.setenv("MAX_WEBHOOK_PATH", "/max/webhook")
        monkeypatch.setenv("MAX_ALLOWED_USERS", "1, 2")
        result = adapter._env_enablement()
        assert result is not None


class TestSplitOutbound:
    """Tests for _split_outbound_text."""

    def test_short_text_one_chunk(self):
        from gateway.config import PlatformConfig
        cfg = PlatformConfig(enabled=True, token="tok")
        a = adapter.MaxAdapter(cfg)
        result = a._split_outbound_text("short text")
        assert len(result) == 1
        assert result[0] == "short text"

    def test_long_text_split(self):
        from gateway.config import PlatformConfig
        cfg = PlatformConfig(enabled=True, token="tok")
        a = adapter.MaxAdapter(cfg)
        long = "a" * 6000
        result = a._split_outbound_text(long)
        # 6000 chars, 3900-char chunks → 3900 + 2100
        assert [len(c) for c in result] == [3900, 2100]
        assert "".join(result) == long

    def test_empty_returns_one_chunk(self):
        from gateway.config import PlatformConfig
        cfg = PlatformConfig(enabled=True, token="tok")
        a = adapter.MaxAdapter(cfg)
        result = a._split_outbound_text("")
        assert len(result) == 1
        assert result[0] == ""


class TestConfigValidation:
    """Tests for config validation functions."""

    def test_validate_config_with_token(self, monkeypatch):
        from gateway.config import PlatformConfig
        monkeypatch.setenv("MAX_BOT_TOKEN", "test-tok")
        cfg = PlatformConfig(enabled=True)
        assert adapter.validate_config(cfg) is True

    def test_validate_config_without_token(self, monkeypatch):
        from gateway.config import PlatformConfig
        monkeypatch.delenv("MAX_BOT_TOKEN", raising=False)
        cfg = PlatformConfig(enabled=True)
        assert adapter.validate_config(cfg) is False

    def test_check_requirements(self, monkeypatch):
        monkeypatch.setenv("MAX_BOT_TOKEN", "test")
        # aiohttp and httpx are available in test environment
        assert adapter.check_max_requirements() is True


class TestMediaHelpers:
    """Tests for media extraction helpers."""

    def test_attachment_kind_audio(self):
        att = {"type": "audio", "payload": {"url": "https://example.com/test.ogg"}}
        assert adapter.MaxAdapter._attachment_kind(att) == "audio"

    def test_attachment_kind_voice(self):
        att = {"type": "voice", "payload": {}}
        assert adapter.MaxAdapter._attachment_kind(att) == "voice"

    def test_attachment_kind_image(self):
        att = {"type": "image", "payload": {}}
        assert adapter.MaxAdapter._attachment_kind(att) == "image"

    def test_attachment_kind_document(self):
        att = {"type": "file", "payload": {}}
        assert adapter.MaxAdapter._attachment_kind(att) == "document"

    def test_attachment_kind_unknown(self):
        att = {"type": "unknown", "payload": {}}
        assert adapter.MaxAdapter._attachment_kind(att) == ""

    def test_find_first_url(self):
        data = {"url": "https://cdn.example.com/file.ogg"}
        assert adapter.MaxAdapter._find_first_url(data) == "https://cdn.example.com/file.ogg"

    def test_find_first_url_nested(self):
        data = {"payload": {"url": "https://cdn.example.com/file.ogg"}}
        assert adapter.MaxAdapter._find_first_url(data) == "https://cdn.example.com/file.ogg"

    def test_find_first_url_not_found(self):
        assert adapter.MaxAdapter._find_first_url({"x": 1}) is None

    def test_find_first_filename(self):
        data = {"filename": "document.pdf"}
        assert adapter.MaxAdapter._find_first_filename(data) == "document.pdf"

    def test_safe_url_for_log(self):
        result = adapter.MaxAdapter._safe_url_for_log(
            "https://cdn.example.com/path/file?token=secret"
        )
        assert "token" not in result
        assert result == "https://cdn.example.com/path/file"

    def test_derive_message_type_text(self):
        assert adapter.MaxAdapter._derive_message_type("hello", []) == adapter.MessageType.TEXT

    def test_derive_message_type_image(self):
        assert adapter.MaxAdapter._derive_message_type("", ["image/jpeg"]) == adapter.MessageType.PHOTO

    def test_derive_message_type_audio(self):
        assert adapter.MaxAdapter._derive_message_type("", ["audio/ogg"]) == adapter.MessageType.VOICE


class TestPolicyProperties:
    """Policy properties must return exact values, not "one of"."""

    def test_dm_policy_is_allowlist_by_default(self, make_adapter):
        a = make_adapter()
        # allow_all_users is False → allowlist, even with an EMPTY allowlist.
        # (That empty list is itself the SEC-05 hole: nothing is enforced.)
        assert a.dm_policy == "allowlist"
        assert a.allow_from == []
        assert a.group_policy == "allowlist"
        assert a.group_allow_from == []
        assert a.max_message_length == 4000

    def test_dm_policy_open_only_when_allow_all(self, make_adapter):
        a = make_adapter(extra={"allow_all_users": True})
        assert a.dm_policy == "open"

    def test_allow_from_normalises_ids_to_strings(self, make_adapter):
        a = make_adapter(extra={"allowed_users": [42, "77"]})
        assert sorted(a.allow_from) == ["42", "77"]

    def test_group_allow_from_is_parsed(self, make_adapter):
        a = make_adapter(extra={"group_allow_from": "1, 2"})
        assert a.group_allow_from == ["1", "2"]

    def test_group_policy_can_be_closed(self, make_adapter):
        a = make_adapter(extra={"group_policy": "closed"})
        assert a.group_policy == "closed"


class TestSendMessageId:
    """send() reports the message_id MAX returned, parsed from the response."""

    async def test_message_id_from_body_mid(self, make_adapter, max_api):
        """MAX API format: data.message.body.mid."""
        max_api.route("POST", "/messages", 200, {"message": {"body": {"mid": "mid-42"}}})
        a = make_adapter()

        result = await a.send("user:42", "hello")

        assert result.success is True
        assert result.message_id == "mid-42"
        assert result.raw_response == {"message": {"body": {"mid": "mid-42"}}}
        assert max_api.params(max_api.calls("POST", "/messages")[0]) == {"user_id": "42"}

    async def test_message_id_from_top_level(self, make_adapter, max_api):
        """Fallback: data.message.message_id."""
        max_api.route("POST", "/messages", 200, {"message": {"message_id": "legacy-99"}})
        a = make_adapter()

        result = await a.send("user:42", "hello")

        assert result.success is True
        assert result.message_id == "legacy-99"

    async def test_message_id_empty_fallback(self, make_adapter, max_api):
        """Neither body.mid nor message_id present → empty id, still success."""
        max_api.route("POST", "/messages", 200, {"message": {}})
        a = make_adapter()

        result = await a.send("user:42", "hello")

        assert result.success is True
        assert result.message_id == ""
