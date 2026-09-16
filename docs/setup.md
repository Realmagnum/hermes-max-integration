# Настройка

## Переменные окружения

Плагин не имеет собственного файла настроек: значения берутся из окружения процесса Hermes (`.env`) и из `config.yaml` ядра. Приоритет для каждого параметра: **переменная окружения → `platforms.max.extra.*` в `config.yaml` → встроенное значение по умолчанию**. Исключение — `MAX_ALLOWED_USERS`: значения из окружения и из конфига **объединяются**, а не перезаписывают друг друга.

Тип `bool` принимает `1`, `true`, `yes`, `y`, `on` (регистр не важен); любое другое непустое значение трактуется как «выключено».

| Переменная | Обязательная | Тип | По умолчанию | Описание |
|------------|--------------|-----|--------------|----------|
| `MAX_BOT_TOKEN` | ✅ | строка | — | Токен бота MAX |
| `MAX_WEBHOOK_URL` | ❌ | строка | пусто | Публичный HTTPS URL; непустое значение включает webhook-режим |
| `MAX_WEBHOOK_SECRET` | ❌ | строка | пусто | Ожидаемое значение заголовка `X-Max-Bot-Api-Secret` |
| `MAX_WEBHOOK_HOST` | ❌ | строка | `0.0.0.0` | Хост webhook-сервера |
| `MAX_WEBHOOK_PORT` | ❌ | целое | `8646` | Порт webhook-сервера (нечисловое значение — ошибка при старте) |
| `MAX_WEBHOOK_PATH` | ❌ | строка | `/max/webhook` | Путь webhook-сервера |
| `MAX_ALLOWED_USERS` | ❌ | список через запятую | пусто | Белый список user_id; объединяется со списком из конфига |
| `MAX_ALLOW_ALL_USERS` | ❌ | bool | `false` | Разрешить любого пользователя |
| `MAX_GROUP_POLICY` | ❌ | строка | `allowlist` | Политика групповых сообщений: `allowlist` — проверять списки, `closed` — игнорировать группы |
| `MAX_GROUP_ALLOWED_USERS` | ❌ | список через запятую | пусто | user_id, разрешённые в группах |
| `MAX_GROUP_ALLOWED_CHATS` | ❌ | список через запятую | пусто | chat_id групп, разрешённых для бота |
| `MAX_HOME_CHANNEL` | ❌ | строка | пусто | Канал по умолчанию для cron/send_message |
| `MAX_HOME_CHANNEL_NAME` | ❌ | строка | `Max Home` | Имя канала по умолчанию; учитывается только если задан `MAX_HOME_CHANNEL` |
| `MAX_TABLE_AS_IMAGE` | ❌ | bool | `false` | Отрисовка таблиц как PNG (HTML→PNG через Playwright, фоллбэк — Pillow) |
| `MAX_AUTO_INSTALL_PLAYWRIGHT` | ❌ | bool | `false` | Авто-установка Playwright + Chromium при первом рендере (нужен доступ в сеть, 1–2 мин) |
| `MAX_CROSS_SESSION` | ❌ | bool | `true` | Кросс-платформенные /sessions и /resume |

Пример `.env`:

```bash
# Минимум — long polling
MAX_BOT_TOKEN=<токен>

# Webhook-режим (дополнительно)
MAX_WEBHOOK_URL=https://your-domain.com/max/webhook
MAX_WEBHOOK_SECRET=<секрет>

# Ограничение доступа и режимы
MAX_ALLOWED_USERS=95825064
MAX_GROUP_POLICY=allowlist
MAX_TABLE_AS_IMAGE=true
MAX_CROSS_SESSION=false
```

Оговорка про `MAX_GROUP_POLICY=allowlist`: списки `MAX_GROUP_ALLOWED_USERS`/`MAX_GROUP_ALLOWED_CHATS` проверяются по OR, и пустой список означает «без ограничения». При обоих пустых списках групповые сообщения не фильтруются (открытый пункт SEC-06 в BACKLOG).

### Переменные вспомогательных скриптов

`scripts/diagnose.sh` дополнительно читает `MAX_HOME_CHANNEL_THREAD_ID` как запасную цель для `--send`. Python-код плагина эту переменную не использует.

## Конфигурация ядра

Всё, что не перечислено выше, задаётся в `config.yaml` ядра Hermes. Ключи `platforms.max.extra` дублируют переменные окружения (приоритет ниже окружения):

| Ключ `platforms.max` | Тип | По умолчанию | Эквивалент в окружении |
|----------------------|-----|--------------|------------------------|
| `token` | строка | — | `MAX_BOT_TOKEN` |
| `extra.host` | строка | `0.0.0.0` | `MAX_WEBHOOK_HOST` |
| `extra.port` | целое | `8646` | `MAX_WEBHOOK_PORT` |
| `extra.path` | строка | `/max/webhook` | `MAX_WEBHOOK_PATH` |
| `extra.webhook_url` | строка | пусто | `MAX_WEBHOOK_URL` |
| `extra.webhook_secret` | строка | пусто | `MAX_WEBHOOK_SECRET` |
| `extra.allowed_users` | список | `[]` | `MAX_ALLOWED_USERS` |
| `extra.allow_all_users` | bool | `false` | `MAX_ALLOW_ALL_USERS` |
| `extra.home_channel` | `{chat_id, name}` | — | `MAX_HOME_CHANNEL`, `MAX_HOME_CHANNEL_NAME` |
| `extra.group_policy` | строка | `allowlist` | `MAX_GROUP_POLICY` |
| `extra.group_allow_from` | список | `[]` | `MAX_GROUP_ALLOWED_USERS` |
| `extra.group_allow_chats` | список | `[]` | `MAX_GROUP_ALLOWED_CHATS` |
| `extra.cross_session` | bool | `true` | `MAX_CROSS_SESSION` |

Транскрипция голоса настраивается не здесь, а в секции `stt` конфига ядра — см. раздел STT в `docs/features.md`.

## Внутренние константы

Эти значения зашиты в код и переменными окружения не переопределяются. Они перечислены, чтобы их не искали в `.env`:

| Константа | Значение | Где определено |
|-----------|----------|----------------|
| Базовый URL API (`MAX_API_BASE`) | `https://platform-api.max.ru` | `adapter.py`, `mixins/*.py` |
| Лимит длины сообщения (`MAX_MESSAGE_LENGTH`) | 4000 символов (лимит MAX API) | `adapter.py`, `mixins/*.py` |
| Лимит исходящего файла (`MAX_FILE_SIZE`) | 50 МиБ | `mixins/media_upload.py` |
| Лимит тела webhook (`WEBHOOK_MAX_BODY_BYTES`) | 1 МиБ | `mixins/webhook.py` |
| `POLL_TIMEOUT` / `POLL_ERROR_DELAY` / `UPLOAD_DELAY` | 5 с / 5 с / 2 с | `adapter.py` |
| Каталог кэша аудио | `$HERMES_HOME/audio_cache` (права 0700) | `adapter.py` |
| Каталог кэша PNG-таблиц | `$HERMES_HOME/table_images` | `adapter.py` |
| Таблица как текст: ширина колонки | не более 38 символов | `mixins/table_renderer.py` |
| Таблица как PNG: размеры полотна | ~1200 px по ширине, `max-width: 820px`, шрифт 14 px (HTML) / 18–20 px (Pillow) | `mixins/table_renderer.py` |

Базовый URL зашит как `platform-api.max.ru`; рекомендованный документацией MAX домен `platform-api2.max.ru` в этой версии не используется (см. DOC-10 в BACKLOG).

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
