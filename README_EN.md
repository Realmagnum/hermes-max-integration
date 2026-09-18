# Hermes MAX Gateway

> **⚠️ Bilingual Project:** The primary documentation language is **Russian**. English translation is in `README_EN.md`. When modifying this file, **always** sync changes with `README.md`.

**Hermes Agent gateway plugin for MAX messenger (max.ru).**  
Voice transcription (STT by the Hermes core), interactive buttons (model picker, approval, clarify), table-as-image rendering (PNG with colored icons), streaming responses, file upload, access control.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Hermes](https://img.shields.io/badge/Hermes-Agent-8A2BE2)](https://hermes-agent.nousresearch.com/docs)

---

## Features

| Feature | Description |
|---------|-------------|
| 🟣 **Max Messenger** | Full gateway integration with max.ru |
| 📡 **Dual Mode** | Long polling (`GET /updates`) + Webhook (`POST /max/webhook`) |
| 🎤 **STT Voice** | Auto-download voice → transcription by the Hermes core (core STT) |
| 🖼️ **Tables as Images** | Render markdown tables as PNGs with colored status icons |
| 📝 **Streaming** | `edit_message` via `PUT /messages` for live token streaming |
| 🔘 **Interactive Buttons** | callback + link + message + request_contact/geo + model picker/approval/clarify |
| 🔗 **Link Buttons** | Link buttons in messages (`send_buttons()` with the `link` type) |
| 👁️ **send_action** | Extended statuses: typing, sending_photo/video/audio/file, read, typing_off |
| ✂️ **Auto-chunking** | Smart 4000-char message splitting preserving paragraphs |
| ⬆️ **File Upload** | Two-step upload: `POST /uploads` → PUT → token → send |
| 🔒 **Access Control** | Per-user allowlist, group policies, webhook secret verification |
| 📎 **Media** | Recursive attachment extraction, image/document/audio caching |
| 🎞️ **Voice/Video/Docs** | Dedicated `send_voice`, `send_video`, `send_document` methods |
| ⚡ **Typing Indicator** | Shows "user is typing" for all chat types |
| 🔧 **Standalone Sender** | Cron/send_message via `_standalone_send` with native file delivery. `hermes send "text MEDIA:/file"` works without core mod |
| 🌐 **Cross-Platform Sessions** | `/sessions` lists sessions from ALL platforms, `/resume <id>` switches to any of them. Enabled by default (`MAX_CROSS_SESSION=true`) |
| 🧪 **Tested** | pytest + pytest-asyncio, **126 tests** |
| 🔧 **Interactive Setup** | `hermes gateway setup` with prompts |
| 📋 **Slash Commands** | 20 commands (`/start`, `/new`, `/status`, `/model`, `/resume`, `/sessions`, `/help`, `/stop`, `/config`, `/restart`, `/retry`, `/undo`, `/title`, `/branch`, `/compress`, `/rollback`, `/background`, `/agents`, `/queue`, `/topic`) via MAX API `PATCH /me/commands` |

## MAX Slash Commands

The bot supports **20 slash commands**, registered via MAX Bot API (`PATCH /me/commands`). Analogous to Telegram `setMyCommands`.

### Core Commands

| Command | Description |
|---------|-------------|
| `/start` | Start the bot |
| `/new` | New session (alias: `/reset`) |
| `/status` | Session status |
| `/model` | Select model |
| `/resume` | Resume session |
| `/sessions` | List sessions |
| `/help` | Help |
| `/stop` | Stop processes |
| `/config` | Configuration |
| `/restart` | Restart gateway |

### Advanced Commands

| Command | Description |
|---------|-------------|
| `/retry` | Retry last message |
| `/undo [N]` | Undo N turns (default 1) |
| `/title [name]` | Set session title |
| `/branch [name]` | Branch session (alias: `/fork`) |
| `/compress` | Compress context (alias: `/compact`) |
| `/rollback [number]` | List or restore checkpoints |
| `/background <prompt>` | Run in background (alias: `/bg`, `/btw`) |
| `/agents` | Active agents and tasks (alias: `/tasks`) |
| `/queue <prompt>` | Queue prompts (alias: `/q`) |
| `/topic [off\|help\|session-id]` | Telegram DM topics |

### MAX Limitations

- Maximum **32 commands** (Telegram: 100)
- Commands are registered automatically on plugin start
- Registration failures are non-fatal — bot works without commands

### Example

```bash
# Check registered commands via API
curl -H "Authorization: $MAX_BOT_TOKEN" \
  https://platform-api2.max.ru/me/commands
```

## Tables as Images in Action

**Without** `MAX_TABLE_AS_IMAGE` (text fallback):
```
`-------------------------`
`| Server   | Status     |`
`| web-01   | ✓ Done     |`
`| db-main  | ✗ Failed   |`
`-------------------------`
```

**With** `MAX_TABLE_AS_IMAGE=true` (PNG image, ~13KB):

![Example table image](assets/table_sample.png)

Each status cell gets a colored icon: ✓ green, ✗ red, ⚠ orange, ◷ amber, ▶ blue.

### Use Cases

| Scenario | Before | After |
|----------|--------|-------|
| 📊 **Monitoring dashboard** | Raw pipe text | Clean table with status icons |
| 📋 **Task list** | Hard to read | Clear columns with priorities |
| 🏗️ **CI/CD pipeline** | Broken layout | PNG with stages ready to share |
| 📈 **Reports** | Collapsed columns | Well-formatted table image |
| 👥 **Team projects** | Visual noise | Color-coded progress table |

### Why images instead of native tables?

**Telegram** supports markdown tables natively — just send `| A | B |` with `format=markdown`, and the client renders columns, borders, and alignment automatically.

**MAX** does not support tables in markdown. The supported formatting is limited to `*italic*`, `**bold**`, `` `code` ``, `[links](url)`, `# headings`, `> quotes`. Pipe syntax (`| A | B |`) and fenced code blocks (`` ``` ``) are not in the supported list.

We tried several approaches before settling on PNG:

| Attempt | Result |
|---------|--------|
| `` ``` `` fenced code block | MAX doesn't support it — fences rendered as literal text |
| `<pre>` HTML tag | Only works in HTML mode, which breaks markdown in the rest of the message |
| inline `` `code` `` | Works as a fallback, but no borders or alignment |
| Plain text with `\|` and `---` | Readable but looks messy without monospace |
| **Pillow PNG** ✅ | **Full control: colors, borders, icons, fonts** |

**Bottom line:** PNG images deliver what Telegram provides natively — clean tables with colored status badges. Bonus: images can be forwarded and don't depend on the client's markdown parser. Trade-off: cell text is not copyable.

## Comparison with Upstream

| | Upstream (vladimiraldushin) | This plugin |
|---|---|---|
| Architecture | Plugin ✅ | Plugin ✅ |
| Long Polling | ❌ Webhook only | ✅ Both modes |
| STT Voice | ❌ | ✅ Hermes core |
| Streaming (edit_message) | ❌ | ✅ |
| **Tables as Images (PNG)** | ❌ | ✅ **Unique** |
| **Interactive Buttons** | ❌ | ✅ model picker, approval, clarify |
| File upload | ❌ | ✅ Two-step |
| Message chunking | ✅ | ✅ Improved |
| Media extraction | ✅ | ✅ Extended |
| Message dedup | ❌ | ✅ 300s window |
| Tests | ✅ Basic | ✅ 94 tests |
| Interactive setup | ✅ | ✅ + tables |

## Architecture

```
┌─────────┐     Long Polling / Webhook     ┌─────────────────┐
│  MAX    │ ──────────────────────────────→ │  MaxAdapter     │
│  Client │                                  │  (adapter.py)   │
│  (bot)  │ ←────────────────────────────── │     ↓           │
└─────────┘     POST /messages (text/PNG)  │  ┌───────────┐  │
                                            │  │ send()    │  │
                                            │  │  ↓        │  │
                                            │  │ tables?   │──┼── MAX_TABLE_AS_IMAGE=true
                                            │  │  ↓   ↓    │  │    → Playwright(HTML→PNG) or Pillow → PNG
                                            │  │ text  PN  │  │    → POST /uploads
                                            │  │       G   │  │    → PUT → token
                                            │  └───────────┘  │    → POST /messages
                                            │  ┌───────────┐  │
                                            │  │ STT (core) │──┼── core STT (config.yaml)
                                            │  └───────────┘  │
                                            └─────────────────┘
```

## Quick Start

### 1. Install

```bash
hermes plugins install Realmagnum/hermes-max-integration --enable
```

> **Source.** The primary development repository is Gitea:
> <https://gitea.rmg7.com/agent/hermes-max-integration>. The `owner/repo` shorthand
> resolves **only** to GitHub, so the command above clones
> <https://github.com/Realmagnum/hermes-max-integration>. Verified 2026-09-16: the
> public GitHub repository exists and its `main` = `b004c573` (matches the audit
> base); Gitea↔GitHub mirroring was not verified — do not assume it. To install
> straight from Gitea, pass the full Git URL (host reachability depends on your
> network): `hermes plugins install https://gitea.rmg7.com/agent/hermes-max-integration.git --enable`

### 2. Get a bot token

Register at https://business.max.ru/self (requires Russian legal entity / sole proprietor).
Create a bot → pass moderation → **Чат-боты → Перейти → Расширенные настройки → Настроить** → copy token.

### 3. Configure

```bash
hermes gateway setup
# Choose: Max
```

Or manually in `~/.hermes/.env`:

```bash
MAX_BOT_TOKEN=your_token_here
MAX_ALLOWED_USERS=your_max_user_id
```

### 4. Enable table images (optional)

The recommended renderer is **HTML→PNG via Playwright/Chromium** (clean tables,
native emoji, no cell overflow). Without a browser the plugin automatically
falls back to classic Pillow rendering.

> **Important:** install dependencies into the same Python the Hermes gateway
> runs in (its venv), otherwise the package won't reach the plugin runtime.
> Windows: `%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe`.

> **Prerequisites.** The scripts run from the plugin directory, and `python`/`pip`
> must come from the gateway's venv (otherwise the package won't reach the plugin
> runtime). The install directory follows the Hermes profile:
> `$HERMES_HOME/plugins/max-platform` (default `~/.hermes/plugins/max-platform`).
> Resolve the interpreter from the `hermes` shebang.

```bash
# Plugin directory (active Hermes profile) and the interpreter of its venv:
cd "${HERMES_HOME:-$HOME/.hermes}/plugins/max-platform"
HERMES_PY="$(head -1 "$(command -v hermes)" | sed 's|^#!||')"

# Variant A (recommended): HTML→PNG via Playwright.
#   Uses system Chrome/Chromium (channel="chrome") or downloads bundled:
"$HERMES_PY" -m pip install 'playwright>=1.40'
"$HERMES_PY" -m playwright install chromium    # ~115 MB, one-time; or install Chrome/Chromium manually

# Idempotent helper script instead of manual commands (installs only what's missing):
"$HERMES_PY" scripts/setup-playwright.py --check-only   # diagnostics (exit 1 if anything missing)
"$HERMES_PY" scripts/setup-playwright.py               # install what's missing

# Variant B (fallback): classic rendering via Pillow
"$HERMES_PY" -m pip install Pillow

echo 'MAX_TABLE_AS_IMAGE=true' >> ~/.hermes/.env
```

**Auto-install (optional):** with `MAX_AUTO_INSTALL_PLAYWRIGHT=true` the plugin
installs the package and Chromium itself on the first table render (takes 1–2
minutes and requires network access; subsequent renders work as usual).

### 5. Restart

```bash
hermes gateway restart
```

## Connection Modes

The plugin supports two modes for receiving messages from MAX API. The mode is determined by a single variable — **`MAX_WEBHOOK_URL`**:

| `MAX_WEBHOOK_URL` | Mode | Mechanism |
|---|---|---|
| Not set (empty) | **Long polling** (default) | Cyclic `GET /updates?timeout=5&marker=...` |
| HTTPS URL set | **Webhook** | aiohttp server on port 8646, `POST /subscriptions` registration |

The choice happens in `connect()` with one line: `self._use_webhook = bool(self._webhook_url)`.

### Switching Long polling → Webhook

```bash
# 1. Add to ~/.hermes/.env
MAX_WEBHOOK_URL=https://your-domain.com/max/webhook
MAX_WEBHOOK_SECRET=my-secret

# 2. Restart
sudo systemctl restart hermes-gateway
```

On startup: `_start_webhook()` → opens `0.0.0.0:8646` → registers a subscription in MAX API → messages arrive via webhook.

### Switching Webhook → Long polling

```bash
# 1. Remove or comment out MAX_WEBHOOK_URL (and MAX_WEBHOOK_SECRET)
# MAX_WEBHOOK_URL=...
# MAX_WEBHOOK_SECRET=...

# 2. Restart
sudo systemctl restart hermes-gateway
```

On startup: `_start_polling()` → checks `GET /subscriptions`, **automatically removes** stale webhook subscriptions (otherwise MAX would keep sending to a dead URL) → starts `_poll_loop`.

### 🚨 Important

If a webhook subscription was registered **manually** (via curl, not through the plugin), auto-cleanup may not find it. In that case, delete it manually:

```bash
curl -X DELETE "https://platform-api.max.ru/subscriptions?url=<URL>" \
  -H "Authorization: $MAX_BOT_TOKEN"
```

Check active subscriptions: `GET /subscriptions` with the same token.

### 💬 Reasoning display (model thinking)

When using reasoning models (DeepSeek R1, Claude Opus, Gemini Thinking, etc.), the reasoning block (`💭 **Reasoning:**`) is automatically prepended to the final response.

To ensure reasoning appears as a **fresh separate message** (rather than an edit of the last streamed draft), add to `~/.hermes/config.yaml`:

```yaml
display:
  platforms:
    max:
      fresh_final_after_seconds: 10
```

This tells the gateway to deliver the final answer as a new message if streaming lasted longer than 10 seconds — the reasoning block is included in full. Without this setting, reasoning is prepended to the last streaming edit and may go unnoticed.

### 🔍 Diagnostics

For a quick health check, run the diagnostics script (located in `scripts/diagnose.sh`). It auto-detects the current mode (webhook or long polling) and adapts the checks:

```bash
cd "${HERMES_HOME:-$HOME/.hermes}/plugins/max-platform"   # plugin directory (active profile)

# Basic check (no test message)
./scripts/diagnose.sh

# Full check with E2E send (delivers a message to the home channel)
./scripts/diagnose.sh --send
```

The script checks 8 items: plugin status, MAX connection, activity (polling or webhook), health/errors, subscriptions, token, E2E send, and reasoning config. Exit code: `0` — all good, `1` — issues found.

## Configuration Reference

| Env Variable | Required | Default | Description |
|-------------|----------|---------|-------------|
| `MAX_BOT_TOKEN` | ✅ | — | Bot token from Max Platform |
| `MAX_API_BASE` | ❌ | `https://platform-api.max.ru` | API base URL (docs now recommend `https://platform-api2.max.ru`) |
| `MAX_WEBHOOK_HOST` | ❌ | `0.0.0.0` | Webhook bind host |
| `MAX_WEBHOOK_PORT` | ❌ | `8646` | Webhook bind port |
| `MAX_WEBHOOK_PATH` | ❌ | `/max/webhook` | Webhook URL path |
| `MAX_WEBHOOK_SECRET` | ❌ | — | Secret for X-Max-Bot-Api-Secret |
| `MAX_WEBHOOK_URL` | ❌ | — | Public HTTPS URL (enables webhook mode) |
| `MAX_ALLOWED_USERS` | ❌ | — | Comma-separated user IDs |
| `MAX_ALLOW_ALL_USERS` | ❌ | `false` | Allow all users |
| `MAX_GROUP_ALLOWED_USERS` | ❌ | — | User IDs allowed to interact in group chats |
| `MAX_GROUP_ALLOWED_CHATS` | ❌ | — | Chat group IDs where bot is allowed |
| `MAX_TABLE_AS_IMAGE` | ❌ | `false` | Render tables as PNG images (HTML→PNG via Playwright, Pillow fallback) |
| `MAX_AUTO_INSTALL_PLAYWRIGHT` | ❌ | `false` | Auto-install Playwright + Chromium on first table render (needs network, 1–2 min) |
| `MAX_HOME_CHANNEL` | ❌ | — | Default cron/send_message target |
| `MAX_HOME_CHANNEL_NAME` | ❌ | — | Default channel name |
| `MAX_INSECURE_SSL` | ❌ | `false` | Disable SSL verification (testing only) |
| `MAX_CROSS_SESSION` | ❌ | `true` | Cross-platform `/sessions` and `/resume` (see below) |

## Table Image Symbol Reference

| Input Emoji | Rendered As | Meaning | Color |
|------------|-------------|---------|-------|
| ✅ | ✓ | Done | `#16a34a` |
| ❌ | ✗ | Failed / Error | `#dc2626` |
| ⚠️ | ⚠ | In review / Warning | `#ea580c` |
| ⏳ / ⌛ | ◷ | Pending | `#ca8a04` |
| ⏳ + "scheduled" | ▶ | Scheduled | `#3b82f6` |
| 🔴 | ● | Critical (red) | `#dc2626` |
| 🟢 | ● | Good (green) | `#16a34a` |
| 🟡 | ● | Mid (yellow) | `#ca8a04` |

Falls back to inline `` `code` `` text if neither Playwright/Chromium nor Pillow is installed.

---

## 🌐 Cross-Platform Sessions

**Why:** by default the Hermes core shows sessions only within a single platform — from MAX you see MAX sessions only. That is correct for multi-tenant setups, but inconvenient when one user works across several platforms.

**How it works:** the adapter intercepts `/sessions` and `/resume` before the core, queries `SessionDB` without a platform filter and formats the response.

| Command | Action | Example output |
|---------|--------|----------------|
| `/sessions` | Last 15 sessions from all platforms | `1. 💻 cli — Zabbix deploy...` |
| `/sessions search <q>` | Search across all sessions | `🔍 Sessions matching "traefik"` |
| `/resume <id>` | Switch to any session | (switches without an error) |

**Requirement:** for `/resume --all` add `max` to `platforms:` in config.yaml:
```yaml
platforms:
  max:
    extra:
      allow_admin_from:
        - "95825064"  # your MAX user_id
```

**Disabling:** `MAX_CROSS_SESSION=false` in `.env` — restores the default core behaviour (MAX sessions only).

---

## 👁️ send_action — Extended Statuses

`send_typing()` now delegates to `send_action()`, which supports all MAX API statuses:

| Method | action | MAX API | Description |
|--------|--------|---------|-------------|
| `send_typing()` | `typing` | `typing_on` | Typing (default) |
| `send_action(cid, "typing_off")` | `typing_off` | `typing_off` | Hide the indicator |
| `send_action(cid, "sending_photo")` | `sending_photo` | `sending_photo` | Sending a photo |
| `send_action(cid, "sending_video")` | `sending_video` | `sending_video` | Sending a video |
| `send_action(cid, "sending_audio")` | `sending_audio` | `sending_audio` | Sending audio |
| `send_action(cid, "sending_file")` | `sending_file` | `sending_file` | Sending a file |
| `send_action(cid, "read")` | `read` | `read` | Mark as read |

```python
await adapter.send_action("chat:123", "sending_file")
```

## 🔗 Link Buttons and send_buttons()

New public method `send_buttons()` — send messages with inline buttons of any type:

```python
await adapter.send_buttons(
    chat_id="chat:123",
    text="Choose an action:",
    buttons=[
        {"type": "link", "text": "🌐 Open website", "url": "https://example.com"},
        {"type": "callback", "text": "✅ Confirm", "payload": "confirm:123"},
        {"type": "request_contact", "text": "📞 Share phone number"},
    ],
)
```

Supported button types:

| type | Parameters | Description |
|------|-----------|-------------|
| `callback` | `text`, `payload` (+ optional `label`) | Inline callback with payload |
| `link` | `text`, `url` (+ optional `label`) | Opens a URL |
| `message` | `text`, `payload` (+ optional `label`) | Sends a pre-filled message |
| `request_contact` | `text` (+ optional `label`) | Requests a contact |
| `request_geo_location` | `text` (+ optional `label`) | Requests a geolocation |

Each button occupies its own row (message width). The standard MAX limit is up to 10 buttons per message.

With 3+ buttons they are numbered automatically (`1.`, `2.`, `3.`...) both in the message body and on the buttons themselves.

The optional `label` field holds the **full description text** for the fallback in the message body — unlike `text` (which goes on the button and may be truncated by MAX on mobile devices). If `label` is omitted, `text` is used.

```python
# text — short (on the button), label — full (in the description)
{"type": "callback", "text": "Basic", "label": "Basic — 500₽/mo, 10GB", "payload": "basic"}
```

If you need several buttons in one row, use `_post_interactive()` directly with a ready-made row structure.

---

## 📎 Native File Delivery (standalone sender)

The plugin can send files via `hermes send` without a running gateway:

```bash
# Text + file (works without core modification)
hermes send --to max:USER_ID "📄 Report MEDIA:/path/to/report.pdf"

# Multiple files
hermes send --to max:USER_ID "📦 Files: MEDIA:/tmp/a.pdf MEDIA:/tmp/b.xlsx"

# MEDIA-only (requires optional core patch — see below)
```

**How it works:**

1. Core extracts `MEDIA:` paths → `media_files: List[Tuple[str, bool]]`
2. Text is sent as a separate `POST /messages`
3. For each file:
    - `POST /uploads?type=file` → CDN upload URL
    - Multipart POST to CDN → file token
    - `POST /messages` with `attachments: [{"type": "file", "payload": {"token": token}}]`

All files use `type=file` — MAX CDN does not validate content, guaranteeing delivery for any safe extension (.txt, .md, .png, .jpg, .mp3, .pdf, .doc, .xlsx, etc.).

⚠️ **MAX CDN limitation:** Extensions `.exe`, `.apk`, `.bat`, `.msi` and other potentially dangerous types are rejected by MAX CDN (HTTP 415 — "File extension is forbidden"). This is a platform limitation, not addressable from the plugin.

For **in-session** file delivery (via gateway), use `send_image_file()`, `send_document()`, `send_voice()`, `send_video()` — these use the adapter with retry on `attachment.not.ready`.

### Optional: MEDIA-only core support

By default `hermes send "MEDIA:/file"` (no text) is blocked by core:

```
send_message MEDIA delivery is currently only supported for telegram, discord...
```

Fix with the optional script that adds MAX to the supported platform list in `tools/send_message_tool.py`:

```bash
cd "${HERMES_HOME:-$HOME/.hermes}/plugins/max-platform"   # plugin directory
HERMES_PY="$(head -1 "$(command -v hermes)" | sed 's|^#!||')"  # gateway venv interpreter
"$HERMES_PY" scripts/apply-core-fix.py          # apply
"$HERMES_PY" scripts/apply-core-fix.py --revert # revert
```

After applying:
```bash
hermes send --to max:USER_ID "MEDIA:/tmp/image.png"      # ✅ works
hermes send --to max:USER_ID "text MEDIA:/file.pdf"       # ✅ already worked
```

## Documentation

- [Setup](docs/setup_EN.md) — .env, webhook, security, deployment
- [Features](docs/features_EN.md) — STT, tables, streaming, buttons, files
- [API](docs/api_EN.md) — MAX API formats, callbacks, file upload
- [Troubleshooting](docs/troubleshooting_EN.md) — errors, diagnose.sh, logs

## Troubleshooting

### Bot not responding

```bash
hermes gateway status
curl -H "Authorization: ***" https://platform-api.max.ru/me
curl http://localhost:8646/health
```

### Tables not rendering as images

```bash
cd "${HERMES_HOME:-$HOME/.hermes}/plugins/max-platform"   # plugin directory
HERMES_PY="$(head -1 "$(command -v hermes)" | sed 's|^#!||')"  # gateway venv interpreter

# Check config
grep MAX_TABLE_AS_IMAGE ~/.hermes/.env

# Renderer diagnostics: playwright package + Chromium present?
"$HERMES_PY" scripts/setup-playwright.py --check-only
#   MISSING → "$HERMES_PY" scripts/setup-playwright.py  (installs what's missing)
#   or manually: "$HERMES_PY" -m pip install 'playwright>=1.40'
#                "$HERMES_PY" -m playwright install chromium

# Check Pillow (fallback renderer)
"$HERMES_PY" -m pip list | grep -i pillow

# Check logs
grep -i "table\|upload\|playwright\|pillow" ~/.hermes/logs/gateway.log
```

### SSL errors with Max API

Max uses Russian MinCifry CA certificates. For testing: `MAX_INSECURE_SSL=true`

### Voice not transcribing

STT is performed by the **Hermes core** (not the plugin). Check:

```bash
# 1. stt section in the core config (provider, language)
grep -A4 "^stt:" ~/.hermes/config.yaml
# 2. STT category in the interactive tools
hermes tools
```

For Russian, set in `config.yaml`:

```yaml
stt:
  enabled: true
  language: ru      # core default is "en"
  provider: local   # or openai (gpt-transcribe), groq, xai...
```

> The plugin adapter downloads and caches audio; the core transcribes it. On first use of the `local` provider the model (~150 MB) is downloaded automatically.

## Project Structure

```
hermes-max-integration/
├── plugin.yaml              # Hermes plugin metadata
├── __init__.py              # register() entry point
├── pyproject.toml           # Python package config
├── adapter.py               # MaxAdapter (~2600 lines)
├── mixins/                  # Adapter layers: buttons, sessions, webhook, media, tables
├── scripts/                 # apply-core-fix.py, check_docs_links.py, diagnose.sh,
│                            #   release.sh, setup-playwright.py
├── skills/max-gateway/      # SKILL.md + SKILL_EN.md (agent skill)
├── tests/                   # pytest: 126 tests
├── docs/                    # api.md, features.md, setup.md, troubleshooting.md (+ _EN)
├── AGENTS.md                # Instructions for AI agents
├── after-install.md         # Post-install guide
├── cliff.toml               # git-cliff config (EN)
├── cliff-ru.toml            # git-cliff config (RU)
├── README.md                # Russian version
└── .github/workflows/ci.yml # CI/CD
```

**Note:** generated table PNGs are cached in `~/.hermes/table_images/`; the cache
key includes the renderer engine (Playwright/Pillow), so switching engines never
serves stale images.

## Security

| Measure | Detail |
|---------|--------|
| 🛡️ **SSRF Protection** | Upload URLs validated against `*.max.ru` / `*.oneme.ru` whitelist |
| 🔐 **Token Safety** | `Authorization` header never forwarded on HTTP redirects |
| 🔑 **Webhook Secret** | Constant-time comparison via `secrets.compare_digest` |
| 🔊 **Voice Privacy** | Audio cache stored with `0700` permissions |
| 🧹 **Error Sanitization** | Tokens/URLs stripped from error messages |
| 🔍 **CI Hardening** | `bandit` SAST + `pip-audit` on every push |

Full audit and fixes: commit `e87ee64`.

## Project History

The project evolved in two stages.

**The first version** was written from scratch for a specific goal: bridging Hermes Agent with the MAX messenger. It introduced voice transcription, two-step file uploads, interactive buttons, and response streaming — features that no other MAX plugin had at the time.

**Later**, a more mature project — [vladimiraldushin/hermes-max-platform](https://github.com/vladimiraldushin/hermes-max-platform) — came to our attention, with well-thought-out plugin architecture, webhooks, and tests. Rather than maintaining two parallel branches, we decided to rework the plugin on top of this foundation:

- Architecture, subscriptions (webhook/long polling), update system — from upstream
- All features from the first version (STT, table images, buttons, streaming, file uploads) — ported and extended
- On top of that, capabilities found in neither original branch: PNG table rendering, improved model picker, standalone cron sender, group policies

**The result** is a hybrid: a solid upstream foundation combined with unique functionality found nowhere else.

## License

MIT — see [LICENSE](LICENSE)

## Credits

- [vladimiraldushin/hermes-max-platform](https://github.com/vladimiraldushin/hermes-max-platform) — architecture base for v2.0 (subscriptions, webhooks, plugin structure)
- Original v1.0 development — Realmagnum (STT, table images, buttons, streaming, file upload)
- [Hermes Agent](https://hermes-agent.nousresearch.com/docs) — the agent framework
