# Instructions for AI Agents Working With This Repository

## Language Policy

> **⚠️ Bilingual Project:** All `*.md` documentation files are written in **Russian** (primary language). Each file must have an English translation in the format `*_EN.md`. Any change to the original **must** be synced to the translation. The English version is an exact translation of the Russian one, with identical structure and content.

This repository contains a Hermes Agent platform plugin that adds Max messenger as a gateway channel (voice transcription is performed by the Hermes core).

When a user gives you this repository and asks to connect Hermes to Max:

1. **Do not invent** Max bot setup steps. Use the fact-checked sources in `README.md` (Russian) or `README_EN.md` (English); if available, re-open the official pages under `https://dev.max.ru/` and prefer current official docs.
2. Install Hermes first if it is missing: https://hermes-agent.nousresearch.com/docs
3. Install this plugin with:
   ```bash
   hermes plugins install Realmagnum/hermes-max-integration --enable
   ```
4. Ensure `aiohttp` and `httpx` are installed in the same Python environment that runs Hermes.
5. Help the user obtain `MAX_BOT_TOKEN` from Max for Partners.
   Current checked path: `Chat-bots → Go → Advanced settings → Configure → Token` after bot moderation.
6. Treat `MAX_BOT_TOKEN` and `MAX_WEBHOOK_SECRET` as secrets. Do not print them back to the chat.
7. Configure a public HTTPS webhook URL that points to the local Hermes gateway server, default local URL `http://localhost:8646/max/webhook`.
   Or use long-polling mode (no HTTPS needed) — just set the token and restart.
8. For webhook mode, register through Max Bot API:
   ```bash
   curl -X POST "https://platform-api.max.ru/subscriptions" \
     -H "Authorization: ***" \
     -H "Content-Type: application/json" \
     -d '{"url":"https://your-domain/max/webhook","update_types":["message_created","message_callback","bot_started"],"secret":"your-secret"}'
   ```
9. Restart Hermes gateway and verify:
   ```bash
   hermes gateway restart
   hermes gateway status
   curl http://localhost:8646/health
   ```
10. STT (voice transcription) is provided by the **Hermes core** (>= 0.20.0): the plugin adapter only downloads and caches audio, the core transcribes it according to the `stt` config in `config.yaml`. No plugin setting is needed; `MAX_STT_ENABLED` was removed.
    - Core providers: `local` (faster-whisper, free), `groq`, `openai` (whisper-1 / gpt-transcribe), `mistral`, `xai`, `elevenlabs`
    - Setup: `hermes tools` → STT category, or manually `config.yaml` → `stt.language` (for Russian — `ru`; default is `"en"`)
11. When the agent receives a voice message (`[Audio: /path/to/file.ogg]`), the core has already transcribed it — just answer the content.

**Important current Max API facts** (checked 2026-07-21):
- Bot API requests use `Authorization: ***` header; token in query parameters is no longer supported.
- Webhook requires public HTTPS; HTTP and self-signed certificates are not supported for webhooks.
- Webhook `secret` is sent back by Max as the raw `X-Max-Bot-Api-Secret` header value, not as an HMAC signature.
- **CRITICAL: Webhook and long polling are mutually exclusive.** If a webhook subscription exists, MAX API routes ALL updates to the webhook URL and `/updates` returns empty. Even after removing `MAX_WEBHOOK_URL` from .env and restarting in long-polling mode, the stale webhook subscription persists in MAX API and blocks message delivery. **Always delete the old webhook subscription when switching modes:**
  ```bash
  curl -X DELETE "https://platform-api.max.ru/subscriptions?url=..." -H "Authorization: ***"
  ```
  The plugin now has auto-cleanup on startup (since v2.1.4+), but manual cleanup may still be needed if the webhook was registered externally.
- `POST /messages` accepts `user_id` or `chat_id`; message `text` is up to 4000 characters and `format` can be `markdown` or `html`.
- This plugin supports **both** long-polling (default, no HTTPS needed) and webhook (requires HTTPS). Long-polling is ideal for development and testing.
- **Callback updates (`message_callback`)** contain a `message` object; the chat_id for routing lives at `message.recipient.chat_id`, NOT at `chat.chat_id` or top-level `chat_id`.

**STT-specific:**
- Voice messages from MAX arrive as audio attachments with `payload.url` for direct download.
- The adapter downloads and caches them; transcription is done by the Hermes core (core STT, `config.yaml` → `stt`).
- Model/provider/language are configured in the core, not in the plugin.

**Tables as Images (`MAX_TABLE_AS_IMAGE=true`):**
- Pipe markdown tables (`| A | B |\n|---|---|`) are rendered as Pillow-generated PNG images.
- Emoji status icons (✅❌⚠️⏳) are replaced with Unicode symbols (✓✗⚠◷▶) in semantic colors.
- Images are uploaded via two-step API (`POST /uploads` → PUT → token → POST /messages`).
- If Pillow is not installed, falls back to inline `` `code` `` text rendering.
- Generated PNGs are cached in `~/.hermes/table_images/`.
