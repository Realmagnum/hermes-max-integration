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
| `MAX_TABLE_AS_IMAGE` | ❌ | `false` | Отрисовка таблиц как PNG через Pillow |
| `MAX_HOME_CHANNEL` | ❌ | — | Канал по умолчанию для cron/send_message |
| `MAX_HOME_CHANNEL_NAME` | ❌ | — | Имя канала по умолчанию |
| `MAX_INSECURE_SSL` | ❌ | `false` | Отключить проверку SSL (для тестов) |
| `MAX_CROSS_SESSION` | ❌ | `true` | Кросс-платформенные /sessions и /resume |

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

### Docker

См. [docs/docker.md](docs/docker.md) (в разработке).
