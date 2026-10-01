# Возможности

## STT (Voice Transcription)

### Как работает

Голосовые сообщения от MAX приходят как аудиовложения с `payload.url` для прямой загрузки. Адаптер автоматически:

1. Загружает аудиофайл в `$HERMES_HOME/cache/audio/` (`~/.hermes/cache/audio/`)
2. Передаёт аудиофайл ядру Hermes
3. Ядро транскрибирует аудио (Core STT) и добавляет текст к сообщению

### Настройка

Транскрипция выполняется **ядром Hermes** (≥ 0.20.0). Настройка выполняется в `config.yaml` ядра:

```yaml
stt:
  enabled: true
  language: ru      # дефолт ядра — "en"
  provider: local   # или openai, groq, mistral, xai, elevenlabs
```

Для интерактивной настройки используйте `hermes tools` (категория 🎙️ Speech-to-Text).

### Параметры

| Параметр | По умолчанию | Описание |
|----------|--------------|----------|
| `enabled` | `false` | Включить транскрипцию голоса в ядре |
| `language` | `en` | Язык транскрипции (`ru` для распознавания русской речи) |
| `provider` | `local` | Провайдер STT (`local`, `openai`, `groq`, `mistral`, `xai`, `elevenlabs`) |

### Проверка конфигурации

```bash
grep -A8 "^stt:" ~/.hermes/config.yaml
```

### Troubleshooting

**STT возвращает пустоту:**
- Проверить настройки в `config.yaml`: `enabled: true`, `language: ru`
- Убедиться, что аудиофайл загружен адаптером: `ls -la ~/.hermes/cache/audio/`

**Локальный провайдер faster-whisper:**
- Для `provider: local` установить пакет в окружение ядра: `pip install faster-whisper`
- Ошибки транскрипции в логах ядра: `grep -i "transcri" ~/.hermes/logs/gateway.log`

## Таблицы-картинки

### Как работает

Markdown-таблицы (`| A | B |\n|---|---|`) рендерятся как PNG-изображения.
Основной рендер — **HTML→PNG через Playwright/Chromium** (фиксированная
раскладка, нативные эмодзи, без переполнения ячеек); если пакет или браузер
недоступны — автоматический фоллбэк на классическую отрисовку через Pillow.

**Алгоритм рендера (v6):**

1. **Playwright (HTML→PNG):** таблица → HTML → скриншот через Chromium
   (системный Chrome при наличии, иначе bundled)
2. **Pillow (фоллбэк):** парсинг markdown-сегментов (`**bold**`, `*italic*`,
   `` `code` ``), измерение ширины ячеек через `draw.textlength()`, soft-wrap
   с учётом стилей, отрисовка с цветными иконками статусов
3. Кэш PNG: ключ включает текст таблицы **и** движок рендера — при
   переключении движка старые картинки не подставляются

### Параметры

| Параметр | Значение | Описание |
|----------|----------|----------|
| `MAX_TABLE_AS_IMAGE` | `false` | Включить рендер в PNG |
| `MAX_AUTO_INSTALL_PLAYWRIGHT` | `false` | Авто-установка Playwright + Chromium при первом рендере |
| `MAX_CELL_WIDTH` | `300px` | Максимальная ширина ячейки |
| `MAX_TABLE_WIDTH` | `1200px` | Максимальная ширина таблицы |
| `CELL_PAD_X` | `22px` | Отступ по горизонтали |
| `CELL_PAD_Y` | `14px` | Отступ по вертикали |

### Иконки статусов

| Эмодзи | Unicode | Цвет | Значение |
|--------|---------|------|----------|
| ✅ | ✓ | `#16a34a` | Готово / Done |
| ❌ | ✗ | `#dc2626` | Ошибка / Failed |
| ⚠️ | ⚠ | `#ea580c` | Предупреждение |
| ⏳ | ◷ | `#ca8a04` | Ожидание |
| ▶ | ▶ | `#2563eb` | В процессе |

### Troubleshooting

**Pillow/Playwright не установлены:**
```bash
python scripts/setup-playwright.py          # ставит playwright + Chromium
python -m pip install Pillow                # фоллбэк-рендер
```

**Текст обрезается:**
- Увеличить `MAX_CELL_WIDTH`
- Проверить шрифты: `fc-list | grep -i dejavu`

**Кривая отрисовка:**
- Убедиться что используется `draw.textlength()` (не `wcswidth * 0.6`)
- Добавить 5px буфер к ширине

## Стриминг

### Как работает

Адаптер использует `edit_message` через `PUT /messages` для вывода токенов в реальном времени.

### Reasoning Display

При использовании reasoning-моделей (DeepSeek R1, Claude Opus, Gemini Thinking) блок с рассуждениями добавляется к финальному ответу.

**Отображение reasoning:**

```yaml
# ~/.hermes/config.yaml
streaming:
  fresh_final_after_seconds: 10
```

> **Примечание:** Ключ `streaming.fresh_final_after_seconds` читается ядром из секции `streaming:` (не `display.platforms.max.*`) и действует только для Telegram. В MAX рассуждения модели передаются в рамках финального редактирования сообщения.

### Troubleshooting

**Reasoning не отображается:**
- Проверить модель (fast модели не генерируют reasoning)
- Проверить журнал шлюза на наличие ошибок стриминга

