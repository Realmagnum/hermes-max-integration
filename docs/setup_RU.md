# Установка и конфигурация

Минимальный поддерживаемый Core: **>=0.21.4**. Минимальный поддерживаемый Python: **>=3.12** (проверено на Python 3.12 с minimum Core 0.21.4 и Python 3.14 с current Core; Python 3.11 не поддерживается). Точный релизный fixture `d337b736aa1e8ebecfab043842d13e4a2d2f48a3` использует Python 3.12: этот релиз требует Python >=3.11,<3.14. Более поздние baseline/current исходники используют Python 3.14. Изолированный кандидат с минимальным Core прошёл свою полную тестовую suite и проверку совместимости зависимостей 2026-10-13; датированные результаты и ограничения сохранены в [evidence приёмки каталога](specs/20261013-catalog-review-137501_RU.md).

Версия плагина определяется в `plugin.yaml`. Текущая suite собирает **796 тестов**; `python scripts/check-doc-claims.py` проверяет это число. Collection не означает прохождение тестов и не обновляет историческое evidence кандидатов.

Ответы агента MAX только с MEDIA markers получают первое имя файла через публичный output hook Core до доставки. Прямая отправка вложений также использует имя файла либо `File`, если имя недоступно; авторские подписи сохраняются. См. [контракты подписей](specs/20261013-media-caption_RU.md). Прямой `hermes send` и пути cron без этого hook по-прежнему требуют текста, например `report.pdf MEDIA:/path/report.pdf`.

## Переменные окружения

| Переменная | Обязательно | По умолчанию | Описание |
|----------|----------|---------|-------------|
| `MAX_BOT_TOKEN` | ✅ | — | Токен бота MAX |
| `MAX_WEBHOOK_HOST` | ❌ | `0.0.0.0` | Хост webhook |
| `MAX_WEBHOOK_PORT` | ❌ | `8646` | Порт webhook |
| `MAX_WEBHOOK_PATH` | ❌ | `/max/webhook` | Путь webhook |
| `MAX_WEBHOOK_SECRET` | ❌ | — | Секрет заголовка `X-Max-Bot-Api-Secret` |
| `MAX_WEBHOOK_URL` | ❌ | — | Публичный HTTPS URL (включает webhook-режим) |
| `MAX_ALLOWED_USERS` | ❌ | — | Список разрешённых пользователей через запятую |
| `MAX_ALLOW_ALL_USERS` | ❌ | `false` | Разрешить всех пользователей |
| `MAX_GROUP_ALLOWED_USERS` | ❌ | — | Пользователи, которым разрешён доступ в группы |
| `MAX_GROUP_ALLOWED_CHATS` | ❌ | — | Группы, в которых боту разрешено работать |
| `MAX_TABLE_AS_IMAGE` | ❌ | `false` | Рендерить таблицы в PNG (Playwright, запасной вариант Pillow) |
| `MAX_AUTO_INSTALL_PLAYWRIGHT` | ❌ | `false` | Автоматически установить Playwright и Chromium при первом рендере |
| `MAX_HOME_CHANNEL` | ❌ | — | Канал по умолчанию для cron/send_message |
| `MAX_HOME_CHANNEL_NAME` | ❌ | — | Имя канала по умолчанию |
| `MAX_CROSS_SESSION` | ❌ | `false` | Кроссплатформенные /sessions и /resume; требуется явное включение |
| `MAX_CROSS_SESSION_USERS` | ❌ | — | Владельцы, которым разрешены кроссплатформенные сессии |
| `MAX_GROUP_POLICY` | ❌ | `allowlist` | Политика групп: `allowlist` или `open` |
| `MAX_WEBHOOK_INSECURE_DEV` | ❌ | `false` | Разрешить webhook без секрета только на loopback в разработке |
| `MAX_EDIT_THROTTLE` | ❌ | `0.2` | Минимальный интервал между streaming-правками одного сообщения |
| `MAX_DEDUP_TTL` | ❌ | `300` | TTL дедупликации входящих событий в секундах |
| `MAX_DEDUP_MAX` | ❌ | `4096` | Максимальное число ключей дедупликации |
| `MAX_QUEUE_MAXSIZE` | ❌ | `100` | Максимальный размер очереди входящих событий |
| `MAX_MAX_CONCURRENCY` | ❌ | `8` | Параллелизм обработки входящих событий |
| `MAX_OVERLOAD_POLICY` | ❌ | `drop-oldest` | Политика очереди: `drop-oldest` или `drop-newest` |
| `MAX_DOWNLOAD_ALLOWED_HOSTS` | ❌ | — | Строгий список разрешённых оператором download-хостов |
| `MAX_TRUSTED_DOWNLOAD_HOSTS` | ❌ | `.max.ru,.oneme.ru` | HTTPS-хосты, которым разрешён заголовок `Authorization` |
| `MAX_INBOUND_MEDIA_MAX_BYTES` | ❌ | `52428800` | Лимит байтов одного входящего вложения |
| `MAX_INBOUND_MEDIA_TOTAL_BYTES` | ❌ | `104857600` | Общий лимит размера вложений одного update, байт |
| `MAX_INBOUND_MEDIA_MAX_ATTACHMENTS` | ❌ | `10` | Лимит числа вложений одного update |
| `MAX_INBOUND_MEDIA_TIMEOUT` | ❌ | `30` | Таймаут загрузки входящего медиа в секундах |
| `MAX_INBOUND_MEDIA_CONCURRENCY` | ❌ | `4` | Параллелизм загрузки входящего медиа |

