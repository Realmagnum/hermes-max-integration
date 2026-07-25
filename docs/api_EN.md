# API Reference

## MAX Update Format

### Update Structure

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

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `update_type` | string | `message_created`, `message_callback`, `bot_started` |
| `chat.chat_id` | string | Chat ID (positive for DM, negative for groups) |
| `chat.chat_type` | string | `dm` or `group` |
| `message.mid` | string | Unique message ID |
| `message.text` | string | Message text |
| `message.from.user_id` | string | Sender ID |
| `message.attachments` | array | Attachments list |

### Attachments

```json
{
  "type": "voice",
  "payload": {
    "url": "https://cdn.max.ru/file.ogg"
  }
}
```

**Attachment types:**

| type | payload.url | Description |
|------|-------------|-------------|
| `voice` | ✅ | Voice message |
| `audio` | ✅ | Audio message |
| `image` | ✅ | Image |
| `video` | ✅ | Video message |
| `document` | ✅ | Document |
| `file` | ✅ | Any file |
| `location` | ✅ | Geolocation |

## Callback Data Format

### Callback Structure

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

### Parse callback_data

**Model picker:**
```
model:pick:{model}:{provider}
```
Example: `model:pick:deepseek-v4-flash:custom`

**Pagination:**
```
model:page:{provider}:{page}
```
Example: `model:page:custom:2`

**Confirm/Clarify:**
```
confirm:{action}
clarify:{question}:{option}
```

### Chat ID for Callback

**IMPORTANT:** For callback updates, chat_id is in `message.recipient.chat_id`, NOT in `chat.chat_id`.

```python
# Correct
chat_id = message.get("recipient", {}).get("chat_id")

# Incorrect
chat_id = chat.get("chat_id")
```

## Upload API

### Step 1: Get Upload URL

```bash
curl -X POST "https://platform-api.max.ru/uploads?type=image" \
  -H "Authorization: your_token" \
  -H "Content-Type: application/json"
```

Response:
```json
{
  "upload_url": "https://storage.max.ru/upload/abc123",
  "token": "cdn_token_123"
}
```

### Step 2: Upload File

```bash
curl -X PUT "https://storage.max.ru/upload/abc123" \
  -H "Content-Type: application/octet-stream" \
  --data-binary @file.jpg
```

### Step 3: Send Message

```bash
curl -X POST "https://platform-api.max.ru/messages?chat_id=95825064" \
  -H "Authorization: your_token" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Here is an image:",
    "attachments": [{
      "type": "image",
      "payload": {"token": "cdn_token_123"}
    }]
  }'
```

### SSRF Protection

Plugin checks upload URL host via `_ALLOWED_UPLOAD_HOSTS`:

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

Max message length: 4000 characters.

**Algorithm:**
1. Split text into paragraphs
2. If paragraph > 4000 chars — split by words
3. Assemble chunks ≤ 4000 chars
4. Send sequentially

### Response Format

```bash
curl -X POST "https://platform-api.max.ru/messages?chat_id=95825064" \
  -H "Authorization: your_token" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Hello",
    "format": "markdown"
  }'
```

**Formats:**
- `markdown` — Markdown (default)
- `html` — HTML

### Edit Message (Streaming)

```bash
curl -X PUT "https://platform-api.max.ru/messages?chat_id=95825064" \
  -H "Authorization: your_token" \
  -H "Content-Type: application/json" \
  -d '{
    "mid": "message_id",
    "text": "Updated text"
  }'
```

## Commands API

### Register Commands

Plugin automatically registers 20 commands via `PATCH /me/commands` on startup.

**Check registered commands:**

```bash
curl -H "Authorization: your_token" \
  https://platform-api.max.ru/me/commands
```

### Limitations

- Maximum **32 commands** (Telegram: 100)
- Registration errors not critical — bot works without commands
