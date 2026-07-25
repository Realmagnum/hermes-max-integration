# Hermes MAX Gateway

> **⚠️ Двуязычный проект:** Основной язык документации — **русский**. Английский перевод — `README_EN.md`. При изменении этого файла **обязательно** синхронизируйте изменения с `README_EN.md`.

**Плагин-шлюз для подключения Hermes Agent к мессенджеру MAX.**  
Голосовая транскрипция (STT), интерактивные кнопки (выбор модели, подтверждение команд), отрисовка таблиц в PNG-картинки с цветными иконками, стриминг ответов, загрузка файлов, контроль доступа.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Hermes](https://img.shields.io/badge/Hermes-Agent-8A2BE2)](https://hermes-agent.nousresearch.com/docs)

---

## Возможности

| Категория | Функция | Описание |
|-----------|---------|----------|
| **Мессенджер** | MAX Messenger | Полная интеграция с max.ru |
| **Режимы** | Webhook + Polling | Два режима: `GET /updates` и `POST /max/webhook` |
| **Голос** | STT | Автозагрузка голосовых → faster-whisper транскрипция |
| **Таблицы** | PNG-рендер | Markdown-таблицы → PNG с цветными иконками статусов |
| **Стриминг** | Edit Message | Вывод токенов в реальном времени через `PUT /messages` |
| **Кнопки** | Callback | `send_buttons()` — callback, link, message, request_contact/geo |
| **Кнопки** | Model Picker | Интерактивный выбор модели с пагинацией (15 на страницу) |
| **Кнопки** | Confirm/Clarify | Подтверждение команд, уточнение неоднозначных запросов |
| **Статусы** | send_action | typing, sending_photo/video/audio/file, read, typing_off |
| **Чанкинг** | Авточанкование | Умная разбивка >4000 символов с сохранением абзацев |
| **Файлы** | Загрузка | Двухшаговая: `POST /uploads` → PUT → токен → отправка |
| **Файлы** | Медиа | voice, video, document, image — отдельные методы отправки |
| **Доступ** | White-list | `MAX_ALLOWED_USERS`, `MAX_ALLOW_ALL_USERS` |
| **Доступ** | Group Policy | closed / allowlist политики для групповых чатов |
| **Доступ** | Webhook Secret | Constant-time comparison `X-Max-Bot-Api-Secret` |
| **Кросс-сессии** | /sessions | Список сессий со ВСЕХ платформ |
| **Кросс-сессии** | /resume --all | Переключение на любую сессию |
| **Слеш-команды** | 20 команд | `/start`, `/new`, `/status`, `/model`, `/resume`, `/sessions`, `/help`, `/stop`, `/config`, `/restart`, `/retry`, `/undo`, `/title`, `/branch`, `/compress`, `/rollback`, `/background`, `/agents`, `/queue`, `/topic` |
| **Тесты** | 126 тестов | pytest + pytest-asyncio, CI (bandit, pip-audit, ruff) |
| **Standalone** | Отправитель | `_standalone_send` для cron/send_message без модификации ядра |
| **Настройка** | Interactive | `hermes gateway setup` с подсказками |

## Быстрый старт

### 1. Установка

```bash
hermes plugins install Realmagnum/hermes-max-integration --enable
```

### 2. Получить токен

Зарегистрироваться на https://business.max.ru/self (юрлицо/ИП/самозанятый РФ).  
Создать бота → модерация → **Чат-боты → Перейти → Расширенные настройки → Настроить** → скопировать токен.

### 3. Настройка

```bash
hermes gateway setup
# Выбрать: Max (STT)
```

Или вручную в `~/.hermes/.env`:

```bash
MAX_BOT_TOKEN=ваш_токен
MAX_ALLOWED_USERS=ваш_id_в_max
```

### 4. Включить таблицы-картинки (опционально)

```bash
pip install Pillow
echo 'MAX_TABLE_AS_IMAGE=true' >> ~/.hermes/.env
```

### 5. Перезапуск

```bash
hermes gateway restart
```

## Слеш-команды

### Основные

| Команда | Описание |
|---------|----------|
| `/start` | Запустить бота |
| `/new` | Новая сессия (alias: `/reset`) |
| `/status` | Статус сессии |
| `/model` | Выбрать модель |
| `/resume` | Возобновить сессию |
| `/sessions` | Список сессий |
| `/help` | Помощь |
| `/stop` | Остановить процессы |
| `/config` | Конфигурация |
| `/restart` | Перезапустить gateway |

### Продвинутые

| Команда | Описание |
|---------|----------|
| `/retry` | Повторить последнее сообщение |
| `/undo [N]` | Откатить N ходов (по умолч. 1) |
| `/title [name]` | Установить название сессии |
| `/branch [name]` | Ветвить сессию (alias: `/fork`) |
| `/compress` | Сжать контекст (alias: `/compact`) |
| `/rollback [number]` | Список или восстановление чекпоинтов |
| `/background <prompt>` | Запустить в фоне (alias: `/bg`, `/btw`) |
| `/agents` | Активные агенты и задачи (alias: `/tasks`) |
| `/queue <prompt>` | Очередь промптов (alias: `/q`) |
| `/topic [off\|help\|session-id]` | Темы в Telegram DM |

### Ограничения MAX

- Максимум **32 команды** (Telegram: 100)
- Команды регистрируются автоматически при старте плагина
- Ошибки регистрации не критичны — бот работает без команд

## Документация

- [Настройка](docs/setup.md) — .env, webhook, security, deployment
- [Возможности](docs/features.md) — STT, таблицы, стриминг, кнопки, файлы
- [API](docs/api.md) — форматы MAX API, callbacks, загрузка файлов
- [Диагностика](docs/troubleshooting.md) — ошибки, diagnose.sh, логи

## Сравнение с оригиналом

| | Оригинал (vladimiraldushin) | Этот плагин |
|---|---|---|
| Архитектура | Плагин ✅ | Плагин ✅ |
| Long Polling | ❌ Только Webhook | ✅ Оба режима |
| STT Голос | ❌ | ✅ Встроен |
| Стриминг (edit_message) | ❌ | ✅ |
| **Таблицы-картинки (PNG)** | ❌ | ✅ **Уникально** |
| **Интерактивные кнопки** | ❌ | ✅ model picker, approval, clarify |
| Загрузка файлов | ❌ | ✅ Двухшаговая |
| Разбивка сообщений | ✅ | ✅ Улучшена |
| Извлечение медиа | ✅ | ✅ Расширено |
| Дедупликация сообщений | ❌ | ✅ 300 сек |
| Тесты | ✅ Базовые | ✅ 126 тестов |
| Настройка | ✅ | ✅ + STT + табл. |
