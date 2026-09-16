"""Regression tests for DOC-08: navigation and reproducible installation.

The card requires a link checker that ignores links shown as *examples* inside
inline code spans or fenced code blocks (e.g. ``[links](url)``), and that every
real relative link in the repository resolves to an existing file.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = REPO_ROOT / "scripts" / "check_docs_links.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_docs_links", CHECKER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = _load_checker()


class TestStripCode:
    def test_inline_code_span_removed(self):
        assert "[links](url)" not in checker.strip_code("text `[links](url)` more")

    def test_double_backtick_span_removed(self):
        assert "[links](url)" not in checker.strip_code("see `` `[links](url)` `` here")

    def test_fenced_block_removed(self):
        text = "before\n```\n[d](missing.md)\n```\nafter"
        assert "[d](missing.md)" not in checker.strip_code(text)

    def test_tilde_fence_removed(self):
        assert "[d](missing.md)" not in checker.strip_code("~~~\n[d](missing.md)\n~~~")

    def test_plain_link_kept(self):
        assert "[d](real.md)" in checker.strip_code("[d](real.md)")


class TestCheckFile:
    def test_broken_relative_link_is_reported(self, tmp_path):
        md = tmp_path / "a.md"
        md.write_text("[gone](nope.md)\n", encoding="utf-8")
        problems = checker.check_file(md, tmp_path)
        assert problems and "nope.md" in problems[0]

    def test_existing_relative_link_is_clean(self, tmp_path):
        (tmp_path / "ok.md").write_text("# ok\n", encoding="utf-8")
        md = tmp_path / "a.md"
        md.write_text("[ok](ok.md)\n", encoding="utf-8")
        assert checker.check_file(md, tmp_path) == []

    def test_anchor_and_external_links_ignored(self, tmp_path):
        md = tmp_path / "a.md"
        md.write_text("[h](#section)\n[ext](https://example.com/x.md)\n", encoding="utf-8")
        assert checker.check_file(md, tmp_path) == []

    def test_code_span_example_not_flagged(self, tmp_path):
        md = tmp_path / "a.md"
        md.write_text("MAX supports `[links](url)` and `` `[x](y)` ``.\n", encoding="utf-8")
        assert checker.check_file(md, tmp_path) == []

    def test_fenced_tree_listing_not_flagged(self, tmp_path):
        md = tmp_path / "a.md"
        md.write_text("tree:\n```\ndocs/\n└── webhook.md\n```\n", encoding="utf-8")
        assert checker.check_file(md, tmp_path) == []


class TestRepositoryLinks:
    def test_no_broken_relative_links(self):
        md_files = sorted(REPO_ROOT.rglob("*.md"))
        assert md_files, "expected markdown files in the repository"
        problems: list[str] = []
        for md in md_files:
            problems.extend(checker.check_file(md, REPO_ROOT))
        assert problems == [], "broken relative links:\n" + "\n".join(problems)


class TestProjectTreeDocs:
    """The README tree must not advertise files that do not exist."""

    def test_readme_trees_match_repository(self):
        missing = []
        for name in ("README.md", "README_EN.md"):
            text = (REPO_ROOT / name).read_text(encoding="utf-8")
            if "docs/webhook.md" in text:
                missing.append(f"{name} still lists docs/webhook.md")
            if "mixins/" not in text:
                missing.append(f"{name} does not list the mixins/ package")
        assert missing == [], "\n".join(missing)
