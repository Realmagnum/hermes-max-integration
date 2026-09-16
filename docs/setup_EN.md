# Setup

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MAX_BOT_TOKEN` | ✅ | — | MAX bot token |
| `MAX_API_BASE` | ❌ | `https://platform-api.max.ru` | Base API URL (docs recommend `https://platform-api2.max.ru`) |
| `MAX_WEBHOOK_HOST` | ❌ | `0.0.0.0` | Webhook host |
| `MAX_WEBHOOK_PORT` | ❌ | `8646` | Webhook port |
| `MAX_WEBHOOK_PATH` | ❌ | `/max/webhook` | Webhook path |
| `MAX_WEBHOOK_SECRET` | ❌ | — | Secret for `X-Max-Bot-Api-Secret` |
| `MAX_WEBHOOK_URL` | ❌ | — | Public HTTPS URL (enables webhook mode) |
| `MAX_ALLOWED_USERS` | ❌ | — | User whitelist (comma-separated) |
| `MAX_ALLOW_ALL_USERS` | ❌ | `false` | Allow all users |
| `MAX_GROUP_ALLOWED_USERS` | ❌ | — | Users allowed in groups |
| `MAX_GROUP_ALLOWED_CHATS` | ❌ | — | Groups allowed for bot |
| `MAX_STT_ENABLED` | ❌ | `true` | Auto-download voice for STT |
| `MAX_STT_VENV` | ❌ | `~/.hermes/stt-venv` | Path to venv for faster-whisper |
| `MAX_TABLE_AS_IMAGE` | ❌ | `false` | Render tables as PNG (HTML→PNG via Playwright, Pillow fallback) |
| `MAX_AUTO_INSTALL_PLAYWRIGHT` | ❌ | `false` | Auto-install Playwright + Chromium on first render |
| `MAX_HOME_CHANNEL` | ❌ | — | Default channel for cron/send_message |
| `MAX_HOME_CHANNEL_NAME` | ❌ | — | Default channel name |
| `MAX_INSECURE_SSL` | ❌ | `false` | Disable SSL verification (for testing) |
| `MAX_CROSS_SESSION` | ❌ | `true` | Cross-platform /sessions and /resume |

## Connection Modes

The plugin supports two modes for receiving messages from MAX API. The mode is determined by a single variable — **`MAX_WEBHOOK_URL`**:

| `MAX_WEBHOOK_URL` | Mode | Mechanism |
|---|---|---|
| Not set (empty) | **Long polling** (default) | Cyclic `GET /updates?timeout=5&marker=...` |
| Set to HTTPS URL | **Webhook** | aiohttp server on port 8646, registration `POST /subscriptions` |

Selection happens in `connect()` with one line: `self._use_webhook = bool(self._webhook_url)`.

### Long polling (default)

```bash
# Just set the token
MAX_BOT_TOKEN=your_token
```

Long polling is ideal for:
- Local development
- Testing
- Cases without public HTTPS

### Webhook

```bash
MAX_BOT_TOKEN=your_token
MAX_WEBHOOK_URL=https://your-domain.com/max/webhook
MAX_WEBHOOK_SECRET=your-secret
```

Webhook required for production. Needs public HTTPS URL.

## Webhook Setup

### Caddy

```caddyfile
your-domain.com {
    reverse_proxy localhost:8646
}
```

### Traefik

```yaml
http:
  routers:
    max-webhook:
      rule: "Host(`your-domain.com`)"
      service: max-gateway
  services:
    max-gateway:
      loadBalancer:
        servers:
          - url: "http://localhost:8646"
```

### Register webhook

The plugin automatically registers webhook on startup. For manual registration:

```bash
curl -X POST "https://platform-api.max.ru/subscriptions" \
  -H "Authorization: your_token" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://your-domain.com/max/webhook",
    "update_types": ["message_created", "message_callback", "bot_started"],
    "secret": "your-secret"
  }'
```

Check subscriptions:

```bash
curl -H "Authorization: your_token" \
  https://platform-api.max.ru/subscriptions
```

## Mode Switching

### Long polling → Webhook

```bash
# 1. Add to ~/.hermes/.env
MAX_WEBHOOK_URL=https://your-domain.com/max/webhook
MAX_WEBHOOK_SECRET=your-secret

# 2. Restart
sudo systemctl restart hermes-gateway
```