## Внутренние константы

| Константа | Значение | Назначение |
|---|---|---|
| Базовый URL API | `platform-api2.max.ru` | Адрес MAX API, не переменная окружения |
| Лимит длины сообщения | `4000` | Максимальная длина текста одного сообщения |
| Лимит исходящего файла | `50 * 1024 * 1024` | Лимит исходящего файла |
| Лимит тела webhook | `1_048_576` | Максимальный размер тела webhook-запроса |
| Таймаут polling | `POLL_TIMEOUT` | Базовый таймаут polling |
| Лимит колонок таблицы | `38` | Лимит колонок текстовой таблицы |
| Ширина PNG таблицы | `1200` | Ширина PNG-холста таблицы |

## Ключи блока `platforms.max`

Ключи YAML передаются адаптеру в `extra`; значения переменных окружения имеют приоритет.

| Ключ в блоке `platforms.max` | Переменная окружения | Назначение |
|---|---|---|
| `token` | `MAX_BOT_TOKEN` | Токен бота |
| `host` | `MAX_WEBHOOK_HOST` | Хост webhook |
| `port` | `MAX_WEBHOOK_PORT` | Порт webhook |
| `path` | `MAX_WEBHOOK_PATH` | Путь webhook |
| `webhook_secret` | `MAX_WEBHOOK_SECRET` | Секрет webhook |
| `webhook_url` | `MAX_WEBHOOK_URL` | Публичный URL webhook |
| `webhook_insecure_dev` | `MAX_WEBHOOK_INSECURE_DEV` | Разрешить webhook без секрета только на loopback в разработке |
| `allowed_users` | `MAX_ALLOWED_USERS` | Список разрешённых пользователей |
| `allow_all_users` | `MAX_ALLOW_ALL_USERS` | Явно разрешить всех пользователей |
| `group_policy` | `MAX_GROUP_POLICY` | Политика групп: `allowlist` или `open` |
| `group_allow_from` | `MAX_GROUP_ALLOWED_USERS` | Разрешённые пользователи групп |
| `group_allow_chats` | `MAX_GROUP_ALLOWED_CHATS` | Разрешённые группы |
| `cross_session` | `MAX_CROSS_SESSION` | Включить кроссплатформенные сессии |
| `cross_session_users` | `MAX_CROSS_SESSION_USERS` | Владельцы, которым разрешены кроссплатформенные сессии |
| `home_channel` | `MAX_HOME_CHANNEL` | Получатель cron/send_message |
| `table_as_image` | `MAX_TABLE_AS_IMAGE` | Рендерить Markdown-таблицы в PNG |
| `edit_throttle` | `MAX_EDIT_THROTTLE` | Минимальный интервал streaming-правок |
| `dedup_ttl` | `MAX_DEDUP_TTL` | TTL дедупликации входящих событий |
| `overload_policy` | `MAX_OVERLOAD_POLICY` | Поведение очереди при перегрузке |
| `download_allowed_hosts` | `MAX_DOWNLOAD_ALLOWED_HOSTS` | Строгий список разрешённых оператором download-хостов |
| `trusted_download_hosts` | `MAX_TRUSTED_DOWNLOAD_HOSTS` | HTTPS-хосты, которым разрешён заголовок `Authorization` |
| `inbound_media_max_bytes` | `MAX_INBOUND_MEDIA_MAX_BYTES` | Лимит одного входящего вложения |
| `inbound_media_total_bytes` | `MAX_INBOUND_MEDIA_TOTAL_BYTES` | Общий лимит вложений одного update |
| `inbound_media_max_attachments` | `MAX_INBOUND_MEDIA_MAX_ATTACHMENTS` | Лимит числа вложений одного update |
| `inbound_media_timeout` | `MAX_INBOUND_MEDIA_TIMEOUT` | Таймаут загрузки входящего медиа |
| `inbound_media_concurrency` | `MAX_INBOUND_MEDIA_CONCURRENCY` | Параллелизм загрузки входящего медиа |

## Режимы подключения

Плагин получает сообщения из MAX API в одном из двух режимов. Режим определяется переменной **`MAX_WEBHOOK_URL`**:

| `MAX_WEBHOOK_URL` | Режим | Механизм |
|---|---|---|
| Не задана или пуста | **Long polling** (по умолчанию) | Циклический `GET /updates?timeout=5&marker=...` |
| Задан HTTPS URL | **Webhook** | aiohttp-сервер на порту 8646, регистрация `POST /subscriptions` |

Режим выбирается в `connect()` одной строкой: `self._use_webhook = bool(self._webhook_url)`.

