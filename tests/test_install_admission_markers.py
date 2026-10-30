"""Install-admission contracts for the plugin's dependency declarations.

Two failure modes are guarded here, both of which refuse the plugin at
admission instead of merely skipping an optional feature:

* **Missing platform guard.** Hermes resolves the plugin workspace for every
  platform its environment markers admit. Playwright and faster-whisper ship no
  Android wheels, so an unguarded entry fails the whole ``uv lock`` even though
  the extra is never selected and the plugin is then refused
  (``sys_platform != 'android'`` is how core declares the same packages).
* **Exact pin colliding with core.** Core pins playwright exactly in its
  ``google-meet`` extra. Two different exact pins cannot co-install, so the
  plugin must declare a range that contains the version core pins — otherwise a
  routine core bump evicts the plugin.

The core-side check reads the installed core's ``pyproject.toml``, so CI (which
installs an exact Core revision) exercises the real pins of every fixture. It is
skipped when only the plugin is installed, e.g. a wheel without a Core checkout.

See docs/specs/20261030-install-admission-markers.md.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
MANIFEST = yaml.safe_load((ROOT / "plugin.yaml").read_text(encoding="utf-8"))

# Distributions the plugin declares that publish no Android wheels and that core
# also guards. Extend this set when a declaration gains another such package.
PLATFORM_GUARDED = ("playwright", "faster-whisper", "ctranslate2")
PLATFORM_MARKER = "sys_platform != 'android'"

REQUIREMENT = re.compile(r"^(?P<name>[A-Za-z0-9_.\-]+)\s*(?:\[[^\]]*\])?\s*(?P<spec>[^;]*)(?:;(?P<marker>.*))?$")


def declarations() -> list[tuple[str, str]]:
    """``(origin, requirement)`` for extras and the manifest's python deps."""
    rows: list[tuple[str, str]] = []
    for extra, requirements in PYPROJECT["project"].get("optional-dependencies", {}).items():
        rows.extend((f"pyproject.toml[{extra}]", requirement) for requirement in requirements)
    rows.extend(
        ("plugin.yaml", requirement) for requirement in MANIFEST.get("python_dependencies", [])
    )
    return rows


def parsed(requirement: str) -> tuple[str, str, str]:
    """``(name, specifier, marker)`` of one requirement string."""
    match = REQUIREMENT.match(requirement.strip())
    assert match, f"unparsable requirement: {requirement}"
    return match["name"], match["spec"].strip(), (match["marker"] or "").strip()


def version_tuple(text: str) -> tuple[int, ...]:
    """Numeric version prefix as a comparable tuple (``1.62.0`` → ``(1, 62, 0)``)."""
    parts = []
    for chunk in re.split(r"[.\-+]", text.strip())[:3]:
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def satisfies(version: str, specifier: str) -> bool:
    """Evaluate the subset of PEP 440 the declarations use (``>=``/``<``/``==``)."""
    actual = version_tuple(version)
    for clause in (part.strip() for part in specifier.split(",")):
        if not clause:
            continue
        for operator in (">=", "<=", "==", ">", "<"):
            if clause.startswith(operator):
                wanted = version_tuple(clause[len(operator):])
                ok = {
                    ">=": actual >= wanted,
                    "<=": actual <= wanted,
                    "==": actual == wanted,
                    ">": actual > wanted,
                    "<": actual < wanted,
                }[operator]
                break
        else:
            return False  # unsupported operator: treat as unsatisfiable, never silently pass
        if not ok:
            return False
    return True


def core_pyproject() -> Path | None:
    """The installed Core ``pyproject.toml``, or ``None`` outside a Core checkout."""
    try:
        import hermes_cli
    except ModuleNotFoundError:
        return None
    candidate = Path(hermes_cli.__file__).resolve().parents[1] / "pyproject.toml"
    return candidate if candidate.is_file() else None


def core_pins() -> dict[str, str]:
    """Exact ``name -> version`` pins of every core extra (the co-install surface)."""
    path = core_pyproject()
    if path is None:
        pytest.skip("no Core checkout beside the plugin: core pins unavailable")
        return {}
    document = tomllib.loads(path.read_text(encoding="utf-8"))
    pins: dict[str, str] = {}
    for requirements in document["project"].get("optional-dependencies", {}).values():
        for requirement in requirements:
            name, spec, _marker = parsed(requirement)
            for clause in (part.strip() for part in spec.split(",")):
                if clause.startswith("==") and not clause.startswith("==="):
                    pins.setdefault(name.lower(), clause[2:].strip())
    return pins


def test_platform_specific_declarations_carry_the_android_guard():
    offenders = [
        f"{origin}: {requirement}"
        for origin, requirement in declarations()
        if parsed(requirement)[0].lower() in PLATFORM_GUARDED
        and PLATFORM_MARKER not in parsed(requirement)[2]
    ]
    assert not offenders, (
        "platform-specific requirements must mirror core's Android guard, "
        f"otherwise the plugin workspace fails to lock: {offenders}"
    )


def test_platform_guarded_declarations_are_declared_at_all():
    """The guard test above is vacuous if the packages are not declared anymore."""
    declared = {parsed(requirement)[0].lower() for _origin, requirement in declarations()}
    assert set(PLATFORM_GUARDED) & declared >= {"playwright", "faster-whisper"}


def test_plugin_never_pins_exactly_a_distribution_core_pins_exactly():
    pins = core_pins()
    collisions = [
        f"{origin}: {requirement} vs core =={pins[name.lower()]}"
        for origin, requirement in declarations()
        if (name := parsed(requirement)[0]) and name.lower() in pins
        and parsed(requirement)[1].startswith("==")
    ]
    assert not collisions, (
        "an exact pin that disagrees with core's exact pin cannot co-install; "
        f"declare a range that contains core's version: {collisions}"
    )


def test_plugin_range_accepts_core_exact_pin():
    """Every core exact pin of a shared distribution must fall inside our range."""
    pins = core_pins()
    unsatisfied = [
        f"{origin}: {requirement} excludes core =={pins[name.lower()]}"
        for origin, requirement in declarations()
        if (name := parsed(requirement)[0]) and name.lower() in pins
        and not satisfies(pins[name.lower()], parsed(requirement)[1])
    ]
    assert not unsatisfied, unsatisfied


def test_playwright_floor_matches_the_oldest_supported_core_pin():
    """The floor may not rise above a core pin the plugin still claims to support."""
    manifest_playwright = [
        requirement
        for origin, requirement in declarations()
        if origin == "plugin.yaml" and parsed(requirement)[0].lower() == "playwright"
    ]
    assert manifest_playwright, "playwright must stay declared for the install hint"
    assert satisfies("1.62.0", parsed(manifest_playwright[0])[1]), (
        f"{manifest_playwright[0]}: 1.62.0 is core 0.22.5's pin and must stay installable"
    )
