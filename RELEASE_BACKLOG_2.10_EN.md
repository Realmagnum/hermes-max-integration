# Hermes MAX Integration 2.10 — Release Backlog (Pending Tasks)

[Russian](RELEASE_BACKLOG_2.10.md)

## Current Status

- **Branch:** `fix/rc-2.10-final-gates` → PR #1 → `RC-2.10`.
- **Measured baseline:** Gitea Actions [run #107](https://gitea.rmg7.com/agent/hermes-max-integration/actions/runs/107), SHA `cff3b75` (2026-09-25): **691 passed, 11 failed, 13 skipped, 2 xfailed**.
- **CI infrastructure:** runner `hermes-max-release-runner` on `a1.rmg7.com` is operational; ruff and Bandit (high severity) pass. Dependency audit and both test-matrix jobs remain red.
- **Completed and Stabilized in Codebase:**
  - **R1:** Polling backoff with `Retry-After`, lossless message chunking, streaming isolation per `(chat_id, message_id)` with flush timer, leak-free connect/disconnect lifecycle.
  - **R3:** Callback auth bound to chat/message/TTL, cross-session owner-only access, group allowlists (users & chats), backpressure queue & telemetry.
  - **R4:** Fail-closed webhook with extracted `_build_webhook_app`, secret validation before JSON parsing, payload limit, strict `/health` contract (`{"status": "ok"}`), telemetry extracted to `/metrics`.
  - **R5:** RU/EN backlogs are maintained in lockstep; run parity, link, external-claim, and API-example checks after every documentation change.

---

## Unresolved Issues (Active Backlog)

### 0. RELEASE · Close the observed CI regressions from run #107

**Priority:** P0
**Affected files:** `tests/test_download_token_leak.py`, `tests/test_ssrf_download.py`, `tests/test_wire_regressions.py`, `tests/test_webhook.py`, fixtures, and callback/streaming code — only where a test proves an implementation regression.

**Run result:** 11 failures on both Python 3.11 and 3.12. This is not a reason to weaken SSRF safeguards, owner/chat/message/TTL callback binding, or the fail-closed webhook policy.

**Next-iteration work:**
1. Reconcile media-test expectations with the contract: public HTTPS without an explicit allowlist is allowed after SSRF validation; plain HTTP receives no `Authorization`; private DNS/IP always prevents a request.
2. Update wire regressions: keyword-only `_remember_interaction_owner`, owner-bound group/dialog callbacks, streaming state through `_edit_states`, and cross-session cases with explicit authorization.
3. Decide and lock down the webhook HTTP contract for a missing secret: implementation currently returns `503`, while an obsolete test expects `403`.
4. Remove or repair a stale strict `xfail` only after the scenario becomes a normal passing test.

**Acceptance criteria:** `python -m pytest -q` has no failed/xpassed tests; both `test (3.11)` and `test (3.12)` jobs are green in one CI run.

---

### 0.1. RELEASE · Close dependency audit

**Priority:** P1
**Run result:** `pip-audit` flags `cryptography 46.0.7` (fixed versions begin at `48.0.1`/`49.0.0`) and transitive dependency `hermes-agent 0.19.0`.

**Next-iteration work:** upgrade and pin compatible safe versions in the dependency groups; separately validate the source and applicability of `hermes-agent` advisories without blanket ignores.

**Acceptance criteria:** the `dependency-audit` job is green without broadly suppressing detected advisories.

---

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
Expected result: 100% PASS across all ~718 tests.
