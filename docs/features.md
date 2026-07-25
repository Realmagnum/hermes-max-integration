# Возможности

## STT (Voice Transcription)

### Как работает

Голосовые сообщения от MAX приходят как аудиовложения с `payload.url` для прямой загрузки. Адаптер автоматически:

1. Загружает аудиофайл в `~/.hermes/audio_cache/max_audio_{message_id}.ogg`
2. Транскрибирует через faster-whisper
3. Добавляет текст к сообщению

### Настройка

```bash
# Создать venv для faster-whisper
python3 -m venv ~/.hermes/stt-venv
~/.hermes/stt-venv/bin/pip install faster-whisper

# Скопировать скрипт
cp scripts/transcribe_audio.py ~/.hermes/scripts/
```

### Параметры

| Параметр | По умолчанию | Описание |
|----------|--------------|----------|
| `MAX_STT_ENABLED` | `true` | Включить/выключить STT |
| `MAX_STT_VENV` | `~/.hermes/stt-venv` | Путь к venv |
| Модель | `base` | faster-whisper модель |

### Скрипт транскрипции

```bash
~/.hermes/scripts/transcribe_audio.py /path/to/file.ogg
```

### Troubleshooting

**STT возвращает пустоту:**
- Проверить модель: `ls ~/.hermes/stt-venv/lib/python*/site-packages/whisper/assets/`
- Убедиться что файл загружен: `ls -la ~/.hermes/audio_cache/max_audio_*.ogg`

**Медленная транскрипция:**
- Использовать модель `tiny` вместо `base`
- Включить GPU: `export WHISPER_DEVICE=cuda:0`

## Таблицы-картинки

### Как работает

Markdown-таблицы (`| A | B |\n|---|---|`) рендерятся как PNG-изображения через Pillow.

**Алгоритм рендера (v5):**

1. Парсинг markdown-сегментов (`**bold**`, `*italic*`, `` `code` ``)
2. Измерение ширины каждой ячейки через `draw.textlength()`
3. Soft-wrap текста с учётом стилей
4. Отрисовка с цветными иконками статусов

### Параметры

| Параметр | Значение | Описание |
|----------|----------|----------|
| `MAX_TABLE_AS_IMAGE` | `false` | Включить рендер в PNG |
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

**Pillow не установлен:**
```bash
pip install Pillow
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

**Pagination callbacks:** `model:page:{provider}:{page}`

### Confirm/Clarify

**Confirm:**
```python
result = await adapter.clarify(
    chat_id="chat:123",
    question="Подтвердить действие?",
    options=["Да", "Нет"],
)
```

**Clarify:**
```python
result = await adapter.clarify(
    chat_id="chat:123",
    question="Какой сервер выбрать?",
    options=["web-01", "db-main"],
)
```

## Загрузка файлов

### Двухшаговая загрузка

1. `POST /uploads?type=image` → получить upload URL
2. `PUT <upload_url>` → загрузить файл
3. Получить CDN token
4. `POST /messages` с `attachments: [{type: "image", payload: {token: "..."}}]`

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

| Метод | Тип | Описание |
|-------|-----|----------|
| `send_voice()` | voice | Голосовое сообщение |
| `send_video()` | video | Видеосообщение |
| `send_document()` | document | Документ |
| `send_image()` | image | Изображение (через CDN) |

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
