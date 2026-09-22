# Hermes MAX Integration 2.10 — Release Backlog

[English](RELEASE_BACKLOG_2.10_EN.md)

## Цель

Подготовить проверяемый release candidate 2.10 для проекта `agent/hermes-max-integration`: вернуть все потерянные при конфликтном merge runtime-пакеты, закрыть P1-безопасность, стабилизировать lifecycle/transport, синхронизировать документацию и получить воспроизводимый зелёный release gate на одном SHA.

**Это backlog, а не утверждение готовности релиза.** До закрытия release gate публикация 2.10 запрещена.

## Текущее состояние на момент сохранения

- Рабочая ветка: `RC-2.10`.
- Прогресс бэклога: **~85–90%** (из ~700 тестов проходят ~650).
- Выполнено и стабилизировано в runtime:
  - **R1 (CODE-01, CODE-02, CODE-03, CODE-07):** Polling backoff с jitter и Retry-After; lossless chunking; streaming isolation per `(chat_id, message_id)` с flush timer; lifecycle connect/disconnect.
  - **R3 (SEC-01, SEC-05, SEC-06, CODE-04, CODE-06, CODE-08):** Callback auth (owner/chat/TTL binding); cross-session owner-only guards; group policy (users/chats allowlists); backpressure bounded queue & telemetry.
  - **R4 (SEC-04, CODE-05 part):** Fail-closed webhook с вынесенным `_build_webhook_app`, предварительной проверкой секрета до парсинга JSON и лимитом размера тела.
  - **R2 (SEC-07):** Inbound media budget, streaming limits, partial file cleanup (исправлен недостающий импорт `contextlib`, 23/23 тестов `test_inbound_media_limits.py` проходят).

### Задачи на следующую итерацию (RC-2.10-it2)

Оставшиеся дефекты изолированы и разделены на 3 блока для простой и надежной доработки:

1. **R2 / SEC-02 & SEC-03 (Media Download & Token Separation):**
   - Разделить проверку доверенного хоста (`_is_trusted_download_origin`) для передачи токена и общую проверку публичности IP (SSRF) при скачивании без токена.
   - В `test_ssrf_download.py::test_private_dns_answer_is_never_fetched` не делать fallback-скачивание при `prepared is None`.
2. **R4 / Webhook Health Contract:**
   - Выровнять контракт `/health`: для базовой проверки wire-тестов возвращать `{"status": "ok"}` (или вынести расширенную телеметрию в `/health/detail` / `/ready`).
3. **R5 / Docs Parity & Claims:**
   - `test_docs_links.py`: добавить директорию `mixins/` в схему структуры проекта в `README.md` и `README_EN.md`.
   - `test_doc_external_claims.py`: скорректировать формулировки о внешних платформах.
   - `test_docs_api_examples.py` & `test_ru_en_parity.py`: синхронизировать таблицы и примеры между RU и EN версиями.


## Правила выполнения

1. Работать только в отдельной ветке `RC-2.10`; `main` не менять до финального approval.
2. Перед каждой runtime-правкой написать/восстановить минимальный failing test и зафиксировать RED.
3. Один тематический пакет — один или несколько маленьких коммитов с ID backlog.
4. После каждого пакета запускать его тесты и ближайшую регрессионную группу.
5. Не выполнять реальные MAX-запросы до отдельного согласования тестового бота; сеть в тестах — MockTransport/локальный aiohttp.
6. Не принимать тест, который проходит только потому, что callback, очередь, webhook или download path фактически не выполняется.
7. После устранения конфликта читать итоговый diff и проверять, что обе стороны контракта сохранены.
8. Незакрытая P1 означает `NO-GO`, даже если тематические тесты зелёные.

## Приоритеты и зависимости

```text
R0: BUILD-01/02 → воспроизводимая среда
R1: CODE-01 + CODE-02 + CODE-03 + CODE-07
R2: SEC-02 + SEC-03 + SEC-07 (единый download pipeline)
R3: SEC-01 + SEC-05 + SEC-06 + CODE-04 + CODE-06 + CODE-08
R4: SEC-04 + CODE-05 (единый webhook lifecycle/readiness)
R5: BUILD-03/04 → DOC-01..10 → full gate
```

## Этап R0 — воспроизводимая база

### REL-00 · Зафиксировать baseline и evidence

**Priority:** P0 · **Status:** OPEN

