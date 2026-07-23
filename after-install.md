# Плагин Max STT установлен

Что делать дальше:

1. **Установите зависимости времени выполнения:**
   ```bash
   pip install aiohttp httpx
   # Для STT-транскрипции голоса:
   pip install faster-whisper
   ```

2. **Настройте платформу:**
   ```bash
   hermes gateway setup
   ```
   Выберите **Max (STT)**, вставьте `MAX_BOT_TOKEN`, укажите host/port/path вебхука и опциональный секрет.

3. **Настройте транскрипцию голоса (опционально):**
   ```bash
   python3 -m venv ~/.hermes/stt-venv
   ~/.hermes/stt-venv/bin/pip install faster-whisper
   cp scripts/transcribe_audio.py ~/.hermes/scripts/
   ```

4. **Выберите режим подключения:**

   **Long polling (проще, без HTTPS):**
   - Просто установите `MAX_BOT_TOKEN` и перезапустите. Адаптер автоматически использует long-polling.
   - Публичный URL не нужен. Подходит для разработки.

   **Webhook (продакшен):**
   - Откройте локальный webhook-сервер через публичный HTTPS:
     ```bash
     cloudflared tunnel --url http://localhost:8646
     # или: ngrok http 8646
     ```
   - Зарегистрируйте публичный URL в MAX:
     ```bash
     curl -X POST "https://platform-api.max.ru/subscriptions" \
       -H "Authorization: ***" \
       -H "Content-Type: application/json" \
       -d '{"url":"https://YOUR-DOMAIN/max/webhook","update_types":["message_created","message_callback","bot_started"],"secret":"CHANGE_ME_5_256_CHARS"}'
     ```

5. **Перезапустите шлюз Hermes:**
   ```bash
   hermes gateway restart
   ```

6. **Проверьте:**
   ```bash
   hermes gateway status
   curl http://localhost:8646/health
   # Ожидается: {"status":"ok"}
   ```

## Официальная документация MAX

Проверено 2026-06-22:
- https://dev.max.ru/docs/chatbots/bots-create
- https://dev.max.ru/docs/chatbots/bots-coding/prepare
- https://dev.max.ru/docs-api/methods/POST/subscriptions
- https://dev.max.ru/docs-api/methods/POST/messages
