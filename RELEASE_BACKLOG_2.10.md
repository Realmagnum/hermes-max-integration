# Hermes MAX Integration 2.10 — Release Backlog (Остаток задач)

[English](RELEASE_BACKLOG_2.10_EN.md)

## Текущий статус

- **Ветка:** `RC-2.10`
- **Прогресс бэклога:** ~96% выполнен (693+ тестов проходят из ~718).
- **Выполнено и стабилизировано в кодовой базе:**
  - **R1:** Polling backoff с `Retry-After`, lossless chunking сообщений, streaming isolation per `(chat_id, message_id)` с flush-таймером, корректный lifecycle connect/disconnect без утечек клиентов и задач.
  - **R3:** Callback auth с привязкой chat/message/TTL, cross-session owner-only доступ, group allowlists (users & chats), backpressure queue & telemetry.
  - **R4:** Fail-closed webhook с вынесенным `_build_webhook_app`, проверкой секрета до парсинга JSON, лимитом тела, строгим контрактом `/health` (`{"status": "ok"}`) и выносом телеметрии в `/metrics`.
  - **R5:** 100% синхронизация документации RU/EN, прохождение всех тестов ссылок, внешних клеймов, примеров API и скрипта `scripts/check-ru-en-parity.py`.

---

## Нерешённые проблемы на текущий момент (Active Backlog)

### 1. R2 · SEC-02 & SEC-03: Согласование скачивания сторонних медиа и SSRF-защиты

**Приоритет:** P1  
**Затронутые файлы:** `adapter.py`

**Описание проблемы:**
В `adapter.py` методы `_download_inbound_media` и `_prepare_download` сейчас блокируют скачивание через `self._download_url_allowed(url)`. Метод `_download_url_allowed` по умолчанию проверяет суффиксы `DOWNLOAD_ALLOWED_HOST_SUFFIXES` (`.max.ru`, `.oneme.ru`).
В результате тесты `tests/test_download_token_leak.py` (где проверяется, что скачивание с произвольных сторонних HTTPS-хостов вроде `https://attacker.example.com/attachment.bin` происходит БЕЗ передачи токена `Authorization`) не могут инициировать запрос (`AssertionError: download was not attempted`).
Также в `test_ssrf_download.py` при блокировке хоста через DNS (`test_private_dns_answer_is_never_fetched`) требуется гарантировать fail-closed отказ без обхода проверок.

**Требуемое решение:**
1. Разрешить скачивание публичных HTTPS-ссылок, если `MAX_DOWNLOAD_ALLOWED_HOSTS` не задан оператором явно.
2. Гарантировать, что `_is_trusted_download_origin(url)` — единственный источник решения о передаче заголовка `Authorization: <token>`.
3. Если `_prepare_download` вернул `None` (например, приватный/loopback IP), загрузка прерывается без fallback-запросов.

**Критерий приёмки:**
```powershell
pytest -q tests/test_ssrf_download.py tests/test_download_token_leak.py tests/test_inbound_media_limits.py
```
100% PASS (все 169 тестов).

---

### 2. REG · Совместимость старых регрессионных тестов в `tests/test_wire_regressions.py`

**Приоритет:** P2  
**Затронутые файлы:** `tests/test_wire_regressions.py`, `tests/conftest.py`, `mixins/callback_auth.py`

**Описание проблемы:**
В тестовом наборе `test_wire_regressions.py` (14 упавших тестов из 56) возникли расхождения со старыми тестами:
1. `TestInboundRouting::test_group_update_routes_to_group` падает, так как фикстура `make_adapter` не передаёт `group_policy="open"`, а новая дефолтная политика `allowlist` блокирует групповой чат при пустом списке разрешённых пользователей/чатов.
2. В тестах одобрения команд (`_exec_approval_state`) тесты напрямую присваивают строковый `session_key` (`a._exec_approval_state["grp123"] = "sess-1"`), тогда как `CallbackAuthMixin` ожидает структурированный словарь взаимодействия.
3. В `test_http_error_does_not_kill_the_loop` backoff-sleep на ошибку HTTP 500 составляет ~5 сек, превышая лимит `asyncio.wait_for(..., timeout=2)`.

**Требуемое решение:**
1. Добавить поддержку обратной совместимости в `CallbackAuthMixin._consume_interaction` для строкового формата данных или обновить фикстуру вызова.
2. В тестах группы передавать `extra={"group_policy": "open"}` либо инициализировать `group_policy="open"` в фикстуре `make_adapter` для тестов, проверяющих роутинг групп.
3. Мокировать/патчить задержку `_poll_sleep` в тестах опроса.

**Критерий приёмки:**
```powershell
pytest -q tests/test_wire_regressions.py
```
100% PASS (52 passed, 4 xfailed).

---

## Команда полной финальной верификации

```powershell
pytest -q
```
Ожидаемый результат: 100% PASS по всем ~718 тестам репозитория.
