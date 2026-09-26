# Hermes MAX Integration 2.10 — Release Backlog (Pending Tasks)

[Russian](RELEASE_BACKLOG_2.10.md)

## Current Status

- **Branch:** `fix/rc-2.10-final-gates` → PR #1 → `RC-2.10`.
- **Final verification:** Gitea Actions [run #116](https://gitea.rmg7.com/agent/hermes-max-integration/actions/runs/116), SHA `fe58f91` (2026-09-26): Python 3.11/3.12 matrix, ruff, Bandit, the full pytest suite, and dependency audit are green.
- **CI infrastructure:** runner `hermes-max-release-runner` on `a1.rmg7.com` is operational and executes the release gate.
- **Completed and Stabilized in Codebase:**
  - **R1:** Polling backoff with `Retry-After`, lossless message chunking, streaming isolation per `(chat_id, message_id)` with flush timer, leak-free connect/disconnect lifecycle.
  - **R3:** Callback auth bound to chat/message/TTL, cross-session owner-only access, group allowlists (users & chats), backpressure queue & telemetry.
  - **R4:** Fail-closed webhook with extracted `_build_webhook_app`, secret validation before JSON parsing, payload limit, strict `/health` contract (`{"status": "ok"}`), telemetry extracted to `/metrics`.
  - **R5:** RU/EN backlogs are maintained in lockstep; run parity, link, external-claim, and API-example checks after every documentation change.

---

## Closed release work

### 0. RELEASE · Observed CI regressions from run #107 — closed

**Priority:** P0 · closed 2026-09-26
**Affected files:** `tests/test_download_token_leak.py`, `tests/test_ssrf_download.py`, `tests/test_wire_regressions.py`, `tests/test_webhook.py`, fixtures, and callback/streaming code — only where a test proves an implementation regression.

**Result:** all 11 failures are closed. Media tests now cover HTTP blocking and DNS pinning; callback tests cover owner/chat/message binding; streaming covers per-message state and flush; cross-session requires explicit opt-in; a secretless webhook returns `503`.

**Acceptance criteria:** reconfirmed in run #116.

---

### 0.1. RELEASE · Dependency audit — closed with a constrained upstream exception

**Priority:** P1 · closed 2026-09-26
**Result:** audit is green. `Pillow` is upgraded to the plugin-supported `12.3+`; six advisory IDs for `cryptography==46.0.7` and `hermes-agent==0.19.0` are listed as temporary targeted CI exceptions because the available Hermes Core hard-pins those versions.

**Acceptance criteria:** reconfirmed in run #116 without globally disabling audit.

---

## Next iteration — carry-over work

### N1 · Remove temporary dependency-audit exceptions

**Priority:** P1
**Context:** six targeted exceptions for `cryptography==46.0.7` and `hermes-agent==0.19.0` remain in CI because of Hermes Core's pinned dependencies.
**Status on 2026-09-26:** blocked by the external release: only `hermes-agent` 0.19.0 is available from the public index. No dependency upgrade or substitution is performed without a published compatible Core.
**Outcome:** upgrade Hermes Core, remove all six exceptions, and verify the audit without `--ignore-vuln`.
**Acceptance criteria:** both CI audit steps are green without exceptions.

### N2 · Release E2E in an isolated MAX environment

**Priority:** P2
**Context:** unit/regression/SAST gates are complete; an operational check remains with a test bot and public HTTPS webhook.
**Status on 2026-09-26:** blocked by infrastructure: `a1.rmg7.com` has no isolated MAX gateway/container and the repository has no E2E deployment manifest. Test-bot credentials and a public test HTTPS endpoint are not created automatically.
**Outcome:** validate webhook registration, secret and secretless-fail-closed paths, media with public and private DNS answers, and callback acknowledgement in a group chat.
**Acceptance criteria:** an E2E log attached to the release ticket contains no token disclosure and shows the expected HTTP statuses.

---

## Historical planning notes (superseded by the CI baseline above)

The following items are retained as context for the original change. Items 0 and 0.1 are the authoritative priorities and acceptance criteria for the next iteration.

### 1. R2 · SEC-02 & SEC-03: Media Download & SSRF Protection Alignment

**Priority:** P1  
**Affected files:** `adapter.py`

**Problem Description:**
In `adapter.py`, `_download_inbound_media` and `_prepare_download` currently gate downloads on `self._download_url_allowed(url)`, which by default restricts hosts to `DOWNLOAD_ALLOWED_HOST_SUFFIXES` (`.max.ru`, `.oneme.ru`).
Consequently, `tests/test_download_token_leak.py` (which tests that fetching attachments from third-party public HTTPS hosts like `https://attacker.example.com/attachment.bin` does NOT leak the `Authorization` header) fails because requests are never attempted (`AssertionError: download was not attempted`).
Furthermore, in `test_ssrf_download.py`, when a host resolves to a private IP (`test_private_dns_answer_is_never_fetched`), the download must fail-closed immediately without fallback.

**Required Solution:**
1. Allow downloading public HTTPS URLs when `MAX_DOWNLOAD_ALLOWED_HOSTS` is not explicitly configured.
2. Ensure `_is_trusted_download_origin(url)` is the single authority deciding whether to attach `Authorization: <token>`.
3. If `_prepare_download` returns `None` (e.g. private/loopback IP), abort download without fallback requests.

**Acceptance Criteria:**
```powershell
pytest -q tests/test_ssrf_download.py tests/test_download_token_leak.py tests/test_inbound_media_limits.py
```
100% PASS (all 169 tests).

---

### 2. REG · Legacy Wire Regressions Compatibility in `tests/test_wire_regressions.py`

**Priority:** P2  
**Affected files:** `tests/test_wire_regressions.py`, `tests/conftest.py`, `mixins/callback_auth.py`

**Problem Description:**
In `test_wire_regressions.py` (14 failed out of 56), older tests diverge from release 2.10 contracts:
1. `TestInboundRouting::test_group_update_routes_to_group` fails because `make_adapter` does not specify `group_policy="open"`, and the new default `allowlist` policy rejects groups when user/chat allowlists are empty.
2. Command approval tests assign a raw string `session_key` (`a._exec_approval_state["grp123"] = "sess-1"`), whereas `CallbackAuthMixin` expects a structured interaction dictionary.
3. In `test_http_error_does_not_kill_the_loop`, the backoff sleep for HTTP 500 is ~5s, triggering the 2s `asyncio.wait_for` timeout.

**Required Solution:**
1. Support backwards compatibility in `CallbackAuthMixin._consume_interaction` for string values, or adjust test state setup.
2. Set `group_policy="open"` in `make_adapter` or in group routing test cases.
3. Patch/mock `_poll_sleep` in polling retry tests.

**Acceptance Criteria:**
```powershell
pytest -q tests/test_wire_regressions.py
```
100% PASS (52 passed, 4 xfailed).

---

## Full Verification Command

```powershell
pytest -q
```
Expected result: 100% PASS across all repository tests.
