---
name: max-gateway
description: "Install and configure Hermes Agent access through Max messenger (voice transcription by the Hermes core)."
version: 2.1.0
author: Alexander / Hermes Agent community
license: MIT
metadata:
  hermes:
    tags: [hermes, gateway, messaging, max, chatbot, voice]
---

# Max Gateway for Hermes

Use this skill when a user wants to control Hermes Agent through Max messenger.

## Official facts to trust first

Checked on 2026-06-22:
- Max partner platform connection: https://dev.max.ru/docs/maxbusiness/connection
- Chatbot creation and token location: https://dev.max.ru/docs/chatbots/bots-create
- Developer setup and token warning: https://dev.max.ru/docs/chatbots/bots-coding/prepare
- API overview: https://dev.max.ru/docs-api
- Webhook subscriptions: https://dev.max.ru/docs-api/methods/POST/subscriptions
- Sending messages: https://dev.max.ru/docs-api/methods/POST/messages

If these docs changed, follow the current official docs instead of this skill.

## Procedure

1. Verify Hermes is installed: `hermes --version`
2. Install plugin dependencies into the same Python the Hermes gateway runs in
   (the core venv; resolve it from the `hermes` shebang):
   ```bash
   HERMES_PY="$(head -1 "$(command -v hermes)" | sed 's|^#!||')"
   "$HERMES_PY" -m pip install aiohttp httpx
   ```
3. Install and enable the plugin:
   ```bash
   hermes plugins install Realmagnum/hermes-max-integration --enable
   ```
   Or from local path:
   ```bash
   hermes plugins install /path/to/hermes-max-integration-plugin --enable
   ```
4. Help the user get a Max bot token.
   Official path after moderation:
   `Chat-bots → Go → Advanced settings → Configure → Token`
5. Save token as `MAX_BOT_TOKEN` in Hermes `.env`. Do not echo the token back.
6. Choose how updates are delivered. The mode is selected **only** by the
   presence of `MAX_WEBHOOK_URL` (`adapter.py:226,230`):

   **Long polling (simpler, no HTTPS):**
   - Just set `MAX_BOT_TOKEN` and restart.
   - ⚠️ On startup in this mode the adapter **deletes** any existing webhook
     subscription in MAX API (`adapter.py:418–450`): webhook and long polling
     are mutually exclusive.

   **Webhook (production) — both values are mandatory:**
   - `MAX_WEBHOOK_URL` — public HTTPS URL; without it the adapter silently stays
     in long polling and deletes your manual subscription on its first start.
   - `MAX_WEBHOOK_SECRET` — the same secret registered in MAX API; without it
     the endpoint accepts events from any sender (`mixins/webhook.py:63–68`).
     5–256 characters.
   ```bash
   MAX_WEBHOOK_URL=https://max.example.com/max/webhook
   MAX_WEBHOOK_SECRET=my-secret-abc123
   MAX_WEBHOOK_HOST=0.0.0.0
   MAX_WEBHOOK_PORT=8646
   MAX_WEBHOOK_PATH=/max/webhook
   ```
7. Put a public HTTPS tunnel/reverse proxy in front of `http://127.0.0.1:8646`
   (MAX API only connects over HTTPS on port 443). Caddy example:
   ```caddyfile
   max.example.com {
       reverse_proxy 127.0.0.1:8646
   }
   ```
8. Restart the gateway — the adapter registers the subscription itself with the
   URL and secret from step 6 (`mixins/webhook.py:129–147`). A manual curl is
   only needed when the subscription was created externally: then the URL,
   secret and `update_types` must match the auto-registration, otherwise the
   secret will not match `MAX_WEBHOOK_SECRET`:
   ```bash
   curl -X POST "https://platform-api.max.ru/subscriptions" \
     -H "Authorization: $MAX_BOT_TOKEN" \
     -H "Content-Type: application/json" \
     -d "{\"url\":\"$MAX_WEBHOOK_URL\",\"update_types\":[\"message_created\",\"message_callback\",\"bot_started\",\"bot_added\"],\"secret\":\"$MAX_WEBHOOK_SECRET\"}"
   ```
   ⚠️ A manual subscription without `MAX_WEBHOOK_URL` is useless: the plugin
   starts in long polling and deletes it.
