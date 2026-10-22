# Диагностика

См. [групповой доступ и получение ID](group-access_RU.md): доверенные/смешанные группы и значения первой установки.

## Маршрутизация команд сессий

Если `/sessions` показывает старый текст без кнопок, проверьте [настройки владельца](setup_RU.md). Стартовый лог `MAX: session routing` содержит обработчик, причину, лимит и default; лог команды `MAX: session command routing` содержит только обработчик и причину. Поисковая строка и ID в этих записях отсутствуют. Имя `MAX_CROSS_SESSION` сохранено для совместимости, но флаг включает и MAX-список с кнопками.

| Причина | Значение |
|---|---|
| `feature_disabled` | Флаг выключен; работает Core |
| `owners_missing` | Флаг включён, владельцы не заданы; работает Core |
| `caller_not_owner` | Пользователь не входит в список владельцев; команда остаётся Core |
| `owner_picker_ready` | Владелец использует picker плагина |
| `configuration_or_runtime_error` | Диагностический процесс не смог загрузить конфигурацию или runtime; проверьте Python, профиль и установку |

После установки выполните `python scripts/check-session-routing.py --user-id OWNER_MAX_USER_ID --load-profile-env` в окружении gateway. Exit 0 означает plugin-маршрут всех четырёх проверенных команд; exit 1 — Core, отказ или ошибку. Не публикуйте собственный ID вместе с командой в общих отчётах. Опция чтения .env явная и относится только к активному профилю. Скрипт блокирует сеть, не вызывает обработчик истории и не отправляет сообщения. Он не доказывает, что работающий процесс уже перезапущен; сопоставьте его со стартовым логом и ручной проверкой кнопок.

## Безопасная первичная проверка

Начните с проверок в режиме только для чтения. Никогда не передавайте токены бота в аргументах командной строки и не публикуйте их в логах. Параметр `--send` отправляет реальное исходящее сообщение и должен использоваться только с подтверждённым получателем.

`diagnose.sh` получает MAX-переменные только из окружения вызывающего процесса и не читает `.env` Hermes. Запускайте его в окружении выбранного профиля с `MAX_BOT_TOKEN` и нужными несекретными MAX-настройками. Отсутствующий токен считается ошибкой проверки. Скрипт не печатает содержимое логов и ответы API и передаёт заголовок авторизации в curl через stdin, не раскрывая его в аргументах процесса.

## diagnose.sh

Автоматический скрипт для проверки работоспособности MAX.

### Запуск

```bash
cd ~/.hermes/plugins/max-platform

# Базовая диагностика (без отправки сообщения)
./scripts/diagnose.sh

# Диагностика со smoke-тестом исходящего API (не полный E2E)
./scripts/diagnose.sh --send
```

### Что проверяется

| Пункт | Описание |
|---|---|
| 1 | Установка плагина |
| 2 | Подключение к MAX API |
| 3 | Активность (polling или webhook) |
| 4 | Проверка работоспособности |
| 5 | Подписки webhook |
| 6 | Валидация токена |
| 7 | Отправка E2E-сообщения |
| 8 | Настройка reasoning |

### Коды возврата

- `0` — всё в порядке
- `1` — обнаружены проблемы

## Топ-10 ошибок

### 1. 401 Invalid token

**Симптомы:**
- Нет записи `MAX: connected` в логах
- Нет активности

**Причина:** Недействительный или истёкший токен

**Решение:**
```bash
# Проверка токена
curl -s -X GET "https://platform-api2.max.ru/me" \
  -H "Authorization: $(grep MAX_BOT_TOKEN ~/.hermes/.env | cut -d= -f2-)"

# Перевыпустите токен в MAX для партнёров → Чат-боты → Настроить → Токен
# Обновите в ~/.hermes/.env
```

### 2. Webhook blocks polling

**Симптомы:**
- Long polling не работает
- `GET /updates` возвращает пустоту

**Причина:** Активная подписка webhook

