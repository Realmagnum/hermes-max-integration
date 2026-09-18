# Max plugin installed

Next steps:

1. **Install runtime dependencies:**
   ```bash
   # Plugin directory (active Hermes profile) and the interpreter of its venv:
   cd "${HERMES_HOME:-$HOME/.hermes}/plugins/max-platform"
   HERMES_PY="$(head -1 "$(command -v hermes)" | sed 's|^#!||')"
   "$HERMES_PY" -m pip install aiohttp httpx
   ```

   **Tables as images (optional):** HTML→PNG rendering via Playwright/Chromium.
   Install into the same Python the Hermes gateway runs in (its venv), otherwise
   the package won't reach the plugin runtime. Windows:
   `%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe`.
   ```bash
   "$HERMES_PY" -m pip install 'playwright>=1.40'
   "$HERMES_PY" -m playwright install chromium    # ~115 MB, one-time
   ```
   Or enable auto-install (the plugin installs the package and browser itself on
   the first table render): add `MAX_AUTO_INSTALL_PLAYWRIGHT=true` to `~/.hermes/.env`.

2. **Configure the platform:**
   ```bash
   hermes gateway setup
   ```
   Choose **Max**, paste `MAX_BOT_TOKEN`, set webhook host/port/path and the secret.

   > ⚠️ **Safe configuration is owner-only.** Always set
   > `MAX_ALLOWED_USERS=<your MAX user_id>`: an empty list with
   > `MAX_ALLOW_ALL_USERS=false` does **not** close access. In webhook mode
   > `MAX_WEBHOOK_SECRET` is mandatory (an empty value only logs a warning, SEC-04), and
   > `MAX_WEBHOOK_HOST` should be `127.0.0.1` behind a reverse proxy. If more than one
   > person uses the bot, set `MAX_CROSS_SESSION=false` (SEC-05).
   > Full picture: [docs/security_EN.md](docs/security_EN.md). Public and multi-user
   > deployments are not supported until SEC-01…07 are closed.

3. **Voice messages:** transcription is performed by the Hermes core (>= 0.20.0) — the plugin only downloads and caches audio. For Russian, set in `config.yaml`:
   ```yaml
   stt:
     enabled: true
     language: ru   # core default is "en"
     provider: local
   ```

4. **Choose connection mode:**

   **Long polling (simpler, no HTTPS):**
   - Just set `MAX_BOT_TOKEN` and restart. The adapter auto-uses long-polling.
   - No public URL needed. Good for development.
   - ⚠️ On startup in this mode the adapter deletes existing webhook subscriptions in MAX API
     (`adapter.py:418–450`) — the two modes are mutually exclusive.

   **Webhook (production) — requires a reverse proxy:**
   - MAX API connects **only to port 443** over HTTPS.
   - You need a reverse proxy (Caddy, Nginx, Traefik, Cloudflare Tunnel) that terminates TLS and proxies to `127.0.0.1:8646`.
   - **Caddy** example (`Caddyfile`):
     ```caddyfile
     max.example.com {
         reverse_proxy 127.0.0.1:8646
     }
     ```
   - **Cloudflare Tunnel** example (no dedicated server):
     ```bash
     cloudflared tunnel --url http://localhost:8646
     ```
   - In `.env` **both** mode parameters are mandatory: `MAX_WEBHOOK_URL` (public HTTPS URL — the
     single switch that selects webhook mode, `adapter.py:226,230`) and `MAX_WEBHOOK_SECRET`
     (5–256 characters; the server compares it with the `X-Max-Bot-Api-Secret` header, `mixins/webhook.py:63–68`):
     ```bash
     MAX_WEBHOOK_URL=https://max.example.com/max/webhook
     MAX_WEBHOOK_SECRET=my-secret-abc123
     MAX_WEBHOOK_HOST=0.0.0.0
     MAX_WEBHOOK_PORT=8646
     MAX_WEBHOOK_PATH=/max/webhook
     ```
   - The adapter registers the subscription itself on startup with the URL and secret from `.env`
     (`mixins/webhook.py:129–147`). A manual curl is only needed for an externally created
     subscription; then the URL, secret and `update_types` must match the auto-registration:
     ```bash
     curl -X POST "https://platform-api.max.ru/subscriptions" \
       -H "Authorization: $MAX_BOT_TOKEN" \
       -H "Content-Type: application/json" \
       -d "{\"url\":\"$MAX_WEBHOOK_URL\",\"update_types\":[\"message_created\",\"message_callback\",\"bot_started\",\"bot_added\"],\"secret\":\"$MAX_WEBHOOK_SECRET\"}"
     ```
     ⚠️ Without `MAX_WEBHOOK_URL` in `.env` the plugin starts in long-polling and deletes such a subscription.

5. **Restart Hermes gateway:**
   ```bash
   hermes gateway restart
   ```

6. **Check mode and environment:**
   ```bash
   hermes gateway status
   printf 'HERMES_HOME=%s\n' "${HERMES_HOME:-$HOME/.hermes}"
   printf 'MAX_WEBHOOK_PORT=%s\n' "${MAX_WEBHOOK_PORT:-8646}"
   command -v python
   python -c 'import sys; print(sys.executable)'
   # Webhook only: /health checks the local endpoint, not full E2E
   curl "http://127.0.0.1:${MAX_WEBHOOK_PORT:-8646}/health"
   ```
   In long-polling mode `/health` does not test delivery: use `GET /me` as an API smoke test, then send a real MAX test message and verify inbound → Hermes core → outbound in logs and in MAX. `scripts/diagnose.sh --send` checks only outbound REST smoke delivery.

## Official Max docs

Checked on 2026-06-22:
- https://dev.max.ru/docs/chatbots/bots-create
- https://dev.max.ru/docs/chatbots/bots-coding/prepare
- https://dev.max.ru/docs-api/methods/POST/subscriptions
- https://dev.max.ru/docs-api/methods/POST/messages
