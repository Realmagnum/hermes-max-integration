# Setup

## Environment Variables

The plugin has no settings file of its own: values come from the Hermes process environment (`.env`) and from the core `config.yaml`. Precedence for every setting: **environment variable → `platforms.max` key in `config.yaml` → built-in default**. Exceptions:

- `MAX_ALLOWED_USERS` — values from the environment and from the config are **merged**, not overwritten;
- `MAX_GROUP_POLICY`, `MAX_HOME_CHANNEL` and `MAX_HOME_CHANNEL_NAME` — the environment variables are honoured **only in an env-only setup, where `MAX_BOT_TOKEN` is also set in the environment**. If the token lives in `config.yaml`, these three variables are silently ignored — set `group_policy` / `home_channel` in the `platforms.max` block instead (see "Core Configuration").

The `bool` type accepts `1`, `true`, `yes`, `y`, `on` (case-insensitive); any other non-empty value means "off".

| Variable | Required | Type | Default | Description |
|----------|----------|------|---------|-------------|
| `MAX_BOT_TOKEN` | ✅ | string | — | MAX bot token |
| `MAX_WEBHOOK_URL` | ❌ | string | empty | Public HTTPS URL; a non-empty value enables webhook mode |
| `MAX_WEBHOOK_SECRET` | ❌ | string | empty | Expected value of the `X-Max-Bot-Api-Secret` header |
| `MAX_WEBHOOK_HOST` | ❌ | string | `0.0.0.0` | Webhook server host |
| `MAX_WEBHOOK_PORT` | ❌ | integer | `8646` | Webhook server port (a non-numeric value fails at startup) |
| `MAX_WEBHOOK_PATH` | ❌ | string | `/max/webhook` | Webhook server path |
| `MAX_ALLOWED_USERS` | ❌ | comma-separated list | empty | user_id allowlist; merged with the config list |
| `MAX_ALLOW_ALL_USERS` | ❌ | bool | `false` | Allow any user |
| `MAX_GROUP_POLICY` | ❌ | string | `allowlist` | Group message policy: `allowlist` — check the allowlists, `closed` — ignore groups (env-only) |
| `MAX_GROUP_ALLOWED_USERS` | ❌ | comma-separated list | empty | user_ids allowed in groups |
| `MAX_GROUP_ALLOWED_CHATS` | ❌ | comma-separated list | empty | Group chat_ids where the bot is allowed |
| `MAX_HOME_CHANNEL` | ❌ | string | empty | Default channel for cron/send_message (env-only) |
| `MAX_HOME_CHANNEL_NAME` | ❌ | string | `Max Home` | Default channel name; only used when `MAX_HOME_CHANNEL` is set (env-only) |
| `MAX_TABLE_AS_IMAGE` | ❌ | bool | `false` | Render tables as PNG (HTML→PNG via Playwright, Pillow fallback) |
| `MAX_AUTO_INSTALL_PLAYWRIGHT` | ❌ | bool | `false` | Auto-install Playwright + Chromium on first render (needs network, 1–2 min) |
| `MAX_CROSS_SESSION` | ❌ | bool | `true` | Cross-platform /sessions and /resume |

Example `.env`:

```bash
# Minimum — long polling
MAX_BOT_TOKEN=<token>

# Webhook mode (additional)
MAX_WEBHOOK_URL=https://your-domain.com/max/webhook
MAX_WEBHOOK_SECRET=<secret>

# Access control and modes
MAX_ALLOWED_USERS=95825064
MAX_GROUP_POLICY=allowlist
MAX_TABLE_AS_IMAGE=true
MAX_CROSS_SESSION=false
```

A note on `MAX_GROUP_POLICY=allowlist`: `MAX_GROUP_ALLOWED_USERS`/`MAX_GROUP_ALLOWED_CHATS` are checked with OR, and an empty list means "no restriction". With both lists empty, group messages are not filtered (open item SEC-06 in BACKLOG).

### Helper script variables

`scripts/diagnose.sh` additionally reads `MAX_HOME_CHANNEL_THREAD_ID` as a fallback target for `--send`. The plugin's Python code does not use this variable.

## Core Configuration

Anything not listed above is configured in the Hermes core `config.yaml`. Keys of the `platforms.max` block (lower precedence than the environment):

