# Troubleshooting

## diagnose.sh

Automated script for checking MAX functionality.

### Running

```bash
cd ~/.hermes/plugins/max-platform

# Basic diagnostics (without sending message)
./scripts/diagnose.sh

# Diagnostics with outbound API smoke test (not full E2E)
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
- Voice messages are not transcribed
- The chat gets `🎙️ ""`, or the agent sees `[voice message could not be transcribed automatically; the audio is available at: …]`
- Core logs: `Voice transcription failed for <path>: <error>`

**Cause:** transcription is done by the Hermes core (not the plugin): STT is disabled
(`stt.enabled`), the language is not set, the selected provider has no API key, or
faster-whisper is missing for the `local` provider.

**Solution:**
```bash
# 1. Check the stt section: enabled, language, provider
grep -A8 "^stt:" ~/.hermes/config.yaml

# 2. Configure interactively (the 🎙️ Speech-to-Text category)
hermes tools

# 3. For provider: local — install the package into the Hermes gateway Python
python -m pip install faster-whisper

# 4. Make sure the adapter actually downloaded the audio
ls -la ~/.hermes/cache/audio/

# 5. Core transcription errors
grep -i "transcri" ~/.hermes/logs/gateway.log | tail -20
```

A dedicated stt-venv, `scripts/transcribe_audio.py` and the `MAX_STT_*` variables are not
used: the plugin only downloads and caches audio, while STT settings live in the core
`config.yaml`. For Russian set `stt.language: ru` (the core default is `"en"`).

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

**Cause:** The MAX API CA is missing from the standard Python/OS bundles.

**Solution:** the plugin offers no switch to disable SSL verification — there is no `MAX_INSECURE_SSL` variable in the code (`adapter.py`), so that "fix" does not apply. Add the CA to the trusted stores:

```bash
# Option 1: system store (Debian/Ubuntu example)
sudo cp max-ca.crt /usr/local/share/ca-certificates/ && sudo update-ca-certificates

# Option 2: the Hermes process only
# SSL_CERT_FILE=/path/to/ca-bundle.crt hermes gateway restart

# Verify the chain to the API
curl -v https://platform-api.max.ru/me 2>&1 | grep -i "SSL\|certificate"
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

Before checking, confirm the environment and mode:

```bash
printf 'HERMES_HOME=%s\n' "${HERMES_HOME:-$HOME/.hermes}"
printf 'MAX_WEBHOOK_PORT=%s\n' "${MAX_WEBHOOK_PORT:-8646}"
command -v python
python -c 'import sys; print(sys.executable)'
```

`/health` exists only in webhook mode and checks the local HTTP endpoint. `GET /me` checks only the API smoke path. Full E2E requires a real inbound MAX message, Hermes core processing, and an outbound reply; confirm all three in logs and in MAX.

### Where to find

**Linux systemd:**
```bash
journalctl -u hermes-gateway -f
```

For a user service use `journalctl --user -u hermes-gateway -f`. macOS has no `journalctl` or `systemctl`; inspect the file configured by launchd/your process manager or run the gateway in the foreground.

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
