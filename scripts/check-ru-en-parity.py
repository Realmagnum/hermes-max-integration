#!/usr/bin/env python3
"""Check bilingual Markdown document structure and locale-correct links."""
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

# Overview, history, or operations docs intentionally differ in structure.
# They are exempt only from structural parity, never from locale-link checks.
STRUCTURE_EXEMPT = {
    "README.md",
    "docs/refactor-plan.md",
    "CHANGELOG.md",
    "BACKLOG.md",
    "AGENTS.md",
}
SKIP_DIRS = {".git", ".github", "assets", "__pycache__", ".venv", "node_modules"}


def split_cells(line: str) -> list[str]:
    return re.split(r"(?<!\\)\|", line.strip().strip("|"))


def scan(text: str):
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
        match = FENCE_OPEN.match(line)
        if match:
            fences.append(match.group(1))
            in_fence = True
            rows = []
            continue
        match = HEADING.match(line)
        if match:
            headings.append(len(match.group(1)))
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
    return {t for t in LINK.findall(text) if not t.startswith(("http://", "https://", "#", "mailto:"))}


def find_pairs(root: Path) -> list[tuple[Path, Path]]:
    pairs = []
    for en_path in sorted(root.rglob("*.md")):
        if any(part in SKIP_DIRS for part in en_path.relative_to(root).parts):
            continue
        if en_path.name.endswith("_RU.md"):
            continue
        ru_path = en_path.with_name("README_RU.md") if en_path.name == "README.md" else en_path.with_name(en_path.stem + "_RU.md")
        if ru_path.exists():
            pairs.append((ru_path, en_path))
    return pairs


def locale_problems(text: str, is_ru: bool, path: Path, root: Path) -> list[str]:
    result = []
    for target in sorted(links(text)):
        target_path = (path.parent / target.split("#", 1)[0]).resolve()
        if target_path.suffix.lower() != ".md":
            continue
        # Language-switch links to the paired document itself are intentional.
        if is_ru:
            expected_peer = path.with_name("README.md") if path.name == "README_RU.md" else path.with_name(path.stem.removesuffix("_RU") + ".md")
        else:
            expected_peer = path.with_name("README_RU.md") if path.name == "README.md" else path.with_name(path.stem + "_RU.md")
        if target_path.resolve() == expected_peer.resolve():
            continue
        if is_ru and target_path.exists() and not target_path.name.endswith("_RU.md") and target_path.with_name(target_path.stem + "_RU.md").exists():
            result.append(f"RU file links to English file with RU counterpart: {target} (use {target_path.stem}_RU.md)")
        elif not is_ru and target_path.name.endswith("_RU.md"):
            result.append(f"EN file links to a Russian-suffixed file: {target}")
    return result


def check_pair(ru_path: Path, en_path: Path, root: Path) -> list[str]:
    ru = ru_path.read_text(encoding="utf-8")
    en = en_path.read_text(encoding="utf-8")
    rel = ru_path.relative_to(root).as_posix()
    problems = locale_problems(ru, True, ru_path, root) + locale_problems(en, False, en_path, root)
    if en_path.relative_to(root).as_posix() in STRUCTURE_EXEMPT:
        return [f"{rel}: {problem}" for problem in problems]
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
        problems.append(f"env tokens differ: RU-only={sorted(tok_ru - tok_en)} EN-only={sorted(tok_en - tok_ru)}")
    return [f"{rel}: {problem}" for problem in problems]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="repository root (default: cwd)")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    checked = exempt = 0
    failures: list[str] = []
    for ru_path, en_path in find_pairs(root):
        failures.extend(check_pair(ru_path, en_path, root))
        if en_path.relative_to(root).as_posix() in STRUCTURE_EXEMPT:
            exempt += 1
        else:
            checked += 1
    for failure in failures:
        print(f"DRIFT {failure}")
    print(f"RU/EN pairs checked: {checked} structural, {exempt} structure-exempt, {len(failures)} problems")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
