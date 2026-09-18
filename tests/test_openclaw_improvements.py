"""Tests for magic bytes MIME detection, typing renewal, and streaming throttle."""

import pytest

import adapter


class TestDetectImageMime:
    """Tests for _detect_image_mime magic bytes detection."""

    def test_png(self):
        # PNG magic bytes: 89 50 4E 47 0D 0A 1A 0A
        data = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
        result = adapter.MaxAdapter._detect_image_mime(data)
        assert result == "image/png"

    def test_jpeg(self):
        # JPEG magic bytes: FF D8 FF
        data = b'\xff\xd8\xff\xe0' + b'\x00' * 100
        result = adapter.MaxAdapter._detect_image_mime(data)
        assert result == "image/jpeg"

    def test_webp(self):
        # WebP: RIFF....WEBP
        data = b'RIFF\x00\x00\x00\x00WEBP' + b'\x00' * 100
        result = adapter.MaxAdapter._detect_image_mime(data)
        assert result == "image/webp"

    def test_gif(self):
        # GIF: GIF8
        data = b'GIF89a' + b'\x00' * 100
        result = adapter.MaxAdapter._detect_image_mime(data)
        assert result == "image/gif"

    def test_bmp(self):
        # BMP: BM
        data = b'BM' + b'\x00' * 100
        result = adapter.MaxAdapter._detect_image_mime(data)
        assert result == "image/bmp"

    def test_unknown_fallback(self):
        data = b'\x00' * 100
        result = adapter.MaxAdapter._detect_image_mime(data)
        assert result == "image/jpeg"

    def test_short_data(self):
        data = b'\x89PNG'  # Less than 12 bytes
        result = adapter.MaxAdapter._detect_image_mime(data)
        assert result == "image/jpeg"


class TestStreamingThrottle:
    """Tests for edit_message streaming throttle (asserted on the wire)."""

    @pytest.mark.asyncio
    async def test_first_edit_goes_through(self, make_adapter, max_api):
        a = make_adapter()
        result = await a.edit_message("user:42", "mid-1", "hello world")
        assert result.success is True
        puts = max_api.calls("PUT", "/messages")
        assert len(puts) == 1
        assert max_api.params(puts[0]) == {"message_id": "mid-1"}
        assert max_api.json_body(puts[0]) == {"text": "hello world", "format": "markdown"}
        # Typing must be renewed with a real chat action request
        actions = [r for r in max_api.requests if r.url.path == "/chats/42/actions"]
        assert len(actions) == 1
        assert max_api.json_body(actions[0]) == {"action": "typing_on"}

    @pytest.mark.asyncio
    async def test_rapid_edits_throttled(self, make_adapter, max_api):
        a = make_adapter()

        # First edit — goes through
        result1 = await a.edit_message("user:42", "mid-1", "first")
        assert result1.success is True

        # Second edit immediately — throttled
        result2 = await a.edit_message("user:42", "mid-1", "second")
        assert result2.success is True
        # Only one PUT reaches MAX; the second is queued, not sent
        assert len(max_api.calls("PUT", "/messages")) == 1

    @pytest.mark.asyncio
    async def test_rapid_edit_stores_pending_content(self, make_adapter, max_api):
        """Throttled edit stores content in _pending_edit (Fix 2)."""
        a = make_adapter()

        # First edit goes through
        await a.edit_message("user:42", "mid-1", "first")
        assert getattr(a, "_pending_edit", None) is None

        # Second edit — throttled, content stored
        await a.edit_message("user:42", "mid-1", "second content")
        assert getattr(a, "_pending_edit", None) == "second content"
        # …and nothing beyond the first payload left the process
        assert [
            max_api.json_body(r)["text"] for r in max_api.calls("PUT", "/messages")
        ] == ["first"]

    @pytest.mark.asyncio
    async def test_pending_content_cleared_on_next_edit(self, make_adapter, max_api):
        """After throttle expires, _pending_edit is cleared."""
        a = make_adapter()

        # First edit goes through
        await a.edit_message("user:42", "mid-1", "first")
        assert getattr(a, "_pending_edit", None) is None

        # Simulate time passing beyond 200ms throttle
        import time as _time
        a._last_edit_at = _time.monotonic() - 1.0  # 1 second ago

        # Second edit now goes through
        await a.edit_message("user:42", "mid-1", "second")
        # Pending should be cleared
        assert getattr(a, "_pending_edit", None) is None
        assert [
            max_api.json_body(r)["text"] for r in max_api.calls("PUT", "/messages")
        ] == ["first", "second"]

    @pytest.mark.asyncio
    async def test_edit_message_converts_tables(self, make_adapter, max_api):
        """edit_message converts pipe tables to backtick-wrapped format (Fix 1)."""
        a = make_adapter()

        await a.edit_message(
            "user:42", "mid-1",
            "table:\n| A | B |\n|---|---|\n| 1 | 2 |"
        )

        # The on-wire payload must contain the converted table, not raw pipes
        text = max_api.json_body(max_api.calls("PUT", "/messages")[0])["text"]
        assert "`| A " in text  # backtick-wrapped, with padding
        assert "B   |`" in text
        assert "`| 1 " in text
        assert "2   |`" in text
        assert "|---|---|" not in text  # separator should be removed
        assert "<pre>" not in text  # no HTML tags
        assert "```" not in text  # no code fences

    @pytest.mark.asyncio
    async def test_finalize_resets_throttle(self, make_adapter, max_api):
        a = make_adapter()

        # First edit
        await a.edit_message("user:42", "mid-1", "first")
        assert len(max_api.calls("PUT", "/messages")) == 1

        # Finalize edit — always goes through, resets throttle
        result = await a.edit_message("user:42", "mid-1", "final", finalize=True)
        assert result.success is True
        assert [
            max_api.json_body(r)["text"] for r in max_api.calls("PUT", "/messages")
        ] == ["first", "final"]
        assert getattr(a, "_last_edit_at", 0.0) == 0.0

    @pytest.mark.asyncio
    async def test_long_edit_is_truncated_to_message_limit(self, make_adapter, max_api):
        a = make_adapter()

        await a.edit_message("user:42", "mid-1", "y" * 5000)

        text = max_api.json_body(max_api.calls("PUT", "/messages")[0])["text"]
        assert len(text) == 4000
        assert text.endswith("...")


class TestTypingRenewal:
    """Tests for typing indicator renewal after edit."""

    @pytest.mark.asyncio
    async def test_typing_renewed_after_edit(self, make_adapter, max_api):
        a = make_adapter()
        await a.edit_message("user:42", "mid-1", "streaming...")
        # send_typing must produce a real chat-action request after the edit
        assert ("POST", "/chats/42/actions") in max_api.methods()

    @pytest.mark.asyncio
    async def test_typing_not_renewed_on_error(self, make_adapter, max_api):
        max_api.route("PUT", "/messages", 500, {"message": "API error"})
        a = make_adapter()
        result = await a.edit_message("user:42", "mid-1", "fail")
        assert result.success is False
        # send_typing should NOT be called on error
        assert ("POST", "/chats/42/actions") not in max_api.methods()
