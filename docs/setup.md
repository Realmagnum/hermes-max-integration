# Настройка

## Переменные окружения

| Переменная | Обязательная | По умолчанию | Описание |
|------------|--------------|--------------|----------|
| `MAX_BOT_TOKEN` | ✅ | — | Токен бота MAX |
| `MAX_API_BASE` | ❌ | `https://platform-api.max.ru` | Базовый URL API (документация рекомендует `https://platform-api2.max.ru`) |
| `MAX_WEBHOOK_HOST` | ❌ | `0.0.0.0` | Хост webhook |
| `MAX_WEBHOOK_PORT` | ❌ | `8646` | Порт webhook |
| `MAX_WEBHOOK_PATH` | ❌ | `/max/webhook` | Путь webhook |
| `MAX_WEBHOOK_SECRET` | ❌ | — | Секрет для `X-Max-Bot-Api-Secret` |
| `MAX_WEBHOOK_URL` | ❌ | — | Публичный HTTPS URL (включает webhook-режим) |
| `MAX_ALLOWED_USERS` | ❌ | — | Белый список пользователей (через запятую) |
| `MAX_ALLOW_ALL_USERS` | ❌ | `false` | Разрешить всех пользователей |
| `MAX_GROUP_ALLOWED_USERS` | ❌ | — | ID пользователей, разрешённых в группах |
| `MAX_GROUP_ALLOWED_CHATS` | ❌ | — | ID групп, разрешённых для бота |
| `MAX_STT_ENABLED` | ❌ | `true` | Автозагрузка голоса для STT |
| `MAX_STT_VENV` | ❌ | `~/.hermes/stt-venv` | Путь к venv для faster-whisper |
| `MAX_TABLE_AS_IMAGE` | ❌ | `false` | Отрисовка таблиц как PNG (HTML→PNG через Playwright, фоллбэк — Pillow) |
| `MAX_AUTO_INSTALL_PLAYWRIGHT` | ❌ | `false` | Авто-установка Playwright + Chromium при первом рендере |
| `MAX_HOME_CHANNEL` | ❌ | — | Канал по умолчанию для cron/send_message |
| `MAX_HOME_CHANNEL_NAME` | ❌ | — | Имя канала по умолчанию |
| `MAX_INSECURE_SSL` | ❌ | `false` | Отключить проверку SSL (для тестов) |
| `MAX_CROSS_SESSION` | ❌ | `false` | Кросс-платформенные /sessions и /resume; требуется явный opt-in |
| `MAX_CROSS_SESSION_USERS` | ❌ | — | Владельцы, которым доступны межплатформенные сессии |
| `MAX_GROUP_POLICY` | ❌ | `allowlist` | Политика групп: `allowlist` или `open` |
| `MAX_WEBHOOK_INSECURE_DEV` | ❌ | `false` | Разрешить webhook без секрета только на loopback для разработки |
| `MAX_EDIT_THROTTLE` | ❌ | `0.2` | Минимальный интервал streaming-edit одного сообщения |
| `MAX_DEDUP_TTL` | ❌ | `300` | TTL дедупликации входящих событий, секунд |
| `MAX_DEDUP_MAX` | ❌ | `4096` | Максимум ключей дедупликации |
| `MAX_QUEUE_MAXSIZE` | ❌ | `100` | Максимальный размер очереди входящих событий |
| `MAX_MAX_CONCURRENCY` | ❌ | `8` | Параллелизм обработки входящих событий |
| `MAX_OVERLOAD_POLICY` | ❌ | `drop-oldest` | Политика очереди: `drop-oldest` или `drop-newest` |
| `MAX_DOWNLOAD_ALLOWED_HOSTS` | ❌ | — | Строгий operator allowlist download-hosts |
| `MAX_TRUSTED_DOWNLOAD_HOSTS` | ❌ | `.max.ru,.oneme.ru` | HTTPS-хосты, которым допустим `Authorization` |
| `MAX_INBOUND_MEDIA_MAX_BYTES` | ❌ | `52428800` | Лимит одного входящего вложения, байт |
| `MAX_INBOUND_MEDIA_TOTAL_BYTES` | ❌ | `104857600` | Суммарный лимит вложений update, байт |
| `MAX_INBOUND_MEDIA_MAX_ATTACHMENTS` | ❌ | `10` | Лимит числа вложений update |
| `MAX_INBOUND_MEDIA_TIMEOUT` | ❌ | `30` | Таймаут download входящего медиа, секунд |
| `MAX_INBOUND_MEDIA_CONCURRENCY` | ❌ | `4` | Параллелизм download входящего медиа |

