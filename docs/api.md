# API Reference

Wire-формат MAX Bot API и то, как его обрабатывает адаптер.

Все JSON-блоки в этом файле валидны и проверяются тестом
`tests/test_docs_api_examples.py`; там же примеры upload/send/edit/callback
исполняются на `httpx.MockTransport` против реального кода адаптера.

Официальная документация: https://dev.max.ru/docs-api

> MAX сейчас рекомендует домен `platform-api2.max.ru` вместо
> `platform-api.max.ru`. Адаптер пока использует `platform-api.max.ru`
> (`MAX_API_BASE` в `mixins/media_upload.py` и `adapter.py`) — примеры ниже
> соответствуют текущей реализации.

## Формат MAX Update

### Личный диалог (message_created)

```json
{
  "update_type": "message_created",
  "timestamp": 1737500130100,
  "message": {
    "sender": {
      "user_id": 95825064,
      "name": "Иван",
      "username": "ivan",
      "is_bot": false
    },
    "recipient": {
      "chat_type": "dialog",
      "user_id": 123456
    },
    "timestamp": 1737500130100,
    "body": {
      "mid": "mid-abc123",
      "seq": 42,
      "text": "Привет!"
    }
  }
}
```

### Групповой чат (message_created)

```json
{
  "update_type": "message_created",
  "timestamp": 1737500130100,
  "message": {
    "sender": {
      "user_id": 95825064,
      "name": "Иван",
      "is_bot": false
    },
    "recipient": {
      "chat_id": -70987654321,
      "chat_type": "chat"
    },
    "body": {
      "mid": "mid-grp-1",
      "seq": 7,
      "text": "Всем привет"
    }
  }
}
```

Корневого объекта `chat` в Update нет: id чата приходит в
`message.recipient.chat_id`. Адаптер считает сообщение групповым, если
`recipient.chat_id` присутствует; иначе это диалог (`user:{user_id}`).

### Поля

| Поле | Тип | Описание |
|------|-----|----------|
| `update_type` | string | Тип события: `message_created`, `message_callback`, `message_edited`, `message_removed`, `bot_added`, `bot_started`, `bot_stopped`, `bot_removed` и др. |
| `message.sender.user_id` | int64 | ID отправителя |
| `message.sender.is_bot` | bool | `true` для сообщений бота — адаптер их игнорирует |
| `message.recipient.chat_id` | int64 | ID чата/канала (есть только у групповых чатов и каналов) |
| `message.recipient.chat_type` | string | `dialog`, `chat` или `channel` |
| `message.body.mid` | string | Уникальный ID сообщения (нужен для `edit_message` / `delete_message`) |
| `message.body.text` | string | Текст сообщения |
| `message.body.attachments` | array | Список вложений |

### Вложения (входящие)

```json
{
  "type": "image",
  "payload": {
    "url": "https://iu.oneme.ru/i?r=abc123",
    "photo_id": 987654
  }
}
```

Официальные типы вложений: `image`, `video`, `audio`, `file`, `sticker`,
`contact`, `inline_keyboard`, `share`, `location`.

Входящие медиа адаптер скачивает по `payload.url` и раскладывает во внутренние
media-типы (`image`, `audio`/`voice`, `document`) — см.
`_extract_inbound_media` и `_attachment_kind` в `adapter.py`.

## Callback Data Format

### Структура message_callback

```json
{
  "update_type": "message_callback",
  "timestamp": 1737500130100,
  "callback": {
    "timestamp": 1737500130100,
    "callback_id": "cb-77",
    "payload": "model:pick:deepseek-v4-flash:custom",
    "user": {
      "user_id": 95825064,
      "name": "Иван"
    }
  },
  "message": {
    "sender": {
      "user_id": 123456,
      "is_bot": true
    },
    "recipient": {
      "chat_type": "dialog",
      "user_id": 123456
    },
    "body": {
      "mid": "mid-picker-1",
      "text": ""
    }
  }
}
```

Данные кнопки лежат в `callback.payload` (адаптер принимает и `callback.data`),
нажавший пользователь — `callback.user.user_id`.

### Chat ID для callback

**ВАЖНО:** для callback chat_id находится в `message.recipient.chat_id`,
НЕ в `chat.chat_id`.

```python
# Правильно
chat_id = message.get("recipient", {}).get("chat_id")

# Неправильно
chat_id = chat.get("chat_id")
```

### Префиксы callback_data (реализация адаптера)

`_on_callback` разбирает `callback.payload` по префиксу до первого `:`:

| Префикс | Формат | Назначение |
|---------|--------|------------|
| `exec` | `exec:{choice}:{approval_id}` | Подтверждение опасной команды (`once` / `session` / `always` / `deny`) |
| `sc` | `sc:{choice}:{confirm_id}` | Подтверждение slash-команды (`once` / `always` / `cancel`) |
| `clarify` | `clarify:{clarify_id}:{index}`, `clarify:{clarify_id}:other` | Выбор варианта clarify (свободный ввод для `other`) |
| `model` | `model:provider:{slug}`, `model:pick:{model}:{provider}`, `model:page:{provider}:{page}`, `model:back` | Model picker |

