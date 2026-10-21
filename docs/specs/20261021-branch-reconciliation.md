# Branch history reconciliation

[Russian version](20261021-branch-reconciliation_RU.md)

Date: 2026-10-21. Candidate `20ca676` preserves baseline `5144194`; incoming branch `598d57b` diverged at `2682f49`. The old HEAD is preserved as `archive/microspec-pipeline-20261021` on GitHub and Gitea. Histories are joined by a normal merge without force-push, using the file decisions below. This is neither a rollback to 2.10.2 nor new release acceptance.

## File decisions

| Paths | Decision |
|---|---|
| `BACKLOG.md`, `BACKLOG_EN.md` | Retain current EN/RU backlog; obsolete 2.10.2 completion claims stay in archived history. |
| `CHANGELOG.md`, `CHANGELOG_EN.md` | Retain the 2.11.0 release record and new session fix, not duplicate 2.10.2 notes. |
| `README.md`, `README_EN.md` | Retain current English-primary/Russian-counterpart layout and verified feature claims. |
| `adapter.py` | Retain owner-bound current model picker and Core media-output hook. Preserve incoming send-action diagnostic logging; omit obsolete send_message_handler registration. |
| `mixins/media_upload.py` | Preserve action-failure debug logging atop current upload/security implementation. |
| `mixins/standalone.py` | Retain current file/image upload policy and tested fallback; the older image-type change is outside session scope and requires separate wire/API validation. |
| `mixins/plugin_media_handler.py`, `tests/test_plugin_media_handler.py`, `tests/test_plugin_media_handler_contract.py` | Do not revive alternative media parsing/registration; current Core send-router and output-hook regressions cover the supported architecture. |
| `plugin.yaml` | Retain version 2.11.0, ru/en YAML locale registration and the new session settings. |
| `pyproject.toml` | Retain bounded dependencies and Python >=3.12. Do not add workspace-only hermes-agent source; standalone plugin has no such workspace dependency. |
| `locales/en-US.json`, `locales/ru-RU.json` | Do not revive incompatible JSON language-pack schema; current ru/en YAML packs and real Desktop harness remain authoritative. |
| `docs/specs/.state.json`, `docs/specs/README.md`, `docs/specs/01-sec-audit.md`, `docs/specs/02-code-transport.md`, `docs/specs/03-model-picker.md`, `docs/specs/04-native-media.md`, `docs/specs/05-locales-desktop.md`, `docs/specs/06-build-ci.md` | Retain dated bilingual specs and evidence conventions; original historical contracts remain readable at the archived commit. Do not promote old planned/closed status to current acceptance. |
| `tests/test_cross_session.py` | Retain current session policy regressions; omit a test that only reimplements a Desktop filter in Python instead of exercising Desktop code. |
| `tests/test_model_picker.py` | Preserve the incoming regression exercising provider-message deletion through the actual callback. |
| `tests/test_ru_en_parity.py` | Retain current YAML/manifest/real-Desktop coverage; omit tests for the superseded JSON schema and a test-local fallback function. |
| `tests/test_webhook_security.py` | Preserve dynamic test-port allocation, avoiding the production gateway port. |

## Verification

The resulting tree differs from `20ca676` only by the documented action logging, model-picker regression, test-port isolation, collected test count and this record. Final verification on 2026-10-21: 837 tests passed on Core ca13a782 (Python 3.14), one upstream warning; Ruff, version/test-count claims, configuration reference, EN/RU parity, 46 Markdown files and git diff --check passed. Production and real MAX messages are untouched. Unrelated deployment-stand files and working backlog changes are excluded. See [session policy](20261021-session-list-policy.md).
