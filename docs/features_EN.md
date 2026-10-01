# Features

## STT (Voice Transcription)

### How it works

Voice messages from MAX come as audio attachments with `payload.url` for direct download. The adapter automatically:

1. Downloads audio file to `$HERMES_HOME/cache/audio/` (`~/.hermes/cache/audio/`)
2. Forwards audio file to Hermes Core
3. Core transcribes audio (Core STT) and appends text to message

### Setup

Transcription is performed by **Hermes Core** (≥ 0.20.0). Configuration lives in the core `config.yaml`:

```yaml
stt:
  enabled: true
  language: ru      # core default is "en"
  provider: local   # or openai, groq, mistral, xai, elevenlabs
```

For interactive setup, use `hermes tools` (🎙️ Speech-to-Text category).

### Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `enabled` | `false` | Enable voice transcription in core |
| `language` | `en` | Transcription language (`ru` for Russian speech) |
| `provider` | `local` | STT provider (`local`, `openai`, `groq`, `mistral`, `xai`, `elevenlabs`) |

### Configuration Check

```bash
grep -A8 "^stt:" ~/.hermes/config.yaml
```

### Troubleshooting

**STT returns empty:**
- Check settings in `config.yaml`: `enabled: true`, `language: ru`
- Verify audio file downloaded by adapter: `ls -la ~/.hermes/cache/audio/`

**Local provider faster-whisper:**
- For `provider: local` install package into core environment: `pip install faster-whisper`
- Core transcription errors in logs: `grep -i "transcri" ~/.hermes/logs/gateway.log`

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

**Reasoning display:**

```yaml
# ~/.hermes/config.yaml
streaming:
  fresh_final_after_seconds: 10
```

> **Note:** The `streaming.fresh_final_after_seconds` key is read by the core from the `streaming:` section (not `display.platforms.max.*`) and applies only to Telegram. In MAX, reasoning is sent as part of the final message edit.

### Troubleshooting

**Reasoning not displayed:**
- Check model (fast models don't generate reasoning)
- Check gateway logs for streaming errors

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
      cross_session_users:
        - "95825064"  # your MAX user_id
```

Environment variable: `MAX_CROSS_SESSION_USERS="95825064"`.
Enable/disable: `MAX_CROSS_SESSION=false` in `.env` (default: `false`).

## Standalone Sender

`_standalone_send()` — send messages from cron/send_message without core modification.

```bash
hermes send "text MEDIA:/file"
```

Works via `_standalone_send` with native file delivery.

## Desktop UI Sessions Sidebar

### How it works

The plugin includes a native UI component for Hermes Desktop — `desktop/plugin.js` (ID: `max-sessions-sidebar`).
When the plugin is enabled, it automatically integrates into the left sidebar of Hermes Desktop.

### Sidebar Features

1. **Active MAX Dialogs List:** shows users and groups communicated with via MAX Bot API.
2. **Session Metrics:** displays message counts and total token consumption for each conversation.
3. **Time Formatting:** leverages localized Hermes time formatters (`fmtDateTime`, `fmtDayTime`, `relativeTime`).
4. **Theme Integration:** seamlessly inherits the active Hermes theme variables, badges, and card styling.

### Automatic Installation (Unified Package)

The desktop widget requires no separate installation:
- Hermes Core's Unified Package mechanism automatically copies and registers `desktop/plugin.js` into the desktop plugins directory.
- Updates to the plugin automatically synchronize the desktop UI component.
