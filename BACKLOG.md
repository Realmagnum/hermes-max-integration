# Outstanding work

[Russian version](BACKLOG_RU.md)

Reviewed 2026-10-13 against implementation `71fb947`. Completed work is removed from this list; audit IDs and evidence remain in the [Micro-Spec](docs/specs/20261013-catalog-review-137501.md) and [changelog](CHANGELOG.md). The original audit of `b004c573318f1d5e521255531d1943cc8a8b8b90` remains in Git history. Old checkboxes do not establish current defects.

## Acceptance still outstanding

Execution resumed on 2026-10-13. Completed items (CODE-06, BUILD-02, DOC-10, CAT-01, INT-01) were verified and moved to [changelog](CHANGELOG.md) and [Micro-Specs](docs/specs/). Follow-up acceptance and catalog review remaining after v2.11.0 publication:

- [ ] **BUILD-01 / DOC-08 · P1 — Final directory-plugin admission and remote-source install.** Minimum-Core clean install and wheel build pass; earlier source admission succeeded. **Acceptance:** validate the final immutable candidate with `hermes plugins validate <plugin-path> --install-deps`; reject both dependency-failure fallback messages; confirm directory assets/runtime import and record remote repository/SHA. A Python wheel is not the complete Hermes directory bundle. GitHub/Gitea equivalence is unverified.
- [ ] **BUILD-03 / MS-009 / MS-010 · P1 — Final CI and dependency audit.** Workflow coverage and install-failure detection exist; pinned Core PyJWT 2.13.0 produces 14 advisories. **Acceptance:** record exact candidate CI and base/test/table/STT audit results; resolve the upstream constraint compatibly. No ignored advisories or incompatible override. The old Gitea-runner criterion is unverified; record the actual remote platform.
- [ ] **CAT-02 / MS-011 · P1 — Complete live delivery and approvals.** Live text, file delivery, model picker and clarify prompts are confirmed in MAX; standalone text+file has API readback. **Acceptance:** verify live execution approval prompt selection (`_send_exec_approval_prompt`) with real offered choices in the running gateway. Commit no real credentials/recipients.
- [ ] **CAT-03 / MS-012 · P2 — Repeat catalog review decision.** [PR #138075](https://github.com/NousResearch/hermes-agent/pull/138075) submits immutable v2.11.0 with schema/admission/CI evidence; the [reviewer reply](https://github.com/NousResearch/hermes-agent/pull/137501#issuecomment-6156793138) is published. The generic Core media issue is already tracked in [#121864](https://github.com/NousResearch/hermes-agent/issues/121864). **Acceptance:** address new review and obtain the maintainer decision; submission and response are complete, catalog acceptance is not confirmed.

## Recently closed in this cycle (verified evidence recorded)

- **CAT-03 / MS-012 (submission):** released catalog [PR #138075](https://github.com/NousResearch/hermes-agent/pull/138075), 602 schema entries, 12 upstream checks and [reviewer reply](https://github.com/NousResearch/hermes-agent/pull/137501#issuecomment-6156793138); review decision pending.
- **INT-01 / Q-001–006:** Native `clarify` choices with Core gateway resolution, single button per row layout, Other text interception, duplicate MessageEvent elimination, and live user verification in chat.
- **CODE-06 / REL-001:** Model picker requester binding and fail-closed handling for unowned group sessions (`tests/test_model_picker.py`).
- **BUILD-02 / REL-003:** Pinned supported Python matrix to `>=3.12` (Python 3.11 excluded); Core >=0.21.4 verified.
- **CAT-01 / MS-006:** Desktop UI visual acceptance completed (EN default, RU pack, date localization); recorded static manifest description limitation.
- **DOC-10 / REL-005:** External claims verification register refreshed on 2026-10-13 (`docs/external-claims.md`).

Historical CI evidence for documentation baseline `887611a`: [GitHub Actions run 38408393501](https://github.com/Realmagnum/hermes-max-integration/actions/runs/38408393501) passed minimum Python 3.12, baseline/current Python 3.14 and security jobs; dependency audit failed with 14 PyJWT 2.13.0 advisories. BUILD-03 remains open. Python 3.11 investigation was later superseded by the verified Python >=3.12 support policy; BUILD-02 is closed.

Release publication completed on 2026-10-14: [v2.11.0](https://github.com/Realmagnum/hermes-max-integration/releases/tag/v2.11.0), tag commit `50c7a9a7c16b6207a079b7b883718dd863e9e951`, English notes, complete directory ZIP, wheel and SHA256SUMS. [Exact candidate CI](https://github.com/Realmagnum/hermes-max-integration/actions/runs/38473952610) passed minimum/baseline/current tests and directory admission plus security; dependency audit failed with 14 upstream PyJWT advisories. Publication does not close BUILD-03, remote-source installation or live execution-approval acceptance.

## Closing a task

Close only independently verified acceptance. Update MS status/evidence and EN/RU changelog; remove completed items here. Retain residual conditions explicitly instead of keeping fixed defects in the roadmap. A failing audit or an unperformed live check stays open.
