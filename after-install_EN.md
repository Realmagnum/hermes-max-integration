# Post-Installation Guide

## 1. Verify Installation

```bash
# Check gateway status
hermes gateway status

# Health check
curl http://localhost:8646/health
# Expected: {"status":"ok"}

# Check plugin loaded
journalctl -u hermes-gateway -g "MAX: connected" --since "5 minutes ago"
```

## 2. Install Dependencies

```bash
# Core dependencies
pip install aiohttp httpx

# For STT voice transcription
pip install faster-whisper
```

## 3. Configure STT (Optional)

```bash
# Create venv for faster-whisper
python3 -m venv ~/.hermes/stt-venv
~/.hermes/stt-venv/bin/pip install faster-whisper

# Copy transcription script
cp scripts/transcribe_audio.py ~/.hermes/scripts/
```

### Test STT

```bash
# Transcribe a test file
~/.hermes/scripts/transcribe_audio.py /path/to/test.ogg

# Check audio cache
ls -la ~/.hermes/audio_cache/
```

## 4. Choose Connection Mode

### Long Polling (Development)

```bash
# Just set token
MAX_BOT_TOKEN=your_token
```

No public URL needed. Good for local development.

### Webhook (Production)

Requires reverse proxy (Caddy, Nginx, Traefik, Cloudflare Tunnel).

**Caddy example:**
```caddyfile
max.example.com {
    reverse_proxy 127.0.0.1:8646
}
```

**Cloudflare Tunnel example:**
```bash
cloudflared tunnel --url http://localhost:8646
```

**Configure in .env:**
```bash
MAX_WEBHOOK_URL=https://max.example.com/max/webhook
MAX_WEBHOOK_SECRET=my-secret-abc123
MAX_WEBHOOK_HOST=0.0.0.0
MAX_WEBHOOK_PORT=8646
MAX_WEBHOOK_PATH=/max/webhook
```

**Register subscription (optional — plugin does this automatically):**
```bash
curl -X POST "https://platform-api.max.ru/subscriptions" \
  -H "Authorization: your_token" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://max.example.com/max/webhook",
    "update_types": ["message_created", "message_callback", "bot_started"],
    "secret": "my-secret-abc123"
  }'
```

## 5. Restart Gateway

```bash
hermes gateway restart
```

## 6. Test

### Basic Test

```bash
# Check logs
journalctl -u hermes-gateway -f

# Send test message to bot
# Expected: Bot responds
```

### Full Diagnostics

```bash
cd ~/.hermes/plugins/max-platform

# Basic check
./scripts/diagnose.sh

# E2E test (sends message to home channel)
./scripts/diagnose.sh --send
```

### Test Voice

```bash
# Send voice message to bot
# Check logs for transcription
journalctl -u hermes-gateway -g "STT" --since "1 minute ago"
```

### Test Tables

```bash
# Enable table images
echo 'MAX_TABLE_AS_IMAGE=true' >> ~/.hermes/.env
hermes gateway restart

# Send message with markdown table
# Expected: PNG image received
```

## 7. Troubleshooting

### Bot not responding

```bash
# Check token
curl -s -X GET "https://platform-api.max.ru/me" \
  -H "Authorization: your_token"

# Check webhook subscriptions
curl -H "Authorization: your_token" \
  https://platform-api.max.ru/subscriptions

# Check logs
journalctl -u hermes-gateway -p err -n 50
```

### SSL errors

```bash
# For testing
MAX_INSECURE_SSL=true
```

### Voice not transcribing

```bash
# Check STT enabled
grep MAX_STT_ENABLED ~/.hermes/.env

# Check faster-whisper installed
~/.hermes/stt-venv/bin/pip list | grep faster-whisper

# Test transcription
python3 scripts/transcribe_audio.py --latest
```

### Tables not rendering

```bash
# Check Pillow installed
pip list | grep Pillow

# Check config
grep MAX_TABLE_AS_IMAGE ~/.hermes/.env

# Check logs
grep -i "table\|upload\|pillow" ~/.hermes/logs/gateway.log
```

## Official MAX Documentation

- https://dev.max.ru/docs/chatbots/bots-create
- https://dev.max.ru/docs/chatbots/bots-coding/prepare
- https://dev.max.ru/docs-api/methods/POST/subscriptions
- https://dev.max.ru/docs-api/methods/POST/messages
