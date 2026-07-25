# API Reference

## Формат MAX Update

### Структура обновления

```json
{
  "update_id": 12345,
  "update_type": "message_created",
  "timestamp": 1234567890,
  "chat": {
    "chat_id": "95825064",
    "chat_type": "dm",
    "title": null,
    "username": "username"
  },
  "message": {
    "mid": "message_id",
    "message_id": 123,
    "text": "Hello",
    "from": {
      "user_id": "95825064",
      "username": "username"
    },
    "attachments": [
      {
        "type": "voice",
        "payload": {
          "url": "https://cdn.max.ru/voice.ogg"
        }
      }
    ]
  },
  "body": {
    "mid": "message_id",
    "attachments": [...]
  }
}
```

### Поля

| Поле | Тип | Описание |
|------|-----|----------|
| `update_type` | string | `message_created`, `message_callback`, `bot_started` |
| `chat.chat_id` | string | ID чата (положительный для DM, отрицательный для групп) |
| `chat.chat_type` | string | `dm` или `group` |
| `message.mid` | string | Уникальный ID сообщения |
| `message.text` | string | Текст сообщения |
| `message.from.user_id` | string | ID отправителя |
| `message.attachments` | array | Список вложений |

### Attachments

```json
{
  "type": "voice",
  "payload": {
    "url": "https://cdn.max.ru/file.ogg"
  }
}
```

**Типы вложений:**

| type | payload.url | Описание |
|------|-------------|----------|
| `voice` | ✅ | Голосовое сообщение |
| `audio` | ✅ | Аудиосообщение |
| `image` | ✅ | Изображение |
| `video` | ✅ | Видеосообщение |
| `document` | ✅ | Документ |
| `file` | ✅ | Любой файл |
| `location` | ✅ | Геолокация |

## Callback Data Format

### Структура callback

```json
{
  "update_type": "message_callback",
  "message": {
    "mid": "message_id",
    "text": "",
    "callback_data": "model:pick:deepseek-v4-flash:custom"
  }
}
```

### Разбор callback_data

**Model picker:**
```
model:pick:{model}:{provider}
```
Пример: `model:pick:deepseek-v4-flash:custom`

**Pagination:**
```
model:page:{provider}:{page}
```
Пример: `model:page:custom:2`

**Confirm/Clarify:**
```
confirm:{action}
clarify:{question}:{option}
```

### Chat ID для callback

**ВАЖНО:** Для callback обновлений chat_id находится в `message.recipient.chat_id`, НЕ в `chat.chat_id`.

```python
# Правильно
chat_id = message.get("recipient", {}).get("chat_id")

# Неправильно
chat_id = chat.get("chat_id")
```

## Upload API

### Шаг 1: Получить URL загрузки

```bash
curl -X POST "https://platform-api.max.ru/uploads?type=image" \
  -H "Authorization: ваш_токен" \
  -H "Content-Type: application/json"
```

Ответ:
```json
{
  "upload_url": "https://storage.max.ru/upload/abc123",
  "token": "cdn_token_123"
}
```

### Шаг 2: Загрузить файл

```bash
curl -X PUT "https://storage.max.ru/upload/abc123" \
  -H "Content-Type: application/octet-stream" \
  --data-binary @file.jpg
```

### Шаг 3: Отправить сообщение

```bash
curl -X POST "https://platform-api.max.ru/messages?chat_id=95825064" \
  -H "Authorization: ваш_токен" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Вот изображение:",
    "attachments": [{
      "type": "image",
      "payload": {"token": "cdn_token_123"}
    }]
  }'
```

### SSRF Protection

Плагин проверяет хост upload URL через `_ALLOWED_UPLOAD_HOSTS`:

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
  -H "Authorization: ваш_токен" \
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

```bash
curl -X PUT "https://platform-api.max.ru/messages?chat_id=95825064" \
  -H "Authorization: ваш_токен" \
  -H "Content-Type: application/json" \
  -d '{
    "mid": "message_id",
    "text": "Updated text"
  }'
```

## Commands API

### Регистрация команд

Плагин автоматически регистрирует 20 команд через `PATCH /me/commands` при старте.

**Проверить зарегистрированные команды:**

```bash
curl -H "Authorization: ваш_токен" \
  https://platform-api.max.ru/me/commands
```

### Ограничения

- Максимум **32 команды** (Telegram: 100)
- Ошибки регистрации не критичны — бот работает без команд
