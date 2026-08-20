"""Tests for markdown table conversion to MAX-compatible format."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

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
    """Cache-hit path of _render_table_as_image: existing PNG is reused.

    The cache key is engine-aware (``html`` vs ``pillow``), so switching
    renderers never serves stale images.
    """

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
        inst = await self._make_adapter(tmp_path)
        cached = inst._table_cache_path(self.TABLE_LINES, "html")
        cached.write_bytes(b"fake-png-bytes")

        with patch("max.mixins.table_renderer._playwright_importable", return_value=True):
            token = await inst._render_table_as_image(self.TABLE_LINES)

        assert token == "token-123"
        inst._upload.assert_awaited_once_with(str(cached), "image")

    @pytest.mark.asyncio
    async def test_engine_switch_invalidates_cache(self, tmp_path):
        """A Pillow-rendered PNG must NOT be served once Playwright is available.

        Regression for the stale-cache bug: after upgrading to the Playwright
        renderer, old Pillow PNGs with the same table text were still served.
        """
        inst = await self._make_adapter(tmp_path)
        pillow_cached = inst._table_cache_path(self.TABLE_LINES, "pillow")
        pillow_cached.write_bytes(b"old-pillow-png")

        with (
            patch("max.mixins.table_renderer._playwright_importable", return_value=True),
            patch(
                "max.mixins.table_renderer.TableRendererMixin._render_table_html_png",
                new=AsyncMock(return_value=True),
            ),
        ):
            token = await inst._render_table_as_image(self.TABLE_LINES)

        html_cached = inst._table_cache_path(self.TABLE_LINES, "html")
        assert token == "token-123"
        # The old pillow file was ignored; the html-keyed file was uploaded.
        inst._upload.assert_awaited_once_with(str(html_cached), "image")

    @pytest.mark.asyncio
    async def test_cache_miss_html_renders_and_uploads(self, tmp_path):
        inst = await self._make_adapter(tmp_path)

        with (
            patch("max.mixins.table_renderer._playwright_importable", return_value=True),
            patch(
                "max.mixins.table_renderer.TableRendererMixin._render_table_html_png",
                new=AsyncMock(return_value=True),
            ),
        ):
            token = await inst._render_table_as_image(self.TABLE_LINES)

        assert token == "token-123"
        inst._upload.assert_awaited_once()
        uploaded_path = inst._upload.await_args.args[0]
        assert Path(uploaded_path).name == inst._table_cache_path(self.TABLE_LINES, "html").name

    @pytest.mark.asyncio
    async def test_html_failure_falls_back_to_pillow_key(self, tmp_path):
        """When the Playwright render fails, the Pillow fallback re-keys the cache."""
        inst = await self._make_adapter(tmp_path)

        with (
            patch("max.mixins.table_renderer._playwright_importable", return_value=True),
            patch(
                "max.mixins.table_renderer.TableRendererMixin._render_table_html_png",
                new=AsyncMock(return_value=False),
            ),
        ):
            token = await inst._render_table_as_image(self.TABLE_LINES)

        assert token == "token-123"
        inst._upload.assert_awaited_once()
        uploaded_path = inst._upload.await_args.args[0]
        assert Path(uploaded_path).name == inst._table_cache_path(self.TABLE_LINES, "pillow").name

    @pytest.mark.asyncio
    async def test_pillow_engine_uses_pillow_key(self, tmp_path):
        """Without playwright the cache is keyed to the pillow engine."""
        inst = await self._make_adapter(tmp_path)

        with patch("max.mixins.table_renderer._playwright_importable", return_value=False):
            token = await inst._render_table_as_image(self.TABLE_LINES)

        assert token == "token-123"
        inst._upload.assert_awaited_once()
        uploaded_path = inst._upload.await_args.args[0]
        assert Path(uploaded_path).name == inst._table_cache_path(self.TABLE_LINES, "pillow").name


class TestPlaywrightAutoInstall:
    """MAX_AUTO_INSTALL_PLAYWRIGHT=true — one-time setup via the bundled script."""

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
    async def test_auto_install_runs_setup_once_and_writes_marker(self, tmp_path, monkeypatch):
        inst = await self._make_adapter(tmp_path)
        marker = tmp_path / ".playwright-ready"
        runs = []

        def fake_run(cmd, **kw):
            runs.append(cmd)
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        monkeypatch.setattr("max.mixins.table_renderer.subprocess.run", fake_run)
        monkeypatch.setattr("max.mixins.table_renderer._playwright_importable", lambda: False)
        monkeypatch.setattr("max.mixins.table_renderer._chromium_browsers_installed", lambda: False)

        await inst._ensure_playwright_ready()
        await inst._ensure_playwright_ready()  # second call must not re-run setup

        assert marker.exists()
        assert len(runs) == 1
        assert str(runs[0][1]).endswith("setup-playwright.py")

    @pytest.mark.asyncio
    async def test_marker_skips_setup_after_failure(self, tmp_path, monkeypatch):
        """A failed setup leaves no marker, so the next render retries."""
        inst = await self._make_adapter(tmp_path)
        marker = tmp_path / ".playwright-ready"
        calls = {"n": 0}

        def failing_run(cmd, **kw):
            calls["n"] += 1
            return SimpleNamespace(returncode=1, stdout="", stderr="boom")

        monkeypatch.setattr("max.mixins.table_renderer.subprocess.run", failing_run)
        monkeypatch.setattr("max.mixins.table_renderer._playwright_importable", lambda: False)
        monkeypatch.setattr("max.mixins.table_renderer._chromium_browsers_installed", lambda: False)

        await inst._ensure_playwright_ready()
        await inst._ensure_playwright_ready()  # no marker → retried

        assert not marker.exists()
        assert calls["n"] == 2

    @pytest.mark.asyncio
    async def test_already_installed_writes_marker_without_subprocess(self, tmp_path, monkeypatch):
        inst = await self._make_adapter(tmp_path)
        marker = tmp_path / ".playwright-ready"

        def no_run(*a, **kw):
            raise AssertionError("subprocess must not be called when everything is present")

        monkeypatch.setattr("max.mixins.table_renderer.subprocess.run", no_run)
        monkeypatch.setattr("max.mixins.table_renderer._playwright_importable", lambda: True)
        monkeypatch.setattr("max.mixins.table_renderer._chromium_browsers_installed", lambda: True)

        await inst._ensure_playwright_ready()

        assert marker.exists()

    @pytest.mark.asyncio
    async def test_flag_gated_render_with_ready_env(self, tmp_path, monkeypatch):
        """With the flag on and everything installed: no subprocess, normal cache hit."""
        inst = await self._make_adapter(tmp_path)
        cached = inst._table_cache_path(self.TABLE_LINES, "html")
        cached.write_bytes(b"fake-png-bytes")

        def no_run(*a, **kw):
            raise AssertionError("subprocess must not be called")

        monkeypatch.setenv("MAX_AUTO_INSTALL_PLAYWRIGHT", "true")
        monkeypatch.setattr("max.mixins.table_renderer.subprocess.run", no_run)
        monkeypatch.setattr("max.mixins.table_renderer._playwright_importable", lambda: True)
        monkeypatch.setattr("max.mixins.table_renderer._chromium_browsers_installed", lambda: True)

        token = await inst._render_table_as_image(self.TABLE_LINES)

        assert token == "token-123"
        inst._upload.assert_awaited_once_with(str(cached), "image")
