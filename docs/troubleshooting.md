# Диагностика

## diagnose.sh

Автоматизированный скрипт для проверки работоспособности MAX.

### Запуск

```bash
cd ~/.hermes/plugins/max-platform

# Базовая диагностика (без отправки сообщения)
./scripts/diagnose.sh

# Диагностика с исходящим API smoke-тестом (не полный E2E)
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
- В чат приходит `🎙️ ""` либо агент видит `[voice message could not be transcribed automatically; the audio is available at: …]`
- В логах ядра: `Voice transcription failed for <path>: <error>`

**Причина:** транскрибирует ядро Hermes (не плагин): STT выключен (`stt.enabled`), не
задан язык, у выбранного провайдера нет ключа либо не установлен faster-whisper для
провайдера `local`.

**Решение:**
```bash
# 1. Проверить секцию stt: enabled, language, provider
grep -A8 "^stt:" ~/.hermes/config.yaml

# 2. Настроить интерактивно (категория 🎙️ Speech-to-Text)
hermes tools

# 3. Для provider: local — поставить пакет в Python шлюза Hermes
python -m pip install faster-whisper

# 4. Убедиться, что аудио скачалось адаптером
ls -la ~/.hermes/cache/audio/

# 5. Ошибки ядра по транскрибации
grep -i "transcri" ~/.hermes/logs/gateway.log | tail -20
```

Отдельный stt-venv, `scripts/transcribe_audio.py` и переменные `MAX_STT_*` не
используются: плагин только скачивает и кэширует аудио, а настройки STT живут в
`config.yaml` ядра. Для русского языка задайте `stt.language: ru` (дефолт ядра — `"en"`).

### 4. Таблицы не рендерятся

**Симптомы:**
- `MAX_TABLE_AS_IMAGE=true` установлен
- Таблицы приходят текстом

**Причина:** нет Playwright/Chromium (основной рендер HTML→PNG) и/или нет Pillow
(фоллбэк). Оба должны быть установлены в Python шлюза Hermes (venv).

**Решение:**
```bash
# Каталог плагина (активный профиль Hermes) и Python его venv:
cd "${HERMES_HOME:-$HOME/.hermes}/plugins/max-platform"
HERMES_PY="$(head -1 "$(command -v hermes)" | sed 's|^#!||')"

# Диагностика: что отсутствует?
"$HERMES_PY" scripts/setup-playwright.py --check-only

# Установить недостающее (идемпотентно):
"$HERMES_PY" scripts/setup-playwright.py
# либо вручную:
"$HERMES_PY" -m pip install 'playwright>=1.40'
"$HERMES_PY" -m playwright install chromium

# Фоллбэк-рендер без браузера:
"$HERMES_PY" -m pip install Pillow

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

**Причина:** CA MAX API отсутствует в стандартных бандлах Python/ОС.

**Решение:** плагин не предоставляет переключателя для отключения проверки SSL — переменной `MAX_INSECURE_SSL` в коде нет (`adapter.py`), и такой способ «лечения» неприменим. Добавьте CA в доверенные:

```bash
# Вариант 1: системное хранилище (пример для Debian/Ubuntu)
sudo cp max-ca.crt /usr/local/share/ca-certificates/ && sudo update-ca-certificates

# Вариант 2: только для процесса Hermes
# SSL_CERT_FILE=/path/to/ca-bundle.crt hermes gateway restart

# Проверка цепочки до API
curl -v https://platform-api.max.ru/me 2>&1 | grep -i "SSL\|certificate"
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

Перед проверкой сверяйте окружение и режим:

```bash
printf 'HERMES_HOME=%s\n' "${HERMES_HOME:-$HOME/.hermes}"
printf 'MAX_WEBHOOK_PORT=%s\n' "${MAX_WEBHOOK_PORT:-8646}"
command -v python
python -c 'import sys; print(sys.executable)'
```

`/health` существует только в webhook-режиме и проверяет локальный HTTP endpoint. `GET /me` проверяет только API smoke. Полный E2E требует реального входящего сообщения MAX, обработки Hermes core и исходящего ответа; подтвердите все три этапа по логам и в MAX.

### Где искать

**Linux systemd:**
```bash
journalctl -u hermes-gateway -f
```

Для user service используйте `journalctl --user -u hermes-gateway -f`. На macOS `journalctl` и `systemctl` отсутствуют: смотрите файл, указанный вашим launchd/процесс-менеджером, или запускайте gateway в foreground.

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
