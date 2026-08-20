# Max plugin installed

Next steps:

1. **Install runtime dependencies:**
   ```bash
   pip install aiohttp httpx
   ```

   **Tables as images (optional):** HTML→PNG rendering via Playwright/Chromium.
   Install into the same Python the Hermes gateway runs in (its venv), otherwise
   the package won't reach the plugin runtime. Windows:
   `%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe`.
   ```bash
   python -m pip install 'playwright>=1.40'
   python -m playwright install chromium    # ~115 MB, one-time
   ```
   Or enable auto-install (the plugin installs the package and browser itself on
   the first table render): add `MAX_AUTO_INSTALL_PLAYWRIGHT=true` to `~/.hermes/.env`.

2. **Configure the platform:**
   ```bash
   hermes gateway setup
   ```
   Choose **Max**, paste `MAX_BOT_TOKEN`, set webhook host/port/path and optional secret.

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
   - In `.env`, set the public URL and secret:
     ```bash
     MAX_WEBHOOK_URL=https://max.example.com/max/webhook
     MAX_WEBHOOK_SECRET=my-secret-abc123
     MAX_WEBHOOK_HOST=0.0.0.0
     MAX_WEBHOOK_PORT=8646
     MAX_WEBHOOK_PATH=/max/webhook
     ```
   - Register the subscription in MAX API (the adapter does this automatically on startup, but manual registration is also possible):
     ```bash
     curl -X POST "https://platform-api.max.ru/subscriptions" \
       -H "Authorization: ***" \
       -H "Content-Type: application/json" \
       -d '{"url":"https://max.example.com/max/webhook","update_types":["message_created","message_callback","bot_started"],"secret":"my-secret-abc123"}'
     ```

5. **Restart Hermes gateway:**
   ```bash
   hermes gateway restart
   ```

6. **Verify:**
   ```bash
   hermes gateway status
   curl http://localhost:8646/health
   # Expected: {"status":"ok"}
   ```

## Official Max docs

Checked on 2026-06-22:
- https://dev.max.ru/docs/chatbots/bots-create
- https://dev.max.ru/docs/chatbots/bots-coding/prepare
- https://dev.max.ru/docs-api/methods/POST/subscriptions
- https://dev.max.ru/docs-api/methods/POST/messages