### Опрос (Long polling, по умолчанию)

```bash
# Укажите токен в защищённой конфигурации
MAX_BOT_TOKEN=<токен_бота>
```

Long polling подходит для:
- Локальной разработки
- Тестирования
- Сред, где нет публичного HTTPS

### Webhook-подключение-подключение

```bash
MAX_BOT_TOKEN=<токен_бота>
MAX_WEBHOOK_URL=https://example.org/max/webhook
MAX_WEBHOOK_SECRET=<секрет_webhook>
```

Для production MAX рекомендует webhook; ему нужен публичный HTTPS URL.

> **Официальная документация (dev.max.ru/docs-api, проверено 2026-09-16):** MAX рекомендует для production webhook; long polling ограничен rate limit и хранением событий. С 25 мая 2026 года HTTP webhook и self-signed сертификаты не поддерживаются. Endpoint должен принимать HTTPS на **порту 443** (порт не указывается в URL) и отвечать HTTP 200 в течение 30 секунд. Плагин по умолчанию слушает `8646`, поэтому reverse proxy должен публиковать его на 443.

## Настройка webhook

### Caddy

```caddyfile
example.org {
    reverse_proxy localhost:8646
}
```

### Traefik

```yaml
http:
  routers:
    max-webhook:
      rule: "Host(`example.org`)"
      service: max-gateway
  services:
    max-gateway:
      loadBalancer:
        servers:
          - url: "http://localhost:8646"
```

### Регистрация webhook

Плагин регистрирует webhook при старте. Ручная регистрация нужна только для отдельно управляемой подписки:

```bash
curl -X POST "https://platform-api2.max.ru/subscriptions" \
  -H "Authorization: your_token" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.org/max/webhook",
    "update_types": ["message_created", "message_callback", "bot_started"],
    "secret": "your-secret"
  }'
```

Проверьте подписки:

```bash
curl -H "Authorization: your_token" \
  https://platform-api2.max.ru/subscriptions
```

## Смена режима

### Long polling → webhook

```bash
# 1. Добавьте в ~/.hermes/.env
MAX_WEBHOOK_URL=https://example.org/max/webhook
MAX_WEBHOOK_SECRET=<секрет_webhook>

# 2. Примените настройки и перезапустите gateway утверждённым способом управления службой.
# Перезапуск production gateway влияет на live-трафик.
```

При старте `_start_webhook()` открывает `0.0.0.0:8646` и регистрирует подписку в MAX API.

### Webhook-подключение-подключение → long polling

Перед переключением проверьте текущие подписки MAX. При запуске polling плагин пытается удалить старые webhook-подписки — это изменение внешнего состояния. Для production-бота заранее согласуйте переключение.
```bash
# 1. Удалите или закомментируйте MAX_WEBHOOK_URL (и MAX_WEBHOOK_SECRET)
# MAX_WEBHOOK_URL=...
# MAX_WEBHOOK_SECRET=...

# 2. Примените настройки и перезапустите gateway утверждённым способом управления службой.
# Перезапуск production gateway влияет на live-трафик.
```

При старте `_start_polling()` проверяет `GET /subscriptions`, **автоматически удаляет** старые webhook-подписки и запускает `_poll_loop`.

### 🚨 Важно

Если webhook-подписка была создана **вручную**, автоочистка может её не найти. Удаляйте её только после проверки и согласования:

```bash
curl -X DELETE "https://platform-api2.max.ru/subscriptions?url=<URL>" \
  -H "Authorization: your_token"
```

## Безопасность

### Секрет webhook

MAX передаёт секрет как исходное значение заголовка `X-Max-Bot-Api-Secret`, а не как HMAC-подпись. Плагин сравнивает его через `secrets.compare_digest()`.

### Управление доступом

**Список разрешённых пользователей:**

```bash
MAX_ALLOWED_USERS=123456789,987654321
```

**Разрешить всех:**

```bash
MAX_ALLOW_ALL_USERS=true
```

**Политики групп:**

```bash
# Закрытая группа — только разрешённые пользователи
MAX_GROUP_POLICY=closed

# Список разрешённых для группы
MAX_GROUP_ALLOWED_USERS=123456789
MAX_GROUP_ALLOWED_CHATS=-1001234567890
```

## Развёртывание

### Служба Systemd-служба

```bash
# Используйте утверждённый для развёртывания менеджер служб. enable/start меняют состояние службы;
# перед запуском проверьте целевой хост и согласуйте окно работ.
systemctl status hermes-gateway
```

### Проверка

```bash
# Проверка health endpoint
curl http://localhost:8646/health

# Статус плагина
hermes gateway status
```

## Проверки при разработке

Сначала отдельно установите выбранные исходники Hermes Core, затем этот checkout командой `python -m pip install -e ".[test,tables]"`. Перед `python -m pytest` выполните `python -m pip check`. CI закрепляет точные ревизии Core и использует независимые окружения. Плагин не объявляет сам Hermes пакетной зависимостью: среду приложения предоставляет Hermes.