- Сохранить текущий SHA, backup-ветку и результаты запусков в `docs/release-evidence/2.10/`.
- Записать версии Python, pytest, Hermes core, uv/pip и OS.
- Зафиксировать команды и полные stdout/stderr, а не только summary.
- Проверить, что рабочий gateway/prod config не меняется.

**Acceptance:** любой разработчик может воспроизвести состояние из `RC-2.10` и понять, какой тест был запущен на каком SHA.

### BUILD-01 · Packaging/install

**Priority:** P1 · **Status:** PARTIAL — packaging fix присутствует в истории, итоговую RC не принимать без проверки.

- Проверить `pyproject.toml`, package discovery flat-layout и содержимое wheel.
- Выполнить clean `uv venv` + editable install и обычную wheel install.
- Проверить plugin install из произвольно названного checkout.

**Acceptance:** `pip/uv install -e '.[dev]'`, `python -m build` и установка wheel проходят в чистой среде Python 3.11 и 3.12; пакет содержит все `mixins`, `skills`, `assets`, но не лишние секреты/тестовые файлы.

### BUILD-02 · Pinned test environment

**Priority:** P1 · **Status:** OPEN

- Закрепить совместимую версию Hermes core или воспроизводимый local-core fixture.
- Убрать зависимость тестов от имени checkout (`max.adapter` aliases допустимы только в test bootstrap).
- Проверить collection в каталоге с произвольным именем и отдельным `HERMES_HOME`.

**Acceptance:** `pytest --collect-only -q` проходит в чистом checkout; Python 3.11 и 3.12 поддержаны или явно ограничены; core contract documented.

## Этап R1 — transport, chunking, lifecycle

### CODE-01 · Polling backoff

**Priority:** P1 · **Status:** REGRESSED/NOT PRESENT in current runtime.

**Likely files:** `adapter.py`, `tests/test_poll_backoff.py`.

- Вернуть `_parse_retry_after`, `_poll_backoff_delay`, `_status_retry_delay`, `_poll_sleep`, deterministic RNG hook.
- Применять backoff к каждому retryable non-200 и transport exception.
- 401 — fatal auth state без pending sleep; 403/429/5xx — retryable according to contract.
- Сохранять marker pagination и сбрасывать error counter после успеха.

**Acceptance:** весь `tests/test_poll_backoff.py` зелёный; virtual clock не ждёт реальные секунды; Retry-After ограничен сверху и не принимает отрицательные/мусорные значения.

### CODE-02 · Lossless chunking

**Priority:** P1 · **Status:** REGRESSED in current runtime; первичный fix — `3126a08`.

**Likely files:** `adapter.py`, `tests/test_chunking.py`.

- Восстановить алгоритм из первичного fix, затем адаптировать к итоговому send/table path.
- Префикс нумерации учитывать до split; не использовать `.strip()` и не терять whitespace/code fences.
- Проверять transmitted payload, а не только helper output.

**Acceptance:** `''.join(transmitted_chunks)` равен исходному тексту по всем lossless fixtures; каждый payload ≤ MAX limit; Unicode, blank lines, long words, paragraphs и code blocks зелёные.

### CODE-03 · Streaming isolation/flush

**Priority:** P1 · **Status:** REGRESSED/NOT PRESENT in current runtime; первичный fix — `ba13553`.

**Likely files:** `adapter.py`, `tests/test_streaming_isolation.py`, `tests/test_openclaw_improvements.py`.

- Вернуть `_edit_states`, `_StreamEditState`, `_edit_state_key`, throttle config и bounded state pruning.
- Состояние ключевать `(chat_id, message_id)`, не adapter-wide.
- Отменять старый timer без обнуления ссылки на новый.
- `finalize=True` немедленно отправляет последний текст, отменяет timer и удаляет state.
- Disconnect отменяет и дожидается timers.

**Acceptance:** весь streaming suite зелёный; два чата/два message id не подавляют друг друга; pending content отправляется ровно один раз.

### CODE-07 · Lifecycle/core contract

**Priority:** P1 · **Status:** PARTIAL; первичный fix — `765b56c`.

- Проверить итоговый `connect/disconnect` после возврата streaming/backoff.
- Устранить race concurrent connect/disconnect.
- Дождаться отменённых poll/queue/handler/flush tasks с bounded timeout.
- Закрывать HTTP clients только после остановки consumers; cleanup обязателен при setup/register failure.

