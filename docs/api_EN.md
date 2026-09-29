# API Reference

Wire format of the MAX Bot API and how the adapter handles it.

Every JSON block in this file is valid and is checked by
`tests/test_docs_api_examples.py`; the same test runs the upload/send/edit/callback
examples on `httpx.MockTransport` against the real adapter code.

Official documentation: https://dev.max.ru/docs-api

> MAX currently recommends the `platform-api2.max.ru` domain instead of
> `platform-api.max.ru`. The adapter still uses `platform-api.max.ru`
> (`MAX_API_BASE` in `mixins/media_upload.py` and `adapter.py`) — the examples
> below match the current implementation.

## MAX Update Format

### Direct dialog (message_created)

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

### Group chat (message_created)

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

An Update has no root `chat` object: the chat id arrives in
`message.recipient.chat_id`. The adapter treats a message as a group message when
`recipient.chat_id` is present; otherwise it is a dialog (`user:{user_id}`).

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `update_type` | string | Event type: `message_created`, `message_callback`, `message_edited`, `message_removed`, `bot_added`, `bot_started`, `bot_stopped`, `bot_removed`, etc. |
| `message.sender.user_id` | int64 | Sender ID |
| `message.sender.is_bot` | bool | `true` for bot messages — the adapter ignores them |
| `message.recipient.chat_id` | int64 | Chat/channel ID (present only for group chats and channels) |
| `message.recipient.chat_type` | string | `dialog`, `chat` or `channel` |
| `message.body.mid` | string | Unique message ID (needed for `edit_message` / `delete_message`) |
| `message.body.text` | string | Message text |
| `message.body.attachments` | array | Attachments list |

### Attachments (inbound)

```json
{
  "type": "image",
  "payload": {
    "url": "https://iu.oneme.ru/i?r=abc123",
    "photo_id": 987654
  }
}
```

Official attachment types: `image`, `video`, `audio`, `file`, `sticker`,
`contact`, `inline_keyboard`, `share`, `location`.

The adapter downloads inbound media via `payload.url` and maps it to internal
media types (`image`, `audio`/`voice`, `document`) — see `_extract_inbound_media`
and `_attachment_kind` in `adapter.py`.

## Callback Data Format

### message_callback structure

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

Button data is in `callback.payload` (the adapter also accepts `callback.data`);
the user who pressed it is `callback.user.user_id`.

### Chat ID for callbacks

**IMPORTANT:** for callback updates the chat_id is in
`message.recipient.chat_id`, NOT in `chat.chat_id`.

```python
# Correct
chat_id = message.get("recipient", {}).get("chat_id")

# Incorrect
chat_id = chat.get("chat_id")
```

### callback_data prefixes (adapter implementation)

`_on_callback` splits `callback.payload` on the prefix up to the first `:`:

| Prefix | Format | Purpose |
|--------|--------|---------|
| `exec` | `exec:{choice}:{approval_id}` | Dangerous-command approval (`once` / `session` / `always` / `deny`) |
| `sc` | `sc:{choice}:{confirm_id}` | Slash-command confirmation (`once` / `always` / `cancel`) |
| `clarify` | `clarify:{clarify_id}:{index}`, `clarify:{clarify_id}:other` | Clarify choice (free-text input for `other`) |
| `model` | `model:provider:{slug}`, `model:pick:{model}:{provider}`, `model:page:{provider}:{page}`, `model:back` | Model picker |

An unknown prefix is logged and ignored (returns `None`).

## Upload API

Uploading a media file takes two steps: get an upload URL, then push the file to
it. The attachment token comes from step 1 (audio/video) or from the CDN response
(image/file).

### Step 1: Get the upload URL

```bash
curl -X POST "https://platform-api.max.ru/uploads?type=image" \
  -H "Authorization: {access_token}"
```

Response:

```json
{
  "url": "https://iu.oneme.ru/upload.do?params=abc123"
}
```

For `type=audio` and `type=video` the response also contains the token right
away:

```json
{
  "url": "https://omu.okcdn.ru/upload.do?params=abc123",
  "token": "cdn_token_abc123"
}
```

Allowed `type` values: `image`, `video`, `audio`, `file` (`type=photo` is no
longer supported). The host in `url` depends on the file type:
`file` → `fu.oneme.ru`, `image` → `iu.oneme.ru`, `video` → `omub.okcdn.ru`,
`audio` → `omu.okcdn.ru`.

### Step 2: Upload the file (multipart POST)

```bash
curl -X POST "https://iu.oneme.ru/upload.do?params=abc123" \
  -H "Content-Type: multipart/form-data" \
  -F "data=@picture.jpg"
```

The file is sent as a multipart form with the `data` field — that is a `POST`,
not a binary `PUT`. The CDN response for `image`/`file`:

```json
{
  "token": "cdn_token_abc123"
}
```

### Step 3: Send a message with the attachment

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

While the CDN is still processing the file, `POST /messages` may return
`{"code": "attachment.not.ready", "message": "..."}` — the adapter retries the
send (2/4/6 s delays).

### SSRF Protection

The plugin checks the upload URL host against `_ALLOWED_UPLOAD_HOSTS`
(plus the `.max.ru`, `.oneme.ru`, `.okcdn.ru` suffixes):

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
2. If a paragraph > 4000 chars — split by words
3. Assemble chunks ≤ 4000 chars
4. Send sequentially

### Response Format

```bash
curl -X POST "https://platform-api.max.ru/messages?chat_id=95825064" \
  -H "Authorization: {access_token}" \
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

Editing goes through `PUT /messages` with the `message_id` query parameter (not
`chat_id`, and not `mid` in the body):

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

### Register Commands

The plugin automatically registers 20 commands via `PATCH /me/commands` on
startup.

**Check registered commands:**

```bash
curl -H "Authorization: {access_token}" \
  https://platform-api.max.ru/me/commands
```

### Limitations

- Maximum **32 commands** (Telegram: 100)
- Registration errors are not critical — the bot works without commands

## Executable examples (mocked)

The examples below run in `tests/test_docs_api_examples.py` on
`httpx.MockTransport`: the adapter code is real, the network is mocked.

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

`edit_message` is asserted through the `message_id` query parameter, and the
callback example feeds the `message_callback` fixture from this file into
`adapter._on_callback`.
