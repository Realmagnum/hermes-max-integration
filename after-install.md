# Плагин Max установлен

Что делать дальше:

1. **Установите зависимости времени выполнения:**
   ```bash
   # Каталог плагина (активный профиль Hermes) и Python его venv:
   cd "${HERMES_HOME:-$HOME/.hermes}/plugins/max-platform"
   HERMES_PY="$(head -1 "$(command -v hermes)" | sed 's|^#!||')"
   "$HERMES_PY" -m pip install aiohttp httpx
   ```

   **Таблицы-картинки (опционально):** HTML→PNG рендер через Playwright/Chromium.
   Ставьте в тот же Python, где работает шлюз Hermes (venv), иначе пакет не
   попадёт в рантайм плагина. Windows: `%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe`.
   ```bash
   "$HERMES_PY" -m pip install 'playwright>=1.40'
   "$HERMES_PY" -m playwright install chromium    # ~115 МБ, один раз
   ```
   Либо включите авто-установку (плагин сам поставит пакет и браузер при первом
   рендере таблицы): добавьте `MAX_AUTO_INSTALL_PLAYWRIGHT=true` в `~/.hermes/.env`.

2. **Настройте платформу:**
   ```bash
   hermes gateway setup
   ```
   Выберите **Max**, вставьте `MAX_BOT_TOKEN`, укажите host/port/path вебхука и секрет.

   > ⚠️ **Безопасная конфигурация — «только владелец».** Обязательно задайте
   > `MAX_ALLOWED_USERS=<ваш MAX user_id>`: пустой список при
   > `MAX_ALLOW_ALL_USERS=false` **не** закрывает доступ. Для webhook-режима
   > `MAX_WEBHOOK_SECRET` обязателен (пустое значение — только предупреждение в логе,
   > SEC-04), а `MAX_WEBHOOK_HOST` за reverse proxy ставьте `127.0.0.1`. Если ботом
   > пользуется больше одного человека — `MAX_CROSS_SESSION=false` (SEC-05).
   > Полная картина: [docs/security.md](docs/security.md). До закрытия SEC-01…07
   > публичный и многопользовательский контур не поддерживаются.

3. **Голосовые сообщения:** транскрипция выполняется ядром Hermes (≥ 0.20.0) — плагин только скачивает и кэширует аудио. Для русского языка задайте в `config.yaml`:
   ```yaml
   stt:
     enabled: true
     language: ru   # дефолт ядра — "en"
     provider: local
   ```

4. **Выберите режим подключения:**

   **Long polling (проще, без HTTPS):**
   - Просто установите `MAX_BOT_TOKEN` и перезапустите. Адаптер автоматически использует long-polling.
   - Публичный URL не нужен. Подходит для разработки.
   - ⚠️ При старте в этом режиме адаптер удаляет существующие подписки вебхука в MAX API
     (`adapter.py:418–450`) — режимы взаимоисключающи.

   **Webhook (продакшен) — требуется reverse proxy:**
   - MAX API стучится **только на порт 443** по HTTPS.
   - Вам нужен reverse proxy (Caddy, Nginx, Traefik, Cloudflare Tunnel), который терминирует TLS и проксирует на `127.0.0.1:8646`.
   - Пример для **Caddy** (`Caddyfile`):
     ```caddyfile
     max.example.com {
         reverse_proxy 127.0.0.1:8646
     }
     ```
   - Пример для **Cloudflare Tunnel** (без своего сервера):
     ```bash
     cloudflared tunnel --url http://localhost:8646
     ```
   - В `.env` обязательны **оба** параметра режима: `MAX_WEBHOOK_URL` (публичный HTTPS-URL —
     это единственный переключатель webhook-режима, `adapter.py:226,230`) и `MAX_WEBHOOK_SECRET`
     (5–256 символов; сервер сверяет его с заголовком `X-Max-Bot-Api-Secret`, `mixins/webhook.py:63–68`):
     ```bash
     MAX_WEBHOOK_URL=https://max.example.com/max/webhook
     MAX_WEBHOOK_SECRET=my-secret-abc123
     MAX_WEBHOOK_HOST=0.0.0.0
     MAX_WEBHOOK_PORT=8646
     MAX_WEBHOOK_PATH=/max/webhook
     ```
   - Подписку адаптер регистрирует сам при старте с URL и секретом из `.env`
     (`mixins/webhook.py:129–147`). Ручной curl нужен только для подписки, созданной извне;
     тогда URL, секрет и `update_types` должны совпадать с авторегистрацией:
     ```bash
     curl -X POST "https://platform-api.max.ru/subscriptions" \
       -H "Authorization: $MAX_BOT_TOKEN" \
       -H "Content-Type: application/json" \
       -d "{\"url\":\"$MAX_WEBHOOK_URL\",\"update_types\":[\"message_created\",\"message_callback\",\"bot_started\",\"bot_added\"],\"secret\":\"$MAX_WEBHOOK_SECRET\"}"
     ```
     ⚠️ Без `MAX_WEBHOOK_URL` в `.env` плагин стартует в long-polling и удалит такую подписку.

5. **Перезапустите шлюз Hermes:**
   ```bash
   hermes gateway restart
   ```

6. **Проверьте режим и окружение:**
   ```bash
   hermes gateway status
   printf 'HERMES_HOME=%s\n' "${HERMES_HOME:-$HOME/.hermes}"
   printf 'MAX_WEBHOOK_PORT=%s\n' "${MAX_WEBHOOK_PORT:-8646}"
   command -v python
   python -c 'import sys; print(sys.executable)'
   # Только webhook: /health проверяет локальный endpoint, не полный E2E
   curl "http://127.0.0.1:${MAX_WEBHOOK_PORT:-8646}/health"
   ```
   В long-polling режиме `/health` не является проверкой доставки: подтвердите `GET /me` как API smoke-тест и отправьте реальное тестовое сообщение MAX, проверив путь inbound → Hermes core → outbound по логам и в MAX. `scripts/diagnose.sh --send` проверяет только исходящий REST smoke-тест.

## Официальная документация MAX

Проверено 2026-06-22:
- https://dev.max.ru/docs/chatbots/bots-create
- https://dev.max.ru/docs/chatbots/bots-coding/prepare
- https://dev.max.ru/docs-api/methods/POST/subscriptions
- https://dev.max.ru/docs-api/methods/POST/messages
