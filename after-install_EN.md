# Max STT plugin installed

Next steps:

1. **Install runtime dependencies:**
   ```bash
   pip install aiohttp httpx
   # For STT voice transcription:
   pip install faster-whisper
   ```

2. **Configure the platform:**
   ```bash
   hermes gateway setup
   ```
   Choose **Max (STT)**, paste `MAX_BOT_TOKEN`, set webhook host/port/path and optional secret.

3. **Set up voice transcription (optional):**
   ```bash
   python3 -m venv ~/.hermes/stt-venv
   ~/.hermes/stt-venv/bin/pip install faster-whisper
   cp scripts/transcribe_audio.py ~/.hermes/scripts/
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
