# Hermes MAX Integration 2.10 — Release Backlog

[Русский](RELEASE_BACKLOG_2.10.md)

## Goal

Prepare a verifiable 2.10 release candidate for `agent/hermes-max-integration`: restore runtime packages lost during conflicted merges, close P1 security issues, stabilize lifecycle/transport, synchronize documentation, and pass a reproducible release gate on one SHA.

**This is a backlog, not a release-readiness claim.** Publishing 2.10 is forbidden until the release gate is green.

## Current state

- Working branch: `RC-2.10`.
- Current SHA: `d11c885` (`fix(rc-2.10): complete callback routing and session guards`).
- `main` is unchanged.
- Branch `rc-2.10-conflicted-backup` preserves the previous conflicted tree.
- Gitea does not yet contain RC 2.10; this backlog must be pushed with the candidate branch.
- Focused suite after the last fixes: `169 passed, 5 xfailed`.
- Full `pytest -q` on the conflicted tree: `267 failed, 412 passed, 13 skipped, 5 xfailed, 28 errors`.
- Linear rebuild from the original fix commits also failed: `186 failed, 49 passed, 28 errors`.

### Confirmed blocker

Merge commits retained tests and parts of fixes but displaced runtime implementations. The final candidate must independently restore and verify polling backoff, per-message streaming, complete SSRF/download helpers and config wiring, one webhook app-builder/readiness contract, lossless chunking, and documentation/CI gates.

Do not close these tasks by deleting tests, weakening assertions, or disabling protections.

## Execution rules

1. Work only in `RC-2.10`; do not change `main` before final approval.
2. Write or restore a minimal failing test before every runtime fix and record RED.
3. Use focused commits with backlog IDs.
4. Run focused and adjacent regression groups after each package.
5. Use MockTransport/local aiohttp until a test bot is explicitly approved.
6. Never accept a test that passes because callback, queue, webhook or download code was bypassed.
7. Inspect every conflict resolution diff and verify both sides survived.
8. Any open P1 is `NO-GO`.

## Priorities and dependencies

```text
R0: BUILD-01/02 → reproducible environment
R1: CODE-01 + CODE-02 + CODE-03 + CODE-07
R2: SEC-02 + SEC-03 + SEC-07 (one download pipeline)
R3: SEC-01 + SEC-05 + SEC-06 + CODE-04 + CODE-06 + CODE-08
R4: SEC-04 + CODE-05 (one webhook lifecycle/readiness)
R5: BUILD-03/04 → DOC-01..10 → full gate
```

## R0 — Reproducible base

### REL-00 · Baseline and evidence

**Priority:** P0 · **Status:** OPEN

Save the current SHA, backup branch, Python/pytest/core/uv/pip/OS versions, exact commands and full outputs under `docs/release-evidence/2.10/`. Confirm production config was untouched.

**Acceptance:** another developer can reproduce the state and identify the SHA for every result.

### BUILD-01 · Packaging/install

**Priority:** P1 · **Status:** PARTIAL.

Verify flat-layout discovery, clean editable install, wheel build/install and installation from an arbitrarily named checkout.

**Acceptance:** clean Python 3.11 and 3.12 editable/wheel installs pass; wheel contains required plugin files and no secrets/tests.

### BUILD-02 · Pinned test environment

**Priority:** P1 · **Status:** OPEN.

Pin a compatible Hermes core or local-core fixture, remove checkout-name assumptions, and verify collection in an isolated `HERMES_HOME`.

**Acceptance:** clean `pytest --collect-only -q`; supported Python/core versions are explicit.

## R1 — Transport, chunking, lifecycle

### CODE-01 · Polling backoff

**Priority:** P1 · **Status:** REGRESSED/NOT PRESENT.

Restore `_parse_retry_after`, `_poll_backoff_delay`, `_status_retry_delay`, `_poll_sleep` and deterministic RNG hooks. Back off every retryable status/transport error; 401 is fatal without pending sleep; preserve markers and reset after success.

**Acceptance:** all `tests/test_poll_backoff.py` pass under virtual clock with bounded Retry-After.

### CODE-02 · Lossless chunking

**Priority:** P1 · **Status:** REGRESSED; primary fix `3126a08`.

Restore the primary algorithm in the final send path. Budget numbering before split and preserve whitespace/code fences.

**Acceptance:** transmitted payload concatenation equals source and every payload fits the MAX limit for all lossless fixtures.

### CODE-03 · Streaming isolation/flush

**Priority:** P1 · **Status:** REGRESSED/NOT PRESENT; primary fix `ba13553`.

Restore per-message `_edit_states`, `_StreamEditState`, keying, throttle configuration, pruning, timer replacement, finalize and disconnect cleanup.

**Acceptance:** streaming isolation suite passes; independent chats/messages never suppress one another; pending content is sent exactly once.

### CODE-07 · Lifecycle/core contract

**Priority:** P1 · **Status:** PARTIAL; primary fix `765b56c`.

Re-test repeated/concurrent connect/disconnect, bounded cancellation cleanup, runner/client teardown and pinned core state contract.

**Acceptance:** no task/client leaks under connect/reconnect/cancellation scenarios.

## R2 — One secure media pipeline

### SEC-02 · Token-free untrusted downloads — P1 — PARTIAL; primary `c9a0eef`.

### SEC-03 · SSRF/DNS/rebinding — P1 — PARTIAL; primary `c34b45e`, wiring `3d6e45f`.

