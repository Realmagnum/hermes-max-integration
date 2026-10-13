"""Execute Desktop contribution behavior using Node's dependency-free harness."""

import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("node") is None, reason="Desktop behavior harness requires Node.js")
def test_desktop_locale_behavior():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [shutil.which("node"), str(root / "tests" / "desktop_locale_harness.cjs")],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
