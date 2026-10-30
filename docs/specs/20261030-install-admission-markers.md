# Install admission: platform markers and the playwright pin — Micro-Spec

Source: upstream issue [Realmagnum/hermes-max-integration#1](https://github.com/Realmagnum/hermes-max-integration/issues/1), verified 2026-10-30 against Core `aad60e1ac67` (local checkout) and `origin/main` (`fa78e686faf`).

Scope: make the plugin installable by Hermes' plugin manager without changing runtime behavior. Nothing here selects the `tables` or `stt` extras; the change only removes reasons for the resolver to refuse the candidate set.

## Problem

Hermes resolves core plus every enabled plugin as one uv workspace and locks **all** extras of the members. Two independent declarations made that lock fail, so admission answered `enable refused: Plugin 'max-platform' conflicts with the dependencies pinned by Hermes core…`:

1. `tables` (playwright) and `stt` (faster-whisper → ctranslate2) were declared without core's `sys_platform != 'android'` guard. Neither distribution publishes Android wheels, so on cores that still solve Android the whole lock failed over a platform the plugin never runs on.
2. `tables` and `plugin.yaml` pinned `playwright==1.62.0` exactly. Core pins the same distribution exactly in its `google-meet` extra and moved that pin from `1.62.0` to `1.64.0` (core commit `65a82c53f94`, 2026-10-23). Two different exact pins cannot co-install, so the plugin stayed uninstallable on every core from that commit onward — including after core's own Android fix (`91c86af0551`, `db5b65607e3`, 2026-10-24) removed cause 1.

Cause 1 alone is fixed in core for hosts installing on a single platform, but the plugin still declares `requires_hermes >=0.21.4` and released cores `≤ v0.22.5` solve Android. The marker is therefore kept: it is correct for those cores and is what core itself declares for the same packages.

## Change

| ID | Trigger / context | Required result | Acceptance | Status |
|---|---|---|---|---|
| DEP-001 | `tables` / `stt` extras, `plugin.yaml` | `playwright` and `faster-whisper` carry `sys_platform != 'android'`, matching core's own markers | `tests/test_install_admission_markers.py`; seeded workspace lock on Core `v0.22.5` | Implemented |
| DEP-002 | Core pins playwright exactly | Plugin declares `playwright>=1.62,<2`: floor is the oldest core pin it supports, ceiling below the next major | `tests/test_install_admission_markers.py`; seeded workspace lock on Core `aad60e1ac67` | Implemented |
| DEP-003 | `scripts/setup-playwright.py` | Accept and install any version inside the declared range instead of enforcing `1.62.0`; never fight the version the gateway already has | `tests/test_setup_playwright.py` (range cases, install command) | Implemented |
| DEP-004 | Core bumps playwright beyond the range | CI fails with the offending requirement instead of users hitting an admission refusal | `tests/test_install_admission_markers.py::test_plugin_range_accepts_core_exact_pin` reads the installed core `pyproject.toml` | Implemented |

## Evidence and limits

Reproduced with the PM-pinned `uv 0.13.5` and CPython 3.14.9 on a generated workspace that mirrors `pm/workspace.py::_generate_pyproject`: core's root `pyproject.toml` with `exclude-newer` dropped, `[tool.uv] workspace.members` pointing at the plugin copy, and — as `pm/packages.py` does (`seed = project / "uv.lock"`) — core's own committed lock copied in as the seed.

| Core | Plugin declarations | Result |
|---|---|---|
| `v0.22.5`, environments un-narrowed | commit `78d9abf` | **refused**, reproducing [issue #1](https://github.com/Realmagnum/hermes-max-integration/issues/1) verbatim: `playwright==1.62.0 has no 'python_full_version >= 3.14'-compatible wheels` in the `sys_platform == 'android'` split |
| `v0.22.5`, environments un-narrowed | this change | lock resolves, 330 packages, member present |
| `aad60e1ac67`, environments un-narrowed | commit `78d9abf` | **refused** in the non-Android split: `hermes-agent[google-meet] depends on playwright==1.64.0` vs `hermes-max-integration[tables] depends on playwright==1.62.0` |
| `aad60e1ac67`, environments un-narrowed | this change | lock resolves, 348 packages, playwright 1.64.0 |
| `aad60e1ac67`, environments narrowed to the installing host (`pm/workspace.py::_solve_only_for`) | this change | lock resolves, 348 packages, playwright 1.64.0, faster-whisper 1.2.1 |

The last two rows matter together: the fix does **not** depend on core's workspace-narrowing commit. Both causes are removed at the declaration site, so the plugin admits on released cores that still solve Android (`≤ v0.22.5`, the case in issue #1) and on current core where the only remaining blocker was the pin collision.

A first harness iteration omitted the seed lock and produced a `spacy 2.0.17` sdist build failure. That is an artifact of resolving everything from scratch, not a property of core: with the seed in place (as PM does it) both cores lock cleanly. Recorded here so the failure is not misread as evidence later.

Not verified here: a live `hermes plugins install` against a published release, Windows/macOS hosts, the `sdist`/wheel build, and an actual Android (Termux) install. Core `dependency-audit` advisories are unrelated and stay tracked as BUILD-03.
