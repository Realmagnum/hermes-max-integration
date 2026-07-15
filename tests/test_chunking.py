"""Tests for message chunking in detail."""

from unittest.mock import MagicMock

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
