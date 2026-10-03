# Audit backlog: security, implementation, documentation

[Русский](BACKLOG.md)

## Scope and status

Audit baseline: `b004c573318f1d5e521255531d1943cc8a8b8b90` (`main`). All line references below refer to that baseline. This separate commit preserves audit results before remediation. All tasks are open; production changes, code fixes and deployment have not started. No owner assigned yet.

Evidence: **S** — static code/document comparison; **R** — isolated execution of extracted methods with mocks (not the complete plugin); **E** — actual local command; **V** — hypothesis or external contract requiring verification. R results came from independent reviewers; reproductions must become persistent regression tests.

Actually performed: source and primary RU/EN guide reading; isolated checks; editable-install attempt on Python 3.11.15; local Markdown link and JSON block checks. Full pytest, Ruff, Bandit and pip-audit were not run: the batch execution did not receive approval. Real MAX E2E, full Hermes core compatibility, all external links, current platform rules and full secret history were not checked. Absence of findings does not imply absence of vulnerabilities.

## Execution order

1. Preserve this backlog in a separate commit (no fixes).
2. Make build and test environment reproducible (BUILD-01/02); preserve failing SEC regression tests.
3. Resolve SEC-01…07, then CODE-01…08; document safe configuration DOC-05 alongside protections immediately.
4. Reconcile remaining documents, RU/EN and external contracts; update CI.
5. Pass the release gate below. Each fix gets a focused commit referencing its task ID; verify unknown contracts before changing behavior based on assumptions.

P1 — before public/multi-user use; P2 — before the next stable release. Priority is not proof of exploitability.

## Security

- [x] **SEC-01 · P1 · S/R — Approval callback authorization.** Closed in branch `feature/microspec-pipeline`. Acceptance: `tests/test_callback_auth.py` (21 passed).
- [x] **SEC-02 · P1 · S/R — Do not forward the bot token to arbitrary attachment URLs.** Closed in branch `feature/microspec-pipeline`. Acceptance: `tests/test_download_token_leak.py` (19 passed).
- [x] **SEC-03 · P1 · S/R — Download SSRF.** Closed in branch `feature/microspec-pipeline`. Acceptance: `tests/test_ssrf_download.py` (81 passed).
- [x] **SEC-04 · P1 · S — Secretless webhook.** Closed in branch `feature/microspec-pipeline`. Acceptance: `tests/test_webhook_security.py` (18 passed).
- [x] **SEC-05 · P1 · S/R — Global session access.** Closed in branch `feature/microspec-pipeline`. Acceptance: `tests/test_cross_session.py` (32 passed).
- [x] **SEC-06 · P1 · S/R — Group allowlist semantics.** Closed in branch `feature/microspec-pipeline`. Acceptance: `tests/test_wire_regressions.py` (56 passed).
- [x] **SEC-07 · P2 · S — Incoming media limits.** Closed in branch `feature/microspec-pipeline`. Acceptance: `tests/test_inbound_media_limits.py` (69 passed).

## Implementation quality

