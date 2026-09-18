"""Tests for message chunking in detail.

Includes the CODE-02 regression suite: outbound chunking must be lossless —
the concatenation of the payloads actually transmitted has to reproduce the
source text (audit baseline: 7800 chars in → 7788 out).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

import adapter


class TestSplitOutboundText:
    """Detailed chunking tests."""

    def _make_adapter(self):
        from gateway.config import PlatformConfig
        cfg = PlatformConfig(enabled=True, token="tok")
        return adapter.MaxAdapter(cfg)

    def test_short_under_limit(self):
        a = self._make_adapter()
        msg = "Hello, world!"
        chunks = a._split_outbound_text(msg)
        assert len(chunks) == 1
        assert chunks[0] == msg

    def test_exactly_at_limit(self):
        a = self._make_adapter()
        msg = "x" * 3900  # limit is 4000 - 100 = 3900
        chunks = a._split_outbound_text(msg)
        assert len(chunks) == 1
        assert len(chunks[0]) == 3900

    def test_two_paragraphs(self):
        a = self._make_adapter()
        para = "x" * 3000
        msg = f"{para}\n\n{para}"
        chunks = a._split_outbound_text(msg)
        assert len(chunks) == 2

    def test_many_small_paragraphs(self):
        a = self._make_adapter()
        paras = ["para" + str(i) for i in range(100)]
        msg = "\n\n".join(paras)
        chunks = a._split_outbound_text(msg)
        # All small paragraphs should fit in one chunk
        assert len(chunks) == 1

    def test_very_long_word(self):
        a = self._make_adapter()
        msg = "x" * 5000
        chunks = a._split_outbound_text(msg)
        assert len(chunks) >= 2
        for c in chunks:
            assert len(c) <= 3900

    def test_empty(self):
        a = self._make_adapter()
        chunks = a._split_outbound_text("")
        assert len(chunks) == 1
        assert chunks[0] == ""

    def test_multiline_block(self):
        a = self._make_adapter()
        block = "\n".join(["line" + str(i) for i in range(500)])
        chunks = a._split_outbound_text(block)
        assert len(chunks) >= 1
        for c in chunks:
            assert len(c) <= 3900


CODE_BLOCK = "```python\n" + ("print('x')\n" * 500) + "```"
LONG_WORD = "x" * 5000
PARAGRAPHS = "\n\n".join(f"Paragraph {i}: " + ("word " * 200) for i in range(4))
UNICODE = "Привет, мир! 👋 " * 600
TRAILING_WS = ("line\n\n\n" * 400) + "   \n\ntail"
BOUNDARY = ("a" * 3894) + "|" + ("b" * 3894) + "|" + ("c" * 3894)

LOSSLESS_CASES = {
    "plain": "a" * 7800,                 # the audit's exact reproduction
    "unicode": UNICODE,
    "paragraphs": PARAGRAPHS,
    "code_block": CODE_BLOCK,
    "long_word": LONG_WORD,
    "trailing_whitespace": TRAILING_WS,
    "boundary": BOUNDARY,
    "blank_lines_only": "\n" * 5000,
    "single_char_over_limit": "a" * 3901,
    "emoji_boundary": "🙂" * 4000,
}


class TestLosslessChunking:
    """CODE-02: chunking must not lose or invent characters."""

    def _make_adapter(self):
        from gateway.config import PlatformConfig
        cfg = PlatformConfig(enabled=True, token="tok")
        return adapter.MaxAdapter(cfg)

    @pytest.mark.parametrize("name", sorted(LOSSLESS_CASES))
    def test_split_concatenation_reproduces_source(self, name):
        content = LOSSLESS_CASES[name]
        a = self._make_adapter()
        chunks = a._split_outbound_text(content)
        assert "".join(chunks) == content

    @pytest.mark.parametrize("name", sorted(LOSSLESS_CASES))
    def test_split_respects_budget(self, name):
        content = LOSSLESS_CASES[name]
        a = self._make_adapter()
        for chunk in a._split_outbound_text(content):
            assert len(chunk) <= adapter.OUTBOUND_CHUNK_LIMIT

    @pytest.mark.parametrize("name", sorted(LOSSLESS_CASES))
    def test_numbered_chunks_reproduce_source(self, name):
        content = LOSSLESS_CASES[name]
        a = self._make_adapter()
        chunks = a._numbered_outbound_chunks(content)
        rebuilt = "".join(
            chunk.split(")\n", 1)[1] if chunk.startswith("(") and ")\n" in chunk[:12] else chunk
            for chunk in chunks
        )
        assert rebuilt == content

    @pytest.mark.parametrize("name", sorted(LOSSLESS_CASES))
    def test_numbered_chunks_fit_api_limit(self, name):
        content = LOSSLESS_CASES[name]
        a = self._make_adapter()
        chunks = a._numbered_outbound_chunks(content)
        assert chunks, "chunker must always return something to send"
        for chunk in chunks:
            assert len(chunk) <= adapter.MAX_MESSAGE_LENGTH

    def test_numbering_prefix_is_present_only_when_split(self):
        a = self._make_adapter()
        assert a._numbered_outbound_chunks("short") == ["short"]
        chunks = a._numbered_outbound_chunks("a" * 7800)
        assert len(chunks) == 3
        assert [c.split(")", 1)[0] + ")" for c in chunks] == ["(1/3)", "(2/3)", "(3/3)"]

    def test_paragraph_boundaries_are_preferred(self):
        a = self._make_adapter()
        msg = "\n\n".join(["x" * 1000] * 4)  # 4006 chars, needs 2 chunks
        chunks = a._split_outbound_text(msg)
        assert len(chunks) == 2
        assert "".join(chunks) == msg
        # the boundary lands on a blank line, not inside a paragraph
        assert chunks[0].endswith("\n\n")

    def test_no_transmitted_chunk_starts_with_blank_line(self):
        a = self._make_adapter()
        msg = ("x" * 3900) + "\n\n" + ("y" * 100)
        chunks = a._numbered_outbound_chunks(msg)
        assert len(chunks) == 2
        assert "".join(c.split(")\n", 1)[1] for c in chunks) == msg
        # the paragraph break travels with the chunk that already held the text
        assert all(not c.split(")\n", 1)[1].startswith("\n") for c in chunks[1:])
        assert len(chunks[0]) <= adapter.MAX_MESSAGE_LENGTH

    def test_long_word_is_cut_by_characters_losslessly(self):
        a = self._make_adapter()
        chunks = a._split_outbound_text(LONG_WORD)
        assert len(chunks) == 2
        assert chunks[0] == "x" * adapter.OUTBOUND_CHUNK_LIMIT
        assert "".join(chunks) == LONG_WORD

    def test_code_block_lines_are_not_rewritten(self):
        a = self._make_adapter()
        chunks = a._split_outbound_text(CODE_BLOCK)
        assert "".join(chunks) == CODE_BLOCK
        # the old splitter injected a space after every newline of a long block
        assert " print('x')" not in "".join(chunks)


class TestSendChunkingTransmission:
    """CODE-02: payloads put on the wire preserve the source text."""

    def _make_adapter_with_capture(self):
        from gateway.config import PlatformConfig
        cfg = PlatformConfig(enabled=True, token="tok")
        a = adapter.MaxAdapter(cfg)
        bodies: list[dict] = []

        async def _post(url, params=None, json=None):  # mirrors the httpx signature
            bodies.append(json)
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json = MagicMock(return_value={"message": {"message_id": "mid-1"}})
            return resp

        client = MagicMock()
        client.post = AsyncMock(side_effect=_post)
        a._http_client = client
        return a, bodies

    @staticmethod
    def _strip_prefixes(payloads):
        out = []
        for payload in payloads:
            if payload.startswith("(") and ")\n" in payload[:12]:
                payload = payload.split(")\n", 1)[1]
            out.append(payload)
        return "".join(out)

    async def test_send_7800_chars_is_lossless(self):
        # Audit baseline: 7800 input chars → 7788 useful output chars.
        content = "a" * 7800
        a, bodies = self._make_adapter_with_capture()
        result = await a.send("user:1", content)
        assert result.success
        payloads = [b["text"] for b in bodies]
        assert len(payloads) == 3
        assert self._strip_prefixes(payloads) == content

    @pytest.mark.parametrize("name", ["unicode", "paragraphs", "code_block", "long_word"])
    async def test_send_preserves_source_text(self, name):
        content = LOSSLESS_CASES[name]
        a, bodies = self._make_adapter_with_capture()
        await a.send("user:1", content)
        payloads = [b["text"] for b in bodies]
        expected = a._convert_markdown_tables(content)
        assert self._strip_prefixes(payloads) == expected

    async def test_every_transmitted_payload_fits_api_limit(self):
        a, bodies = self._make_adapter_with_capture()
        await a.send("user:1", UNICODE + CODE_BLOCK)
        assert bodies
        for body in bodies:
            assert len(body["text"]) <= adapter.MAX_MESSAGE_LENGTH
            assert body["format"] == "markdown"

    async def test_short_message_is_sent_unchanged(self):
        a, bodies = self._make_adapter_with_capture()
        await a.send("user:1", "short message")
        assert [b["text"] for b in bodies] == ["short message"]

    async def test_multibyte_text_measured_in_characters(self):
        # 2000 emoji = 2000 code points: chunking must be lossless for
        # multi-byte text as well.
        content = "🙂" * 2000
        a, bodies = self._make_adapter_with_capture()
        await a.send("user:1", content)
        assert self._strip_prefixes([b["text"] for b in bodies]) == content
