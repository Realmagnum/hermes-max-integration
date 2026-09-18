#!/usr/bin/env python3
"""Guard published version/test claims against the repository state (DOC-09).

Two documentation claims are checked mechanically, because both have already
drifted in this repo (pyproject said 2.1.4 while plugin.yaml said 2.9.0; the
README advertised 126 and 94 tests in different tables):

  * **Version.** ``plugin.yaml`` is the single source of truth — it is what
    Hermes shows for the plugin and what ``scripts/release.sh`` reads. The
    ``pyproject.toml`` version and the newest ``CHANGELOG*`` heading must
    mirror it.
  * **Test count.** Every ``<N> tests`` / ``<N> тестов`` claim in ``README.md``
    and ``README_EN.md`` must equal the number of tests pytest actually
    collects (``pytest --collect-only``), never a count typed by hand.

Exit code 1 with a report when a claim drifts; 0 when everything matches.
Run from anywhere: ``python scripts/check-doc-claims.py``.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README_FILES = ("README.md", "README_EN.md")
CHANGELOG_FILES = ("CHANGELOG.md", "CHANGELOG_EN.md")

# "<N> tests" / "<N> тестов" / "<N> теста" — the published test-count claims.
TEST_CLAIM_RE = re.compile(r"(\d+)\s+(?:тест\w*|tests?)\b", re.IGNORECASE)
PLUGIN_VERSION_RE = re.compile(r"^version:\s*(\S+)", re.MULTILINE)
CHANGELOG_VERSION_RE = re.compile(r"^##\s*\[?v?([0-9][^\s\]]*)\]?", re.MULTILINE)


def plugin_version() -> str:
    text = (ROOT / "plugin.yaml").read_text(encoding="utf-8")
    match = PLUGIN_VERSION_RE.search(text)
    if not match:
        raise SystemExit("plugin.yaml: no top-level `version:` key found")
    return match.group(1).strip()


def pyproject_version() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def changelog_version(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    match = CHANGELOG_VERSION_RE.search(text)
    if not match:
        raise SystemExit(f"{path.name}: no `## [x.y.z]` heading found")
    return match.group(1).strip().lstrip("v")


def collected_test_count() -> int:
    """Tests pytest actually collects — the only accepted source for the count."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "--collect-only", "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    match = re.search(r"(\d+)\s+tests? collected", proc.stdout)
    if not match:
        sys.stderr.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        raise SystemExit("could not parse `pytest --collect-only` output")
    return int(match.group(1))


def test_claims() -> list[tuple[str, int]]:
    claims: list[tuple[str, int]] = []
    for name in README_FILES:
        text = (ROOT / name).read_text(encoding="utf-8")
        claims.extend((name, int(n)) for n in TEST_CLAIM_RE.findall(text))
    return claims


def main() -> int:
    failures: list[str] = []

    version = plugin_version()
    py_version = pyproject_version()
    if py_version != version:
        failures.append(
            f"pyproject.toml version={py_version!r} does not mirror plugin.yaml={version!r}"
        )
    for name in CHANGELOG_FILES:
        cl_version = changelog_version(ROOT / name)
        if cl_version != version:
            failures.append(
                f"{name} newest heading {cl_version!r} does not match plugin.yaml={version!r}"
            )

    count = collected_test_count()
    claims = test_claims()
    if not claims:
        failures.append("no `<N> tests` claims found in " + ", ".join(README_FILES))
    for src, claimed in claims:
        if claimed != count:
            failures.append(
                f"{src} claims {claimed} tests but pytest collects {count}"
            )

    print(f"plugin.yaml version : {version}")
    print(f"pyproject.toml      : {py_version}  (mirrors plugin.yaml)")
    for name in CHANGELOG_FILES:
        print(f"{name:19s} : {changelog_version(ROOT / name)}")
    print(f"pytest collection   : {count} tests")
    print(f"README test claims  : {len(claims)}")
    for src, claimed in claims:
        print(f"  {src}: {claimed} tests")

    if failures:
        print("\nFAILED:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("\nOK: all documented versions and test counts are current.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
