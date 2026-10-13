# Outstanding work

[Russian version](BACKLOG_RU.md)

Reviewed 2026-10-13 against implementation `71fb947`. Completed work is removed from this list; audit IDs and evidence remain in the [Micro-Spec](docs/specs/catalog-review-137501.md) and [changelog](CHANGELOG.md). The original audit of `b004c573318f1d5e521255531d1943cc8a8b8b90` remains in Git history. Old checkboxes do not establish current defects.

## Acceptance still outstanding

- [ ] **CODE-06 · P2 — Model-picker ownership policy.** An unowned group picker binds ownership to the first live tap; strict original-requester binding is not established. TTL, stale-message and second-user rejection tests exist. **Acceptance:** decide and document the intended policy; verify missing owner/message metadata, two users and stale callbacks. A stricter policy requires a separate behavior change. Related SEC-01 exec/slash/clarify protections are complete.
- [ ] **BUILD-01 / DOC-08 · P1 — Final directory-plugin admission and remote-source install.** Minimum-Core clean install and wheel build pass; earlier source admission succeeded. **Acceptance:** validate the final immutable candidate with `hermes plugins validate <plugin-path> --install-deps`; reject both dependency-failure fallback messages; confirm directory assets/runtime import and record remote repository/SHA. A Python wheel is not the complete Hermes directory bundle. GitHub/Gitea equivalence is unverified.
- [ ] **BUILD-02 · P2 — Remaining Python coverage.** Exact Core 0.21.4/Python 3.12 and later Core/Python 3.14 are verified. Historical Python 3.11 acceptance is unverified. **Acceptance:** test 3.11 with the released minimum or explicitly define a narrower supported Python matrix; preserve Core >=0.21.4 and the recorded fixtures.
- [ ] **BUILD-03 / MS-009 / MS-010 · P1 — Final CI and dependency audit.** Workflow coverage and install-failure detection exist; pinned Core PyJWT 2.13.0 produces 14 advisories. **Acceptance:** record exact candidate CI and base/test/table/STT audit results; resolve the upstream constraint compatibly. No ignored advisories or incompatible override. The old Gitea-runner criterion is unverified; record the actual remote platform.
- [ ] **DOC-10 · P2 — Refresh external claims.** The external register is dated 2026-09-16; fixtures do not refresh platform eligibility, limits or TLS rules. **Acceptance:** verify current official MAX/Telegram/Core sources, record date/version and synchronize EN/RU. Preserve the tested media-only Core limitation.
- [ ] **CAT-01 / MS-006 · P1 — Complete Desktop visual acceptance.** Shipped-JS harness and observed EN/RU labels/dates pass; manual inspection was interrupted. **Acceptance:** inspect default/en/ru/unknown locale, loading/empty/error/search and locale changes; document older SDK static-palette reload limitations.
- [ ] **CAT-02 / MS-011 · P1 — Complete live delivery and approvals.** Incoming messages reach Core/reply dispatch; standalone text+file has API readback. **Acceptance:** confirm the approved user's exact response/attachment receipt, denied-user behavior and real offered approval choices in the running gateway. Health, send attempts and isolated tests are insufficient. Commit no real credentials/recipients.
- [ ] **CAT-03 / MS-012 · P1 — Catalog publication and repeat review.** Implementation branch is pushed. **Acceptance:** publish the generic Core media issue, repin catalog SHA/image/docs, run final schema/admission checks, provide exact CI/evidence links and reply to the reviewer. These external actions require the user's instruction; this documentation update does not publish them.

## Closing a task

Close only independently verified acceptance. Update MS status/evidence and EN/RU changelog; remove completed items here. Retain residual conditions explicitly instead of keeping fixed defects in the roadmap. A failing audit or an unperformed live check stays open.
