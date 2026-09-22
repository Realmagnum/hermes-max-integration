# Hermes MAX Integration 2.10 — Release Backlog (Pending Tasks)

[Русский](RELEASE_BACKLOG_2.10.md)

## Current Status

- **Branch:** `RC-2.10`
- **Progress:** ~85–90% complete (650+ tests passing out of ~700).
- **Completed and stabilized in codebase:**
  - R1: Polling backoff with `Retry-After`, lossless chunking, streaming isolation per `(chat_id, message_id)` with flush timer, lifecycle connect/disconnect.
  - R3: Callback auth with chat/message/TTL binding, cross-session owner-only access, group allowlists (users & chats), backpressure queue & telemetry.
  - R4: Fail-closed webhook with extracted `_build_webhook_app`, secret check prior to JSON parsing, body size cap.
  - R2: Inbound media limits, download concurrency semaphore, streaming timeouts, partial file cleanup (`contextlib`).

---

## Open Tasks for Next Iteration (RC-2.10-it2)

### 1. R2 · SEC-02 & SEC-03 (Media Download & Token Separation)

**Priority:** P1  
**Target files:** `adapter.py`, `tests/test_ssrf_download.py`, `tests/test_download_token_leak.py`

**Issue:**
1. `_download_url_allowed` rejects non-whitelisted origins (`attacker.example.com`, `partner.example`), causing tests in `test_download_token_leak.py` to fail with `download was not attempted`.
2. In `test_ssrf_download.py::test_private_dns_answer_is_never_fetched`, fallback download occurs when `prepared` is None instead of immediate abort.

**Solution:**
- Separate concerns:
  - `_is_trusted_download_origin(url)`: decides whether to attach the bot token / authorization header.
  - `_validate_download_url(url)` / SSRF filter: validates HTTPS scheme and public IP addresses (blocks loopback, private, link-local, cloud metadata).
- Allow downloading from public untrusted origins without attaching credentials.
- Abort immediately on private DNS resolution without fallback.

**Acceptance:**
- All tests in `tests/test_download_token_leak.py` and `tests/test_ssrf_download.py` pass.

---

### 2. R4 · CODE-05 (Webhook Health Endpoint Contract)

**Priority:** P1  
**Target files:** `mixins/webhook.py`, `tests/test_wire_regressions.py`

**Issue:**
- `tests/test_wire_regressions.py:1022` expects strict `health.json() == {"status": "ok"}`. Currently `/health` returns extended telemetry and backpressure details.

**Solution:**
- Match base contract: return `{"status": "ok"}` on healthy state.
- Keep detailed telemetry in a separate endpoint or `/ready`.

**Acceptance:**
- `tests/test_wire_regressions.py` passes alongside `tests/test_webhook_readiness.py` and `tests/test_webhook_security.py`.

---

### 3. R5 · DOC-01..10 (Documentation Parity & Validation Scripts)

**Priority:** P1  
**Target files:** `README.md`, `README_EN.md`, `docs/api.md`, `docs/api_EN.md`

**Issue:**
- Documentation tests fail due to discrepancies after mixins refactoring and terminology changes.

**Solution:**
- `test_docs_links.py`: add `mixins/` directory to repository layout in `README.md` and `README_EN.md`.
- `test_doc_external_claims.py`: update claims about external platforms.
- `test_docs_api_examples.py` & `test_ru_en_parity.py`: synchronize payload examples and parameter tables between RU and EN versions.

**Acceptance:**
- `pytest -q tests/test_docs_links.py tests/test_doc_external_claims.py tests/test_docs_api_examples.py tests/test_ru_en_parity.py` passes.

---

## Verification Commands for Pending Tasks

```powershell
# R2: Download & SSRF
pytest -q tests/test_ssrf_download.py tests/test_download_token_leak.py tests/test_inbound_media_limits.py

# R4: Webhook health
pytest -q tests/test_webhook_security.py tests/test_webhook_readiness.py tests/test_wire_regressions.py

# R5: Docs
pytest -q tests/test_docs_links.py tests/test_doc_external_claims.py tests/test_docs_api_examples.py tests/test_ru_en_parity.py
```
