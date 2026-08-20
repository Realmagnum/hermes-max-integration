# Диагностика

## diagnose.sh

Автоматизированный скрипт для проверки работоспособности MAX.

### Запуск

```bash
cd ~/.hermes/plugins/max-platform

# Базовая диагностика (без отправки сообщения)
./scripts/diagnose.sh

# Полная диагностика с E2E-тестом
./scripts/diagnose.sh --send
```

### Что проверяет

| Пункт | Описание |
|-------|----------|
| 1 | Установка плагина |
| 2 | Подключение к MAX API |
| 3 | Активность (polling или webhook) |
| 4 | Health check |
| 5 | Webhook подписки |
| 6 | Валидация токена |
| 7 | E2E отправка сообщения |
| 8 | Настройка reasoning |

### Exit code

- `0` — всё ок
- `1` — есть проблемы

## Топ-10 ошибок

### 1. 401 Invalid token

**Симптомы:**
- Нет `MAX: connected` в логах
- Нет активности

**Причина:** Неверный или истёкший токен

**Решение:**
```bash
# Проверить токен
curl -s -X GET "https://platform-api.max.ru/me" \
  -H "Authorization: $(grep MAX_BOT_TOKEN ~/.hermes/.env | cut -d= -f2-)"

# Перегенерировать токен в MAX Partners → Чат-боты → Настроить → Токен
# Обновить в ~/.hermes/.env
```

### 2. Webhook blocks polling

**Симптомы:**
- Long polling не работает
- `GET /updates` возвращает пустоту

**Причина:** Активная webhook-подписка

**Решение:**
```bash
# Удалить подписку
curl -X DELETE "https://platform-api.max.ru/subscriptions?url=<URL>" \
  -H "Authorization: ваш_токен"

# Проверить подписки
curl -H "Authorization: ваш_токен" \
  https://platform-api.max.ru/subscriptions
```

### 3. STT возвращает пустоту

**Симптомы:**
- Голосовые сообщения не транскрибируются
- В логах: `STT returned empty transcription`

**Причина:** Нет faster-whisper или модель не загружена

**Решение:**
```bash
# Проверить venv
ls ~/.hermes/stt-venv/lib/python*/site-packages/whisper/

# Установить модель
~/.hermes/stt-venv/bin/pip install faster-whisper

# Проверить файл
ls -la ~/.hermes/audio_cache/max_audio_*.ogg
```

### 4. Таблицы не рендерятся

**Симптомы:**
- `MAX_TABLE_AS_IMAGE=true` установлен
- Таблицы приходят текстом

**Причина:** нет Playwright/Chromium (основной рендер HTML→PNG) и/или нет Pillow
(фоллбэк). Оба должны быть установлены в Python шлюза Hermes (venv).

**Решение:**
```bash
# Диагностика: что отсутствует?
python scripts/setup-playwright.py --check-only

# Установить недостающее (идемпотентно):
python scripts/setup-playwright.py
# либо вручную:
python -m pip install 'playwright>=1.40'
python -m playwright install chromium

# Фоллбэк-рендер без браузера:
python -m pip install Pillow

hermes gateway restart
```

**Альтернатива:** `MAX_AUTO_INSTALL_PLAYWRIGHT=true` — плагин сам поставит
пакет и Chromium при первом рендере таблицы (нужен доступ в сеть).

### 5. Reasoning не отображается

**Симптомы:**
- Reasoning-модель используется
- Блок рассуждений не виден

**Причина:** Быстрая модель или неправильная настройка

**Решение:**
```bash
# Проверить модель
grep 'default:' ~/.hermes/config.yaml | head -1

# Проверить настройку
grep -A3 'max:' ~/.hermes/config.yaml | grep fresh_final
# Должно быть: fresh_final_after_seconds: 10
```

### 6. SSL fails silently

**Симптомы:**
- Webhook не работает
- Нет ошибок в логах

**Причина:** MinCifry CA не в стандартных бандлах

**Решение:**
```bash
# Для тестов
MAX_INSECURE_SSL=true

# Для production — добавить CA в систему
```

### 7. MAX API auth format error

**Симптомы:**
- 401 Malformed access token

**Причина:** Использование `Bearer <token>` вместо raw token

**Решение:**
```bash
# Неправильно
Authorization: Bearer <token>

# Правильно
Authorization: <token>
```

### 8. Callback не приходит

**Симптомы:**
- Кнопки отображаются
- Callback не обрабатывается

**Причина:** Неправильный chat_id в callback

**Решение:**
```python
# Проверить код обработки callback
chat_id = message.get("recipient", {}).get("chat_id")
```

### 9. Сообщения дублируются

**Симптомы:**
- Одно сообщение → два ответа

**Причина:** Webhook + polling одновременно

**Решение:**
```bash
# Убедиться что только один режим активен
# Проверить подписки
curl -H "Authorization: ваш_токен" \
  https://platform-api.max.ru/subscriptions
```

### 10. Gateway не перезапускается

**Симптомы:**
- `hermes gateway restart` зависает
- Gateway не запускается

**Причина:** Блокировка изнутри gateway

**Решение:**
```bash
# Использовать внешний терминал
sudo systemctl restart hermes-gateway

# Или из sandbox
```

## Логи

### Где искать

**Journald:**
```bash
journalctl -u hermes-gateway -f
```

**Файл:**
```bash
tail -f ~/.hermes/logs/gateway.log
```

### Полезные команды

```bash
# Последние ошибки
journalctl -u hermes-gateway -p err -n 50

# Фильтр по MAX
journalctl -u hermes-gateway -g "MAX:" -f

# Время старта
journalctl -u hermes-gateway --since "10 minutes ago"
```

## Webhook vs Polling

### Конфликты

**Вебхук и long polling взаимоисключаемы.** Если существует webhook-подписка, MAX API направляет ВСЕ обновления на URL вебхука.

### Миграция

**Webhook → Polling:**
1. Удалить `MAX_WEBHOOK_URL` из `.env`
2. Перезапустить gateway
3. Плагин автоматически удалит webhook-подписку

**Polling → Webhook:**
1. Добавить `MAX_WEBHOOK_URL` в `.env`
2. Перезапустить gateway
3. Плагин автоматически зарегистрирует webhook

### Ручная очистка

Если автоочистка не сработала:
```bash
curl -X DELETE "https://platform-api.max.ru/subscriptions?url=<URL>" \
  -H "Authorization: ваш_токен"
```
