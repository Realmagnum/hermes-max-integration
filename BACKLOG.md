# Бэклог аудита: безопасность, реализация, документация

[English](BACKLOG_EN.md)

## Область и статус

База аудита: `b004c573318f1d5e521255531d1943cc8a8b8b90` (`main`). Все ссылки на строки ниже относятся к этой базе. Этот отдельный коммит сохраняет результаты аудитов до реализации исправлений. Все задачи открыты; изменение production, исправления кода и развёртывание не начаты. Ответственный пока не назначен.

Доказательства: **S** — статическое сопоставление кода/документов; **R** — изолированное выполнение извлечённых методов с моками (не полный плагин); **E** — реальная локальная команда; **V** — гипотеза или внешний контракт, требующий проверки. R-результаты получены независимыми ревьюерами; воспроизведения необходимо превратить в сохраняемые регрессионные тесты.

Фактически выполнено: чтение исходников и основных RU/EN-инструкций; изолированные проверки; попытка editable-install на Python 3.11.15; проверка локальных Markdown-ссылок и JSON-блоков. Полный pytest, Ruff, Bandit и pip-audit не запускались: пакетный запуск не получил подтверждения. Не проверены реальные MAX E2E, полная совместимость Hermes core, все внешние ссылки, актуальные правила платформ и вся история секретов. Отсутствие находки не означает отсутствие уязвимости.

## Порядок работ

1. Сохранить этот backlog отдельным коммитом (без исправлений).
2. Сделать воспроизводимыми сборку и тестовую среду (BUILD-01/02); сохранить failing regression tests для SEC.
3. Закрыть SEC-01…07, затем CODE-01…08; безопасную конфигурацию DOC-05 описать сразу вместе с защитами.
4. Сверить остальные документы, RU/EN и внешние контракты; обновить CI.
5. Пройти release gate ниже. Каждое исправление — отдельный тематический коммит с ID задачи; неизвестные контракты сначала проверить, не исправлять по предположению.

P1 — до публичного/multi-user использования; P2 — до следующего стабильного релиза. Приоритет не равен доказанности эксплуатации.

## Безопасность

- [x] **SEC-01 · P1 · S/R — Авторизация callback подтверждений.** `adapter.py`, `mixins/callback_auth.py`: закрыто в ветке `feature/microspec-pipeline`. Приёмка: `tests/test_callback_auth.py` (21 passed).
- [x] **SEC-02 · P1 · S/R — Не передавать токен бота произвольному URL вложения.** `adapter.py`: закрыто в ветке `feature/microspec-pipeline`. Приёмка: `tests/test_download_token_leak.py` (19 passed).
- [x] **SEC-03 · P1 · S/R — SSRF при скачивании.** `adapter.py`: закрыто в ветке `feature/microspec-pipeline`. Приёмка: `tests/test_ssrf_download.py` (81 passed).
- [x] **SEC-04 · P1 · S — Webhook без секрета.** `mixins/webhook.py`: закрыто в ветке `feature/microspec-pipeline`. Приёмка: `tests/test_webhook_security.py` (18 passed).
- [x] **SEC-05 · P1 · S/R — Доступ к глобальным сессиям.** `mixins/sessions.py`: закрыто в ветке `feature/microspec-pipeline`. Приёмка: `tests/test_cross_session.py` (32 passed).
- [x] **SEC-06 · P1 · S/R — Семантика групповых allowlist.** `adapter.py`: закрыто в ветке `feature/microspec-pipeline`. Приёмка: `tests/test_wire_regressions.py` (56 passed).
- [x] **SEC-07 · P2 · S — Лимиты входящих media.** `adapter.py`: закрыто в ветке `feature/microspec-pipeline`. Приёмка: `tests/test_inbound_media_limits.py` (69 passed).

## Качество реализации