On startup: `_start_webhook()` → opens `0.0.0.0:8646` → registers subscription in MAX API.

### Webhook → Long polling

```bash
# 1. Remove or comment MAX_WEBHOOK_URL (and MAX_WEBHOOK_SECRET)
# MAX_WEBHOOK_URL=...
# MAX_WEBHOOK_SECRET=...

# 2. Restart
sudo systemctl restart hermes-gateway
```

On startup: `_start_polling()` → checks `GET /subscriptions`, **automatically removes** old webhook subscriptions → starts `_poll_loop`.

### 🚨 Important

If webhook subscription was registered **manually** (via curl, not through plugin), auto-cleanup may not find it. Delete manually:

```bash
curl -X DELETE "https://platform-api.max.ru/subscriptions?url=<URL>" \
  -H "Authorization: your_token"
```

## Security

The honest security model — what is protected, what is not, and which tasks are open:
[docs/security_EN.md](security_EN.md). Below is the minimally safe configuration.

### Safe defaults (single owner)

```bash
# ~/.hermes/.env
MAX_BOT_TOKEN=<bot token>
MAX_ALLOWED_USERS=<your MAX user_id>          # mandatory
MAX_CROSS_SESSION=false                       # until SEC-05 is closed
MAX_WEBHOOK_SECRET=<long random string>       # mandatory in webhook mode
MAX_WEBHOOK_HOST=127.0.0.1                    # behind a reverse proxy
```

- **Always set `MAX_ALLOWED_USERS`.** An empty list with `MAX_ALLOW_ALL_USERS=false`
  does **not** close access: anyone able to message the bot reaches the core
  (SEC-05/SEC-06).
- **Groups:** `MAX_GROUP_POLICY=closed`, or `allowlist` with **both** lists populated —
  an empty list under the `allowlist` policy means "allowed" and lists combine with OR
  (SEC-06).
- **`MAX_CROSS_SESSION=false`** if more than one person uses the bot: with `true`,
  `/sessions` bypasses the platform filter and exposes titles and previews of sessions
  from all platforms (SEC-05).
- Do not enable **`MAX_ALLOW_ALL_USERS=true`** on a bot reachable from the network.

### Webhook Secret

Secret is sent by MAX as raw value in `X-Max-Bot-Api-Secret` header, not as HMAC signature. Plugin uses `secrets.compare_digest()` for timing-safe comparison.

An empty secret produces **only a log warning**; webhook processing continues and the
`user_id` is taken from the request JSON (SEC-04). So the secret is mandatory, and the
port must be closed at the network level as well — do not rely on the plugin.

### Ingress and firewall

- Bind the webhook listener to `127.0.0.1` (`MAX_WEBHOOK_HOST=127.0.0.1`); MAX connects
  to port 443 only, so TLS terminates on a reverse proxy
  (Caddy/Nginx/Traefik/Cloudflare Tunnel).
- Port `8646` **must not** be reachable from the internet: allow inbound 443 to the
  reverse proxy only.
- The built-in webhook rate limit (30 requests / 10 s per IP, in memory) resets on
  restart and does not distinguish clients behind a proxy — burst protection only.
- `/health` is served without authentication and only proves the process is up.

### Access Control

**User whitelist:**

```bash
MAX_ALLOWED_USERS=123456789,987654321
```

**Allow all** (deliberate public deployments only):

```bash
MAX_ALLOW_ALL_USERS=true
```

**Group policies:**

```bash
# Closed group — only allowed users
MAX_GROUP_POLICY=closed

# Whitelist for group
MAX_GROUP_ALLOWED_USERS=123456789
MAX_GROUP_ALLOWED_CHATS=-1001234567890
```

### What is not protected

SSRF through DNS, the token sent to an attachment URL, group approvals, incoming media
limits, and more — see the SEC-01…07 table in [docs/security_EN.md](security_EN.md).
Until those are closed the plugin is not intended for public or multi-user deployments.

## Deployment

### Systemd

```bash
sudo systemctl enable hermes-gateway
sudo systemctl start hermes-gateway
sudo systemctl status hermes-gateway
```

### Check

```bash
# Health check
curl http://localhost:8646/health

# Plugin status
hermes gateway status
```

### Docker

See [docs/docker.md](docs/docker.md) (in development).
