# Webhook in hermes-max-integration

Detailed description of the webhook server architecture, startup, request handling, and security.

---

## 1. Architecture

```
MAX Cloud               Your Server                    Hermes Gateway
─────────────          ─────────────                   ──────────────
                       ┌──────────────┐
User writes            │ Reverse Proxy │               ┌────────────┐
to bot ───────────────→│ (Traefik)    │──→ :8646 ──→  │ MaxAdapter │
                       │ TLS terminate│               │ (aiohttp)  │
MAX API ◀──────────────│              │               └─────┬──────┘
(sends                 └──────────────┘                     │
 callback)                                                 ↓
                                              ┌─────────────────────┐
                                              │ asyncio.Queue       │
                                              │ → handle_message()  │
                                              │ → Agent.process()   │
                                              └─────────────────────┘
```

---

## 2. Configuration

Webhook activates **only** when `MAX_WEBHOOK_URL` is set — a public HTTPS address:

```bash
# ~/.hermes/.env
MAX_BOT_TOKEN=***
MAX_WEBHOOK_URL=https://max.rmg7.com/max/webhook
MAX_WEBHOOK_SECRET=***    # optional but strongly recommended
MAX_WEBHOOK_HOST=0.0.0.0               # IP to listen on (default: all)
MAX_WEBHOOK_PORT=8646                  # port (default: 8646)
MAX_WEBHOOK_PATH=/max/webhook          # URL path for receiving callbacks
```

Without `MAX_WEBHOOK_URL`, the adapter runs in **long polling** mode — it polls MAX API every 5 seconds.

---

## 3. Startup Flow

```
connect()
  │
  ├─ 1. Token check → GET https://platform-api.max.ru/me
  │     └─ 401 → fatal error, stop
  │     └─ 200 → ok, read user_id/username
  │
  ├─ 2. self._use_webhook == True? → _start_webhook()
  │     │
  │     ├─ 2a. Check: aiohttp installed?
  │     │
  │     ├─ 2b. Check: port 8646 free?
  │     │     └─ connect(127.0.0.1, 8646) — if responds → port busy, error
  │     │
  │     ├─ 2c. Create aiohttp Application
  │     │     ├─ GET  /health       → {"status": "ok"}
  │     │     └─ POST /max/webhook  → webhook_handler()
  │     │
  │     ├─ 2d. Start server → web.TCPSite(host=0.0.0.0, port=8646)
  │     │
  │     ├─ 2e. Auto-register in MAX API:
  │     │     POST https://platform-api.max.ru/subscriptions
  │     │     Body: {
  │     │       "url": "https://max.rmg7.com/max/webhook",
  │     │       "secret": "***",
  │     │       "update_types": ["message_created", "message_callback",
  │     │                        "bot_started", "bot_added"]
  │     │     }
  │     │
  │     └─ 2f. Start _queue_poll_loop() — processes the message queue
  │
  └─ 3. _mark_connected() → adapter ready
```

---

## 4. Incoming Request Handling

When a user messages the bot, MAX API POSTs to the webhook:

```
POST https://max.rmg7.com/max/webhook
Header: X-Max-Bot-Api-Secret: my-secret-abc123
Body: {
  "update_type": "message_created",
  "message": {
    "sender": {"user_id": 42, "name": "Chief"},
    "recipient": {"chat_type": "dialog"},
    "body": {"mid": "msg-001", "text": "Hello!"}
  }
}
```

### `webhook_handler()` — 5 protection layers:

| Step | What | Rejection → |
|------|------|-------------|
| 🛡️ **Rate limit** | Count requests per IP. >30 per 10s? | **429** |
| 🔑 **Secret** | `X-Max-Bot-Api-Secret` == `MAX_WEBHOOK_SECRET`? | **403** |
| 📦 **JSON parse** | Valid JSON body? | **400** |
| 🏗️ **Build event** | `_build_event(payload)` — parse, dedup, access control | **nil** (silent) |
| 📬 **Enqueue** | Put `MessageEvent` into `asyncio.Queue` | — |

```python
# Simplified logic:
async def webhook_handler(req):
    # 1. Rate limit (30 req/10s per IP)
    if too_many_requests(req.remote):
        return 429

    # 2. Secret verification
    body = await req.read()
    if not secrets.compare_digest(req.headers["X-Max-Bot-Api-Secret"], my_secret):
        return 403

    # 3. JSON parse
    payload = json.loads(body)

    # 4. Build event (dedup, access control, media extraction, STT)
    event = await self._build_event(payload)
    if event is None:  # duplicate, bot, unauthorized...
        return 200      # silently ignore

    # 5. Into the processing queue
    await self._message_queue.put(event)
    return 200
```

---

## 5. What Happens After the Webhook

The queue is processed by `_queue_poll_loop()`:

```
_message_queue ──→ handle_message(event)
                      │
                      └──→ Gateway.process_message()
                              │
                              └──→ Agent.run()
                                      │
                                      └──→ Response via send() → MAX API
```

The message is **not processed inside the webhook handler** — the handler is as fast as possible (validation + enqueue only) to keep the aiohttp event loop responsive and avoid losing requests.

---

## 6. Handled update_type Values

| update_type | What the adapter does |
|-------------|----------------------|
| `message_created` | Parse text/media → `MessageEvent` |
| `message_edited` | Same as above (MAX doesn't distinguish) |
| `message_callback` | Inline button press → `_on_callback()` |
| `bot_started` | `/start` → saves user_id in `_dm_user_ids` |
| `bot_added` | Bot added to group → `/start` (internal) |

---

## 7. Dedup (Duplicate Protection)

MAX sometimes sends the same message twice. The adapter stores `_seen_msgs: {mid → timestamp}`:

- If `mid` is already in the dictionary AND < 300 seconds old → ignore (None)
- Otherwise → remember `mid`, clean old entries (>300s), clean if >5000 entries

---

## 8. Shutdown

```python
async def disconnect():
    self._running = False
    self._stop.set()
    # Stop the webhook server
    await self._webhook_runner.cleanup()
    # Close HTTP client
    await self._http_client.aclose()
    # Cancel background tasks
    for task in self._background_tasks:
        task.cancel()
```

---

## 9. Long Polling vs Webhook

| | Long Polling | Webhook |
|----|-------------|---------|
| **How it works** | Adapter polls MAX API (`GET /updates`) | MAX API calls the adapter (`POST /webhook`) |
| **Latency** | Up to 5 seconds | Instant |
| **HTTPS needed** | No | **Yes** (MAX requirement) |
| **Public URL needed** | No | Yes (Traefik/Cloudflare/ngrok) |
| **When to use** | Development, testing | Production |
| **Activation** | Default (no `MAX_WEBHOOK_URL`) | When `MAX_WEBHOOK_URL` is set |

---

## 10. Security Overview

```
External World
    │
    ▼
┌──────────────────────┐
│ Reverse Proxy (TLS)  │  ← terminates HTTPS
│ Traefik / nginx      │
└────────┬─────────────┘
         │ HTTP (internal network)
         ▼
┌──────────────────────┐
│ 0.0.0.0:8646         │
│ aiohttp webhook      │
│                      │
│ 🛡️ Rate limit: 30/10s│  ← DoS protection
│ 🔑 Secret verify     │  ← only MAX API
│ 📦 JSON validate     │  ← parser safety
│ 🏗️ Dedup: 300s       │  ← no duplicate messages
│ 👤 Access control    │  ← whitelist only
└────────┬─────────────┘
         │
         ▼
    asyncio.Queue → Gateway
```
