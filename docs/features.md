# Возможности

## STT (транскрипция голоса)

### Как это работает

Голосовые сообщения приходят из MAX как аудиовложение с `payload.url`. Плагин только
скачивает и кэширует аудио — **транскрибирует ядро Hermes** (≥ 0.20.0):

1. Адаптер скачивает аудио в кэш аудио ядра: `$HERMES_HOME/cache/audio/`
   (по умолчанию `~/.hermes/cache/audio/`). Если в легаси-каталоге
   `~/.hermes/audio_cache/` уже есть файлы, используется он.
2. Ядро транскрибирует файл по секции `stt` из `config.yaml` (провайдер, язык, модель).
3. Распознанный текст подставляется в сообщение, которое получает агент.
4. При `stt.echo_transcripts: true` (дефолт ядра) ядро дополнительно присылает в чат
   эхо-транскрипт отдельным сообщением в формате `🎙️ "<текст>"`.

Плагин сам голос не транскрибирует и не содержит настроек STT: отдельный stt-venv,
`scripts/transcribe_audio.py`, `MAX_STT_ENABLED` и `MAX_STT_VENV` удалены (STT вынесен
в ядро). Всё управление STT — на стороне ядра Hermes.

### Настройка

```bash
# Интерактивно: категория 🎙️ Speech-to-Text
hermes tools
```

Либо вручную в `~/.hermes/config.yaml`:

```yaml
stt:
  enabled: true
  language: ru        # дефолт ядра — "en"; "" = автоопределение
  provider: local     # local | groq | openai | mistral | xai | elevenlabs | deepinfra
  echo_transcripts: true
  local:
    model: base       # tiny | base | small | medium | large-v3
```

Если `provider` не задан, ядро подбирает провайдера автоматически по доступным ключам
(`local` — первый в цепочке). Для провайдера `local` пакет faster-whisper и модель
(`base` ≈ 150 МБ) ставятся и скачиваются при первом использовании.

### Параметры (дефолты ядра)

| Параметр | По умолчанию | Описание |
|----------|--------------|----------|
| `stt.enabled` | `true` | Автотранскрипция входящих голосовых |
| `stt.language` | `"en"` | Глобальный язык; `""` = автоопределение |
| `stt.provider` | не задан | Провайдер; не задан = автоподбор по доступным ключам |
| `stt.echo_transcripts` | `true` | Эхо-транскрипт `🎙️ "..."` в чат |
| `stt.local.model` | `base` | Модель faster-whisper |
| `stt.local.vad` | `true` | VAD-фильтр (антигаллюцинации на тишине) |
| `stt.groq.model` | `whisper-large-v3-turbo` | Модель Groq |
| `stt.openai.model` | `whisper-1` | Модель OpenAI (`gpt-4o-transcribe`, `gpt-transcribe`, …) |
| `stt.mistral.model` | `voxtral-mini-latest` | Модель Mistral (в `hermes tools` не показывается) |
| `stt.elevenlabs.model_id` | `scribe_v2` | Модель ElevenLabs Scribe |

У каждого провайдера есть и свой `language` (`language_code` у ElevenLabs): он
переопределяет глобальный `stt.language`.

### Диагностика

```bash
# 1. Что реально настроено в ядре
grep -A8 "^stt:" ~/.hermes/config.yaml

# 2. Кэш скачанного аудио (пусто → вложение не скачалось)
ls -la ~/.hermes/cache/audio/

# 3. Что говорит ядро
grep -i "transcri" ~/.hermes/logs/gateway.log | tail -20
```

Характерные записи в логе:

- `Voice transcription failed for <path>: <error>` — провайдер вернул ошибку
  (нет ключа, сеть, лимит, неподдерживаемый формат).
- `Configured STT failed for <path>; recovered with local STT` — сработал фоллбэк
  на локальный faster-whisper.
- `[voice message could not be transcribed automatically; the audio is available at: …]` —
  транскрипт не получен, агент видит путь к файлу вместо текста.
- Пустой транскрипт = тишина или слишком короткий клип (VAD отсекает тишину).

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
cd "${HERMES_HOME:-$HOME/.hermes}/plugins/max-platform"   # каталог плагина
HERMES_PY="$(head -1 "$(command -v hermes)" | sed 's|^#!||')"  # Python окружения шлюза
"$HERMES_PY" scripts/setup-playwright.py    # ставит playwright + Chromium
"$HERMES_PY" -m pip install Pillow          # фоллбэк-рендер
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

**Отображение как отдельное сообщение:**

```yaml
# ~/.hermes/config.yaml
display:
  platforms:
    max:
      fresh_final_after_seconds: 10
```

После 10 секунд стриминга финальный ответ отправляется новым сообщением (с reasoning внутри).

### Troubleshooting

**Reasoning не отображается:**
- Проверить модель (fast модели не генерируют reasoning)
- Проверить `fresh_final_after_seconds` в config.yaml

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

`{model}`/`{provider}` percent-кодируются, поэтому ID с двоеточием
(`llama3:8b`, `...:free`) разбираются однозначно.

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
      allow_admin_from:
        - "95825064"  # ваш MAX user_id
```

Отключение: `MAX_CROSS_SESSION=false` в `.env`.

## Standalone отправитель

`_standalone_send()` — отправка сообщений из cron/send_message без модификации ядра.

```bash
hermes send "текст MEDIA:/file"
```

Работает через `_standalone_send` с нативной доставкой файлов.