**Acceptance:** connect→disconnect→connect, concurrent connect, cancellation during webhook start и cancellation during polling проходят без task/client leaks; core `_running`/mark methods соответствуют pinned core.

## Этап R2 — единый безопасный media pipeline

### SEC-02 · Token-free untrusted download

**Priority:** P1 · **Status:** PARTIAL/REGRESSION RISK; первичный fix — `c9a0eef`.

### SEC-03 · SSRF/DNS/rebinding

**Priority:** P1 · **Status:** PARTIAL/REGRESSION RISK; первичный fix — `c34b45e`, config wiring — `3d6e45f`.

### SEC-07 · Size/count/time/concurrency limits

**Priority:** P1 · **Status:** PARTIAL/REGRESSION RISK; первичный fix — `d6f8fbc`.

**Единый контракт для SEC-02/03/07:**

```text
parse and normalize URL
→ exact HTTPS + trusted-origin decision
→ never attach bot token to untrusted origin
→ resolve all A/AAAA; reject any private/loopback/link-local/reserved answer
→ pin validated address; no redirects
→ bounded streaming read with total deadline
→ per-update attachment count/byte budget and concurrency semaphore
→ atomic cache write + partial-file cleanup
→ redact URL credentials/token in logs
```

**Likely files:** `adapter.py`, `mixins/media_upload.py`, `tests/test_ssrf_download.py`, `tests/test_download_token_leak.py`, `tests/test_inbound_media_limits.py`.

**Acceptance:** all three test groups pass; no real network; trusted MAX/CDN origin behavior explicit; arbitrary HTTPS, plain HTTP, lookalike host, credentials, alternative IP forms, DNS private answer, rebinding, redirect, false Content-Length, slow stream and disk failure covered.

## Этап R3 — authorization, routing, backpressure

### SEC-01 · Callback authorization

**Priority:** P1 · **Status:** THEMATIC TESTS PASS, wire contract needs final integration.

- Keep one common gate before resolver and state pop.
- Bind owner, scoped chat, prompt message and TTL.
- Apply to exec, slash confirm, clarify and model picker.
- Group callback acknowledgement must target group; dialog callback must target user.

**Acceptance:** foreign user/chat/message cannot resolve, consume or cause acknowledgement; owner can retry valid button; replay/expired button is inert.

### SEC-05 · Cross-session access

**Priority:** P1 · **Status:** THEMATIC TESTS PASS, verify in final adapter.

- Feature off by default.
- Explicit `cross_session_users` or non-empty `allowed_users` owner set only; `allow_all_users` alone never grants global sessions.
- Authorization before SessionDB construction, outbound send or `--all` rewrite.

**Acceptance:** `/sessions`, search, `/resume` no-arg/target matrix passes for owner/non-owner/empty config.

### SEC-06 · Group allowlist

**Priority:** P1 · **Status:** THEMATIC TESTS PASS, verify final config mapping.

- Normalize YAML/env list/string values.
- Empty allowlist fails closed for allowlist policy.
- Preserve documented AND semantics when both user and chat lists are configured.

**Acceptance:** full group policy matrix and end-to-end inbound command tests pass.

### CODE-04 · Opaque model callback IDs

**Priority:** P2 · **Status:** NEEDS final suite verification.

- Use percent-encoding or structured payload serialization; split only fixed prefix fields.
- Round-trip `llama3:8b`, `openrouter:model:free`, malformed and expired callbacks.

### CODE-06 · Model picker isolation

**Priority:** P1 · **Status:** THEMATIC TESTS PASS, verify after CODE-03/lifecycle merge.

- Owner, scope, provider/model message id and TTL checks.
- Reject stale callback after replacement/pagination; bind unowned group picker only on current live message and first valid owner tap.

### CODE-08 · Backpressure/dedup

**Priority:** P1 · **Status:** THEMATIC TESTS PASS, verify final tree.

- Bounded queue, explicit drop-oldest/drop-newest policy, bounded handler concurrency, hard dedup cap and telemetry.
- Webhook ingress must not block on full queue.

**Acceptance:** `tests/test_backpressure.py` plus webhook/polling queue tests pass under burst; no task leak and metrics reflect drops.

## Этап R4 — webhook/readiness

### SEC-04 · Fail-closed webhook

**Priority:** P1 · **Status:** THEMATIC TESTS PASS in prior tree; final integration broken/partial.

