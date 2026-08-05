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
6. Настройте параметры привязки вебхука (по умолчанию):
   ```
   MAX_WEBHOOK_HOST=0.0.0.0
   MAX_WEBHOOK_PORT=8646
   MAX_WEBHOOK_PATH=/max/webhook
   ```
7. Создайте публичный HTTPS-туннель к `http://localhost:8646` или используйте HTTPS-домен пользователя.
8. Зарегистрируйте подписку:
   ```bash
   curl -X POST "https://platform-api.max.ru/subscriptions" \
     -H "Authorization: ***" \
     -H "Content-Type: application/json" \
     -d '{"url":"https://YOUR-DOMAIN/max/webhook","update_types":["message_created","message_callback","bot_started"],"secret":"CHANGE_ME_5_256_CHARS"}'
   ```
9. Перезапустите и проверьте:
   ```bash
   hermes gateway restart
   hermes gateway status
   curl http://localhost:8646/health
   ```
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
  - **Предотвращение:** Не устанавливайте `MAX_WEBHOOK_URL` в .env, если у вас нет работающего обратного прокси перед портом 8646. При переключении режимов всегда сначала очищайте старую подписку.
- Держите туннель/шлюз работающими при использовании MAX.
- MAX API требует юрисдикции Российской Федерации для регистрации бота.
