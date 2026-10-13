# MAX catalog review — Micro-Spec

[Russian version](catalog-review-137501_RU.md)

Date: 2026-10-13. Implementation: [`71fb947`](https://github.com/Realmagnum/hermes-max-integration/commit/71fb947ea7e3ba0c2ffc8dc88b7606e9b879869d), branch `fix/catalog-review-137501`. This record describes implemented behavior and actual acceptance evidence; it does not claim completed review or release.

## Intent and boundaries

Address the four required changes and four recommendations in [review 5501512593](https://github.com/NousResearch/hermes-agent/pull/137501#pullrequestreview-5501512593). Baseline plugin: `9b4df24c07933968742edb156283a75bd43a6aa8`, version 2.10.2. Preserve the original MS identifiers from the planning handoff. Only this change delta is specified; unrelated features and a Core refactor are outside scope. The historical audit baseline is `b004c573318f1d5e521255531d1943cc8a8b8b90`.

Verified means the named acceptance scope passed. Partial means implementation exists but an acceptance condition remains. Pending means the required publication or observation has not occurred. Automated verification and live delivery are separate evidence.

Source handoff: `2026-10-13_hermes-max-catalog-review-microspec.md`, sections “Behavior contracts” and “Evidence and completion”; execution notes supplied the dated results below. The source plan remains separate. This repository record supersedes its obsolete blanket unscoped refusal and planned-only status, with corrections explicitly recorded below.

## Behavior contracts

| ID | Trigger / context | Required observable result | Acceptance evidence | Source / implementation | Status |
|---|---|---|---|---|---|
| MS-001 | New setup, default answer or refusal of public access | Access stays private; an existing allowlist survives unless allow-all is explicitly selected | Setup fixtures assert false default, preserved IDs and explicit allow-all | Required 1; `adapter.py`; [catalog security tests](../../tests/test_catalog_security.py) | Verified |
| MS-002 | Empty closed allowlist or denied sender: message, media, command, callback, start/add event | Reject before download, Core dispatch or approval; preserve the owner's pending state | DM/group policy matrix; denied media produces no download/dispatch; foreign callback does not consume state | Required 1 / recommendation 1; [catalog security](../../tests/test_catalog_security.py), [callback authorization](../../tests/test_callback_auth.py), [group access](../../tests/test_group_access.py) | Verified |
| MS-003 | Profile A has an installed scope while process env contains B; default-profile multiplex startup has no scope | A's scope is authoritative, including a missing token; default startup uses Core's supported platform helper; unexpected errors propagate | Real Core registry constructs the default adapter without connecting; empty routed scope rejects env/config fallback; lookup-error fixtures | Required 2; `credential_support.py`, `adapter.py`, `mixins/standalone.py`; [catalog security](../../tests/test_catalog_security.py), [file send](../../tests/test_file_send.py) | Verified |
| MS-004 | Diagnostics run with caller-provided MAX credentials or without them | Use caller env; do not open credential files or disclose secret values/API bodies/token arguments | Fake credential-file read is forbidden; token markers absent from output and process arguments; missing env produces failure | Required 2; `scripts/diagnose.sh`; [diagnostic privacy](../../tests/test_diagnostics_privacy.py) | Verified |
| MS-005 | Plugin installation and documented media procedures | No bundled Core-editing script or instructions; describe unsupported public router behavior honestly | Script removed; docs checks pass; earlier source admission reported safe/no Core override; repeat exact final admission remains in release gate | Required 3; [Core router tests](../../tests/test_core_send_router.py), [architecture](../architecture.md) | Verified for script removal and isolated router; final admission pending |
| MS-006 | Desktop default/en/ru/unknown locale and locale changes | English default/fallback, Russian pack, locale-aware dates through public SDK | Shipped-JS harness checks loading/empty/error/search/date behavior; real Desktop en/ru labels and dates observed; complete visual state matrix not finished | Required 4; `desktop/plugin.js`; [Desktop behavior](../../tests/test_desktop_locale_behavior.py), [locale manifest](../../tests/test_locales_manifest.py) | Partial |
| MS-007 | Core requests exec approval | Inherited entry point sends only offered choices; owner/chat/message/TTL checks reject another user's action | Actual Core entry point exercised; permitted choices mapped; unoffered choice rejected without consuming pending state | Recommendation 2; `mixins/buttons.py`; [catalog security](../../tests/test_catalog_security.py), [interactive](../../tests/test_interactive.py), [callback authorization](../../tests/test_callback_auth.py) | Verified automatically; live buttons belong to MS-011 |
| MS-008 | API/upload and download clients are created | Additional CA limited to API/upload; standard download TLS, SSRF protection and token isolation retained; README discloses trust extension | Download client verify=True; CA/DNS/origin/token fixtures pass; README EN/RU disclosure present | Recommendation 3; [TLS](../../tests/test_ssl_support.py), [SSRF](../../tests/test_ssrf_download.py), [token isolation](../../tests/test_download_token_leak.py), [catalog security](../../tests/test_catalog_security.py) | Verified |
| MS-009 | Clean install and optional dependency setup | Normal resolution without incompatible overrides; fixed Playwright/browser revision; truthful audit results | Minimum/current resolver and pip check pass; Playwright setup fixtures pass; PyJWT audit has 14 advisories; complete final base/extras gate is unresolved | Recommendation 4; `plugin.yaml`, `pyproject.toml`; [Playwright setup](../../tests/test_setup_playwright.py), [CI contracts](../../tests/test_ci_pinned_core.py) | Partial |
| MS-010 | Minimum and later pinned Core fixtures run | Explicit Core/Python pins; collect and run tests; installation failures cannot be hidden by validator fallback | Minimum/current full suites pass; matrix and both dependency-failure guards tested; final remote CI/audit not confirmed green | CI compatibility; [workflow](../../.github/workflows/ci.yml), [CI contracts](../../tests/test_ci_pinned_core.py), [lifecycle](../../tests/test_lifecycle.py) | Partial |
| MS-011 | Text/media/approval delivery is claimed | Report actual delivery scope; partial attachment delivery or rejected media-only routing cannot be called complete success | Actual registry/router tests; live standalone text+file API readback; live inbound reaches Core and response dispatch; exact user receipt and live approval selection unconfirmed | Release gate; [Core router](../../tests/test_core_send_router.py), [file send](../../tests/test_file_send.py), [wire regressions](../../tests/test_wire_regressions.py) | Partial |
| MS-012 | Candidate is submitted for repeat catalog review | Catalog pins the tested immutable plugin SHA; admission/schema/CI and reviewer response refer to it | Branch pushed; catalog repin, generic media issue, final admission/schema, reviewer reply and repeat review still pending | Catalog publication; [PR](https://github.com/NousResearch/hermes-agent/pull/137501) | Pending |

## Material contract corrections

- MS-003: a blanket refusal of unscoped multiplex reads was incorrect. Core intentionally constructs the default platform unscoped; `get_scoped_secret` implements its startup env fallback. An installed routed scope remains authoritative. The passive dependency probe must not read credentials.
- MS-006: older supported Desktop SDKs lack the optional locale-change callback. The page uses reactive plugin i18n; static palette strings require reload on those SDKs. No private-store/DOM patch is used.
- MS-010: the claimed Core >=0.20 floor was replaced by >=0.21.4 after testing the exact released minimum. Core 0.20 lacks the native exec-approval hook. This is a verified supported floor, not a claim that every intervening revision was tested.
- MS-011: the tested public Core router rejects media-only input before plugin dispatch. The lower adapter can send it; that is not proof of generic Core routing. No Core patch is shipped.

## Recorded verification

| Fixture / check | Actual result | Boundary |
|---|---|---|
| Minimum Core 0.21.4: `d337b736aa1e8ebecfab043842d13e4a2d2f48a3`, isolated Python 3.12.10, Windows | Clean install of Core plus plugin/test/tables: 87 resolved packages; pip check pass; 776 tests passed, 62.51s | No incompatible dependency overrides; Python 3.11 not verified |
| Later Core source: `ca13a7828acd2ba8c75e1c1d1694cbc1aee7df3f`, Python 3.14.7, Windows | Final implementation: 776 tests passed, 49.98s; Ruff, pip check, config/claims/parity and 30 Markdown link checks pass | Fixed source fixture; not a moving-main claim |
| Earlier baseline: `d0288be5b3330d2442e3907185b8e9d0958297bb` | Updated credential/security/file cases: 60 passed | Shared compatible dependencies; not a clean full-suite proof of the final candidate |
| Source admission before final helper/floor updates | Dependency install succeeded; safe; no Core override | Not final `71fb947` admission evidence |
| Wheel build of `71fb947`: `uv build --wheel` | Build passed; adapter, credential_support, ssl_support and mixins packaged | Python distribution only; not the full Hermes directory bundle; setuptools license-table deprecation warning |
| Bandit high-severity CI threshold | Passed on implementation snapshot | Low/medium findings remain; not a zero-findings audit |
| Dependency audit of pinned later Core | 14 PyJWT 2.13.0 advisories | Upstream constraint; no ignored advisories or incompatible override; see [external claims](../external-claims.md) |
| Installed Core `7157422022ff06f3e632d1dd394ee1253b17ad37`, webhook mode | Token stays in active profile's `.env`; corrected helper matches workspace; graceful restart connects MAX; local/public health succeeds; incoming message reaches Core and reply dispatch | Real secrets, recipients and hostnames omitted; user receipt of requested marker and live approval selection not confirmed |
| Registered standalone sender, installed Core | Text plus file returned success/media_delivered/media_sent=1; API readback HTTP200 confirmed attachment and recipient | Outbound evidence only; no substitute for inbound/approval acceptance |

## Historical audit reconciliation

These are inherited repairs already present in the candidate, not all changes introduced by `71fb947`. Original audit details remain in Git history; [changelog](../../CHANGELOG.md) records release history. [Backlog](../../BACKLOG.md) contains only outstanding work.

| Audit IDs | Current disposition | Regression evidence |
|---|---|---|
| SEC-01 | Exec/slash/clarify defect closed; model-picker owner policy remains CODE-06 | `test_callback_auth.py`, `test_catalog_security.py` |
| SEC-02, SEC-03, SEC-04 | Closed within tested token/DNS/webhook boundaries | `test_download_token_leak.py`, `test_ssrf_download.py`, `test_webhook_security.py` |
| SEC-05, SEC-06, SEC-07 | Closed within tested access/media boundaries | `test_cross_session.py`, `test_group_access.py`, `test_inbound_media_limits.py` |
| CODE-01, CODE-02, CODE-03, CODE-04 | Closed | `test_poll_backoff.py`, `test_chunking.py`, `test_streaming_isolation.py`, `test_model_picker.py` |
| CODE-05, CODE-07, CODE-08 | Closed in verified Core fixtures | `test_webhook_readiness.py`, `test_webhook_health_contract.py`, `test_lifecycle.py`, `test_backpressure.py` |
| CODE-06 | Partial: unowned group picker binds its owner to first tap | `test_model_picker.py`; strict original-requester binding not established |
| BUILD-01, BUILD-02 | Original packaging/path defects resolved; remaining final install and Python coverage checks retained | Clean minimum install/full tests, wheel build; `test_ci_pinned_core.py`, `tests/conftest.py` |
| BUILD-03, BUILD-04 | Gates/regression implementations exist; remote audit and remaining live acceptance retained | `test_wire_regressions.py`, `test_docs_api_examples.py`, `test_core_send_router.py` |
| DOC-01, DOC-02, DOC-03, DOC-04, DOC-06 | Documented single STT/config/webhook/wire/diagnostic defects closed | Config checker; `test_webhook_mode_docs.py`, `test_docs_api_examples.py`, `test_diagnostics_privacy.py` |
| DOC-05, DOC-07, DOC-09 | Current security caveats, EN/RU backlog and unreleased history corrected; structural checks are not proof of every historical translation | Documentation checks; historical 2.10 test counts describe those releases only |
| DOC-08, DOC-10 | Navigation/unsupported claims corrected; remote-source installation and renewed external verification remain | Link checker, `test_doc_external_claims.py`; dated external register is not renewed verification |

## Reproduction and completion

Use an isolated checkout and the exact Core fixture from CI. Install Core separately and the plugin with test/table extras through normal dependency resolution. Run pip check, pytest and Ruff; then the existing claims/config/parity/link checkers. In a populated development checkout, pass tracked Markdown files to the link checker so unrelated environment README files are excluded. Check admission logs as well as exit status: minimum and later Core emit different dependency-install failure messages.

Keep live tests on an approved bot/recipient. Record input, observed output and Core/candidate revision without credential or personal-data dumps. Do not treat health, a send attempt or mocked callbacks as proof of complete delivery. The outstanding checks in the backlog must pass before the corresponding contracts are accepted and repeat review is described as ready.
