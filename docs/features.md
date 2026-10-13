# Features

## STT (Voice Transcription)

### How it works

Voice messages from MAX come as audio attachments with `payload.url` for direct download. The adapter automatically:

1. Downloads audio file to `$HERMES_HOME/cache/audio/` (`~/.hermes/cache/audio/`)
2. Forwards audio file to Hermes Core
3. Core transcribes audio (Core STT) and appends text to message

### Setup

Transcription is performed by **Hermes Core** (≥ 0.21.4). Configuration lives in the core `config.yaml`:

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
    "platform-api2.max.ru",
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
3. **Time Formatting:** uses `Intl.DateTimeFormat` with the user's Desktop locale.
4. **Theme Integration:** seamlessly inherits the active Hermes theme variables, badges, and card styling.

The sessions page, notifications and statusbar use plugin-scoped English/Russian locale bundles through the public Desktop SDK. English is the default and fallback for other languages; dates retain the user's selected locale. When `ctx.i18n.onLocaleChange` is available, palette labels also refresh on language changes. Older SDKs keep palette labels in the language active at registration until the plugin reloads; the page and statusbar remain reactive. Verified against the public SDK on 2026-10-13: [Hermes 0.21.4](https://github.com/NousResearch/hermes-agent/blob/v2026.9.21/apps/desktop/src/i18n/plugin-i18n.ts) lacks this subscription, while [Hermes 0.21.5](https://github.com/NousResearch/hermes-agent/blob/v2026.9.24/apps/desktop/src/i18n/plugin-i18n.ts) provides it.

### Localization acceptance and host limitation

**CAT-01 / MS-006, checked 2026-10-14 against the installed Hermes Desktop source build:** application package version `0.0.0`, clean build commit `7157422022ff06f3e632d1dd394ee1253b17ad37`, build timestamp `2026-10-05T11:24:05.84Z`. The running application's `install-stamp.json` identifies that commit; the local Core checkout has the same SHA. A release number cannot be inferred from the package's `0.0.0` placeholder.

Visual acceptance recorded English/Russian page labels, buttons, dates and Cmd+K commands. Page/button strings use `usePluginI18n`; dates use `Intl.DateTimeFormat` with the selected locale. **The description in Capabilities → Plugins stays in English when the language changes**, because this MAX package provides English static descriptions. At the checked revision, the [runtime loader](https://github.com/NousResearch/hermes-agent/blob/7157422022ff06f3e632d1dd394ee1253b17ad37/apps/desktop/src/contrib/runtime-loader.ts#L459) copies `plugin.description` into the record, [package merging](https://github.com/NousResearch/hermes-agent/blob/7157422022ff06f3e632d1dd394ee1253b17ad37/apps/desktop/src/app/capabilities/plugins/plugin-packages.ts#L63) retains the agent manifest description with a Desktop-description fallback, and the [Plugins row](https://github.com/NousResearch/hermes-agent/blob/7157422022ff06f3e632d1dd394ee1253b17ad37/apps/desktop/src/app/capabilities/plugins/plugins-tab.tsx#L366) displays `pkg.description` directly. This path does not apply plugin i18n to descriptions.

This is a host metadata limitation at the recorded revision, not an unfinished MAX page translation. MS-006 remains accepted. Recheck the loader, package merging and row renderer when upgrading Desktop; this finding does not assert that every later version has the same limitation. The older-SDK palette reload condition above is a separate issue.

### Automatic Installation (Unified Package)

The desktop widget requires no separate installation:
- Hermes Core's Unified Package mechanism automatically copies and registers `desktop/plugin.js` into the desktop plugins directory.
- Updates to the plugin automatically synchronize the desktop UI component.
