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
| `MAX_CROSS_SESSION` | ❌ | `false` | Cross-platform /sessions and /resume; requires explicit opt-in |
| `MAX_CROSS_SESSION_USERS` | ❌ | — | Owners allowed to use cross-platform sessions |
| `MAX_GROUP_POLICY` | ❌ | `allowlist` | Group policy: `allowlist` or `open` |
| `MAX_WEBHOOK_INSECURE_DEV` | ❌ | `false` | Allow a secretless webhook only on loopback for development |
| `MAX_EDIT_THROTTLE` | ❌ | `0.2` | Minimum interval between streaming edits of one message |
| `MAX_DEDUP_TTL` | ❌ | `300` | Incoming-event deduplication TTL in seconds |
| `MAX_DEDUP_MAX` | ❌ | `4096` | Maximum number of deduplication keys |
| `MAX_QUEUE_MAXSIZE` | ❌ | `100` | Maximum incoming-event queue size |
| `MAX_MAX_CONCURRENCY` | ❌ | `8` | Incoming-event handling concurrency |
| `MAX_OVERLOAD_POLICY` | ❌ | `drop-oldest` | Queue policy: `drop-oldest` or `drop-newest` |
| `MAX_DOWNLOAD_ALLOWED_HOSTS` | ❌ | — | Strict operator download-host allowlist |
| `MAX_TRUSTED_DOWNLOAD_HOSTS` | ❌ | `.max.ru,.oneme.ru` | HTTPS hosts eligible for `Authorization` |
| `MAX_INBOUND_MEDIA_MAX_BYTES` | ❌ | `52428800` | Per-inbound-attachment byte limit |
| `MAX_INBOUND_MEDIA_TOTAL_BYTES` | ❌ | `104857600` | Per-update aggregate attachment byte limit |
| `MAX_INBOUND_MEDIA_MAX_ATTACHMENTS` | ❌ | `10` | Per-update attachment count limit |
| `MAX_INBOUND_MEDIA_TIMEOUT` | ❌ | `30` | Inbound-media download timeout in seconds |
| `MAX_INBOUND_MEDIA_CONCURRENCY` | ❌ | `4` | Inbound-media download concurrency |

## Internal Constants

| Constant | Value | Purpose |
|---|---|---|
| API base URL | `platform-api.max.ru` | MAX API address; not an environment setting |
| Message length limit | `4000` | Maximum text length in one message |
| Outbound file limit | `50 * 1024 * 1024` | Outbound file limit |
| Webhook body limit | `1_048_576` | Maximum webhook request-body size |
| Poll timeout | `POLL_TIMEOUT` | Base polling timeout |
| Table column cap | `38` | Text-table column limit |
| Table PNG width | `1200` | PNG-table canvas width |

## Keys in the `platforms.max` block

YAML keys are promoted to adapter `extra`; environment values take precedence.

| Key in the `platforms.max` block | Environment equivalent | Purpose |
|---|---|---|
| `token` | `MAX_BOT_TOKEN` | Bot token |
| `host` | `MAX_WEBHOOK_HOST` | Webhook host |
| `port` | `MAX_WEBHOOK_PORT` | Webhook port |
| `path` | `MAX_WEBHOOK_PATH` | Webhook path |
| `webhook_secret` | `MAX_WEBHOOK_SECRET` | Webhook secret |
| `webhook_url` | `MAX_WEBHOOK_URL` | Public webhook URL |
| `webhook_insecure_dev` | `MAX_WEBHOOK_INSECURE_DEV` | Allow secretless webhook only on loopback for development |
| `allowed_users` | `MAX_ALLOWED_USERS` | User allowlist |
| `allow_all_users` | `MAX_ALLOW_ALL_USERS` | Explicitly allow all users |
| `group_policy` | `MAX_GROUP_POLICY` | Group policy: `allowlist` or `open` |
| `group_allow_from` | `MAX_GROUP_ALLOWED_USERS` | Allowed group users |
| `group_allow_chats` | `MAX_GROUP_ALLOWED_CHATS` | Allowed groups |
| `cross_session` | `MAX_CROSS_SESSION` | Enable cross-platform sessions |
| `cross_session_users` | `MAX_CROSS_SESSION_USERS` | Owners allowed to use cross-platform sessions |
| `home_channel` | `MAX_HOME_CHANNEL` | cron/send_message target |
| `table_as_image` | `MAX_TABLE_AS_IMAGE` | Render markdown tables as PNG |
| `edit_throttle` | `MAX_EDIT_THROTTLE` | Minimum streaming-edit interval |
| `dedup_ttl` | `MAX_DEDUP_TTL` | Incoming-event deduplication TTL |
| `overload_policy` | `MAX_OVERLOAD_POLICY` | Queue behavior under overload |
| `download_allowed_hosts` | `MAX_DOWNLOAD_ALLOWED_HOSTS` | Strict operator download-host allowlist |
| `trusted_download_hosts` | `MAX_TRUSTED_DOWNLOAD_HOSTS` | HTTPS hosts eligible for `Authorization` |
| `inbound_media_max_bytes` | `MAX_INBOUND_MEDIA_MAX_BYTES` | Per-inbound-attachment limit |
| `inbound_media_total_bytes` | `MAX_INBOUND_MEDIA_TOTAL_BYTES` | Per-update aggregate attachment limit |
| `inbound_media_max_attachments` | `MAX_INBOUND_MEDIA_MAX_ATTACHMENTS` | Per-update attachment count limit |
| `inbound_media_timeout` | `MAX_INBOUND_MEDIA_TIMEOUT` | Inbound-media download timeout |
| `inbound_media_concurrency` | `MAX_INBOUND_MEDIA_CONCURRENCY` | Inbound-media download concurrency |

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

Webhook is required for production. A public HTTPS URL is needed.

> **Official (dev.max.ru/docs-api, checked 2026-09-16):** MAX delivers events via Webhook only; Long Polling is rate-limited and retention-bound and "is not suitable for a production environment". Since May 25, 2026 HTTP webhooks and self-signed certificates are unsupported, the endpoint must listen on **port 443** (the port must not appear in the URL) and return HTTP 200 within 30 seconds. The plugin binds to `8646` by default, so a reverse proxy must publish it on 443 (see examples below).

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