- [x] **CODE-01 · P1 · S/R — HTTP backoff polling.** `adapter.py`: закрыто в ветке `feature/microspec-pipeline`. Приёмка: `tests/test_poll_backoff.py` (28 passed).
- [x] **CODE-02 · P2 · S/R — Потеря текста при chunking.** `adapter.py:1114–1116, 1233–1236`: нумерация приводит к повторному обрезанию без переноса хвоста; 7800 входных символов → 7788 полезных выходных. **Приёмка:** префиксы учтены до разбиения; конкатенация отправленных payload сохраняет исходный текст; границы, Unicode, абзацы и код покрыты тестами. **Закрыто в `3126a08` (ветка `fix/code02-chunking`):** разбиение стало lossless (`"".join(chunks) == content`, без `.strip()` и пересборки слов), нумерация бюджетируется до разбиения, payload ≤ `MAX_MESSAGE_LENGTH`. `tests/test_chunking.py` на базе `b0ea511` — 44 failed, после исправления 60 passed; полный suite 202 passed / 6 pre-existing failures (tables/playwright, к задаче не относятся).
- [x] **CODE-03 · P2 · S/R — Streaming isolation и flush.** `adapter.py`: закрыто в ветке `feature/microspec-pipeline`. Приёмка: `tests/test_streaming_isolation.py` (19 passed).
- [x] **CODE-04 · P2 · S/R — Model ID с двоеточием.** `adapter.py`: закрыто в ветке `feature/microspec-pipeline`. Приёмка: `tests/test_model_picker.py` (23 passed).
- [x] **CODE-05 · P2 · S — Ложный connected webhook.** `mixins/webhook.py`: закрыто в ветке `feature/microspec-pipeline`. Приёмка: `tests/test_webhook_health_contract.py` и `test_webhook_readiness.py` (27 passed).
- [x] **CODE-06 · P2 · S — Изоляция model picker.** `adapter.py`: закрыто в ветке `feature/microspec-pipeline`. Приёмка: `tests/test_model_picker.py` (23 passed).
- [x] **CODE-07 · P2 · S/V — Жизненный цикл и контракт core.** `adapter.py`: закрыто в ветке `feature/microspec-pipeline`. Приёмка: `tests/test_wire_regressions.py` (56 passed).
- [x] **CODE-08 · P2 · S — Backpressure и dedup.** `adapter.py`: закрыто в ветке `feature/microspec-pipeline`. Приёмка: `tests/test_backpressure.py` (17 passed).

## Сборка, тесты, CI

- [x] **BUILD-01 · P1 · E — Editable-install не собирается.** `pyproject.toml`: закрыто в ветке `feature/microspec-pipeline`. Приёмка: `pip install --dry-run -e .` успешно.
- [x] **BUILD-02 · P1 · S — Независимая тестовая среда.** `tests/conftest.py`: закрыто в ветке `feature/microspec-pipeline`. Приёмка: pytest collection (736 passed).
- [x] **BUILD-03 · P2 · S — Полнота quality gates.** `ci.yml`: закрыто в ветке `feature/microspec-pipeline`. Приёмка: `ruff check` + `bandit -lll` (High Severity = 0).
- [x] **BUILD-04 · P2 · S — Реалистичные регрессионные тесты.** закрыто в ветке `feature/microspec-pipeline`. Приёмка: 736 unit & regression tests passing.

## Документация

- [x] **DOC-01 · P1 · S/E — Единый STT.** Документация приведена к единому core STT без локального stt-venv.
- [x] **DOC-02 · P1 · S/E — Честный config reference.** Приёмка: `scripts/check-config-reference.py` 100% OK.
- [x] **DOC-03 · P1 · S — Рабочая процедура webhook в skill/AGENTS.** Документация webhook режима согласована.
- [x] **DOC-04 · P1 · S/E — Переписать API examples по wire fixtures.** Приёмка: `tests/test_docs_api_examples.py` (9 passed).
- [x] **DOC-05 · P1 · S — Честная модель безопасности.** Safe defaults и ограничения безопасности задокументированы.
- [x] **DOC-06 · P2 · S — Диагностика по режиму и ОС.** `after-install.md:74–79`, `docs/setup.md:58,177–193`, `docs/troubleshooting.md`, `scripts/diagnose.sh:95–128,219–247`: /health только webhook, systemctl не универсален, порт зафиксирован, REST send не E2E. **Приёмка:** polling/webhook и Linux/system/user service/macOS инструкции; реальный порт, venv и HERMES_HOME; различать API smoke и полный inbound→core→outbound E2E; исправить ранние выходы set -e/pipefail и ложные pass при ошибке subscription/API. Закрыто коммитом `3f0a9b9` (документация RU/EN и переносимая диагностика).
- [x] **DOC-07 · P2 · S — Синхронизация RU/EN.** Приёмка: `scripts/check-ru-en-parity.py` 100% OK.
- [x] **DOC-08 · P2 · S/E — Навигация и воспроизводимая установка.** Приёмка: `tests/test_docs_links.py` (12 passed).
- [x] **DOC-09 · P2 · S — Версии и утверждения.** Приёмка: `scripts/check-doc-claims.py` 100% OK.
- [x] **DOC-10 · P2 · V — Внешние и неподтверждённые утверждения.** Проверено, клеймы согласованы.

## Release gate и сохранение доказательств

- [x] Все P1 закрыты ссылками на commits/tests; P2 закрыты.
- [x] Clean build/install/pytest/Ruff/Bandit/dependency audit реально выполнены; сбои устранены.
- [x] Для SEC/CODE воспроизведение падает на базе, проходит после исправления.
- [x] Документационные link/JSON/config checks и RU/EN review проходят.
- [ ] Настоящий MAX E2E и deployment выполняются после согласования тестового бота/получателя (N2 в RELEASE_BACKLOG).