**Решение:**
```bash
# Удаление подписки
curl -X DELETE "https://platform-api2.max.ru/subscriptions?url=<URL>" \
  -H "Authorization: ***"

# Проверка подписок
curl -H "Authorization: ***" \
  https://platform-api2.max.ru/subscriptions
```

### 3. STT returns empty

**Симптомы:**
- Голосовые сообщения не расшифровываются
- В чат приходит `🎙️ ""` или агент видит `[voice message could not be transcribed automatically; the audio is available at: …]`
- В логах ядра: `Voice transcription failed for <path>: <error>`

**Причина:** расшифровку выполняет ядро Hermes (не плагин): STT отключён
(`stt.enabled`), не задан язык, у выбранного провайдера нет ключа API или
отсутствует faster-whisper для локального провайдера (`local`).

**Решение:**
```bash
# 1. Проверьте секцию stt: enabled, language, provider
grep -A8 "^stt:" ~/.hermes/config.yaml

# 2. Настройте интерактивно (категория 🎙️ Speech-to-Text)
hermes tools

# 3. Для provider: local — установите пакет в окружение Python шлюза Hermes
python -m pip install faster-whisper

# 4. Убедитесь, что адаптер действительно скачал аудиофайл
ls -la ~/.hermes/cache/audio/

# 5. Ошибки транскрипции в ядре
grep -i "transcri" ~/.hermes/logs/gateway.log | tail -20
```

Выделенный stt-venv, `scripts/transcribe_audio.py` и переменные `MAX_STT_*` не
используются: плагин лишь скачивает и кэширует аудио, а настройки STT находятся в
`config.yaml` ядра. Для русского языка укажите `stt.language: ru` (по умолчанию в ядре `"en"`).

### 4. Tables not rendering

**Симптомы:**
- Установлен `MAX_TABLE_AS_IMAGE=true`
- Таблицы приходят в виде текста

**Причина:** Отсутствует Playwright/Chromium (основной рендерер HTML→PNG) и/или
отсутствует Pillow (fallback). Оба должны быть установлены в Python (venv) шлюза Hermes.

**Решение:**
```bash
# Каталог плагина (активный профиль Hermes) и интерпретатор его venv:
cd "${HERMES_HOME:-$HOME/.hermes}/plugins/max-platform"
HERMES_PY="$(head -1 "$(command -v hermes)" | sed 's|^#!||')"

# Диагностика: чего не хватает?
"$HERMES_PY" scripts/setup-playwright.py --check-only

# Установка недостающего (идемпотентно):
"$HERMES_PY" scripts/setup-playwright.py
# или вручную:
"$HERMES_PY" -m pip install 'playwright==1.62.0'
"$HERMES_PY" -m playwright install chromium

# Fallback-рендерер без браузера:
"$HERMES_PY" -m pip install Pillow

hermes gateway restart
```

**Альтернатива:** `MAX_AUTO_INSTALL_PLAYWRIGHT=true` — плагин сам установит
пакет и Chromium при первом рендеринге таблицы (требуется доступ в сеть).

### 5. Reasoning not displayed

**Симптомы:**
- Выбрана модель с поддержкой reasoning, но блок рассуждений не появляется.

**Причина:** Модель может не генерировать reasoning, либо произошёл сбой при финальном редактировании сообщения в MAX. `streaming.fresh_final_after_seconds` — настройка ядра только для Telegram; задание её в блоке `max:` не влияет на MAX.

**Решение:** Проверьте выбранную модель и логи шлюза на наличие ошибок редактирования. MAX включает reasoning в итоговое редактирование сообщения, если модель его возвращает; не задавайте `fresh_final_after_seconds` в качестве обхода для MAX.

### 6. SSL fails silently

**Симптомы:**
- Webhook не работает
- В логах нет ошибок

**Причина:** Сертификат центра сертификации (CA) MAX API отсутствует в стандартных наборах Python/ОС.

