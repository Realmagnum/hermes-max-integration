# Features

## STT (Voice Transcription)

### How it works

Voice messages from MAX come as audio attachments with `payload.url` for direct download. The adapter automatically:

1. Downloads audio file to `~/.hermes/audio_cache/max_audio_{message_id}.ogg`
2. Transcribes via faster-whisper
3. Adds text to message

### Setup

```bash
# Create venv for faster-whisper
python3 -m venv ~/.hermes/stt-venv
~/.hermes/stt-venv/bin/pip install faster-whisper

# Copy script
cp scripts/transcribe_audio.py ~/.hermes/scripts/
```

### Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `MAX_STT_ENABLED` | `true` | Enable/disable STT |
| `MAX_STT_VENV` | `~/.hermes/stt-venv` | Venv path |
| Model | `base` | faster-whisper model |

### Transcription Script

```bash
~/.hermes/scripts/transcribe_audio.py /path/to/file.ogg
```

### Troubleshooting

**STT returns empty:**
- Check model: `ls ~/.hermes/stt-venv/lib/python*/site-packages/whisper/assets/`
- Verify file downloaded: `ls -la ~/.hermes/audio_cache/max_audio_*.ogg`

**Slow transcription:**
- Use `tiny` model instead of `base`
- Enable GPU: `export WHISPER_DEVICE=cuda:0`

## Table Images

### How it works

Markdown tables (`| A | B |\n|---|---|`) rendered as PNG images via Pillow.

**Render algorithm (v5):**

1. Parse markdown segments (`**bold**`, `*italic*`, `` `code` ``)
2. Measure each cell width via `draw.textlength()`
3. Soft-wrap text with styles
4. Draw with colored status icons

### Parameters

| Parameter | Value | Description |
|-----------|-------|-------------|
| `MAX_TABLE_AS_IMAGE` | `false` | Enable PNG render |
| `MAX_CELL_WIDTH` | `300px` | Max cell width |
| `MAX_TABLE_WIDTH` | `1200px` | Max table width |
| `CELL_PAD_X` | `22px` | Horizontal padding |
| `CELL_PAD_Y` | `14px` | Vertical padding |

### Status Icons

| Emoji | Unicode | Color | Meaning |
|-------|---------|-------|---------|
| ✅ | ✓ | `#16a34a` | Done |
| ❌ | ✗ | `#dc2626` | Failed |
| ⚠️ | ⚠ | `#ea580c` | Warning |
| ⏳ | ◷ | `#ca8a04` | Pending |
| ▶ | ▶ | `#2563eb` | In progress |

### Troubleshooting

**Pillow not installed:**
```bash
pip install Pillow
```

**Text truncated:**
- Increase `MAX_CELL_WIDTH`
- Check fonts: `fc-list | grep -i dejavu`

**Bad rendering:**
- Ensure `draw.textlength()` is used (not `wcswidth * 0.6`)
- Add 5px buffer to width

## Streaming

### How it works

Adapter uses `edit_message` via `PUT /messages` for real-time token output.

### Reasoning Display

When using reasoning models (DeepSeek R1, Claude Opus, Gemini Thinking), reasoning block added to final response.

**Display as separate message:**

```yaml
# ~/.hermes/config.yaml
display:
  platforms:
    max:
      fresh_final_after_seconds: 10
```

After 10 seconds of streaming, final response sent as new message (with reasoning inside).

### Troubleshooting

**Reasoning not displayed:**
- Check model (fast models don't generate reasoning)
- Check `fresh_final_after_seconds` in config.yaml

## Buttons

### send_buttons()

Public method for sending messages with inline buttons:

```python
await adapter.send_buttons(
    chat_id="chat:123",
    text="Choose action:",
    buttons=[
        {"type": "link", "text": "🌐 Site", "url": "https://example.com"},
        {"type": "callback", "text": "✅ Confirm", "payload": "confirm:123"},
        {"type": "request_contact", "text": "📞 Contact"},
    ],
)
```

### Button Types

| type | Parameters | Description |
|------|------------|-------------|
| `callback` | `text`, `payload` | Inline callback |
| `link` | `text`, `url` | Open URL |
| `message` | `text`, `payload` | Pre-filled message |
| `request_contact` | `text` | Request contact |
| `request_geo_location` | `text` | Request location |

### Model Picker

Interactive model selection with pagination (15 per page).

**Callback format:** `model:pick:{model}:{provider}`

**Pagination callbacks:** `model:page:{provider}:{page}`

### Confirm/Clarify

**Confirm:**
```python
result = await adapter.clarify(
    chat_id="chat:123",
    question="Confirm action?",
    options=["Yes", "No"],
)
```

**Clarify:**
```python
result = await adapter.clarify(
    chat_id="chat:123",
    question="Which server?",
    options=["web-01", "db-main"],
)
```

## File Upload

### Two-step Upload

1. `POST /uploads?type=image` → get upload URL
2. `PUT <upload_url>` → upload file
3. Get CDN token
4. `POST /messages` with `attachments: [{type: "image", payload: {token: "..."}}]`

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

### Send Methods

| Method | Type | Description |
|--------|------|-------------|
| `send_voice()` | voice | Voice message |
| `send_video()` | video | Video message |
| `send_document()` | document | Document |
| `send_image()` | image | Image (via CDN) |

## Cross-Platform Sessions

### How it works

Adapter intercepts `/sessions` and `/resume` before core, queries `SessionDB` without platform filter.

### Commands

| Command | Action |
|---------|--------|
| `/sessions` | Last 15 sessions from all platforms |
| `/sessions search <q>` | Search all sessions |
| `/resume <id>` | Switch to any session |

### Setup

```yaml
# ~/.hermes/config.yaml
platforms:
  max:
    extra:
      allow_admin_from:
        - "95825064"  # your MAX user_id
```

Disable: `MAX_CROSS_SESSION=false` in `.env`.

## Standalone Sender

`_standalone_send()` — send messages from cron/send_message without core modification.

```bash
hermes send "text MEDIA:/file"
```

Works via `_standalone_send` with native file delivery.
