# MAX Deployment Test Stand Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Periodically validate a clean current-upstream Hermes install, normal MAX plugin installation, and basic gateway behavior against a minimal deterministic MAX simulator.

**Architecture:** Add a standalone, loopback-only simulator and a driver under `test-stand/`; reuse the actual MAX payload shapes and wire assertions from `tests/conftest.py` without making pytest fixtures a production dependency. Run a real gateway in a disposable isolated environment. Separate fast in-process tests from full install/gateway smoke; preserve existing CI. Prevent outbound connections to production MAX hosts rather than redirecting TLS/DNS globally.

**Tech Stack:** Python >=3.12, lightweight HTTP server selected after checking installed project dependencies, pytest/httpx for test driver; upstream Hermes CLI for installation; disposable Linux VM or LXC for periodic full-stack runs. Container may run the simulator, but the OS install path should be exercised in the disposable guest.

---

## Baseline and constraints

- Repository: actual Git checkout `D:/!Projects/hermes-max-catalog-fixes`, branch `feature/microspec-pipeline`, HEAD `97e20538aae81dc6d879dff43388bdd280fc70fc`; unrelated changes already exist in `mixins/sessions.py` and untracked `_rel_body.txt`. Preserve them.
- Contract: `docs/specs/20261020-max-deployment-test-stand.md` and `_RU.md`, IDs MTS-001–008. Existing `tests/conftest.py::MockMaxAPI` covers in-process HTTP only; existing `.github/workflows/ci.yml` tests pinned Core SHAs and local admission, not fresh install plus gateway.
- Current `MAX_API_BASE` appears in `adapter.py`, `mixins/buttons.py`, `mixins/media_upload.py`, `mixins/standalone.py`, `mixins/webhook.py`; inspect all exact call sites and `docs/security.md` before choosing injection. Upload and download URL policies are separate; do not bypass DNS/SSRF guards. `PUT /messages` uses query `message_id`, not a URL path parameter; uploads may use multipart POST to provided URL — verify source before implementing.
- No real bot/token or production subscription access. Fake LLM should provide a deterministic reply through a supported Core provider interface; verify current Core version and configuration first. If deterministic local inference cannot be configured using public APIs, report that specific barrier rather than equating API transport tests with full E2E.
- Core selection: choose current stable upstream release at runtime and resolve immutable commit/digest; separate optional upstream-main canary. Record both Core and plugin SHAs and exact plugin install source. A successful `hermes plugins validate` exit code alone is insufficient if dependency fallback is logged (see CI).

## Tasks

### Task 1: Confirm baseline and entry points

**Objective:** Determine exact supported install, gateway startup and fake-provider paths before designing the stand.

**Files:** Read `AGENTS.md`, `docs/setup.md`, `docs/security.md`, `docs/api.md`, `docs/specs/20261020-max-deployment-test-stand.md`, `.github/workflows/ci.yml`, `tests/conftest.py`, `adapter.py`, `mixins/{webhook,media_upload,buttons,standalone}.py`; inspect selected Core docs and CLI `--help` at resolved SHA.

**Steps:** Check `git status`, remotes, fresh remote HEAD and existing concurrent edits. Enumerate only actually invoked MAX endpoints and payload shapes. Confirm what gateway sends to LLM provider and how to supply an in-guest deterministic response. Record decisions in plan/spec evidence before implementation; if repository layout differs, adjust planned file paths rather than inventing stubs.

**Verification:** Produce a table: request method/path, response shape, source call site, covered MTS IDs. No code change or commit in this step.

### Task 2: Test-only API routing and network isolation

**Objective:** Route all MAX REST calls to loopback without changing production default or weakening upload protections.

**Files:** Likely new `mixins/base.py` routing helper or equivalent; modify only confirmed call sites in `adapter.py`, `mixins/{buttons,media_upload,webhook,standalone}.py`; add focused `tests/test_test_stand_routing.py`.

**Steps:** Write a failing test showing all relevant calls use only test loopback under explicitly enabled isolated test mode and default production host otherwise; verify failure. Implement the narrowest configuration seam; disallow non-loopback overrides. Keep Authorization header origin-scoped; test no leaked credential on media/upload redirect. Run focused tests to pass, then existing wire/security tests. Do not introduce public arbitrary base-URL overrides.

**Verification:** `python -m pytest tests/test_test_stand_routing.py tests/test_wire_regressions.py tests/test_webhook_security.py -q` (exact venv runner per `docs/setup.md`), `python -m pip check`; record output. Keep code concern separate if later committing.

