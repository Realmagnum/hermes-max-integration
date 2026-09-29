"""Guard the release script's fail-closed ordering (RC-2.10 release gate)."""

from pathlib import Path

SCRIPT = (Path(__file__).resolve().parents[1] / "scripts" / "release.sh").read_text(
    encoding="utf-8"
)


def test_release_script_requires_a_successful_ci_run_for_exact_head() -> None:
    assert 'CI_RUN_ID="$2"' in SCRIPT
    assert 'GITEA_TOKEN:?Set GITEA_TOKEN' in SCRIPT
    assert 'actions/runs/$CI_RUN_ID' in SCRIPT
    assert 'run_sha != expected_sha' in SCRIPT
    assert 'required = ("test", "test-current-core", "security", "dependency-audit")' in SCRIPT
    assert "if missing or failed:" in SCRIPT


def test_release_script_validates_committed_release_material_before_tagging() -> None:
    assert "python scripts/check-doc-claims.py" in SCRIPT
    assert "python scripts/check-config-reference.py" in SCRIPT
    assert "python scripts/check-ru-en-parity.py" in SCRIPT
    assert "git cliff" not in SCRIPT
    assert SCRIPT.index("if missing or failed:") < SCRIPT.index('git tag -a "$VERSION"')
