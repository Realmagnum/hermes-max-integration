# Маршрутизация получателей вложений — Micro-Spec

[English version](20261119-media-recipient-routing.md)

Источник: расследование ошибки доставки вложений. База: `69717984d5ee2c81007d4b59242765c8db6bcd69`. Core: установленный локальный runtime, не pinned CI fixture.

## Контракт

Локальные image/file/audio/video должны использовать правильный query-параметр MAX без изменения upload, retry, download, TLS, авторизации или Core. Официальный контракт: https://dev.max.ru/docs-api/methods/POST/messages/ (`user_id` для пользователей, `chat_id` для чатов/каналов; проверено 2026-11-19).

| ID | Условие | Требуемый результат | Реализация | Проверка |
|---|---|---|---|---|
| MR-001 | Отрицательная цель без префикса | Adapter upload/send использует только `chat_id`; все четыре локальных media entry points | Реализовано | Проверено офлайн |
| MR-002 | Явные `chat:` или `user:`; положительный DM/user без префикса | Явный namespace сохраняется, положительный ID по умолчанию user; известный adapter DM chat ID преобразуется в user ID | Реализовано | Проверено офлайн |
| MR-003 | Standalone text/media delivery | Аналогичная маршрутизация namespace/sign без adapter-only DM state | Реализовано | Проверено офлайн |
| MR-004 | Обработка вложения или неоднозначный send | Существующая ограниченная readiness retry policy и однократный upload сохраняются | Без изменений | Readiness tests проходят |

## Свидетельства

Приёмка офлайн: настоящие асинхронные production entry points с заменёнными network/upload boundaries. Live delivery, полная pinned-Core CI matrix и deployment не заявлены. Проверка 2026-11-19, baseline плюс этот diff: `pytest tests/test_media_recipient_routing.py -q` → 73 passed (baseline с теми же тестами: 15 failed, 58 passed). Первая регрессия `send_document("-42", ...)` упала до изменения production: фактически `user_id=-42`, ожидалось `chat_id=-42`; тот же тест падает на release pin `50c7a9a7c16b6207a079b7b883718dd863e9e951` и installed pin `ae49b6092ed190ff721237f1676205edfaee8dec`. Профильный набор media/readiness/security: 298 passed. Полная suite с экспортированным исходником Core `ca13a7828acd2ba8c75e1c1d1694cbc1aee7df3f`, Python 3.14.9 и повторно использованными установленными runtime dependencies: 984 passed, 6 skipped (Core standalone-policy feature guards); это не чистая установка зависимостей CI. Runner предварительно импортировал namespace тестов плагина против коллизии с тестами Core. На установленном локальном Core runtime baseline и candidate имеют одинаковые 15 посторонних падений (clarify API и удалённый send-message module). Ruff изменённых файлов проходит; полный Ruff имеет две одинаковые baseline RUF100 в пакетных `__init__.py`. pytest-asyncio сообщает существующее предупреждение unset loop-scope. Полная minimum/baseline/current CI, dependency audit и live delivery не запускались. Вне scope: URL-image, location и button routing; широкий parser refactor; новая target grammar; production operations.