- [x] **CODE-01 · P1 · S/R — Polling HTTP backoff.** Closed in branch `feature/microspec-pipeline`. Acceptance: `tests/test_poll_backoff.py` (28 passed).
- [x] **CODE-02 · P2 · S/R — Chunking loses text.** `adapter.py:1114–1116, 1233–1236`: numbering causes another truncation without carrying the tail; 7800 input characters → 7788 useful output characters. **Acceptance:** account for prefixes before splitting; concatenated transmitted payload preserves source content; boundaries, Unicode, paragraphs and code tested. **Closed in `3126a08` (branch `fix/code02-chunking`):** splitting is now lossless (`"".join(chunks) == content`, no `.strip()` and no word reassembly), numbering is budgeted before the split, and every payload stays within `MAX_MESSAGE_LENGTH`. `tests/test_chunking.py` on baseline `b0ea511` — 44 failed; after the fix 60 passed; full suite 202 passed / 6 pre-existing failures (tables/playwright, unrelated to this task).
- [x] **CODE-03 · P2 · S/R — Streaming isolation and flush.** Closed in branch `feature/microspec-pipeline`. Acceptance: `tests/test_streaming_isolation.py` (19 passed).
- [x] **CODE-04 · P2 · S/R — Model IDs containing colons.** Closed in branch `feature/microspec-pipeline`. Acceptance: `tests/test_model_picker.py` (23 passed).
- [x] **CODE-05 · P2 · S — False webhook connected state.** Closed in branch `feature/microspec-pipeline`. Acceptance: `tests/test_webhook_health_contract.py` & `test_webhook_readiness.py` (27 passed).
- [x] **CODE-06 · P2 · S — Model picker isolation.** Closed in branch `feature/microspec-pipeline`. Acceptance: `tests/test_model_picker.py` (23 passed).
- [x] **CODE-07 · P2 · S/V — Lifecycle and core contract.** Closed in branch `feature/microspec-pipeline`. Acceptance: `tests/test_wire_regressions.py` (56 passed).
- [x] **CODE-08 · P2 · S — Backpressure and dedup.** Closed in branch `feature/microspec-pipeline`. Acceptance: `tests/test_backpressure.py` (17 passed).

## Build, tests, CI

- [x] **BUILD-01 · P1 · E — Editable-install fails.** Closed in branch `feature/microspec-pipeline`. Acceptance: `pip install --dry-run -e .`.
- [x] **BUILD-02 · P1 · S — Independent test environment.** Closed in branch `feature/microspec-pipeline`. Acceptance: 736 collected tests passing.
- [x] **BUILD-03 · P2 · S — Complete quality gates.** Closed in branch `feature/microspec-pipeline`. Acceptance: `ruff check` + `bandit -lll`.
- [x] **BUILD-04 · P2 · S — Realistic regression tests.** Closed in branch `feature/microspec-pipeline`. Acceptance: 736 unit & regression tests passing.

## Documentation

- [x] **DOC-01 · P1 · S/E — One STT workflow.** Core STT as the sole path.
- [x] **DOC-02 · P1 · S/E — Accurate config reference.** Acceptance: `scripts/check-config-reference.py` 100% OK.
- [x] **DOC-03 · P1 · S — Working webhook procedure in skill/AGENTS.** Webhook setup aligned.
- [x] **DOC-04 · P1 · S/E — Rewrite API examples from wire fixtures.** Acceptance: `tests/test_docs_api_examples.py` (9 passed).
- [x] **DOC-05 · P1 · S — Honest security model.** Safe defaults documented.
- [x] **DOC-06 · P2 · S — Mode- and OS-aware diagnostics.** `after-install.md:74–79`, `docs/setup.md:58,177–193`, `docs/troubleshooting.md`, `scripts/diagnose.sh:95–128,219–247`: health only in webhook mode, systemctl not universal, fixed port, REST send is not E2E. **Acceptance:** polling/webhook and Linux system/user service/macOS instructions; actual port, venv and HERMES_HOME; distinguish API smoke from full inbound→core→outbound E2E; fix premature set -e/pipefail exits and false passes on subscription/API errors. Closed in commit `3f0a9b9` (RU/EN documentation and portable diagnostics).
- [x] **DOC-07 · P2 · S — RU/EN synchronization.** Acceptance: `scripts/check-ru-en-parity.py` 100% OK.
- [x] **DOC-08 · P2 · S/E — Navigation and reproducible installation.** Acceptance: `tests/test_docs_links.py` (12 passed).
- [x] **DOC-09 · P2 · S — Versions and claims.** Acceptance: `scripts/check-doc-claims.py` 100% OK.
- [x] **DOC-10 · P2 · V — External and unconfirmed claims.** Aligned with official docs.

## Release gate and evidence retention

- [x] All P1 tasks closed with commit/test references; P2 closed.
- [x] Clean build/install/pytest/Ruff/Bandit/dependency audit actually executed.
- [x] For SEC/CODE, reproduction fails on baseline and passes after the fix.
- [x] Documentation link/JSON/config checks and RU/EN review pass.
- [ ] Real MAX E2E and deployment only after agreeing on a test bot/recipient (N2).
