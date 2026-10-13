# Возможности плагина

## Распознавание голосовых (STT)

### Как это работает

Голосовые MAX приходят как аудиовложения с URL в `payload.url`. Адаптер:

1. Скачивает аудио в `$HERMES_HOME/cache/audio/` (`~/.hermes/cache/audio/`)
2. Передаёт файл в Hermes Core
3. Core распознаёт речь (Core STT) и добавляет текст к сообщению

### Настройка

Распознавание выполняет **Hermes Core** (≥ 0.21.4). Настройка находится в `config.yaml` Core:

```yaml
stt:
  enabled: true
  language: ru      # core default is "en"
  provider: local   # также openai, groq, mistral, xai, elevenlabs
```

Для интерактивной настройки используйте `hermes tools` (категория 🎙️ Speech-to-Text).

### Параметры

| Параметр | По умолчанию | Описание |
|-----------|---------|-------------|
| `enabled` | `false` | Включить распознавание в Core |
| `language` | `en` | Язык распознавания (`ru` для русской речи) |
| `provider` | `local` | STT-провайдер (`local`, `openai`, `groq`, `mistral`, `xai`, `elevenlabs`) |

### Проверка конфигурации

```bash
grep -A8 "^stt:" ~/.hermes/config.yaml
```

### Устранение неполадок

**STT возвращает пустой результат:**
- Проверьте параметры в `config.yaml`: `enabled: true`, `language: ru`
- Убедитесь, что адаптер скачал аудио: `ls -la ~/.hermes/cache/audio/`

**Локальный провайдер faster-whisper:**
- Для `provider: local` установите пакет в окружение Core: `pip install faster-whisper`
- Ошибки распознавания Core смотрите в журнале: `grep -i "transcri" ~/.hermes/logs/gateway.log`

## Таблицы-изображения

### Как это работает

Markdown-таблицы (`| A | B |\n|---|---|`) преобразуются в PNG.
Основной рендерер — **HTML→PNG через Playwright/Chromium** (стабильная вёрстка, нативные
emoji без переполнения ячеек); если пакет или браузер недоступен, используется
классический рендерер Pillow.

**Алгоритм рендеринга (v6):**

1. **Playwright (HTML→PNG):** таблица → HTML → снимок Chromium
   (системный Chrome, если доступен, иначе встроенный)
2. **Pillow (резерв):** разбор Markdown-фрагментов (`**bold**`, `*italic*`,
   `` `code` ``), измерение ячеек через `draw.textlength()`, перенос строк с
   styles, draw with colored status icons
3. PNG-кэш учитывает текст таблицы **и** движок —
   смена движка не возвращает устаревшие изображения

### Параметры

| Параметр | Значение | Описание |
|-----------|-------|-------------|
| `MAX_TABLE_AS_IMAGE` | `false` | Включить PNG-рендеринг |
| `MAX_AUTO_INSTALL_PLAYWRIGHT` | `false` | Устанавливать Playwright и Chromium при первом рендере |
| `MAX_CELL_WIDTH` | `300px` | Максимальная ширина ячейки |
| `MAX_TABLE_WIDTH` | `1200px` | Максимальная ширина таблицы |
| `CELL_PAD_X` | `22px` | Горизонтальный отступ |
| `CELL_PAD_Y` | `14px` | Вертикальный отступ |

### Значки статуса

| Emoji | Unicode | Цвет | Значение |
|-------|---------|-------|---------|
| ✅ | ✓ | `#16a34a` | Готово |
| ❌ | ✗ | `#dc2626` | Ошибка |
| ⚠️ | ⚠ | `#ea580c` | Предупреждение |
| ⏳ | ◷ | `#ca8a04` | Ожидание |
| ▶ | ▶ | `#2563eb` | Выполняется |

### Устранение неполадок

**Pillow/Playwright не установлены:**
```bash
python scripts/setup-playwright.py          # установить playwright и Chromium
python -m pip install Pillow                # резервный рендерер
```

**Текст обрезан:**
- Увеличьте `MAX_CELL_WIDTH`
- Проверьте шрифты: `fc-list | grep -i dejavu`

**Некорректный рендеринг:**
- Используйте `draw.textlength()`, а не `wcswidth * 0.6`
- Добавьте запас 5px к ширине

## Потоковая отправка

### Как это работает

Адаптер использует `edit_message` через `PUT /messages` для потокового вывода токенов.

### Отображение reasoning

Для reasoning-моделей (DeepSeek R1, Claude Opus, Gemini Thinking) блок reasoning добавляется к итоговому ответу.

**Reasoning display:**

```yaml
# ~/.hermes/config.yaml
streaming:
  fresh_final_after_seconds: 10
```

> **Примечание:** Core читает `streaming.fresh_final_after_seconds` из секции `streaming:` (не `display.platforms.max.*`); настройка действует только для Telegram. В MAX reasoning входит в итоговое редактирование сообщения.

### Устранение неполадок

**Reasoning не отображается:**
- Проверьте модель: быстрые модели могут не выдавать reasoning
- Проверьте ошибки потоковой отправки в журналах Gateway

## Кнопки

### send_buttons()

Публичный метод отправки сообщений с inline-кнопками:

```python
await adapter.send_buttons(
    chat_id="chat:123",
    text="Выберите действие:",
    buttons=[
        {"type": "link", "text": "🌐 Site", "url": "https://example.com"},
        {"type": "callback", "text": "✅ Confirm", "payload": "confirm:123"},
        {"type": "request_contact", "text": "📞 Contact"},
    ],
)
```

