"""Static regression checks for the pinned Hermes Core CI setup."""

from pathlib import Path


CI = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml").read_text(
    encoding="utf-8"
)
PINNED_CORE_SHA = "d0288be5b3330d2442e3907185b8e9d0958297bb"


def test_pinned_core_is_fetched_explicitly_without_tip_fallback() -> None:
    expected_fetch = f"git -C /tmp/hermes-core fetch --no-tags --depth=1 origin {PINNED_CORE_SHA}"
    assert CI.count(expected_fetch) == 2
    assert CI.count('test "$(git -C /tmp/hermes-core rev-parse HEAD)" = "') == 2
    assert "git clone --depth 1 https://github.com/NousResearch/hermes-agent.git" not in CI
