---
name: max-gateway
description: "Установка и настройка доступа Hermes Agent через мессенджер MAX (транскрипция голоса — ядром Hermes)."
version: 2.1.0
author: Alexander / Hermes Agent community
license: MIT
metadata:
  hermes:
    tags: [hermes, gateway, messaging, max, chatbot, voice]
---

# Шлюз MAX для Hermes

Используйте этот навык, когда пользователь хочет управлять Hermes Agent через мессенджер MAX.

## Официальные факты, которым доверять в первую очередь

Проверено 2026-06-22:
- Подключение партнёрской платформы MAX: https://dev.max.ru/docs/maxbusiness/connection
- Создание чат-бота и расположение токена: https://dev.max.ru/docs/chatbots/bots-create
- Настройка разработчика и предупреждение о токене: https://dev.max.ru/docs/chatbots/bots-coding/prepare
- Обзор API: https://dev.max.ru/docs-api
- Подписки вебхуков: https://dev.max.ru/docs-api/methods/POST/subscriptions
- Отправка сообщений: https://dev.max.ru/docs-api/methods/POST/messages

Если эти документы изменились, следуйте текущей официальной документации вместо этого навыка.

## Процедура

1. Проверьте, установлен ли Hermes: `hermes --version`
2. Установите зависимости плагина:
   ```bash
   pip install aiohttp httpx
   ```
3. Установите и включите плагин:
   ```bash
   hermes plugins install Realmagnum/hermes-max-integration --enable
   ```
   Или из локального пути:
   ```bash
   hermes plugins install /path/to/hermes-max-integration-plugin --enable
   ```
4. Помогите пользователю получить токен MAX-бота.
   Официальный путь после модерации:
   `Чат-боты → Перейти → Расширенные настройки → Настроить → Токен`
5. Сохраните токен как `MAX_BOT_TOKEN` в `.env` Hermes. Не выводите токен обратно.
6. Выберите режим получения обновлений. Режим определяется **только** наличием
   `MAX_WEBHOOK_URL` (`adapter.py:226,230`):

   **Long polling (проще, HTTPS не нужен):**
   - Задайте только `MAX_BOT_TOKEN` и перезапустите.
   - ⚠️ При старте в этом режиме адаптер **удаляет** любые существующие
     подписки вебхука в MAX API (`adapter.py:418–450`): вебхук и long polling
     взаимоисключающи.

   **Webhook (продакшен) — обязательны оба параметра:**
   - `MAX_WEBHOOK_URL` — публичный HTTPS-URL; без него адаптер молча останется
     в long polling и при первом же запуске удалит вашу ручную подписку.
   - `MAX_WEBHOOK_SECRET` — тот же секрет, что регистрируется в MAX API; без
     него endpoint принимает события от любого отправителя
     (`mixins/webhook.py:63–68`). 5–256 символов.
   ```bash
   MAX_WEBHOOK_URL=https://max.example.com/max/webhook
   MAX_WEBHOOK_SECRET=my-secret-abc123
   MAX_WEBHOOK_HOST=0.0.0.0
   MAX_WEBHOOK_PORT=8646
   MAX_WEBHOOK_PATH=/max/webhook
   ```
7. Поднимите публичный HTTPS-туннель/обратный прокси на `http://127.0.0.1:8646`
   (MAX API обращается только к HTTPS на порт 443). Пример Caddy:
   ```caddyfile
   max.example.com {
       reverse_proxy 127.0.0.1:8646
   }
   ```
