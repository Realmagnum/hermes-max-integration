# Hermes MAX Integration 2.10 — Release Backlog (Остаток задач)

[English](RELEASE_BACKLOG_2.10_EN.md)

## Текущий статус

- **Ветка:** `RC-2.10`
- **Прогресс бэклога:** ~85–90% выполнен (650+ тестов проходят из ~700).
- **Выполнено и стабилизировано в коде:**
  - R1: Polling backoff с `Retry-After`, lossless chunking сообщений, streaming isolation per `(chat_id, message_id)` с flush-таймером, lifecycle connect/disconnect.
  - R3: Callback auth с привязкой chat/message/TTL, cross-session owner-only доступ, group allowlists (users & chats), backpressure queue & telemetry.
  - R4: Fail-closed webhook с вынесенным `_build_webhook_app`, проверкой секрета до парсинга JSON и лимитом тела.
  - R2: Inbound media limits, семафор загрузок, таймауты, очистка временных файлов (`contextlib`).

---

## Открытые задачи на следующую итерацию (RC-2.10-it2)

### 1. R2 · SEC-02 & SEC-03 (Media Download & Token Separation)

**Приоритет:** P1  
**Затронутые файлы:** `adapter.py`, `tests/test_ssrf_download.py`, `tests/test_download_token_leak.py`

**Проблема:**
1. Метод `_download_url_allowed` блокирует скачивание с любых сторонних хостов (`attacker.example.com`, `partner.example`), из-за чего тесты в `test_download_token_leak.py` падают с ошибкой `download was not attempted`.
2. В тесте `test_ssrf_download.py::test_private_dns_answer_is_never_fetched` при невалидном `prepared` происходит fallback-скачивание вместо немедленного отказа.

**Требуемое решение:**
- Разделить логику:
  - `_is_trusted_download_origin(url)`: решает только вопрос, передавать ли заголовок авторизации/токен бота на хост назначения.
  - `_validate_download_url(url)` / SSRF-фильтр: проверяет только корректность схемы (HTTPS) и публичность разрешенных IP-адресов (запрет loopback, private, link-local, cloud metadata).
- При скачивании с публичных недоверенных хостов скачивать файл **без передачи токена**, а не блокировать запрос.
- При обнаружении приватного DNS-ответа немедленно возвращать отказ без fallback-запросов.

**Критерий приёмки:**
- Все тесты `tests/test_download_token_leak.py` и `tests/test_ssrf_download.py` проходят на 100%.

---

### 2. R4 · CODE-05 (Webhook Health Endpoint Contract) [ВЫПОЛНЕНО]

**Приоритет:** P1  
**Затронутые файлы:** `mixins/webhook.py`, `tests/test_wire_regressions.py`, `tests/test_backpressure.py`, `tests/test_webhook_health_contract.py`

**Проблема:**
- `tests/test_wire_regressions.py:1022` ожидает строгий контракт `health.json() == {"status": "ok"}`. Ранее эндпоинт `/health` возвращал расширенную телеметрию бэкпрешера и состояния очередей.

**Решение:**
- Приведен ответ `/health` в соответствие с базовым контрактом: возвращает строго `{"status": "ok"}` (Liveness).
- Расширенная телеметрия бэкпрешера вынесена в отдельный эндпоинт `GET /metrics`, а также доступна через `GET /ready` и опциональные query-параметры `?backpressure=1` / `?metrics=1`.
- Создан изолированный тестовый набор `tests/test_webhook_health_contract.py`.

**Критерий приёмки:**
- Все тесты `tests/test_webhook_health_contract.py`, `tests/test_wire_regressions.py`, `tests/test_webhook_readiness.py` и `tests/test_webhook_security.py` проходят успешно.

---

### 3. R5 · DOC-01..10 (Синхронизация документации и проверочные скрипты)

**Приоритет:** P1  
**Затронутые файлы:** `README.md`, `README_EN.md`, `docs/api.md`, `docs/api_EN.md`

**Проблема:**
- Тесты документации падают из-за расхождений после рефакторинга миксинов и обновлений формулировок.

**Требуемое решение:**
- `test_docs_links.py`: добавить папку `mixins/` в схему структуры репозитория в `README.md` и `README_EN.md`.
- `test_doc_external_claims.py`: скорректировать формулировки о сторонних сервисах и платформах.
- `test_docs_api_examples.py` & `test_ru_en_parity.py`: синхронизировать примеры payload и параметры в документации между RU и EN версиями.

**Критерий приёмки:**
- `pytest -q tests/test_docs_links.py tests/test_doc_external_claims.py tests/test_docs_api_examples.py tests/test_ru_en_parity.py` проходит на 100%.

---

## Команды верификации остатка задач

```powershell
# R2: Download & SSRF
pytest -q tests/test_ssrf_download.py tests/test_download_token_leak.py tests/test_inbound_media_limits.py

# R4: Webhook health
pytest -q tests/test_webhook_security.py tests/test_webhook_readiness.py tests/test_wire_regressions.py

# R5: Документация
pytest -q tests/test_docs_links.py tests/test_doc_external_claims.py tests/test_docs_api_examples.py tests/test_ru_en_parity.py
```
