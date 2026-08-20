"""Tests for scripts/setup-playwright.py (pure helper functions).

The script itself is a standalone CLI; here we import it by file path and
exercise its pure logic (browser detection, interpreter probing) without
running pip or downloading anything.
"""

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "setup-playwright.py"
_spec = importlib.util.spec_from_file_location("setup_playwright", _SCRIPT)
assert _spec and _spec.loader, f"cannot load {_SCRIPT}"
setup_playwright = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(setup_playwright)


class TestBrowserDetection:
    def test_chromium_dir_detected(self, tmp_path, monkeypatch):
        (tmp_path / "chromium-1234").mkdir()
        (tmp_path / "ffmpeg-1011").mkdir()
        monkeypatch.setattr(setup_playwright, "browsers_root", lambda: tmp_path)
        assert setup_playwright.chromium_installed() is True

    def test_headless_shell_counts_as_installed(self, tmp_path, monkeypatch):
        (tmp_path / "chromium_headless_shell-1234").mkdir()
        monkeypatch.setattr(setup_playwright, "browsers_root", lambda: tmp_path)
        assert setup_playwright.chromium_installed() is True

    def test_empty_root_reports_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(setup_playwright, "browsers_root", lambda: tmp_path)
        assert setup_playwright.chromium_installed() is False

    def test_nonexistent_root_reports_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            setup_playwright, "browsers_root", lambda: tmp_path / "nope"
        )
        assert setup_playwright.chromium_installed() is False


class TestProbe:
    def test_playwright_installed_in_running_interpreter(self):
        """The interpreter running the tests (hermes venv) has playwright."""
        import sys

        assert setup_playwright.playwright_installed(sys.executable) is True

    def test_probe_returns_false_for_missing_interpreter(self):
        """A non-existent interpreter → probe returns '' → not installed."""
        assert (
            setup_playwright.playwright_installed("definitely-not-a-python-exe")
            is False
        )
