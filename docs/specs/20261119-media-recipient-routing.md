# Media recipient routing — Micro-Spec

[Russian version](20261119-media-recipient-routing_RU.md)

Source: attachment delivery bug investigation. Baseline: `69717984d5ee2c81007d4b59242765c8db6bcd69`. Core: installed local runtime, not a pinned CI fixture.

## Contract

Route local image/file/audio/video attachments using the MAX recipient query parameter, without changing upload, retry, download, TLS, authorization or Core behavior. Official contract: https://dev.max.ru/docs-api/methods/POST/messages/ (`user_id` for users, `chat_id` for chats/channels; checked 2026-11-19).

| ID | Trigger | Required result | Implementation | Verification |
|---|---|---|---|---|
| MR-001 | Bare negative target | Adapter upload/send uses only `chat_id`; all four local media entry points | Implemented | Offline verified |
| MR-002 | Explicit `chat:` or `user:` target; bare positive DM/user | Explicit namespace preserved, positive defaults to user; known adapter DM chat ID maps to user ID | Implemented | Offline verified |
| MR-003 | Standalone text/media delivery | Same namespace and sign routing, without adapter-only DM state | Implemented | Offline verified |
| MR-004 | Attachment processing delay or ambiguous send | Existing bounded readiness retry policy and single upload preserved | Unchanged | Existing readiness tests pass |

## Evidence

Acceptance is offline: real asynchronous production entry points with replaced network/upload boundaries. Live delivery, full pinned-Core CI matrix and deployment are not claimed. Verification 2026-11-19, baseline plus this diff: `pytest tests/test_media_recipient_routing.py -q` → 73 passed (baseline with the same tests: 15 failed, 58 passed). The first `send_document("-42", ...)` regression failed before production edits: actual `user_id=-42`, expected `chat_id=-42`; the same test fails on release pin `50c7a9a7c16b6207a079b7b883718dd863e9e951` and installed pin `ae49b6092ed190ff721237f1676205edfaee8dec`. Targeted media/readiness/security suite: 298 passed. Full suite with exported Core source `ca13a7828acd2ba8c75e1c1d1694cbc1aee7df3f`, Python 3.14.9 and reused installed runtime dependencies: 984 passed, 6 skipped (Core standalone-policy feature guards); this is not a clean CI dependency installation. The runner pre-imported the plugin tests namespace to avoid collision with Core tests. On the installed local Core runtime, full baseline and candidate both had the same 15 unrelated failures (clarify API and removed send-message module). Changed-file Ruff passes; full Ruff has two identical baseline RUF100 findings in package `__init__.py` files. pytest-asyncio reports an existing unset loop-scope warning. Complete minimum/baseline/current CI, dependency audit and live delivery were not run. Non-goals: URL-image, location and button routing; broad parser refactoring; new target grammar; production operations.
