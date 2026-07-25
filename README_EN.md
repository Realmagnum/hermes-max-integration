# Hermes MAX Gateway

> **⚠️ Bilingual Project:** The primary documentation language is **Russian**. English translation is in `README_EN.md`. When modifying this file, **always** sync changes with `README.md`.

**Hermes Agent gateway plugin for MAX messenger (max.ru).**  
Voice transcription (STT), interactive buttons (model picker, approval, clarify), table-as-image rendering (PNG with colored icons), streaming responses, file upload, access control.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Hermes](https://img.shields.io/badge/Hermes-Agent-8A2BE2)](https://hermes-agent.nousresearch.com/docs)

---

## Features

| Category | Feature | Description |
|----------|---------|-------------|
| **Messenger** | MAX Messenger | Full integration with max.ru |
| **Modes** | Webhook + Polling | Two modes: `GET /updates` and `POST /max/webhook` |
| **Voice** | STT | Auto-download voice → faster-whisper transcription |
| **Tables** | PNG render | Markdown tables → PNG with colored status icons |
| **Streaming** | Edit Message | Real-time token output via `PUT /messages` |
| **Buttons** | Callback | `send_buttons()` — callback, link, message, request_contact/geo |
| **Buttons** | Model Picker | Interactive model selection with pagination (15 per page) |
| **Buttons** | Confirm/Clarify | Command approval, clarify ambiguous requests |
| **Statuses** | send_action | typing, sending_photo/video/audio/file, read, typing_off |
| **Chunking** | Auto-chunking | Smart split of >4000 chars preserving paragraphs |
| **Files** | Upload | Two-step: `POST /uploads` → PUT → token → send |
| **Files** | Media | voice, video, document, image — dedicated send methods |
| **Access** | White-list | `MAX_ALLOWED_USERS`, `MAX_ALLOW_ALL_USERS` |
| **Access** | Group Policy | closed / allowlist policies for group chats |
| **Access** | Webhook Secret | Constant-time comparison `X-Max-Bot-Api-Secret` |
| **Cross-sessions** | /sessions | List sessions from ALL platforms |
| **Cross-sessions** | /resume --all | Switch to any session |
| **Slash commands** | 20 commands | `/start`, `/new`, `/status`, `/model`, `/resume`, `/sessions`, `/help`, `/stop`, `/config`, `/restart`, `/retry`, `/undo`, `/title`, `/branch`, `/compress`, `/rollback`, `/background`, `/agents`, `/queue`, `/topic` |
| **Tests** | 126 tests | pytest + pytest-asyncio, CI (bandit, pip-audit, ruff) |
| **Standalone** | Sender | `_standalone_send` for cron/send_message without core modification |
| **Setup** | Interactive | `hermes gateway setup` with prompts |

## Quick Start

### 1. Install

```bash
hermes plugins install Realmagnum/hermes-max-integration --enable
```

### 2. Get a bot token

Register at https://business.max.ru/self (requires Russian legal entity / sole proprietor).  
Create a bot → pass moderation → **Chat-bots → Go → Advanced settings → Configure** → copy token.

### 3. Configure

```bash
hermes gateway setup
# Choose: Max (STT)
```

Or manually in `~/.hermes/.env`:

```bash
MAX_BOT_TOKEN=your_token
MAX_ALLOWED_USERS=your_max_user_id
```

### 4. Enable table images (optional)

```bash
pip install Pillow
echo 'MAX_TABLE_AS_IMAGE=true' >> ~/.hermes/.env
```

### 5. Restart

```bash
hermes gateway restart
```

## Slash Commands

### Core

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

### Advanced

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
- Commands registered automatically on plugin start
- Registration failures non-fatal — bot works without commands

## Documentation

- [Setup](docs/setup.md) — .env, webhook, security, deployment
- [Features](docs/features.md) — STT, tables, streaming, buttons, files
- [API](docs/api.md) — MAX API formats, callbacks, file upload
- [Troubleshooting](docs/troubleshooting.md) — errors, diagnose.sh, logs

## Comparison with Upstream

| | Upstream (vladimiraldushin) | This plugin |
|---|---|---|
| Architecture | Plugin ✅ | Plugin ✅ |
| Long Polling | ❌ Webhook only | ✅ Both modes |
| STT Voice | ❌ | ✅ Built-in |
| Streaming (edit_message) | ❌ | ✅ |
| **Tables as Images (PNG)** | ❌ | ✅ **Unique** |
| **Interactive Buttons** | ❌ | ✅ model picker, approval, clarify |
| File upload | ❌ | ✅ Two-step |
| Message chunking | ✅ | ✅ Improved |
| Media extraction | ✅ | ✅ Extended |
| Message dedup | ❌ | ✅ 300s window |
| Tests | ✅ Basic | ✅ 126 tests |
| Setup | ✅ | ✅ + STT + tables |