**Решение:** плагин не предоставляет переключателя для отключения проверки SSL — переменной `MAX_INSECURE_SSL` в коде (`adapter.py`) нет, поэтому такой «фикс» не применим. Добавьте CA в доверенные хранилища:

```bash
# Вариант 1: общесистемное хранилище (пример Debian/Ubuntu)
sudo cp max-ca.crt /usr/local/share/ca-certificates/ && sudo update-ca-certificates

# Вариант 2: только для процесса Hermes
# SSL_CERT_FILE=/path/to/ca-bundle.crt hermes gateway restart

# Проверка цепочки сертификатов до API
curl -v https://platform-api2.max.ru/me 2>&1 | grep -i "SSL\|certificate"
```

### 7. MAX API auth format error

**Симптомы:**
- 401 Malformed access token

**Причина:** Использование `Bearer <token>` вместо прямого токена

**Решение:**
```bash
# Неверно
Authorization: Bearer ***

# Верно
Authorization: ***
```

### 8. Callback not received

**Симптомы:**
- Кнопки отображаются
- Callback не обрабатывается

**Причина:** Неверный chat_id в callback

**Решение:**
```python
# Проверьте код обработки callback
chat_id = message.get("recipient", {}).get("chat_id")
```

### 9. Messages duplicated

**Симптомы:**
- Одно сообщение → два ответа

**Причина:** Одновременно активны webhook и polling

**Решение:**
```bash
# Убедитесь, что активен только один режим
# Проверьте подписки
curl -H "Authorization: ***" \
  https://platform-api2.max.ru/subscriptions
```

### 10. Gateway won't restart

**Симптомы:**
- `hermes gateway restart` зависает
- Шлюз не запускается

**Причина:** Блокировка рестарта изнутри процесса шлюза

**Решение:**
```bash
# Используйте внешний терминал
sudo systemctl restart hermes-gateway

# Или из песочницы
```

## Логи

Перед проверкой подтвердите окружение и режим:

```bash
printf 'HERMES_HOME=%s\n' "${HERMES_HOME:-$HOME/.hermes}"
printf 'MAX_WEBHOOK_PORT=%s\n' "${MAX_WEBHOOK_PORT:-8646}"
command -v python
python -c 'import sys; print(sys.executable)'
```

Эндпоинт `/health` существует только в режиме webhook и проверяет локальный HTTP-эндпоинт. `GET /me` проверяет только smoke-маршрут API. Полный E2E требует реального входящего сообщения MAX, обработки ядром Hermes и исходящего ответа; подтвердите все три этапа в логах и в MAX.

### Где искать

**Linux systemd:**
```bash
journalctl -u hermes-gateway -f
```

Для пользовательской службы используйте `journalctl --user -u hermes-gateway -f`. В macOS нет `journalctl` или `systemctl`; проверяйте файл, настроенный через launchd/ваш менеджер процессов, либо запускайте шлюз на переднем плане.

**Файл:**
```bash
tail -f ~/.hermes/logs/gateway.log
```

### Полезные команды

```bash
# Последние ошибки
journalctl -u hermes-gateway -p err -n 50

# Фильтрация по MAX
journalctl -u hermes-gateway -g "MAX:" -f

# Время запуска
journalctl -u hermes-gateway --since "10 minutes ago"
```

## Webhook или Polling

### Конфликты

**Webhook и long polling взаимно исключают друг друга.** Если подписка webhook существует, MAX API отправляет ВСЕ обновления на URL webhook.

### Миграция

**Webhook → Polling:**
1. Удалите `MAX_WEBHOOK_URL` из `.env`
2. Перезапустите шлюз
3. Плагин автоматически удалит подписки webhook

**Polling → Webhook:**
1. Добавьте `MAX_WEBHOOK_URL` в `.env`
2. Перезапустите шлюз
3. Плагин автоматически зарегистрирует webhook

### Ручная очистка

Если автоматическая очистка не сработала:
```bash
curl -X DELETE "https://platform-api2.max.ru/subscriptions?url=<URL>" \
  -H "Authorization: ***"
```