### SEC-07 · Size/count/time/concurrency limits — P1 — PARTIAL; primary `d6f8fbc`.

Shared pipeline: normalize URL → exact HTTPS/trust decision → no token for untrusted origin → validate all A/AAAA → pin address/no redirects → bounded streaming/deadline → per-update budgets/semaphore → atomic cache/cleanup → redact logs.

**Files:** `adapter.py`, `mixins/media_upload.py`, `tests/test_ssrf_download.py`, `tests/test_download_token_leak.py`, `tests/test_inbound_media_limits.py`.

**Acceptance:** all groups pass with no real network, covering arbitrary hosts, HTTP, lookalikes, credentials, alternative IPs, private DNS, rebinding, redirects, false Content-Length, slow streams and disk failures.

## R3 — Authorization, routing, backpressure

### SEC-01 · Callback authorization — P1 — focused tests pass; final wire integration required.

One gate before resolver/state removal; bind owner/scope/message/TTL; cover exec, slash, clarify and model picker; route acknowledgements to the correct target.

### SEC-05 · Cross-session access — P1 — focused tests pass; verify final adapter.

Off by default; explicit owner set only; authorize before SessionDB, send or `--all` rewrite. Test `/sessions`, search and `/resume` matrix.

### SEC-06 · Group allowlist — P1 — focused tests pass; verify final config.

Normalize values, fail closed on empty allowlists and preserve documented AND semantics.

### CODE-04 · Opaque model callback IDs — P2 — final-suite verification required.

Use encoding/structured serialization and round-trip colon-containing IDs plus malformed/expired payloads.

### CODE-06 · Model picker isolation — P1 — focused tests pass; verify after lifecycle merge.

Owner/scope/message/TTL checks; reject stale replacements/pagination; bind unowned group state only on current live message and first valid tap.

### CODE-08 · Backpressure/dedup — P1 — focused tests pass; verify final tree.

Bound queue/concurrency/dedup, explicit drop policy and telemetry; webhook ingress must not block.

## R4 — Webhook/readiness

### SEC-04 · Fail-closed webhook — P1 — focused tests passed in an earlier tree; final integration partial.

Restore one app-builder/startup contract. Require secret for non-loopback; retain loopback insecure-dev only as explicit opt-in; authenticate before parsing with body cap and constant-time comparison.

### CODE-05 · Readiness/registration — P1 — focused tests passed in an earlier tree; final integration partial.

Separate liveness/telemetry from readiness; validate `/me` and subscription transport/status/body; tear down on failure and never mark connected.

**Acceptance:** webhook security, readiness, mode-docs and wire webhook tests pass together.

## R5 — Build, tests, documentation

### BUILD-03 · Quality gates — P1 — OPEN

Ruff/Bandit/pytest/dependency audit must cover adapter, all mixins, scripts and packaging; CI must run for candidate pushes/PRs; optional dependencies and skips must be recorded.

### BUILD-04 · Realistic regressions — P1 — PARTIAL

Use real Response/MockTransport fixtures for DM/group/callback/webhook. Prefer contract assertions and make bound-state message IDs explicit.

### DOC-01..DOC-10

P1: DOC-01..05. P2: DOC-06..10.

- DOC-01: one Hermes-core STT workflow.
- DOC-02: implemented config only, with defaults/precedence/types.
- DOC-03: complete webhook URL/secret/mode/readiness procedure.
- DOC-04: executable parseable RU/EN API examples matching wire payloads.
- DOC-05: honest security model and known limitations.
- DOC-06: preserve verified mode/OS-aware diagnostics.
- DOC-07: RU/EN parity across docs, skills and changelog.
- DOC-08: links/tree/cwd/venv/profile/Gitea install correctness.
- DOC-09: one version source and generated test count.
- DOC-10: external claims verified with source/date/version.

## Required verification commands

```bash
python --version
python -m pip install -e '.[dev]'
python -m build
pytest --collect-only -q
pytest -q tests/test_poll_backoff.py tests/test_chunking.py
pytest -q tests/test_streaming_isolation.py tests/test_openclaw_improvements.py
pytest -q tests/test_ssrf_download.py tests/test_download_token_leak.py tests/test_inbound_media_limits.py
pytest -q tests/test_callback_auth.py tests/test_cross_session.py tests/test_group_access.py tests/test_model_picker.py
pytest -q tests/test_webhook_security.py tests/test_webhook_readiness.py tests/test_wire_regressions.py
pytest -q
ruff check adapter.py mixins scripts tests
bandit -r adapter.py mixins scripts
pip-audit
python scripts/check_docs_links.py
python scripts/check_docs_json.py
python scripts/check_ru_en_parity.py
git diff --check
git status --short
```

Record unavailable tools or blockers exactly; never invent a green result.

## Release gate

GO only when:

- no conflicts/uncommitted changes;
- all P1 tasks have commit IDs and passing regressions;
- full pytest is green and xfails are removed/approved;
- clean Python 3.11/3.12 build/install passes;
- Ruff, Bandit and dependency audit pass or have accepted exceptions;
- no token leak, SSRF, webhook-auth, cross-session or callback-auth failure;
- streaming, backoff, chunking, queue and lifecycle pass together;
- RU/EN docs, links, JSON, config defaults and release notes match code;
- isolated `HERMES_HOME` smoke test passes;
- approved MAX E2E test bot passes DM, group, approval, model picker, media, polling and webhook;
- release/rollback review is complete.

**Current verdict: NO-GO.**
