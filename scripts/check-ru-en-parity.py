#!/usr/bin/env python3
"""RU/EN documentation parity checker for the Max plugin.

The repository is bilingual by policy (see AGENTS.md): every `*.md` file is
written in Russian and must have an `*_EN.md` counterpart with an *identical
structure*. Translation wording of course differs — this checker only guards
the mechanical, language-independent invariants, so it cannot produce a false
alarm just because a sentence is translated:

  * the heading tree (levels and order) is the same;
  * markdown tables have the same shape (rows x columns);
  * fenced code blocks have the same languages;
  * the set of `MAX_*` / `HERMES_*` environment tokens is the same;
  * links stay inside their locale (`*_EN.md` must not link to a Russian-only
    file, and a Russian file must not link to an `*_EN.md` file).

Exit code 0 = in sync, 1 = drift found (details on stdout).

Usage:
    python3 scripts/check-ru-en-parity.py [--root .]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
TOKEN = re.compile(r"\b(?:MAX|HERMES)_[A-Z0-9_]+\b")
FENCE_OPEN = re.compile(r"^```(\w*)\s*$")
FENCE_CLOSE = re.compile(r"^```\s*$")

# Pairs that are known to be out of sync and are tracked separately. Keeping
# them here (instead of silently skipping the whole check) means the list is
# visible and shrinks as the debt is paid off.
KNOWN_DRIFT = {
    # The EN translation predates the RU Roadmap section (114 RU lines vs 79 EN).
    "docs/refactor-plan.md",
    # Historical changelog has drifted across releases.
    "CHANGELOG.md",
    # Audit backlogs carry cross-language links.
    "BACKLOG.md",
    "RELEASE_BACKLOG_2.10.md",
}

# Directory names never scanned for documentation pairs.
SKIP_DIRS = {".git", ".github", "assets", "__pycache__", ".venv", "node_modules"}


def split_cells(line: str) -> list[str]:
    """Split a markdown table row on unescaped pipes only."""
    return re.split(r"(?<!\\)\|", line.strip().strip("|"))


def scan(text: str):
    """Return (headings, table_shapes, fence_langs) for one markdown file."""
    headings: list[int] = []
    tables: list[tuple[int, ...]] = []
    fences: list[str] = []
    rows: list[int] = []
    in_fence = False
    for line in text.splitlines():
        if in_fence:
            if FENCE_CLOSE.match(line):
                in_fence = False
            continue
        m = FENCE_OPEN.match(line)
        if m:
            fences.append(m.group(1))
            in_fence = True
            rows = []
            continue
        m = HEADING.match(line)
        if m:
            headings.append(len(m.group(1)))
            continue
        if line.lstrip().startswith("|"):
            rows.append(len(split_cells(line)))
        elif rows:
            tables.append(tuple(rows))
            rows = []
    if rows:
        tables.append(tuple(rows))
    return headings, tables, fences


def links(text: str) -> set[str]:
    return {t for t in LINK.findall(text) if not t.startswith(("http://", "https://", "#"))}


def en_variant(target: str) -> str | None:
    return target[:-3] + "_EN.md" if target.endswith(".md") else None


def find_pairs(root: Path) -> list[tuple[Path, Path]]:
    pairs = []
    for path in sorted(root.rglob("*.md")):
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if path.name.endswith("_EN.md"):
            continue
        counterpart = path.with_name(path.stem + "_EN.md")
        if counterpart.exists():
            pairs.append((path, counterpart))
    return pairs


def check_pair(ru_path: Path, en_path: Path, root: Path) -> list[str]:
    ru, en = ru_path.read_text(encoding="utf-8"), en_path.read_text(encoding="utf-8")
    rel = ru_path.relative_to(root)
    problems: list[str] = []

    h_ru, t_ru, f_ru = scan(ru)
    h_en, t_en, f_en = scan(en)

    if h_ru != h_en:
        problems.append(f"heading levels differ: {h_ru} != {h_en}")
    if t_ru != t_en:
        problems.append(f"table shapes differ: {t_ru} != {t_en}")
    if f_ru != f_en:
        problems.append(f"code-fence languages differ: {f_ru} != {f_en}")

    tok_ru, tok_en = set(TOKEN.findall(ru)), set(TOKEN.findall(en))
    if tok_ru != tok_en:
        problems.append(
            f"env tokens differ: RU-only={sorted(tok_ru - tok_en)} EN-only={sorted(tok_en - tok_ru)}"
        )

    for target in sorted(links(ru)):
        if "_EN" in target:
            problems.append(f"RU file links to a translated file: {target}")
    for target in sorted(links(en)):
        if "_EN" in target:
            continue
        variant = en_variant(target)
        if variant and (root / variant).exists():
            problems.append(f"EN file links to a Russian-only file: {target} (use {variant})")

    return [f"{rel}: {p}" for p in problems]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="repository root (default: cwd)")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    checked = skipped = 0
    failures: list[str] = []

    for ru_path, en_path in find_pairs(root):
        rel = ru_path.relative_to(root).as_posix()
        if rel in KNOWN_DRIFT:
            skipped += 1
            continue
        checked += 1
        failures.extend(check_pair(ru_path, en_path, root))

    for line in failures:
        print(f"DRIFT {line}")
    print(f"RU/EN pairs checked: {checked} in sync, {skipped} known-drift, {len(failures)} problems")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