### Task 3: Stateful simulator process

**Objective:** Provide just enough MAX behavior for deterministic gateway checks.

**Files:** Create `test-stand/max_simulator.py`, `test-stand/test_max_simulator.py`; optional requirements/config only if dependencies demand them.

**Steps:** Write failing tests first for `/me`, current subscription semantics, marker-resumable `/updates`, `POST/PUT /messages` with query `message_id`, commands/callback acknowledgement and exact upload flow used by code. Add a loopback-only control surface to enqueue updates, inspect outbound calls, reset state and inject one-shot `401`, `429`, `500`/timeout. Implement minimal HTTP handling and stable IDs. Do not simulate unneeded MAX APIs or random updates. Ensure control endpoints require local isolation/test key and are not exposed to production.

**Verification:** Run focused tests; start simulator as a separate process and probe real HTTP with a test token; assert duplicate poll marker is stable, messages are captured, failure modes deterministic; terminate cleanly.

### Task 4: Real gateway driver and behavioral matrix

**Objective:** Exercise real plugin loader/router/gateway in polling and local webhook modes.

**Files:** Create `test-stand/run_smoke.py` and focused supporting fixtures under `test-stand/`; use exact runtime config supported by resolved Core. Do not use arbitrary production env vars.

**Steps:** Start simulator, fake provider and gateway with disposable home; wait for startup; inject a uniquely tagged message, correlate its outgoing reply; poll again to exclude replay. Repeat in webhook mode with valid/invalid secret. Drive a real command and owned/foreign callback. Exercise text edit and small attachment upload with approved local test URLs and verify rejection of a deliberately forbidden host. Inject `401` and transient errors with deadlines. Every scenario records pass/fail, not fabricated counters.

**Verification:** Run the driver with fixed Core/plugin revisions; inspect simulator capture and gateway logs; an injected negative condition must fail the run. If a scenario needs special routing that conflicts with media security, leave it explicitly pending instead of weakening guards.

### Task 5: Clean installation runner and schedule

**Objective:** Cover full install from current upstream and publish actionable evidence.

**Files:** Create `test-stand/run_clean_install.sh` (or a portable runner appropriate to chosen Linux guest), `test-stand/README.md`; add a separate scheduled workflow/job only after deciding the runner VM/LXC and credentials availability. Update `BACKLOG.md` and `BACKLOG_RU.md` with the subproject until verified.

**Steps:** In a fresh guest/home, resolve latest stable Core tag to immutable SHA, install Core with its documented official method, check `hermes --version`, install plugin via `hermes plugins install <source> --enable`, validate/show/list and check dependency warnings. Launch Task 4. Save JSON and concise summary with Core/plugin SHA, mode, per-ID evidence, redacted logs and nonzero failure. On subsequent runs do not reuse plugin state. Run daily if a suitable isolated runner is provisioned; optional upstream-main canary in a distinct job. Avoid scheduled live MAX tests: no real bot required. Do not configure a schedule on a shared/production host without choosing an isolated runner.

**Verification:** Successful clean run on the supplied isolated host; force a simulator failure to verify nonzero exit and alert/report; re-read schedule status. If no host supplied, document runner requirements and leave the scheduled job **pending**, not claimed working.

### Task 6: Documentation and handoff

**Objective:** Leave a reproducible subproject with honest status.

**Files:** Update spec EN/RU evidence, `test-stand/README.md` (and Russian counterpart per doc rules where durable), `BACKLOG.md`/`BACKLOG_RU.md`; existing CI remains unchanged except additive justified checks.

**Steps:** Map MTS IDs to exact changed paths, commands/output, Core/plugin SHAs and dates; clearly distinguish in-process tests, simulator E2E and live MAX (out of scope). Update only docs whose described behavior changes.

**Verification:** `python scripts/check_docs_links.py`, `python scripts/check-ru-en-parity.py`, `python scripts/check-doc-claims.py`, `python scripts/check-config-reference.py`, `git diff --check`; run relevant code checks and report actual outputs. No commit/push/merge until explicitly requested.

## Open dependencies

- An isolated Linux VM or LXC with network access for current Core installation and CI scheduler; reserve a private loopback network namespace and ensure it can block production MAX egress. Docker alone is sufficient for fast simulation, not proof of host install.
- Exact current Core release and gateway fake-provider mechanism need live inspection at implementation time.
- Repo checkout is currently a shared branch with unrelated edits; avoid overwriting them and recheck before each write. This document specifies and plans only; no simulator, full-stack check or schedule exists yet.
