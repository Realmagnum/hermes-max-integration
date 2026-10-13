# Outstanding work

[Russian version](BACKLOG_RU.md)

Reviewed 2026-10-13 against implementation `71fb947`. Completed work is removed from this list; audit IDs and evidence remain in the [Micro-Spec](docs/specs/catalog-review-137501.md) and [changelog](CHANGELOG.md). The original audit of `b004c573318f1d5e521255531d1943cc8a8b8b90` remains in Git history. Old checkboxes do not establish current defects.

## Acceptance still outstanding

Execution resumed on 2026-10-13. Completed items (CODE-06, BUILD-02, DOC-10, CAT-01, INT-01) were verified and moved to [changelog](CHANGELOG.md) and [Micro-Specs](docs/specs/). Remaining work to complete before release publication and repeat catalog review:

- [ ] **BUILD-01 / DOC-08 · P1 — Final directory-plugin admission and remote-source install.** Minimum-Core clean install and wheel build pass; earlier source admission succeeded. **Acceptance:** validate the final immutable candidate with `hermes plugins validate <plugin-path> --install-deps`; reject both dependency-failure fallback messages; confirm directory assets/runtime import and record remote repository/SHA. A Python wheel is not the complete Hermes directory bundle. GitHub/Gitea equivalence is unverified.
- [ ] **BUILD-03 / MS-009 / MS-010 · P1 — Final CI and dependency audit.** Workflow coverage and install-failure detection exist; pinned Core PyJWT 2.13.0 produces 14 advisories. **Acceptance:** record exact candidate CI and base/test/table/STT audit results; resolve the upstream constraint compatibly. No ignored advisories or incompatible override. The old Gitea-runner criterion is unverified; record the actual remote platform.
- [ ] **CAT-02 / MS-011 · P1 — Complete live delivery and approvals.** Live text, file delivery, model picker and clarify prompts are confirmed in MAX; standalone text+file has API readback. **Acceptance:** verify live execution approval prompt selection (`_send_exec_approval_prompt`) with real offered choices in the running gateway. Commit no real credentials/recipients.
- [ ] **REL-01 / REL-008 · P1 — Complete release.** Prepare the final version, paired changelogs, immutable source/artifacts and checksums after open acceptance passes. **Acceptance:** verify installation from the released artifact and record exact evidence. Release publication is pending; tests from older commits do not qualify a new candidate.
- [ ] **CAT-03 / MS-012 · Deferred until release — Catalog publication and repeat review.** The user explicitly postponed catalog PR changes and the reviewer response until a complete release. Afterwards, repin released SHA/image/docs, run schema/admission checks and provide exact CI/evidence links. Preparation of the generic Core media issue remains open; nothing was published during this pause.

## Recently closed in this cycle (verified evidence recorded)

- **INT-01 / Q-001–006:** Native `clarify` choices with Core gateway resolution, single button per row layout, Other text interception, duplicate MessageEvent elimination, and live user verification in chat.
- **CODE-06 / REL-001:** Model picker requester binding and fail-closed handling for unowned group sessions (`tests/test_model_picker.py`).
- **BUILD-02 / REL-003:** Pinned supported Python matrix to `>=3.12` (Python 3.11 excluded); Core >=0.21.4 verified.
- **CAT-01 / MS-006:** Desktop UI visual acceptance completed (EN default, RU pack, date localization); recorded static manifest description limitation.
- **DOC-10 / REL-005:** External claims verification register refreshed on 2026-10-13 (`docs/external-claims.md`).

Latest CI evidence for documentation baseline `887611a`: [GitHub Actions run 38408393501](https://github.com/Realmagnum/hermes-max-integration/actions/runs/38408393501) passed minimum Python 3.12, baseline/current Python 3.14 and security jobs; dependency audit failed with 14 PyJWT 2.13.0 advisories. BUILD-03 remains open. Python 3.11 installation was started, but its result and acceptance tests were not collected; BUILD-02 remains open.

## Closing a task

Close only independently verified acceptance. Update MS status/evidence and EN/RU changelog; remove completed items here. Retain residual conditions explicitly instead of keeping fixed defects in the roadmap. A failing audit or an unperformed live check stays open.
