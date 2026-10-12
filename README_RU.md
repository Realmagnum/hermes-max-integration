# Hermes MAX Gateway

<p align="center">
  <img src="assets/banner.jpg" alt="Интеграция Hermes с MAX" width="100%">
</p>

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

Краткую карту заметок покажет `tree docs`. `docs/architecture_RU.md` описывает компоненты; `docs/setup_RU.md` — установку и конфигурацию; `docs/security_RU.md` — границы безопасности; `docs/api_RU.md` — API-контракты; `docs/features_RU.md` — поведение функций; `docs/troubleshooting_RU.md` — диагностику; `docs/external-claims_RU.md` — датированные внешние утверждения. Правила документации — в `docs/document_writing_RU.md`.

Основные документы в `docs/` пишутся на английском (`name.md`), русские переводы — `name_RU.md`. `README.md` — английский, `README_RU.md` — русский.

## Быстрый старт

```bash
hermes plugins install Realmagnum/hermes-max-integration --enable
hermes gateway setup
```

Создайте бота MAX и получите токен по актуальной [официальной документации MAX](https://dev.max.ru/). `hermes gateway setup` поможет настроить токен и доступ. По умолчанию используется long polling. Для webhook задайте `MAX_WEBHOOK_URL` и `MAX_WEBHOOK_SECRET`, опубликуйте endpoint через публичный HTTPS и перезапустите gateway. **Перед сменой режима проверьте существующие подписки MAX:** при старте polling плагин пытается удалить устаревшие webhook-подписки.

Подробности и требования к production — в `docs/setup_RU.md`. Не сохраняйте токены и секреты в репозитории.

## Конфигурация

Полный справочник переменных окружения, значений по умолчанию и YAML-ключей `platforms.max` находится в `docs/setup_RU.md`.

## Slash-команды

Плагин пытается зарегистрировать 20 команд MAX; ошибка регистрации не мешает обработке сообщений. MAX допускает до 32 команд.

Основные: `/start`, `/new` (`/reset`), `/status`, `/model`, `/resume`, `/sessions`, `/help`, `/stop`, `/config`, `/restart`.

Дополнительные: `/retry`, `/undo [N]`, `/title [name]`, `/branch` (`/fork`), `/compress` (`/compact`), `/rollback [number]`, `/background` (`/bg`, `/btw`), `/agents` (`/tasks`), `/queue` (`/q`), `/topic`.

## Таблицы-картинки

Telegram Bot API 10.1+ поддерживает таблицы через отдельный API `sendRichMessage`; у MAX в текущем контракте нет аналогичного формата таблиц.

Настройка отображения reasoning в Hermes Core задаётся через `streaming:
  fresh_final_after_seconds`, но сейчас Core применяет её только к Telegram, не к MAX. Перед использованием как обхода проверьте `docs/features_RU.md`.

Для PNG-рендера Markdown-таблиц установите `MAX_TABLE_AS_IMAGE=true`. Основной рендерер — Playwright/Chromium, Pillow используется как fallback. Дополнительные зависимости должны быть установлены в том же Python-окружении, где работает Hermes Gateway. См. `docs/features_RU.md` и `docs/troubleshooting_RU.md`.

## Проверки и диагностика

Диагностика описана в `docs/troubleshooting_RU.md`. `scripts/diagnose.sh --send` отправляет реальное сообщение; запускайте только с одобренным адресатом.

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
