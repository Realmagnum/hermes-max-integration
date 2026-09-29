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

Markdown tables (`| A | B |\n|---|---|`) rendered as PNG images.
Primary renderer is **HTML→PNG via Playwright/Chromium** (fixed layout, native
emoji, no cell overflow); if the package or browser is unavailable it falls back
to classic Pillow rendering.

**Render algorithm (v6):**

1. **Playwright (HTML→PNG):** table → HTML → screenshot via Chromium
   (system Chrome when available, bundled otherwise)
2. **Pillow (fallback):** parse markdown segments (`**bold**`, `*italic*`,
   `` `code` ``), measure each cell via `draw.textlength()`, soft-wrap with
   styles, draw with colored status icons
3. PNG cache: the key includes the table text **and** the renderer engine —
   switching engines never serves stale images

### Parameters

| Parameter | Value | Description |
|-----------|-------|-------------|
| `MAX_TABLE_AS_IMAGE` | `false` | Enable PNG render |
| `MAX_AUTO_INSTALL_PLAYWRIGHT` | `false` | Auto-install Playwright + Chromium on first render |
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

**Pillow/Playwright not installed:**
```bash
python scripts/setup-playwright.py          # installs playwright + Chromium
python -m pip install Pillow                # fallback renderer
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

There is no public `adapter.clarify()` method. The core calls the adapter through
`send_clarify`, and the user's answer arrives as a callback with the prefix
`clarify:{clarify_id}:{index|other}`.

**Sending the question:**

```python
result = await adapter.send_clarify(
    chat_id="chat:123",
    question="Which server?",
    choices=["web-01", "db-main"],   # None → the question is sent as plain text
    clarify_id="clr-42",
    session_key="telegram:42",
)
```

**Answer (callback):** `clarify:clr-42:0`, `clarify:clr-42:1`, …,
`clarify:clr-42:other` (the last one puts the session into free-text input
mode). Handler — `_handle_clarify_callback`. Dangerous-command approval is a
separate `exec` prefix, slash-command confirmation is `sc` (full table in
`docs/api.md`).

## File Upload

### Two-step Upload

1. `POST /uploads?type=image` → get the upload URL (`url` field) and, for
   audio/video, the `token` right away
2. `POST <url>` as a multipart form with the `data` field → get the `token`
   (for image/file)
3. `POST /messages` with `attachments: [{type: "image", payload: {token: "..."}}]`

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

`_upload_send(chat_id, path, type, ...)` passes a MAX attachment type, not the
method name: `send_voice()` sends `type=audio`, `send_document()` sends
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