## Кнопки

### send_buttons()

Публичный метод для отправки сообщений с inline-кнопками:

```python
await adapter.send_buttons(
    chat_id="chat:123",
    text="Выберите действие:",
    buttons=[
        {"type": "link", "text": "🌐 Сайт", "url": "https://example.com"},
        {"type": "callback", "text": "✅ Подтвердить", "payload": "confirm:123"},
        {"type": "request_contact", "text": "📞 Контакт"},
    ],
)
```

### Типы кнопок

| type | Параметры | Описание |
|------|-----------|----------|
| `callback` | `text`, `payload` | Inline callback |
| `link` | `text`, `url` | Открыть URL |
| `message` | `text`, `payload` | Предзаполненное сообщение |
| `request_contact` | `text` | Запрос контакта |
| `request_geo_location` | `text` | Запрос геолокации |

### Model Picker

Интерактивный выбор модели с пагинацией (15 на страницу).

**Callback format:** `model:pick:{model}:{provider}`

**Pagination callbacks:** `model:page:{provider}:{page}`

### Confirm/Clarify

Публичного метода `adapter.clarify()` нет. Ядро вызывает адаптер через
`send_clarify`, а ответ пользователя приходит callback'ом с префиксом
`clarify:{clarify_id}:{index|other}`.

**Отправка вопроса:**

```python
result = await adapter.send_clarify(
    chat_id="chat:123",
    question="Какой сервер выбрать?",
    choices=["web-01", "db-main"],   # None → вопрос уходит обычным текстом
    clarify_id="clr-42",
    session_key="telegram:42",
)
```

**Ответ (callback):** `clarify:clr-42:0`, `clarify:clr-42:1`, …,
`clarify:clr-42:other` (последний переводит сессию в режим ожидания
свободного текста). Обработчик — `_handle_clarify_callback`.
Подтверждение опасных команд — отдельный префикс `exec`, подтверждение
slash-команд — `sc` (полная таблица в `docs/api.md`).

## Загрузка файлов

### Двухшаговая загрузка

1. `POST /uploads?type=image` → получить upload URL (поле `url`) и, для
   audio/video, сразу `token`
2. `POST <url>` multipart-формой с полем `data` → получить `token`
   (для image/file)
3. `POST /messages` с `attachments: [{type: "image", payload: {token: "..."}}]`

### SSRF Allowlist

```python
_ALLOWED_UPLOAD_HOSTS = {
    "platform-api.max.ru",
    "cdn.max.ru",
    "storage.max.ru",
    "upload.max.ru",
    "iu.oneme.ru",
    "fu.oneme.ru",
}
```

### Методы отправки

`_upload_send(chat_id, path, type, ...)` передаёт в MAX attachment-тип, а не
имя метода: `send_voice()` шлёт `type=audio`, `send_document()` — `type=file`.

| Метод | Attachment `type` | Описание |
|-------|-------------------|----------|
| `send_voice()` | `audio` | Голосовое сообщение |
| `send_video()` | `video` | Видеосообщение |
| `send_document()` | `file` | Документ |
| `send_image_file()` | `image` | Изображение из файла (через CDN) |
| `send_image()` | `image` (`payload.url`) | Изображение по внешнему URL, без загрузки |
| `send_multiple_images()` | `image` | Несколько изображений одним сообщением |
| `send_animation()` | `image` | GIF (в MAX отправляется как изображение) |

## Кросс-платформенные сессии

### Как работает

Адаптер перехватывает `/sessions` и `/resume` до ядра, запрашивает `SessionDB` без фильтра платформы.

### Команды

| Команда | Действие |
|---------|----------|
| `/sessions` | Последние 15 сессий со всех платформ |
| `/sessions search <q>` | Поиск по всем сессиям |
| `/resume <id>` | Переключиться на любую сессию |

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
Включение/отключение: `MAX_CROSS_SESSION=false` в `.env` (по умолчанию: `false`).

## Standalone отправитель

`_standalone_send()` — отправка сообщений из cron/send_message без модификации ядра.

```bash
hermes send "текст MEDIA:/file"
```

Работает через `_standalone_send` с нативной доставкой файлов.

## Сайдбар сессий Desktop UI

### Как работает

Плагин содержит нативный компонент интерфейса для Hermes Desktop — `desktop/plugin.js` (ID: `max-sessions-sidebar`).
При включении плагина он автоматически отображается в левой боковой панели Hermes Desktop.

### Возможности сайдбара

1. **Список активных диалогов MAX:** вывод пользователей и групп, с которыми велась переписка через MAX Bot API.
2. **Метрики сессий:** отображение количества сообщений в диалоге и объема потребленных токенов.
3. **Форматирование времени:** использование локализованных утилит времени Hermes (`fmtDateTime`, `fmtDayTime`, `relativeTime`).
4. **Стилевая интеграция:** адаптация под активную тему оформления Hermes (CSS-переменные темы, нативные классы бейджей и карточек).

### Автоматическая установка (Unified Package)

Десктоп-виджет не требует отдельной установки или настройки пользователем:
- Механизм Unified Package ядра Hermes автоматически считывает `desktop/plugin.js` из состава плагина и разворачивает его в каталоге виджетов рабочего стола.
- При обновлении плагина виджет обновляется синхронно.