### Типы кнопок

| type | Parameters | Description |
|------|------------|-------------|
| `callback` | `text`, `payload` | Inline callback |
| `link` | `text`, `url` | Open URL |
| `message` | `text`, `payload` | Pre-filled message |
| `request_contact` | `text` | Request contact |
| `request_geo_location` | `text` | Request location |

### Выбор модели

Интерактивный выбор модели с пагинацией (по 15 на страницу).

**Callback format:** `model:pick:{model}:{provider}`

**Pagination callbacks:** `model:page:{provider}:{page}`

### Подтверждение и уточнение

У адаптера нет публичного метода `adapter.clarify()`. Core вызывает `send_clarify`,
а ответ пользователя приходит callback с префиксом
`clarify:{clarify_id}:{index|other}`.

**Sending the question:**

```python
result = await adapter.send_clarify(
    chat_id="chat:123",
    question="Какой сервер?",
    choices=["web-01", "db-main"],   # None → the question is sent as plain text
    clarify_id="clr-42",
    session_key="telegram:42",
)
```

**Answer (callback):** `clarify:clr-42:0`, `clarify:clr-42:1`, …,
`clarify:clr-42:other` переводит сессию в режим свободного ввода. Обработчик —
`_handle_clarify_callback`. Подтверждение опасной команды использует префикс `exec`,
а подтверждение slash-команды — `sc` (полная таблица в `docs/api_RU.md`).

## Отправка файлов

### Загрузка в два этапа

1. `POST /uploads?type=image` → get the upload URL (`url` field) and, for
   audio/video, the `token` right away
2. `POST <url>` as a multipart form with the `data` field → get the `token`
   (for image/file)
3. `POST /messages` with `attachments: [{type: "image", payload: {token: "..."}}]`

### Allowlist для SSRF-защиты

```python
_ALLOWED_UPLOAD_HOSTS = {
    "platform-api2.max.ru",
    "platform-api.max.ru",
    "cdn.max.ru",
    "storage.max.ru",
    "upload.max.ru",
    "iu.oneme.ru",
    "fu.oneme.ru",
}
```

### Методы отправки

`_upload_send(chat_id, path, type, ...)` passes a MAX attachment type, not the
имя метода: `send_voice()` отправляет `type=audio`, `send_document()` отправляет
`type=file`.

| Method | Attachment `type` | Description |
|--------|-------------------|-------------|
| `send_voice()` | `audio` | Voice message |
| `send_video()` | `video` | Video message |
| `send_document()` | `file` | Document |
| `send_image_file()` | `image` | Image from a file (via CDN) |
| `send_image()` | `image` (`payload.url`) | Image by external URL, no upload |
| `send_multiple_images()` | `image` | Several images in one message |
| `send_animation()` | `image` | GIF (MAX sends it as an image) |

## Кроссплатформенные сессии

### Как это работает

Адаптер перехватывает `/sessions` и `/resume` до передачи в Core и запрашивает `SessionDB` без фильтра платформы.

### Команды

| Command | Action |
|---------|--------|
| `/sessions` | Last 15 sessions from all platforms |
| `/sessions search <q>` | Search all sessions |
| `/resume <id>` | Switch to any session |

### Настройка

```yaml
# ~/.hermes/config.yaml
platforms:
  max:
    extra:
      cross_session_users:
        - "95825064"  # ваш MAX user_id
```

Переменная окружения: `MAX_CROSS_SESSION_USERS="95825064"`.
Включение: `MAX_CROSS_SESSION=false` in `.env` (default: `false`).

## Автономная отправка

`_standalone_send()` — send messages from cron/send_message without core modification.

```bash
hermes send "text MEDIA:/file"
```

Работает через `_standalone_send` с нативной отправкой файлов.

## Боковая панель сессий Hermes Desktop

### Как это работает

The plugin includes a native UI component for Hermes Desktop — `desktop/plugin.js` (ID: `max-sessions-sidebar`).
При включении плагин автоматически добавляется в левую боковую панель Hermes Desktop.

### Возможности боковой панели

1. **Список диалогов MAX:** пользователи и группы, с которыми общались через MAX Bot API.
2. **Метрики сессий:** число сообщений и суммарный расход токенов в каждом диалоге.
3. **Время:** используется `Intl.DateTimeFormat` с выбранной пользователем локалью Desktop.
4. **Тема:** используются переменные активной темы Hermes, стили значков и карточек.

Страница сессий, уведомления и статусбар используют английский и русский наборы переводов плагина через публичный Desktop SDK. Английский применяется по умолчанию и для остальных языков; даты сохраняют выбранную пользователем локаль. При наличии `ctx.i18n.onLocaleChange` подписи команд палитры также обновляются при смене языка. В старых SDK подписи палитры сохраняют язык, активный при регистрации, до перезагрузки плагина; страница и статусбар остаются реактивными. Проверено по публичному SDK 2026-10-13: в [Hermes 0.21.4](https://github.com/NousResearch/hermes-agent/blob/v2026.9.21/apps/desktop/src/i18n/plugin-i18n.ts) этой подписки нет, а в [Hermes 0.21.5](https://github.com/NousResearch/hermes-agent/blob/v2026.9.24/apps/desktop/src/i18n/plugin-i18n.ts) она есть.

### Автоматическая установка (единый пакет)

Виджет Desktop не требует отдельной установки:
- Механизм Unified Package в Hermes Core копирует и регистрирует `desktop/plugin.js` в каталоге плагинов Desktop.
- При обновлении плагина компонент Desktop UI синхронизируется автоматически.
