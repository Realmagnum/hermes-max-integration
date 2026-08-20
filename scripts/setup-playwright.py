#!/usr/bin/env python3
"""Idempotent Playwright setup for the MAX plugin table renderer.

Ensures the ``playwright`` package and its bundled Chromium browser are
installed for a given Python interpreter. When invoked by the plugin this
is the Hermes gateway venv python (``sys.executable``), which is exactly
the interpreter the plugin runs under — installing into the system python
instead would silently miss the gateway.

Safe to run repeatedly: the checks are cheap when everything is present,
so the script can be re-run on every upgrade or from cron.

Usage:
    python setup-playwright.py                # install what's missing
    python setup-playwright.py --check-only   # report only; exit 1 if missing
    python setup-playwright.py --python /path/to/python   # explicit interpreter
    python setup-playwright.py --quiet        # no output on success

Optional on Linux: ``playwright install --with-deps chromium`` installs
system libraries (apt) as well — run it manually if Chromium fails to
launch with missing shared libraries.

Exit codes:
    0 — everything already installed (or install succeeded)
    1 — something is missing and was not installed (--check-only / failure)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

PLAYWRIGHT_REQ = "playwright>=1.40"
BROWSER = "chromium"


def browsers_root() -> Path:
    """Directory where `playwright install` drops browsers."""
    override = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "ms-playwright"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "ms-playwright"
    return Path.home() / ".cache" / "ms-playwright"


def chromium_installed() -> bool:
    """True when the bundled Chromium (or headless shell) is present.

    Playwright installs per-revision dirs like ``chromium-1234`` and
    ``chromium_headless_shell-1234`` (headless shell ships with the
    regular ``chromium`` target since Playwright 1.49).
    """
    root = browsers_root()
    if not root.is_dir():
        return False
    return any(p.name.startswith("chromium") and p.is_dir() for p in root.iterdir())


def probe(py: str, code: str) -> str:
    """Run a snippet with the target interpreter; return trimmed output."""
    try:
        r = subprocess.run(
            [py, "-c", code], capture_output=True, text=True, timeout=120
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return (r.stdout or r.stderr).strip()


def playwright_installed(py: str) -> bool:
    """True when the target interpreter can import playwright."""
    return (
        probe(py, "import importlib.util; print(bool(importlib.util.find_spec('playwright')))")
        .lower()
        .endswith("true")
    )


def run(cmd: list[str], quiet: bool = False) -> int:
    """Run a subprocess, streaming output unless quiet; return exit code."""
    if quiet:
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"command failed (rc={r.returncode}): {' '.join(cmd)}")
            print((r.stderr or r.stdout).strip()[-2000:])
        return r.returncode
    return subprocess.run(cmd).returncode


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__.split("Usage:")[0].strip(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--check-only",
        action="store_true",
        help="report what is missing and exit (1 if anything is missing)",
    )
    ap.add_argument(
        "--python",
        default=sys.executable,
        help="target Python interpreter (default: the one running this script)",
    )
    ap.add_argument("--quiet", action="store_true", help="no output on success")
    args = ap.parse_args()

    py = args.python
    missing = []
    if not playwright_installed(py):
        missing.append("package (playwright)")
    if not chromium_installed():
        missing.append(f"browser ({BROWSER})")

    if args.check_only:
        if missing:
            print("MISSING: " + ", ".join(missing))
            print(f"Fix: {py} {Path(__file__).name}")
            return 1
        print("OK: playwright + Chromium present")
        return 0

    if not missing:
        if not args.quiet:
            print("OK: playwright + Chromium already installed")
        return 0

    if "package (playwright)" in missing:
        print(f"Installing {PLAYWRIGHT_REQ} into {py} ...")
        if run([py, "-m", "pip", "install", "-q", PLAYWRIGHT_REQ], quiet=args.quiet) != 0:
            return 1

    if "browser (chromium)" in missing:
        print("Installing Chromium (~115 MB, one-time) ...")
        if run([py, "-m", "playwright", "install", BROWSER], quiet=args.quiet) != 0:
            return 1

    # Re-verify (pip can be stale, browser install can be interrupted)
    still_missing = []
    if not playwright_installed(py):
        still_missing.append("package (playwright)")
    if not chromium_installed():
        still_missing.append(f"browser ({BROWSER})")
    if still_missing:
        print("STILL MISSING: " + ", ".join(still_missing))
        return 1

    print("Done: playwright + Chromium ready")
    return 0


if __name__ == "__main__":
    sys.exit(main())
