# Features

## STT (Voice Transcription)

### How it works

Voice messages arrive from MAX as audio attachments with `payload.url`. The plugin only
downloads and caches the audio — **the Hermes core transcribes it** (≥ 0.20.0):

1. The adapter caches the audio in the core audio cache: `$HERMES_HOME/cache/audio/`
   (default `~/.hermes/cache/audio/`). The legacy `~/.hermes/audio_cache/` directory is
   used instead when it already holds files.
2. The core transcribes the file per the `stt` section of `config.yaml` (provider,
   language, model).
3. The transcript is prepended to the message the agent receives.
4. With `stt.echo_transcripts: true` (core default) the core also sends the raw transcript
   back to the chat as a separate `🎙️ "<text>"` message.

The plugin does not transcribe voice itself and holds no STT settings: the dedicated
stt-venv, `scripts/transcribe_audio.py`, `MAX_STT_ENABLED` and `MAX_STT_VENV` were removed
(STT moved into the core). All STT configuration lives in the Hermes core.

### Setup

```bash
# Interactively: the 🎙️ Speech-to-Text category
hermes tools
```

Or by hand in `~/.hermes/config.yaml`:

```yaml
stt:
  enabled: true
  language: ru        # core default is "en"; "" = auto-detect
  provider: local     # local | groq | openai | mistral | xai | elevenlabs | deepinfra
  echo_transcripts: true
  local:
    model: base       # tiny | base | small | medium | large-v3
```

When `provider` is unset, the core picks one automatically from the available keys
(`local` comes first in the ladder). For the `local` provider the faster-whisper package
and the model (`base` ≈ 150 MB) are installed/downloaded on first use.

### Parameters (core defaults)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `stt.enabled` | `true` | Auto-transcribe inbound voice messages |
| `stt.language` | `"en"` | Global language; `""` = auto-detect |
| `stt.provider` | unset | Provider; unset = autodetect from available keys |
| `stt.echo_transcripts` | `true` | Echo the transcript back as `🎙️ "..."` |
| `stt.local.model` | `base` | faster-whisper model |
| `stt.local.vad` | `true` | VAD filter (anti-hallucination on silence) |
| `stt.groq.model` | `whisper-large-v3-turbo` | Groq model |
| `stt.openai.model` | `whisper-1` | OpenAI model (`gpt-4o-transcribe`, `gpt-transcribe`, …) |
| `stt.mistral.model` | `voxtral-mini-latest` | Mistral model (not listed in `hermes tools`) |
| `stt.elevenlabs.model_id` | `scribe_v2` | ElevenLabs Scribe model |

Each provider also has its own `language` (`language_code` for ElevenLabs), which
overrides the global `stt.language`.

### Diagnostics

```bash
# 1. What the core is actually configured with
grep -A8 "^stt:" ~/.hermes/config.yaml

# 2. Audio download cache (empty → the attachment never got downloaded)
ls -la ~/.hermes/cache/audio/

# 3. What the core says
grep -i "transcri" ~/.hermes/logs/gateway.log | tail -20
```

Typical log lines:

- `Voice transcription failed for <path>: <error>` — the provider returned an error
  (missing key, network, quota, unsupported format).
- `Configured STT failed for <path>; recovered with local STT` — the local
  faster-whisper fallback took over.
- `[voice message could not be transcribed automatically; the audio is available at: …]` —
  no transcript; the agent sees the file path instead of text.
- An empty transcript means silence or a too-short clip (VAD trims silence).

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
