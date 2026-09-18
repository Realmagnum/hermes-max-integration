#!/usr/bin/env python3
"""Markdown link checker for the hermes-max-integration docs.

Checks that every *real* relative link and image target in the repository's
Markdown files resolves to an existing file.  Links written inside inline code
spans or fenced code blocks (docs frequently show ``[label](url)`` as an
example) are ignored on purpose -- they are illustrations, not navigation.

Usage:
    python scripts/check_docs_links.py [PATH ...]

PATH defaults to the repository root.  External http(s) links are not fetched
(the checker is offline-safe).

Exit code is 0 when no broken link is found, 1 otherwise.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

FENCE_RE = re.compile(r"^[ \t]*(```+|~~~+).*$", re.MULTILINE)
# A code span opens with a run of N backticks and closes with the next run of
# the same length; the body may itself contain shorter backtick runs.
INLINE_CODE_RE = re.compile(r"(`+).+?\1", re.DOTALL)
# [label](target) and ![label](target); target may be <bracketed> and may carry
# an optional "title".
LINK_RE = re.compile(r"!?\[[^\]]*\]\(\s*(<[^>]*>|[^\s)]+)(?:\s+[\"'][^\"']*[\"'])?\s*\)")
SCHOOL_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


def strip_code(text: str) -> str:
    """Remove fenced code blocks and inline code spans so example links vanish."""
    # Drop fenced blocks (opening fence through the matching closing fence).
    lines = text.splitlines()
    out: list[str] = []
    fence: str | None = None
    for line in lines:
        m = FENCE_RE.match(line)
        if fence is None:
            if m:
                fence = m.group(1)[0] * 3
                continue
            out.append(line)
        else:
            if m and m.group(1)[0] * 3 == fence:
                fence = None
            # inside a fence: drop the line entirely
    text = "\n".join(out)
    # Drop inline code spans, including ""doubled""-backtick spans used to wrap
    # an example that itself contains backticks.
    return INLINE_CODE_RE.sub("", text)


def check_file(md: Path, root: Path) -> list[str]:
    problems: list[str] = []
    text = strip_code(md.read_text(encoding="utf-8", errors="replace"))
    for m in LINK_RE.finditer(text):
        target = m.group(1).strip("<>").strip()
        if not target or target.startswith("#"):
            continue  # pure anchor within the same document
        if "://" in target or target.startswith("//"):
            continue  # external link: never fetched offline
        if target.startswith("mailto:") or SCHOOL_SCHEME_RE.match(target):
            continue
        path_part = target.split("#", 1)[0].split("?", 1)[0]
        if not path_part:
            continue
        resolved = (md.parent / path_part).resolve()
        if not resolved.exists():
            rel = md.relative_to(root) if root in md.parents else md
            problems.append(f"{rel}: broken link -> {target}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", default=["."])
    args = parser.parse_args(argv)

    root = Path(args.paths[0]).resolve()
    md_files: list[Path] = []
    for p in args.paths:
        pth = Path(p)
        if pth.is_file() and pth.suffix == ".md":
            md_files.append(pth.resolve())
        else:
            md_files.extend(sorted(pth.rglob("*.md")))

    problems: list[str] = []
    for md in md_files:
        problems.extend(check_file(md, root))

    for line in problems:
        print(line)
    print(f"\nchecked {len(md_files)} markdown files, {len(problems)} broken link(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
