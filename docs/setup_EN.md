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
| `MAX_TABLE_AS_IMAGE` | ❌ | `false` | Render tables as PNG via Pillow |
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

### Webhook Secret

Secret is sent by MAX as raw value in `X-Max-Bot-Api-Secret` header, not as HMAC signature. Plugin uses `secrets.compare_digest()` for timing-safe comparison.

### Access Control

**User whitelist:**

```bash
MAX_ALLOWED_USERS=123456789,987654321
```

**Allow all:**

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