## Внутренние константы

| Константа | Значение | Назначение |
|---|---|---|
| API base URL | `platform-api.max.ru` | Адрес MAX API; не является настройкой окружения |
| Message length limit | `4000` | Максимальная длина одного текстового сообщения |
| Outbound file limit | `50 * 1024 * 1024` | Лимит исходящего файла |
| Webhook body limit | `1_048_576` | Максимальный размер тела webhook |
| Poll timeout | `POLL_TIMEOUT` | Базовый timeout polling |
| Table column cap | `38` | Лимит столбцов текстовой таблицы |
| Table PNG width | `1200` | Ширина canvas PNG-таблицы |

## Ключи в блоке `platforms.max`

Ключи YAML передаются в адаптер как `extra`; значения окружения имеют приоритет.

| Ключ в блоке `platforms.max` | Эквивалент окружения | Назначение |
|---|---|---|
| `token` | `MAX_BOT_TOKEN` | Токен бота |
| `host` | `MAX_WEBHOOK_HOST` | Хост webhook |
| `port` | `MAX_WEBHOOK_PORT` | Порт webhook |
| `path` | `MAX_WEBHOOK_PATH` | Путь webhook |
| `webhook_secret` | `MAX_WEBHOOK_SECRET` | Секрет webhook |
| `webhook_url` | `MAX_WEBHOOK_URL` | Публичный URL webhook |
| `webhook_insecure_dev` | `MAX_WEBHOOK_INSECURE_DEV` | Разрешить secretless webhook только на loopback для разработки |
| `allowed_users` | `MAX_ALLOWED_USERS` | Пользовательский allowlist |
| `allow_all_users` | `MAX_ALLOW_ALL_USERS` | Явно разрешить всех пользователей |
| `group_policy` | `MAX_GROUP_POLICY` | Политика групп: `allowlist` или `open` |
| `group_allow_from` | `MAX_GROUP_ALLOWED_USERS` | Разрешённые пользователи в группах |
| `group_allow_chats` | `MAX_GROUP_ALLOWED_CHATS` | Разрешённые группы |
| `cross_session` | `MAX_CROSS_SESSION` | Включить межплатформенные сессии |
| `cross_session_users` | `MAX_CROSS_SESSION_USERS` | Владельцы, допущенные к межплатформенным сессиям |
| `home_channel` | `MAX_HOME_CHANNEL` | Адресат cron/send_message |
| `table_as_image` | `MAX_TABLE_AS_IMAGE` | Рендерить markdown-таблицы как PNG |
| `edit_throttle` | `MAX_EDIT_THROTTLE` | Минимальный интервал streaming-edit |
| `dedup_ttl` | `MAX_DEDUP_TTL` | TTL дедупликации входящих событий |
| `overload_policy` | `MAX_OVERLOAD_POLICY` | Поведение очереди при перегрузке |
| `download_allowed_hosts` | `MAX_DOWNLOAD_ALLOWED_HOSTS` | Строгий операторский allowlist download-hosts |
| `trusted_download_hosts` | `MAX_TRUSTED_DOWNLOAD_HOSTS` | HTTPS-хосты, которым допустим `Authorization` |
| `inbound_media_max_bytes` | `MAX_INBOUND_MEDIA_MAX_BYTES` | Лимит одного входящего вложения |
| `inbound_media_total_bytes` | `MAX_INBOUND_MEDIA_TOTAL_BYTES` | Суммарный лимит вложений update |
| `inbound_media_max_attachments` | `MAX_INBOUND_MEDIA_MAX_ATTACHMENTS` | Лимит числа вложений update |
| `inbound_media_timeout` | `MAX_INBOUND_MEDIA_TIMEOUT` | Таймаут download входящего медиа |
| `inbound_media_concurrency` | `MAX_INBOUND_MEDIA_CONCURRENCY` | Параллелизм download входящего медиа |

## Режимы подключения

Плагин поддерживает два режима получения сообщений от MAX API. Режим определяется единственной переменной — **`MAX_WEBHOOK_URL`**:

| `MAX_WEBHOOK_URL` | Режим | Механизм |
|---|---|---|
| Не задан (пуст) | **Long polling** (по умолчанию) | Цикличный `GET /updates?timeout=5&marker=...` |
| Задан HTTPS URL | **Webhook** | aiohttp сервер на порту 8646, регистрация `POST /subscriptions` |

