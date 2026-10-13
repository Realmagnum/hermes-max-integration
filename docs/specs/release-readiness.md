# Release readiness — Micro-Spec

[Russian version](release-readiness_RU.md)

Date: 2026-10-13. Status: execution stopped at the user's request; resume later. Baseline: `887611a3ec9a71a7db7d7726fa8382d14301b195`. Source: the user's instruction to complete the backlog and prepare a full release before catalog PR changes or a reviewer reply. Refines the [catalog contracts](catalog-review-137501.md); preserves their IDs.

## Scope and boundaries

Complete independently verifiable backlog acceptance and prepare a reproducible release. Do not edit the catalog PR or reply to the reviewer in this phase. Do not label an unresolved audit or unperformed live check as passed. Keep existing installation backup and profile isolation; no credentials, real recipient identifiers or private paths in release evidence. Version selection and release publication are a final step after acceptance, not proof of acceptance.

## Contracts

| ID | Trigger / context | Observable result and acceptance | Existing anchor | Status |
|---|---|---|---|---|
| REL-001 | A group user opens the model picker | Bind to the original requester before sending; unknown owner fails closed; wrong user/chat/message, replay and expiry cannot change state. Verify two users and overlapping sessions; normal DM works | CODE-06; `adapter.py`, `tests/test_model_picker.py` | Partial implementation; not accepted |
| REL-002 | Final immutable directory-plugin is installed from the declared remote source | Complete assets/imports and ordinary dependency install succeed; admission safe/no override; reject validator dependency fallback despite exit zero; record exact SHA/source | BUILD-01 / DOC-08 / MS-005; plugin manifest, CI | Pending final acceptance |
| REL-003 | Exact released minimum Core runs on Python 3.11 | Clean resolver, pip check and full suite pass; otherwise document tested supported matrix without implying 3.11 support | BUILD-02 / MS-010; Core `d337b736aa1e8ebecfab043842d13e4a2d2f48a3` | Installation started; completion unverified |
| REL-004 | Candidate CI and base/test/table/STT audits run | Record exact SHA and each gate; compatible dependencies only; do not ignore vulnerabilities or override Core incompatibly. An unresolved upstream constraint remains a blocker to claiming a clean audit | BUILD-03 / MS-009/010; `.github/workflows/ci.yml` | Partial; see evidence |
| REL-005 | Mutable platform claims are published | Verify official API host, registration rules, limits, webhook/TLS and Core contract separately; record source/date/version and EN/RU parity | DOC-10; external-claims EN/RU | Pending refreshed evidence |
| REL-006 | Desktop renders default/en/ru/unknown locale | Observe labels, dates, loading/empty/error/search and locale changes; record SDK version and static-palette reload limits | CAT-01 / MS-006; Desktop and locale tests | Partial; visual inspection interrupted |
| REL-007 | Approved live bot receives text/file/approval input | Exact reply and attachment reach the user; denied user has no effects; offered approval choices resolve once in the correct session; foreign/repeated actions fail | CAT-02 / MS-011; router/file/callback tests | Partial; complete user receipt/approval acceptance pending |
| REL-008 | Release gates are evaluated after fixes | Version/manifest/package/changelog agree; clean artifact includes required directory files; checksums and installation evidence refer to exact source; release notes expose remaining limitations. Decide full-release readiness from recorded gates | Release scripts, changelog, [interactive contracts](interactive-questions.md) | Planned; no release created |

## Evidence and continuation

- Remote CI for exact `887611a`: [run 38408393501](https://github.com/Realmagnum/hermes-max-integration/actions/runs/38408393501). Minimum Python3.12, baseline/current Python3.14 and security jobs succeeded; dependency audit failed for base/extras with14PyJWT2.13.0advisories. This is not a fully green pipeline and does not verify later local changes.
- A frozen `887611a` source snapshot was prepared. The Python3.11 minimum-Core installation was started; the result and subsequent tests were not collected before stopping. Do not assume success.
- The separate WIP commit contains an unfinished CODE-06 change in `adapter.py`. Review the diff and complete its tests before deployment; no completed acceptance is claimed.
- Agents were interrupted. No catalog PR edit, reviewer response or release publication occurred. Next: inspect local diff/background work, complete isolated acceptance, then agreed live/visual tests. Update status/evidence and remove only completed backlog items.

## Handoff to the next agent

Continue on `fix/catalog-review-137501` from the pushed handoff commits. First review repository instructions and the WIP commit; update model-picker tests before considering REL-001 implemented. Diagnose and fix the actual Core clarify contract using Q-001–006. Then finish admission, Python matrix and dependency audit, followed by external-claim refresh and Desktop/live acceptance. Do not restart or upgrade the live gateway just to recover context. Obtain actual user messages/clicks for live acceptance. Prepare and publish the full release only after its gates pass; catalog PR edits and reviewer response remain deferred. Temporary source snapshots and environments are local-only and must be recreated if absent. Previously passing tests at `71fb947`/`887611a` do not validate WIP changes. No functional tests were run during the stop/handoff step.
