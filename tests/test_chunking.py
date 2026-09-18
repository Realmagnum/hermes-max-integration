"""Tests for message chunking in detail.

`TestSplitOutboundText` covers the splitter itself; `TestChunkedSendPayload`
covers what a long answer actually puts on the wire, which is where CODE-02
lives (the per-chunk "(i/n)" prefix truncating the tail of a full chunk).
"""

import re

import adapter

ACCEPT_AFFIX = re.compile(r"^\(\d+/\d+\)\n")
LIMIT = 3900  # MAX_MESSAGE_LENGTH - 100


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
        msg = "x" * LIMIT
        chunks = a._split_outbound_text(msg)
        assert len(chunks) == 1
        assert chunks[0] == msg

    def test_one_char_over_limit_splits_without_loss(self):
        a = self._make_adapter()
        msg = "x" * (LIMIT + 1)
        chunks = a._split_outbound_text(msg)
        assert len(chunks) == 2
        assert "".join(chunks) == msg

    def test_two_paragraphs(self):
        a = self._make_adapter()
        para = "x" * 3000
        msg = f"{para}\n\n{para}"
        chunks = a._split_outbound_text(msg)
        assert chunks == [para, para]

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
        # No word break available → hard split at the limit: 3900 + 1100
        assert [len(c) for c in chunks] == [LIMIT, 5000 - LIMIT]
        assert "".join(chunks) == msg
        for c in chunks:
            assert len(c) <= LIMIT

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
            assert len(c) <= LIMIT
        # every source line must survive somewhere in the output
        joined = "\n".join(chunks)
        for i in (0, 1, 250, 499):
            assert f"line{i}" in joined


class TestChunkedSendPayload:
    """What a multi-chunk `send()` actually puts on the wire."""

    async def test_every_chunk_targets_the_same_chat(self, make_adapter, max_api):
        a = make_adapter()

        result = await a.send("user:42", "x" * 5000)

        assert result.success is True
        reqs = max_api.calls("POST", "/messages")
        assert len(reqs) == 2
        for req in reqs:
            assert max_api.params(req) == {"user_id": "42"}
            assert max_api.json_body(req)["text"].startswith("(")

    async def test_chunk_prefixes_number_the_message(self, make_adapter, max_api):
        a = make_adapter()

        await a.send("user:42", "x" * 5000)

        texts = [max_api.json_body(r)["text"] for r in max_api.calls("POST", "/messages")]
        assert texts[0].startswith("(1/2)\n")
        assert texts[1].startswith("(2/2)\n")
        assert all(len(t) <= 4000 for t in texts)
        # Nothing but the payload plus the numeric prefix — no injected prose.
        assert all(ACCEPT_AFFIX.sub("", t).strip("x") == "" for t in texts)

    async def test_single_chunk_is_sent_without_prefix(self, make_adapter, max_api):
        a = make_adapter()

        await a.send("user:42", "short answer")

        reqs = max_api.calls("POST", "/messages")
        assert len(reqs) == 1
        assert max_api.json_body(reqs[0])["text"] == "short answer"