Выбор происходит в коде `connect()` одной строкой: `self._use_webhook = bool(self._webhook_url)`.

### Long polling (по умолчанию)

```bash
# Просто установить токен
MAX_BOT_TOKEN=ваш_токен
```

Long polling идеален для:
- Локальной разработки
- Тестирования
- Случаев, когда нет публичного HTTPS

### Webhook

```bash
MAX_BOT_TOKEN=ваш_токен
MAX_WEBHOOK_URL=https://your-domain.com/max/webhook
MAX_WEBHOOK_SECRET=your-secret
```

Webhook требуется для production. Нужен публичный HTTPS URL.

> **Официально (dev.max.ru/docs-api, сверено 2026-09-16):** MAX принимает события только через Webhook; Long Polling ограничен по скорости и сроку хранения событий и «не подходит для production-окружения». С 25 мая 2026 не поддерживаются HTTP-webhook и самоподписанные сертификаты, endpoint обязан слушать **порт 443** (порт в URL не указывается) и отдавать HTTP 200 за 30 секунд. Плагин по умолчанию биндится на `8646` — наружу его публикует reverse proxy на 443 (см. примеры ниже).

## Webhook Setup

### Caddy

```caddyfile
your-domain.com {
    reverse_proxy localhost:8646
}
```

### Traefik

```yaml
http:
  routers:
    max-webhook:
      rule: "Host(`your-domain.com`)"
      service: max-gateway
  services:
    max-gateway:
      loadBalancer:
        servers:
          - url: "http://localhost:8646"
```

### Регистрация webhook

Плагин автоматически регистрирует webhook при старте. Для ручной регистрации:

```bash
curl -X POST "https://platform-api.max.ru/subscriptions" \
  -H "Authorization: ваш_токен" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://your-domain.com/max/webhook",
    "update_types": ["message_created", "message_callback", "bot_started"],
    "secret": "your-secret"
  }'
```

Проверить подписки:

```bash
curl -H "Authorization: ваш_токен" \
  https://platform-api.max.ru/subscriptions
```

## Переключение режимов

### Long polling → Webhook

```bash
# 1. Добавить в ~/.hermes/.env
MAX_WEBHOOK_URL=https://your-domain.com/max/webhook
MAX_WEBHOOK_SECRET=your-secret

# 2. Перезапустить
sudo systemctl restart hermes-gateway
```

При старте: `_start_webhook()` → открывает `0.0.0.0:8646` → регистрирует подписку в MAX API.

### Webhook → Long polling

```bash
# 1. Удалить или закомментировать MAX_WEBHOOK_URL (и MAX_WEBHOOK_SECRET)
# MAX_WEBHOOK_URL=...
# MAX_WEBHOOK_SECRET=...

# 2. Перезапустить
sudo systemctl restart hermes-gateway
```

При старте: `_start_polling()` → проверяет `GET /subscriptions`, **автоматически удаляет** старые webhook-подписки → запускает `_poll_loop`.

### 🚨 Важно

Если webhook-подписка была зарегистрирована **вручную** (curl'ом, не через плагин), автоочистка может её не найти. Удалите вручную:

```bash
curl -X DELETE "https://platform-api.max.ru/subscriptions?url=<URL>" \
  -H "Authorization: ваш_токен"
```

## Security

### Webhook Secret

Секрет отправляется MAX как сырое значение заголовка `X-Max-Bot-Api-Secret`, а не как HMAC-подпись. Плагин использует `secrets.compare_digest()` для timing-safe сравнения.

### Access Control

**Белый список пользователей:**

```bash
MAX_ALLOWED_USERS=123456789,987654321
```

**Разрешить всех:**

```bash
MAX_ALLOW_ALL_USERS=true
```

**Групповые политики:**

```bash
# Закрытая группа — только разрешённые пользователи
MAX_GROUP_POLICY=closed

# Белый список для группы
MAX_GROUP_ALLOWED_USERS=123456789
MAX_GROUP_ALLOWED_CHATS=-1001234567890
```

## Deployment

### Systemd

```bash
sudo systemctl enable hermes-gateway
sudo systemctl start hermes-gateway
sudo systemctl status hermes-gateway
```

### Проверка

```bash
# Health check
curl http://localhost:8646/health

# Статус плагина
hermes gateway status
```