9. Verify that webhook mode is actually active:
   ```bash
   hermes gateway restart
   hermes gateway status
   curl http://localhost:8646/health
   # Expected: {"status":"ok"}
   curl "https://platform-api.max.ru/subscriptions" -H "Authorization: $MAX_BOT_TOKEN"
   # Expected: a subscription pointing at your MAX_WEBHOOK_URL
   ```
   The gateway log must contain `MAX: webhook on 0.0.0.0:8646/max/webhook`. If it
   says `MAX: long polling started`, `MAX_WEBHOOK_URL` was not picked up and the
   subscription will be deleted on startup.
10. Ask the user to send a real message to the Max bot and verify Hermes answers.

## Voice Messages (STT)

Transcription is performed by the **Hermes core** (>= 0.20.0) — the plugin only downloads and caches audio:

1. The adapter auto-downloads voice messages into the core audio cache (`$HERMES_HOME/cache/audio/`, default `~/.hermes/cache/audio/`); the core transcribes them per the `stt` config
2. Core providers: `local` (faster-whisper, free), `groq`, `openai` (whisper-1, gpt-transcribe), `mistral`, `xai`, `elevenlabs`
3. Setup: `hermes tools` → STT category, or `config.yaml` → `stt` (for Russian — `stt.language: ru`)
4. The transcript is prepended to the agent's message; with `stt.echo_transcripts` the core also sends the raw transcript back as `🎙️ "<text>"`

### Pitfalls for STT

- `stt` section in `config.yaml`: `enabled`, `provider`, `language`, `echo_transcripts`
- The `local` model is downloaded automatically on first use (~150 MB)
- If no transcript arrives, check in this order:
  ```bash
  grep -A8 "^stt:" ~/.hermes/config.yaml    # enabled / language / provider
  ls -la ~/.hermes/cache/audio/             # did the audio download at all?
  grep -i "transcri" ~/.hermes/logs/gateway.log | tail -20
  ```
  In the core log look for `Voice transcription failed for <path>: <error>` (provider error) and the marker `[voice message could not be transcribed automatically; the audio is available at: …]`
- More: README → "Voice not transcribing", `docs/troubleshooting_EN.md`

## Pitfalls (general)

- Use `Authorization: ***` not query params and not `Bearer <token>`.
- Webhook must be HTTPS with a trusted certificate.
- If `secret` is configured, Max sends it raw in `X-Max-Bot-Api-Secret`; compare it directly with constant-time comparison.
- **A secret is mandatory for the webhook (fail closed).** Without `MAX_WEBHOOK_SECRET` the adapter refuses to start the webhook (`webhook_secret_required`) — an unprotected endpoint would let anyone forge a `user_id`. The header is verified before the body is read. To debug without a secret use long polling, or `MAX_WEBHOOK_INSECURE_DEV=true` with `MAX_WEBHOOK_HOST=127.0.0.1` only.
- **🚨 CRITICAL: Webhook and Long Polling are mutually exclusive.** If a webhook subscription exists in MAX API, `/updates` returns empty and ALL messages go to the webhook URL instead. Even after removing `MAX_WEBHOOK_URL` from .env and restarting, the stale subscription persists in MAX API and silently blocks message delivery.
  - **Fix:** Delete the old subscription:
    ```bash
    curl -X DELETE "https://platform-api.max.ru/subscriptions?url=<URL>" -H "Authorization: ***"
    ```
  - **Auto-fix (v2.1.4+):** The plugin now auto-cleans stale webhook subscriptions on startup when running in long-polling mode.
  - **Prevention:** Don't set `MAX_WEBHOOK_URL` in .env unless you have a working reverse proxy in front of port 8646. When switching modes, always clean up the old subscription first. If step 6 of the procedure is followed (`MAX_WEBHOOK_URL` and `MAX_WEBHOOK_SECRET` are set), the auto-cleanup never fires — the adapter runs in webhook mode.
- Keep tunnel/gateway running while using Max.
- Max API requires Russian Federation jurisdiction for bot registration.
