"""Regression checks for exact Core CI fixtures and dependency resolution."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CI = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
WORKFLOW = yaml.safe_load(CI)


def test_minimum_baseline_and_current_are_independent_exact_source_fixtures():
    cores = WORKFLOW["jobs"]["test"]["strategy"]["matrix"]["core"]
    assert {core["label"] for core in cores} == {"minimum", "baseline", "current"}
    assert {core["job-name"] for core in cores} == {"test-minimum-core", "test", "test-current-core"}
    assert len({core["sha"] for core in cores}) == 3
    assert all(len(core["sha"]) == 40 for core in cores)
    minimum = next(core for core in cores if core["label"] == "minimum")
    assert minimum["sha"] == "d337b736aa1e8ebecfab043842d13e4a2d2f48a3"
    assert minimum["python"] == "3.12"
    assert all(core["python"] == "3.14" for core in cores if core["label"] != "minimum")
    assert next(core["sha"] for core in cores if core["label"] == "current") == (
        WORKFLOW["env"]["CURRENT_CORE_SHA"]
    )
    assert CI.count("fetch --no-tags --depth=1 origin") == 2
    assert CI.count('test "$(git -C /tmp/hermes-core rev-parse HEAD)" =') == 2
    assert "git clone --depth 1" not in CI


def test_dependencies_must_resolve_without_override_and_pass_admission():
    assert "--no-deps" not in CI
    assert "--ignore-vuln" not in CI
    assert "hermes plugins validate" in CI and "--install-deps" in CI
    assert "! grep -q 'dependency preparation failed:'" in CI
    assert "! grep -q 'Python dependencies not installed'" in CI
    assert "python -m pip check" in CI
    assert next(
        step["with"]["python-version"]
        for step in WORKFLOW["jobs"]["test"]["steps"]
        if step.get("uses", "").startswith("actions/setup-python@")
    ) == "${{ matrix.core.python }}"
    assert all(
        step["with"]["python-version"] == "3.14"
        for job_name, job in WORKFLOW["jobs"].items()
        for step in job["steps"]
        if job_name != "test" and step.get("uses", "").startswith("actions/setup-python@")
    )