| Key in the `platforms.max` block | Type | Default | Environment equivalent |
|----------------------------------|------|---------|------------------------|
| `enabled` | bool | — (auto-enabled when a token is present) | — |
| `token` | string | — | `MAX_BOT_TOKEN` |
| `home_channel` | `{platform: max, chat_id, name, thread_id?}` | — | `MAX_HOME_CHANNEL`, `MAX_HOME_CHANNEL_NAME` |
| `host` | string | `0.0.0.0` | `MAX_WEBHOOK_HOST` |
| `port` | integer | `8646` | `MAX_WEBHOOK_PORT` |
| `path` | string | `/max/webhook` | `MAX_WEBHOOK_PATH` |
| `webhook_url` | string | empty | `MAX_WEBHOOK_URL` |
| `webhook_secret` | string | empty | `MAX_WEBHOOK_SECRET` |
| `allowed_users` | list of strings | `[]` | `MAX_ALLOWED_USERS` (merged) |
| `allow_all_users` | bool | `false` | `MAX_ALLOW_ALL_USERS` |
| `group_policy` | string | `allowlist` | `MAX_GROUP_POLICY` |
| `group_allow_from` | comma-separated string | empty | `MAX_GROUP_ALLOWED_USERS` |
| `group_allow_chats` | comma-separated string | empty | `MAX_GROUP_ALLOWED_CHATS` |
| `table_as_image` | bool | `false` | `MAX_TABLE_AS_IMAGE` |
| `cross_session` | bool | `true` | `MAX_CROSS_SESSION` |

`enabled`, `token` and `home_channel` are typed core keys and must be written directly in the `platforms.max` block. The adapter reads the remaining keys from `extra`, but the Hermes core promotes every unrecognised top-level key of the block into `extra`, so `platforms.max.table_as_image` and `platforms.max.extra.table_as_image` are equivalent. A `home_channel` object written as `platforms.max.extra.home_channel` is silently dropped — the core only reads `home_channel` as a top-level key.

Example `config.yaml`:

```yaml
platforms:
  max:
    enabled: true
    token: "<token>"
    group_policy: closed
    group_allow_from: "-123456,78901"
    table_as_image: true
    home_channel:
      platform: max
      chat_id: "-123456789"
      name: "Max Home"
```

The `platform: max` field inside `home_channel` is mandatory: without it config loading fails with `KeyError: 'platform'`. Do not hand-write this block unless you have to — send `/sethome` once in the target chat and the core will persist `platforms.max.home_channel` in the correct shape. A `MAX_HOME_CHANNEL` value from the environment (in an env-only setup) takes precedence over this key.

`group_allow_from` and `group_allow_chats` accept **only a comma-separated string** (`"-123456,78901"`), not a YAML list: the adapter runs the value through `str()` and then splits on commas, so a list `["-123456", "78901"]` would degrade into garbage entries `["['-123456'", "'78901']"]`. This is the mirror image of `allowed_users`, which requires a list of strings (a bare string does not work there either — it is split per character).

`MAX_AUTO_INSTALL_PLAYWRIGHT` is not mirrored in `config.yaml`: that flag is read from the environment only.

Voice transcription is configured elsewhere — in the core config `stt` section; see the STT section in `docs/features_EN.md`.

## Internal Constants

These values are hard-coded and cannot be overridden by environment variables. They are listed so you do not look for them in `.env`:

| Constant | Value | Defined in |
|----------|-------|------------|
| API base URL (`MAX_API_BASE`) | `https://platform-api.max.ru` | `adapter.py`, `mixins/*.py` |
| Message length limit (`MAX_MESSAGE_LENGTH`) | 4000 characters (MAX API limit) | `adapter.py`, `mixins/*.py` |
| Outbound file limit (`MAX_FILE_SIZE`) | 50 MiB | `mixins/media_upload.py` |
| Webhook body limit (`WEBHOOK_MAX_BODY_BYTES`) | 1 MiB | `mixins/webhook.py` |
| `POLL_TIMEOUT` / `POLL_ERROR_DELAY` / `UPLOAD_DELAY` | 5 s / 5 s / 2 s | `adapter.py` |
| Audio cache directory | `$HERMES_HOME/audio_cache` (mode 0700) | `adapter.py` |
| Table PNG cache directory | `$HERMES_HOME/table_images` | `adapter.py` |
| Table as text: column width | at most 38 characters | `mixins/table_renderer.py` |
| Table as PNG: canvas size | ~1200 px wide, `max-width: 820px`, font 14 px (HTML) / 18–20 px (Pillow) | `mixins/table_renderer.py` |

The base URL is hard-coded to `platform-api.max.ru`; the `platform-api2.max.ru` domain recommended by the MAX documentation is not used in this version (see DOC-10 in BACKLOG).

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
