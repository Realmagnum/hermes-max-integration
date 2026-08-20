# Troubleshooting

## diagnose.sh

Automated script for checking MAX functionality.

### Running

```bash
cd ~/.hermes/plugins/max-platform

# Basic diagnostics (without sending message)
./scripts/diagnose.sh

# Full diagnostics with E2E test
./scripts/diagnose.sh --send
```

### What it checks

| Item | Description |
|------|-------------|
| 1 | Plugin installation |
| 2 | MAX API connection |
| 3 | Activity (polling or webhook) |
| 4 | Health check |
| 5 | Webhook subscriptions |
| 6 | Token validation |
| 7 | E2E message send |
| 8 | Reasoning setup |

### Exit code

- `0` — all good
- `1` — issues found

## Top 10 Errors

### 1. 401 Invalid token

**Symptoms:**
- No `MAX: connected` in logs
- No activity

**Cause:** Invalid or expired token

**Solution:**
```bash
# Check token
curl -s -X GET "https://platform-api.max.ru/me" \
  -H "Authorization: $(grep MAX_BOT_TOKEN ~/.hermes/.env | cut -d= -f2-)"

# Regenerate token in MAX Partners → Chat-bots → Configure → Token
# Update in ~/.hermes/.env
```

### 2. Webhook blocks polling

**Symptoms:**
- Long polling not working
- `GET /updates` returns empty

**Cause:** Active webhook subscription

**Solution:**
```bash
# Delete subscription
curl -X DELETE "https://platform-api.max.ru/subscriptions?url=<URL>" \
  -H "Authorization: your_token"

# Check subscriptions
curl -H "Authorization: your_token" \
  https://platform-api.max.ru/subscriptions
```

### 3. STT returns empty

**Symptoms:**
- Voice messages not transcribed
- Logs: `STT returned empty transcription`

**Cause:** No faster-whisper or model not loaded

**Solution:**
```bash
# Check venv
ls ~/.hermes/stt-venv/lib/python*/site-packages/whisper/

# Install model
~/.hermes/stt-venv/bin/pip install faster-whisper

# Check file
ls -la ~/.hermes/audio_cache/max_audio_*.ogg
```

### 4. Tables not rendering

**Symptoms:**
- `MAX_TABLE_AS_IMAGE=true` set
- Tables arrive as text

**Cause:** Playwright/Chromium missing (primary HTML→PNG renderer) and/or Pillow
missing (fallback). Both must be installed into the Hermes gateway Python (venv).

**Solution:**
```bash
# Diagnostics: what is missing?
python scripts/setup-playwright.py --check-only

# Install what's missing (idempotent):
python scripts/setup-playwright.py
# or manually:
python -m pip install 'playwright>=1.40'
python -m playwright install chromium

# Fallback renderer without a browser:
python -m pip install Pillow

hermes gateway restart
```

**Alternative:** `MAX_AUTO_INSTALL_PLAYWRIGHT=true` — the plugin installs the
package and Chromium itself on the first table render (needs network access).

### 5. Reasoning not displayed

**Symptoms:**
- Reasoning model used
- Reasoning block not visible

**Cause:** Fast model or wrong configuration

**Solution:**
```bash
# Check model
grep 'default:' ~/.hermes/config.yaml | head -1

# Check setting
grep -A3 'max:' ~/.hermes/config.yaml | grep fresh_final
# Should be: fresh_final_after_seconds: 10
```

### 6. SSL fails silently

**Symptoms:**
- Webhook not working
- No errors in logs

**Cause:** MinCifry CA not in standard bundles

**Solution:**
```bash
# For testing
MAX_INSECURE_SSL=true

# For production — add CA to system
```

### 7. MAX API auth format error

**Symptoms:**
- 401 Malformed access token

**Cause:** Using `Bearer <token>` instead of raw token

**Solution:**
```bash
# Incorrect
Authorization: Bearer <token>

# Correct
Authorization: <token>
```

### 8. Callback not received

**Symptoms:**
- Buttons displayed
- Callback not handled

**Cause:** Wrong chat_id in callback

**Solution:**
```python
# Check callback handling code
chat_id = message.get("recipient", {}).get("chat_id")
```

### 9. Messages duplicated

**Symptoms:**
- One message → two responses

**Cause:** Webhook + polling simultaneously

**Solution:**
```bash
# Ensure only one mode is active
# Check subscriptions
curl -H "Authorization: your_token" \
  https://platform-api.max.ru/subscriptions
```

### 10. Gateway won't restart

**Symptoms:**
- `hermes gateway restart` hangs
- Gateway won't start

**Cause:** Blocked from inside gateway

**Solution:**
```bash
# Use external terminal
sudo systemctl restart hermes-gateway

# Or from sandbox
```

## Logs

### Where to find

**Journald:**
```bash
journalctl -u hermes-gateway -f
```

**File:**
```bash
tail -f ~/.hermes/logs/gateway.log
```

### Useful commands

```bash
# Recent errors
journalctl -u hermes-gateway -p err -n 50

# Filter by MAX
journalctl -u hermes-gateway -g "MAX:" -f

# Start time
journalctl -u hermes-gateway --since "10 minutes ago"
```

## Webhook vs Polling

### Conflicts

**Webhook and long polling are mutually exclusive.** If webhook subscription exists, MAX API sends ALL updates to webhook URL.

### Migration

**Webhook → Polling:**
1. Remove `MAX_WEBHOOK_URL` from `.env`
2. Restart gateway
3. Plugin automatically removes webhook subscriptions

**Polling → Webhook:**
1. Add `MAX_WEBHOOK_URL` to `.env`
2. Restart gateway
3. Plugin automatically registers webhook

### Manual Cleanup

If auto-cleanup doesn't work:
```bash
curl -X DELETE "https://platform-api.max.ru/subscriptions?url=<URL>" \
  -H "Authorization: your_token"
```