Неизвестный префикс логируется и игнорируется (возвращается `None`).

## Upload API

Загрузка медиафайла — два шага: получить URL для загрузки и залить по нему
файл. Токен для вложения берётся из ответа шага 1 (audio/video) или из ответа
CDN (image/file).

### Шаг 1: Получить URL загрузки

```bash
curl -X POST "https://platform-api.max.ru/uploads?type=image" \
  -H "Authorization: {access_token}"
```

Ответ:

```json
{
  "url": "https://iu.oneme.ru/upload.do?params=abc123"
}
```

Для `type=audio` и `type=video` в ответе сразу приходит и токен:

```json
{
  "url": "https://omu.okcdn.ru/upload.do?params=abc123",
  "token": "cdn_token_abc123"
}
```

Допустимые значения `type`: `image`, `video`, `audio`, `file`
(`type=photo` больше не поддерживается). Домен в `url` зависит от типа файла:
`file` → `fu.oneme.ru`, `image` → `iu.oneme.ru`, `video` → `omub.okcdn.ru`,
`audio` → `omu.okcdn.ru`.

### Шаг 2: Загрузить файл (multipart POST)

```bash
curl -X POST "https://iu.oneme.ru/upload.do?params=abc123" \
  -H "Content-Type: multipart/form-data" \
  -F "data=@picture.jpg"
```

Файл передаётся multipart-формой с полем `data` — это `POST`, а не бинарный
`PUT`. Ответ CDN для `image`/`file`:

```json
{
  "token": "cdn_token_abc123"
}
```

### Шаг 3: Отправить сообщение с вложением

```bash
curl -X POST "https://platform-api.max.ru/messages?chat_id=95825064" \
  -H "Authorization: {access_token}" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Вот изображение:",
    "attachments": [
      {
        "type": "image",
        "payload": {"token": "cdn_token_abc123"}
      }
    ]
  }'
```

Пока CDN обрабатывает файл, `POST /messages` может вернуть
`{"code": "attachment.not.ready", "message": "..."}` — адаптер повторяет
отправку (задержки 2/4/6 с).

### SSRF Protection

Плагин проверяет хост upload URL через `_ALLOWED_UPLOAD_HOSTS`
(плюс суффиксы `.max.ru`, `.oneme.ru`, `.okcdn.ru`):

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

## Message Sending

### Chunking

Максимальная длина сообщения: 4000 символов.

**Алгоритм:**
1. Разбить текст на абзацы
2. Если абзац > 4000 символов — разбить по словам
3. Собрать чанки ≤ 4000 символов
4. Отправить последовательно

### Формат ответа

```bash
curl -X POST "https://platform-api.max.ru/messages?chat_id=95825064" \
  -H "Authorization: {access_token}" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Hello",
    "format": "markdown"
  }'
```

**Форматы:**
- `markdown` — Markdown (по умолчанию)
- `html` — HTML

### Edit Message (Стриминг)

Правка идёт через `PUT /messages` с query-параметром `message_id` (не
`chat_id` и не `mid` в теле):

```bash
curl -X PUT "https://platform-api.max.ru/messages?message_id=mid-abc123" \
  -H "Authorization: {access_token}" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Updated text",
    "format": "markdown"
  }'
```

### Delete Message

```bash
curl -X DELETE "https://platform-api.max.ru/messages?message_id=mid-abc123" \
  -H "Authorization: {access_token}"
```

## Commands API

### Регистрация команд

Плагин автоматически регистрирует 20 команд через `PATCH /me/commands` при
старте.

**Проверить зарегистрированные команды:**

```bash
curl -H "Authorization: {access_token}" \
  https://platform-api.max.ru/me/commands
```

### Ограничения

- Максимум **32 команды** (Telegram: 100)
- Ошибки регистрации не критичны — бот работает без команд

## Исполняемые примеры (mocked)

Примеры ниже запускаются в `tests/test_docs_api_examples.py` на
`httpx.MockTransport`: код адаптера настоящий, сеть замокана.

```python
import httpx
from gateway.config import PlatformConfig

import adapter


def _adapter(handler):
    cfg = PlatformConfig(enabled=True, token="test-token", extra={"token": "test-token"})
    a = adapter.MaxAdapter(cfg)
    a._http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return a


# upload + send: POST /uploads → multipart POST <url> → POST /messages
async def handler(request):
    if request.url.path == "/uploads":
        return httpx.Response(200, json={"url": "https://iu.oneme.ru/upload.do?params=abc"})
    if request.url.host == "iu.oneme.ru":
        return httpx.Response(200, json={"token": "cdn_token_abc123"})
    return httpx.Response(200, json={"message": {"body": {"mid": "mid-1"}}})
```

Результат `edit_message` проверяется по query-параметру `message_id`, а
callback — по фикстуре `message_callback` из этого файла, поданной в
`adapter._on_callback`.
