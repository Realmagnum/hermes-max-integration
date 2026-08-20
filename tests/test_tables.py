"""Tests for markdown table conversion to MAX-compatible format."""

from unittest.mock import AsyncMock

import pytest

import adapter


class TestConvertMarkdownTables:
    """Tests for _convert_markdown_tables."""

    def test_simple_table(self):
        text = """Some text before.

| Name | Value | Status |
|------|-------|--------|
| foo  | 42    | ok     |
| bar  | 99    | fail   |

After text."""

        result = adapter.MaxAdapter._convert_markdown_tables(text)

        # Should render as backtick-wrapped monospace lines
        assert "`-------" in result
        assert "`| Name" in result
        assert "`| foo" in result
        assert "Value" in result
        assert "Status" in result
        assert "bar" in result
        # Original text preserved
        assert "Some text before" in result
        assert "After text" in result
        # Original pipe table syntax should be gone
        assert "|------|" not in result
        # No fenced code blocks or HTML
        assert "```" not in result
        assert "<pre>" not in result

    def test_no_table_unchanged(self):
        text = "Just plain text without any tables."
        result = adapter.MaxAdapter._convert_markdown_tables(text)
        assert result == text

    def test_multiple_tables(self):
        text = """First table:

| A | B |
|---|---|
| 1 | 2 |

Middle text.

| X | Y |
|---|---|
| 3 | 4 |"""

        result = adapter.MaxAdapter._convert_markdown_tables(text)

        # Both tables converted — each line backtick-wrapped
        assert result.count("`-------") >= 4  # 2 tables × (top + bottom)
        assert "1" in result
        assert "2" in result
        assert "3" in result
        assert "4" in result
        assert "Middle text" in result
        assert "First table" in result

    def test_wide_columns_capped(self):
        text = """| VeryLongColumnNameThatExceeds | Short |
|-------------------------------|-------|
| very_long_value_here_too      | ok    |"""

        result = adapter.MaxAdapter._convert_markdown_tables(text)

        # Long tokens are NOT truncated — ZWSP soft breaks (every 15 chars)
        # keep them wrappable on mobile (table-renderer fix d7e003c / 2d46046)
        assert "VeryLongColumnN\u200bameThatExceeds" in result
        assert "very_long_value\u200b_here_too" in result
        assert "Short" in result
        assert "ok" in result

    def test_single_column_table(self):
        text = """| Item |
|------|
| one  |
| two  |"""

        result = adapter.MaxAdapter._convert_markdown_tables(text)

        # Backtick-wrapped separator line
        assert "`-------" in result
        assert "`| Item" in result
        assert "`| one" in result
        assert "two" in result

    def test_markdown_formatting_in_cells(self):
        text = """| Feature | Status |
|---------|--------|
| **Bold** | ✅ |
| *Italic* | ❌ |"""

        result = adapter.MaxAdapter._convert_markdown_tables(text)

        # Markdown formatting in cells is preserved
        assert "**Bold**" in result
        assert "*Italic*" in result
        assert "✅" in result

    def test_empty_cells(self):
        text = """| A | B | C |
|---|---|---|---|
| 1 |   | 3 |
|   | 2 |   |"""

        result = adapter.MaxAdapter._convert_markdown_tables(text)

        # Backtick-wrapped empty cells
        assert "`-------" in result
        assert "1" in result
        assert "3" in result
        assert "2" in result


class TestRenderTableAsImageCache:
    """Cache-hit path of _render_table_as_image: existing PNG is reused."""

    TABLE_LINES = (
        "| Name | Value |",
        "|------|-------|",
        "| foo  | 42    |",
    )

    async def _make_adapter(self, tmp_path):
        inst = object.__new__(adapter.MaxAdapter)
        inst._table_image_dir = tmp_path
        inst._table_as_image = True
        inst._upload = AsyncMock(return_value="token-123")
        inst._http_client = AsyncMock()
        return inst

    @pytest.mark.asyncio
    async def test_cache_hit_reuses_existing_png(self, tmp_path):
        import hashlib

        digest = hashlib.md5(str(self.TABLE_LINES).encode(), usedforsecurity=False).hexdigest()[:12]
        cached = tmp_path / f"table_{digest}.png"
        cached.write_bytes(b"fake-png-bytes")

        inst = await self._make_adapter(tmp_path)
        token = await inst._render_table_as_image(self.TABLE_LINES)

        assert token == "token-123"
        inst._upload.assert_awaited_once_with(str(cached), "image")

    @pytest.mark.asyncio
    async def test_cache_miss_renders_and_uploads(self, tmp_path):
        inst = await self._make_adapter(tmp_path)
        token = await inst._render_table_as_image(self.TABLE_LINES)

        # Render path produced a file and uploaded it; token returned.
        assert token == "token-123"
        assert inst._upload.await_count == 1
        uploaded_path = inst._upload.await_args.args[0]
        assert uploaded_path.endswith(".png")