- Restore `_build_webhook_app` or unify app-builder/startup contract; do not maintain two divergent webhook implementations.
- Require secret for non-loopback; explicit loopback-only `MAX_WEBHOOK_INSECURE_DEV` opt-in if retained.
- Authenticate before JSON parsing/body processing, with body cap and constant-time comparison.

### CODE-05 · Readiness and registration

**Priority:** P1 · **Status:** THEMATIC TESTS PASS in prior tree; final integration broken/partial.

- `/health` = liveness/telemetry; `/ready` = registered and accepting events.
- `/me` accepts only valid HTTP/body success.
- Subscription registration validates transport/status/body; failure tears down runner and does not mark connected.

**Acceptance:** `tests/test_webhook_security.py`, `tests/test_webhook_readiness.py`, webhook mode docs test and wire webhook tests pass together.

## Этап R5 — build, tests, docs

### BUILD-03 · Quality gates

**Priority:** P1 · **Status:** OPEN.

- Ruff, Bandit, pytest and dependency audit cover `adapter.py`, every `mixins/*.py`, scripts and packaging.
- CI must run on push/PR for candidate branch, not only main.
- Pin/record optional Pillow/Playwright/STT dependencies and skip behavior.

### BUILD-04 · Realistic regressions

**Priority:** P1 · **Status:** PARTIAL.

- Keep MockTransport/real Response fixtures for MAX DM/group/callback/webhook.
- Replace tests that assert implementation-only state with contract assertions where possible.
- Keep bound-state tests explicit about message IDs and new security shape.

### DOC-01..DOC-10

**Priority:** P1 for DOC-01..05; P2 for DOC-06..10.

- DOC-01: one Hermes-core STT workflow; remove nonexistent script/env settings.
- DOC-02: config reference only for implemented settings; document defaults/precedence/types.
- DOC-03: webhook skill sets URL, secret, host/path and verifies mode/readiness.
- DOC-04: executable, parseable RU/EN API examples matching wire payloads.
- DOC-05: honest security model, safe defaults, known limitations and no absolute claims.
- DOC-06: preserve verified mode/OS-aware diagnostics.
- DOC-07: RU/EN topic/default/example parity including skills and changelog.
- DOC-08: links, tree, cwd, venv, profile and Gitea install procedure.
- DOC-09: one version source, generated test count, current dependency/architecture claims.
- DOC-10: verify external MAX/Telegram/Hermes claims with source/date/version.

## Required verification commands

Run from a clean RC checkout with pinned core:

```bash
python --version
python -m pip install -e '.[dev]'
python -m build
pytest --collect-only -q
pytest -q tests/test_poll_backoff.py tests/test_chunking.py
pytest -q tests/test_streaming_isolation.py tests/test_openclaw_improvements.py
pytest -q tests/test_ssrf_download.py tests/test_download_token_leak.py tests/test_inbound_media_limits.py
pytest -q tests/test_callback_auth.py tests/test_cross_session.py tests/test_group_access.py tests/test_model_picker.py
pytest -q tests/test_webhook_security.py tests/test_webhook_readiness.py tests/test_wire_regressions.py
pytest -q
ruff check adapter.py mixins scripts tests
bandit -r adapter.py mixins scripts
pip-audit
python scripts/check_docs_links.py
python scripts/check_docs_json.py
python scripts/check_ru_en_parity.py

git diff --check
git status --short
```

If a command/tool is unavailable, record the exact blocker and do not substitute a guessed green result.

## Release gate — GO only if every item is true

- [ ] No unresolved git conflicts or uncommitted changes.
- [ ] All P1 tasks closed with commit IDs and passing regression tests.
- [ ] Full pytest green; xfails are either eliminated or explicitly approved with issue IDs.
- [ ] Build/install green in clean Python 3.11 and 3.12 environments.
- [ ] Ruff, Bandit and dependency audit green or documented accepted exceptions.
- [ ] No token leak, SSRF, webhook auth, cross-session or callback authorization failures.
- [ ] Streaming, backoff, chunking, queue and lifecycle tests green together.
- [ ] RU/EN documentation, links, JSON examples, config defaults and release notes agree with code.
- [ ] Separate HERMES_HOME clean-install smoke test passes.
- [ ] MAX E2E with an explicitly approved test bot passes: DM, group, callback approval, model picker, media, polling and webhook.
- [ ] Release commit/tag and rollback procedure reviewed; only then merge/push to release target.

**Current verdict: NO-GO.**
