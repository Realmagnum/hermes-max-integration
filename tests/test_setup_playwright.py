"""Playwright setup must check the exact package/browser in the target Python."""

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "setup-playwright.py"
_spec = importlib.util.spec_from_file_location("setup_playwright", _SCRIPT)
assert _spec and _spec.loader
setup_playwright = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(setup_playwright)


@pytest.mark.parametrize("version,expected", [("1.62.0", True), ("1.63.0", False), ("", False)])
def test_exact_package_pin(monkeypatch, version, expected):
    calls = []
    def probe(py, code):
        calls.append((py, code))
        return version
    monkeypatch.setattr(setup_playwright, "probe", probe)
    assert setup_playwright.playwright_installed("target-python") is expected
    assert calls[0][0] == "target-python"
    assert "metadata.version('playwright')" in calls[0][1]


@pytest.mark.parametrize("response,expected", [("True", True), ("False", False), ("error True", False)])
def test_browser_checks_target_revision(monkeypatch, response, expected):
    calls = []
    def probe(py, code):
        calls.append((py, code))
        return response
    monkeypatch.setattr(setup_playwright, "probe", probe)
    assert setup_playwright.chromium_installed("target-python") is expected
    assert calls[0][0] == "target-python"
    assert "chromium.executable_path" in calls[0][1]
    assert "is_file()" in calls[0][1]


def test_check_only_does_not_install(monkeypatch):
    monkeypatch.setattr("sys.argv", [str(_SCRIPT), "--check-only"])
    monkeypatch.setattr(setup_playwright, "playwright_installed", lambda py: False)
    monkeypatch.setattr(setup_playwright, "chromium_installed", lambda py: False)
    def forbidden(*args, **kwargs):
        pytest.fail("check-only must not install")
    monkeypatch.setattr(setup_playwright, "run", forbidden)
    assert setup_playwright.main() == 1


def test_package_upgrade_rechecks_browser_revision(monkeypatch):
    monkeypatch.setattr("sys.argv", [str(_SCRIPT), "--python", "target-python"])
    packages = iter([False, True])
    browsers = iter([True, False, True])
    monkeypatch.setattr(setup_playwright, "playwright_installed", lambda py: next(packages))
    monkeypatch.setattr(setup_playwright, "chromium_installed", lambda py: next(browsers))
    commands = []
    monkeypatch.setattr(setup_playwright, "run", lambda cmd, **kw: commands.append(cmd) or 0)
    assert setup_playwright.main() == 0
    assert commands == [
        ["target-python", "-m", "pip", "install", "-q", "playwright==1.62.0"],
        ["target-python", "-m", "playwright", "install", "chromium"],
    ]


def test_resolver_failure_stops_browser_install(monkeypatch):
    monkeypatch.setattr("sys.argv", [str(_SCRIPT)])
    monkeypatch.setattr(setup_playwright, "playwright_installed", lambda py: False)
    monkeypatch.setattr(setup_playwright, "chromium_installed", lambda py: False)
    commands = []
    monkeypatch.setattr(setup_playwright, "run", lambda cmd, **kw: commands.append(cmd) or 1)
    assert setup_playwright.main() == 1
    assert len(commands) == 1


def test_missing_interpreter_is_not_installed():
    assert not setup_playwright.playwright_installed("definitely-not-a-python-exe")
