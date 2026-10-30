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
import subprocess
import sys
from pathlib import Path

PLAYWRIGHT_MIN = (1, 62)  # floor: the oldest core pin this plugin supports
PLAYWRIGHT_MAX_MAJOR = 2  # ceiling: next major (core pins an exact 1.x)
PLAYWRIGHT_REQ = f"playwright>={PLAYWRIGHT_MIN[0]}.{PLAYWRIGHT_MIN[1]},<{PLAYWRIGHT_MAX_MAJOR}"
BROWSER = "chromium"


def version_supported(text: str) -> bool:
    """True when a reported playwright version satisfies the declared range.

    The plugin no longer pins an exact playwright release: core pins the same
    distribution exactly (its ``google-meet`` extra), and two exact pins cannot
    co-install. Any 1.x at or above the floor is accepted, so installing the
    package never fights the version the gateway already has.
    """
    parts = []
    for chunk in (text or "").strip().split(".")[:3]:
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else -1)
    if not parts or parts[0] < 0:
        return False
    version = tuple(parts + [0] * (3 - len(parts)))
    return PLAYWRIGHT_MIN + (0,) <= version < (PLAYWRIGHT_MAX_MAJOR,)


def chromium_installed(py: str) -> bool:
    """Check the target package's exact browser revision, not stale cache dirs."""
    return probe(
        py,
        "from pathlib import Path; from playwright.sync_api import sync_playwright; "
        "p = sync_playwright().start(); "
        "print(Path(p.chromium.executable_path).is_file()); p.stop()",
    ).lower() == "true"


def probe(py: str, code: str) -> str:
    """Run a snippet with the target interpreter; return trimmed output."""
    try:
        r = subprocess.run(
            [py, "-c", code], capture_output=True, text=True, timeout=120, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return (r.stdout or r.stderr).strip()


def playwright_installed(py: str) -> bool:
    """True when the target interpreter has a playwright inside the declared range."""
    return version_supported(
        probe(
            py, "import importlib.metadata; print(importlib.metadata.version('playwright'))"
        )
    )


def run(cmd: list[str], quiet: bool = False) -> int:
    """Run a subprocess, streaming output unless quiet; return exit code."""
    if quiet:
        r = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if r.returncode != 0:
            print(f"command failed (rc={r.returncode}): {' '.join(cmd)}")
            print((r.stderr or r.stdout).strip()[-2000:])
        return r.returncode
    return subprocess.run(cmd, check=False).returncode


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
    if not chromium_installed(py):
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

    # A package upgrade changes Chromium revision even if an old browser was
    # present at the initial probe. Re-probe after installing the declared range.
    if not chromium_installed(py):
        print("Installing Chromium (~115 MB, one-time) ...")
        if run([py, "-m", "playwright", "install", BROWSER], quiet=args.quiet) != 0:
            return 1

    # Re-verify (pip can be stale, browser install can be interrupted)
    still_missing = []
    if not playwright_installed(py):
        still_missing.append("package (playwright)")
    if not chromium_installed(py):
        still_missing.append(f"browser ({BROWSER})")
    if still_missing:
        print("STILL MISSING: " + ", ".join(still_missing))
        return 1

    print("Done: playwright + Chromium ready")
    return 0


if __name__ == "__main__":
    sys.exit(main())
