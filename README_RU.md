# Hermes MAX Gateway

![Интеграция Hermes с MAX](assets/banner.jpg)

> Английская версия: [README.md](README.md). Этот файл — русская версия; синхронизируйте факты и ссылки в обеих версиях.

Плагин-платформа Hermes Agent для мессенджера MAX. Подключает polling/webhook, потоковые ответы, интерактивные кнопки и подтверждения, медиа, политики доступа, таблицы-картинки и необязательный сайдбар сессий Hermes Desktop. Распознавание голосовых выполняет Hermes Core STT, а не плагин.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Hermes Agent](https://img.shields.io/badge/Hermes-Agent-8A2BE2)](https://hermes-agent.nousresearch.com/docs)

## Возможности

- Long polling или webhook через MAX Bot API.
- Потоковые ответы, разбиение длинных сообщений, статусы действий.
- Callback/link/message/contact/location-кнопки; выбор модели, подтверждение команд и clarify.
- Загрузка и отправка медиа; интеграция с `hermes send`.
- Необязательная отрисовка Markdown-таблиц в PNG: Playwright/Chromium с fallback на Pillow.
- Политики доступа для пользователей и групп, проверка секрета webhook, проверка владельца callback.
- Необязательные кросс-платформенные `/sessions` и `/resume` с явной авторизацией.
- Необязательный сайдбар сессий Hermes Desktop и локализация RU/EN.
- Голосовые файлы передаются в STT-конвейер Hermes Core; настройка распознавания выполняется в Core.

## Карта документации

Краткую карту заметок покажет `tree docs`. [docs/architecture_RU.md](docs/architecture_RU.md) описывает компоненты; [docs/setup_RU.md](docs/setup_RU.md) — установку и конфигурацию; [docs/security_RU.md](docs/security_RU.md) — границы безопасности; [docs/api_RU.md](docs/api_RU.md) — API-контракты; [docs/features_RU.md](docs/features_RU.md) — поведение функций; [docs/troubleshooting_RU.md](docs/troubleshooting_RU.md) — диагностику; [docs/external-claims_RU.md](docs/external-claims_RU.md) — датированные внешние утверждения. Правила документации — в [docs/document_writing_RU.md](docs/document_writing_RU.md).

Основные документы в `docs/` пишутся на английском (`name.md`), русские переводы — `name_RU.md`. `README.md` — английский, `README_RU.md` — русский.

[Разработка по Micro-Spec](docs/micro-spec-development_RU.md): требования, реализация, проверка и передача работы. [Контракты каталога и evidence приёмки](docs/specs/catalog-review-137501_RU.md); [оставшаяся работа](BACKLOG_RU.md); [история изменений](CHANGELOG_RU.md).

## Быстрый старт

Требуется Hermes Core **>=0.21.4**. Минимальный релиз проверен на `d337b736aa1e8ebecfab043842d13e4a2d2f48a3` (0.21.4, Python 3.12); CI также проверяет более поздние baseline/current исходники. В Core 0.20 нет необходимого плагину entry point для нативного подтверждения команд.

```bash
hermes plugins install Realmagnum/hermes-max-integration --enable
hermes gateway setup
```

Создайте бота MAX и получите токен по актуальной [официальной документации MAX](https://dev.max.ru/). `hermes gateway setup` поможет настроить токен и доступ. По умолчанию используется long polling. Для webhook задайте `MAX_WEBHOOK_URL` и `MAX_WEBHOOK_SECRET`, опубликуйте endpoint через публичный HTTPS и перезапустите gateway. **Перед сменой режима проверьте существующие подписки MAX:** при старте polling плагин пытается удалить устаревшие webhook-подписки.

Подробности и требования к production — в [docs/setup_RU.md](docs/setup_RU.md). Не сохраняйте токены и секреты в репозитории.

## Конфигурация

Полный справочник переменных окружения, значений по умолчанию и YAML-ключей `platforms.max` находится в [docs/setup_RU.md](docs/setup_RU.md).

## Slash-команды

Плагин пытается зарегистрировать 20 команд MAX; ошибка регистрации не мешает обработке сообщений. MAX допускает до 32 команд.

Основные: `/start`, `/new` (`/reset`), `/status`, `/model`, `/resume`, `/sessions`, `/help`, `/stop`, `/config`, `/restart`.

Дополнительные: `/retry`, `/undo [N]`, `/title [name]`, `/branch` (`/fork`), `/compress` (`/compact`), `/rollback [number]`, `/background` (`/bg`, `/btw`), `/agents` (`/tasks`), `/queue` (`/q`), `/topic`.

## Таблицы-картинки

Telegram Bot API 10.1+ поддерживает таблицы через отдельный API `sendRichMessage`; у MAX в текущем контракте нет аналогичного формата таблиц.

Настройка отображения reasoning в Hermes Core задаётся через `streaming:
  fresh_final_after_seconds`, но сейчас Core применяет её только к Telegram, не к MAX. Перед использованием как обхода проверьте [docs/features_RU.md](docs/features_RU.md).

Для PNG-рендера Markdown-таблиц установите `MAX_TABLE_AS_IMAGE=true`. Основной рендерер — Playwright/Chromium, Pillow используется как fallback. Дополнительные зависимости должны быть установлены в том же Python-окружении, где работает Hermes Gateway. См. [docs/features_RU.md](docs/features_RU.md) и [docs/troubleshooting_RU.md](docs/troubleshooting_RU.md).

## Безопасность и приватность

Плагин содержит российский корневой сертификат Russian Trusted Root CA и добавляет его только клиентам MAX API и загрузки исходящих файлов. Это расширяет их обычный набор доверенных CA. Скачивание вложений использует стандартное доверие TLS без дополнительного CA и сохраняет защиту от SSRF. См. [docs/security_RU.md](docs/security_RU.md).

Проверенный набор зависимостей Core закрепляет PyJWT 2.13.0; аудит сообщает 14 advisories для этой версии. Аудит остаётся неуспешным до исправления ограничения upstream Core; исключения аудита и несовместимые подмены зависимостей не используются. См. [docs/external-claims_RU.md](docs/external-claims_RU.md).

Исходящие API-запросы направляются только на endpoint MAX Bot API, закреплённый в плагине (`MAX_API_BASE`, `https://platform-api2.max.ru`) и официальные медиа-хосты MAX (`*.max.ru`, `*.oneme.ru`). Скачанные медиафайлы и PNG-таблицы хранятся локально в `HERMES_HOME`. В плагине нет телеметрии, аналитики или кода автообновления; режим webhook требует `MAX_WEBHOOK_SECRET` (fail-closed). См. [docs/security_RU.md](docs/security_RU.md).

## Проверки и диагностика

Диагностика описана в [docs/troubleshooting_RU.md](docs/troubleshooting_RU.md). `scripts/diagnose.sh --send` отправляет реальное сообщение; запускайте только с одобренным адресатом.

```bash
python scripts/check_docs_links.py
python scripts/check-ru-en-parity.py
python scripts/check-doc-claims.py
python scripts/check-config-reference.py
python -m pytest tests/ -q
```

## Структура проекта

```text
adapter.py                  MAX gateway adapter и lifecycle
mixins/                      Webhook, медиа, кнопки, callbacks, сессии, рендер таблиц
desktop/plugin.js            Сайдбар Hermes Desktop
locales/                     Локализация плагина и Desktop
scripts/                     Setup, release, диагностика, проверки документации
tests/                       Unit-, API-contract-, security- и docs-тесты
docs/                        Долговечные заметки; русские версии имеют суффикс _RU
skills/max-gateway/          Операционный workflow установки и сопровождения
plugin.yaml                  Метаданные Hermes-плагина
pyproject.toml               Python package и настройки тестов
```

## Лицензия

MIT. См. `LICENSE`.

## Благодарности

- [Hermes Agent](https://hermes-agent.nousresearch.com/docs) — агентский фреймворк.
- [vladimiraldushin/hermes-max-platform](https://github.com/vladimiraldushin/hermes-max-platform) — архитектурная отправная точка интеграции MAX.
