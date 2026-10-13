# Release readiness — Micro-Spec

[Russian version](20261013-release-readiness_RU.md)

Date: 2026-10-13. Status: in progress — acceptance contracts REL-001, REL-003, REL-005, REL-006 verified. Baseline: `63846af6ca9d585ae16167684d2c5324c3c8c876`. Source: user instruction to complete backlog acceptance before catalog PR update or reviewer reply. Refines [catalog contracts](20261013-catalog-review-137501.md); preserves their IDs.

## Scope and boundaries

Complete independently verifiable backlog acceptance and prepare a reproducible release. Do not edit the catalog PR or reply to the reviewer in this phase. Do not label an unresolved audit or unperformed live check as passed. Keep existing installation backup and profile isolation; no credentials, real recipient identifiers or private paths in release evidence. Version selection and release publication are a final step after acceptance, not proof of acceptance.

## Contracts

| ID | Trigger / context | Observable result and acceptance | Existing anchor | Status |
|---|---|---|---|---|
| REL-001 | A group user opens the model picker | Bind to the original requester before sending; unknown owner fails closed; wrong user/chat/message, replay and expiry cannot change state. Verify two users and overlapping sessions; normal DM works | CODE-06; `adapter.py`, `tests/test_model_picker.py` | Verified; commit `7cf6516` covers requester binding and fail-closed isolation |
| REL-002 | Final immutable directory-plugin is installed from the declared remote source | Complete assets/imports and ordinary dependency install succeed; admission safe/no override; reject validator dependency fallback despite exit zero; record exact SHA/source | BUILD-01 / DOC-08 / MS-005; plugin manifest, CI | Pending final acceptance |
| REL-003 | Exact released minimum Core runs on Python 3.12 | Clean resolver, pip check and full suite pass; supported Python matrix pinned to >=3.12 (Python 3.11 excluded); Core >=0.21.4 | BUILD-02 / MS-010; Core `d337b736aa1e8ebecfab043842d13e4a2d2f48a3` | Verified; pyproject.toml and setup docs require >=3.12 |
| REL-004 | Candidate CI and base/test/table/STT audits run | Record exact SHA and each gate; compatible dependencies only; do not ignore vulnerabilities or override Core incompatibly. An unresolved upstream constraint remains a blocker to claiming a clean audit | BUILD-03 / MS-009/010; `.github/workflows/ci.yml` | Partial; see evidence |
| REL-005 | Mutable platform claims are published | Verify official API host, registration rules, limits, webhook/TLS and Core contract separately; record source/date/version and EN/RU parity | DOC-10; external-claims EN/RU | Verified; register refreshed on 2026-10-13 |
| REL-006 | Desktop renders default/en/ru/unknown locale | Observe labels, dates, loading/empty/error/search and locale changes; record SDK version and static-palette reload limits | CAT-01 / MS-006; Desktop and locale tests | Verified; visual acceptance completed. Limitation: manifest description is static |
| REL-007 | Approved live bot receives text/file/approval input | Exact reply and attachment reach the user; denied user has no effects; offered approval choices resolve once in the correct session; foreign/repeated actions fail | CAT-02 / MS-011; router/file/callback tests | Partial; text/file/clarify verified live, live exec approval prompt selection pending |
| REL-008 | Release gates are evaluated after fixes | Version/manifest/package/changelog agree; clean artifact includes required directory files; checksums and installation evidence refer to exact source; release notes expose remaining limitations. Decide full-release readiness from recorded gates | Release scripts, changelog, [interactive contracts](20261013-interactive-questions.md) | Planned; no release created |

## Evidence and continuation

- Remote CI for snapshot `887611a`: [run 38408393501](https://github.com/Realmagnum/hermes-max-integration/actions/runs/38408393501) passed minimum Python 3.12, baseline/current Python 3.14 and security jobs; dependency audit reported 14 PyJWT 2.13.0 upstream advisories.
- Python coverage (REL-003): Python matrix explicitly pinned to `>=3.12` in `pyproject.toml` and documentation; Python 3.11 excluded from support.
- Model picker requester binding (REL-001): completed in commit `7cf6516`; 22 isolation tests pass.
- Desktop UI visual acceptance (REL-006): completed; English default, Russian pack and date formatting verified. Recorded limitation: manifest description in Capabilities -> Plugins is static.
- External claims (REL-005): register refreshed on 2026-10-13 in `docs/external-claims.md`.
- Interactive clarify (Q-001–Q-006): choice labels, Other text input and repeat click inertness confirmed live in chat.
- Remaining items before release (REL-008): final directory-plugin admission validation (`--install-deps`), live execution approval prompt verification, and remote CI audit verification.

## Handoff to the next agent

Continue on `fix/catalog-review-137501` from commit `63846af`. The core contracts for clarify (Q-001–006), model picker requester binding (REL-001), Python matrix (REL-003), Desktop visual check (REL-006) and external claims (REL-005) are verified. Next: complete live execution approval verification (`_send_exec_approval_prompt`), directory admission validation with `--install-deps`, and evaluate final release gates. Do not edit catalog PR or reply to reviewer until full release is prepared.