8. Перезапустите шлюз — адаптер сам зарегистрирует подписку с URL и секретом из
   шага 6 (`mixins/webhook.py:129–147`). Ручной curl нужен только если подписка
   создана извне: тогда URL, секрет и `update_types` должны совпадать с
   авторегистрацией, иначе секрет не будет совпадать с `MAX_WEBHOOK_SECRET`:
   ```bash
   curl -X POST "https://platform-api.max.ru/subscriptions" \
     -H "Authorization: $MAX_BOT_TOKEN" \
     -H "Content-Type: application/json" \
     -d "{\"url\":\"$MAX_WEBHOOK_URL\",\"update_types\":[\"message_created\",\"message_callback\",\"bot_started\",\"bot_added\"],\"secret\":\"$MAX_WEBHOOK_SECRET\"}"
   ```
   ⚠️ Ручная подписка при незаданном `MAX_WEBHOOK_URL` бесполезна: плагин
   стартует в long polling и удаляет её.
9. Проверьте, что активен именно webhook-режим:
   ```bash
   hermes gateway restart
   hermes gateway status
   curl http://localhost:8646/health
   # Ожидается: {"status":"ok"}
   curl "https://platform-api.max.ru/subscriptions" -H "Authorization: $MAX_BOT_TOKEN"
   # Ожидается подписка на ваш MAX_WEBHOOK_URL
   ```
   В логах шлюза должно быть `MAX: webhook on 0.0.0.0:8646/max/webhook`. Если там
   `MAX: long polling started` — `MAX_WEBHOOK_URL` не подхватился, и подписка
   будет удалена при старте.
10. Попросите пользователя отправить реальное сообщение MAX-боту и проверьте, отвечает ли Hermes.

## Голосовые сообщения (STT)

Транскрипция выполняется **ядром Hermes** (≥ 0.20.0) — плагин только скачивает и кэширует аудио:

1. Адаптер автоматически загружает голосовые в кэш; ядро транскрибирует их по конфигу `stt`
2. Провайдеры ядра: `local` (faster-whisper, бесплатно), `groq`, `openai` (whisper-1, gpt-transcribe), `mistral`, `xai`, `elevenlabs`
3. Настройка: `hermes tools` → категория STT, либо `config.yaml` → `stt` (для русского — `stt.language: ru`)

### Проблемы STT

- Секция `stt` в `config.yaml`: `enabled`, `provider`, `language`, `echo_transcripts`
- Модель `local` скачивается автоматически при первом использовании (~150 МБ)
- Если транскрипт не приходит — проверьте `stt.enabled` и язык (`stt.language`), см. README → «Голос не транскрибируется»

## Проблемы (общие)

- Используйте `Authorization: ***`, а не параметры запроса и не `Bearer <token>`.
- Вебхук должен быть HTTPS с доверенным сертификатом.
- Если настроен `secret`, MAX отправляет его как сырое значение в `X-Max-Bot-Api-Secret`; сравнивайте напрямую с constant-time сравнением.
- **🚨 КРИТИЧНО: Вебхук и Long Polling взаимоисключающи.** Если в MAX API существует подписка вебхука, `/updates` возвращает пустой ответ, и ВСЕ сообщения идут на URL вебхука. Даже после удаления `MAX_WEBHOOK_URL` из .env и перезапуска, устаревшая подписка сохраняется в MAX API и молча блокирует доставку сообщений.
  - **Исправление:** Удалите старую подписку:
    ```bash
    curl -X DELETE "https://platform-api.max.ru/subscriptions?url=<URL>" -H "Authorization: ***"
    ```
  - **Авто-исправление (v2.1.4+):** Плагин теперь автоматически очищает устаревшие подписки вебхуков при запуске в режиме long-polling.
  - **Предотвращение:** Не устанавливайте `MAX_WEBHOOK_URL` в .env, если у вас нет работающего обратного прокси перед портом 8646. При переключении режимов всегда сначала очищайте старую подписку. Если шаг 6 процедуры выполнен (заданы `MAX_WEBHOOK_URL` и `MAX_WEBHOOK_SECRET`), автоочистка не срабатывает — адаптер работает в webhook-режиме.
- Держите туннель/шлюз работающими при использовании MAX.
- MAX API требует юрисдикции Российской Федерации для регистрации бота.
