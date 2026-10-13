# Архитектура Hermes MAX Gateway

## Граница интеграции

Плагин реализует адаптер MAX для Hermes Gateway и регистрирует его через entry point пакета. Hermes Core отвечает за агентский цикл, хранение сессий и STT; плагин преобразует события MAX в контракт платформы Hermes.

## Модули

- `adapter.py` — конфигурация, lifecycle, polling, нормализация events и координация mixins.
- `mixins/base.py` — общее состояние и transport helpers.
- `mixins/webhook.py` — aiohttp endpoint, регистрация subscriptions, проверка запроса.
- `mixins/media_upload.py` и `mixins/standalone.py` — MAX CDN uploads и standalone media delivery.
- `mixins/buttons.py` и `mixins/callback_auth.py` — интерактивные сообщения, callback ack и авторизация инициатора.
- `mixins/sessions.py` — необязательные кросс-платформенные `/sessions` и `/resume`.
- `mixins/table_renderer.py` — Markdown-таблицы в PNG: Playwright/Chromium и Pillow fallback.
- `desktop/plugin.js`, `locales/` — дополнительный Hermes Desktop sidebar и локализация.

Сверяйте актуальные классы и импорты с исходниками: эта карта не заменяет код.

## Потоки данных

### Входящие сообщения

MAX доставляет updates через polling или webhook. Адаптер нормализует событие, применяет дедупликацию и access policy, ограниченно скачивает допустимые вложения и передаёт сообщение в Hermes Core. Голосовые аудиофайлы передаются Core для STT; отдельного STT engine в плагине нет.

### Исходящие сообщения

Core вызывает platform methods. Адаптер форматирует и делит текст на chunks, ограничивает частоту streaming edits, при необходимости превращает Markdown-таблицу в PNG и отправляет вложение через MAX upload API и CDN. Зарегистрированный `standalone_sender_fn` выполняет standalone delivery, когда Core направляет запрос в него. Маршрутизация media-only зависит от выбранной версии Core; плагин не изменяет Core для её включения.

## Неочевидные инварианты

- MAX API ожидает raw bot token в `Authorization`, без префикса `Bearer`.
- Публичный webhook требует HTTPS и secret; secretless dev режим допустим только для явно разрешённого loopback.
- Upload/CDN hostnames и redirects — граница безопасности: не пересылайте `Authorization` стороннему origin.
- При переходе на polling startup удаляет найденные webhook subscriptions; проверяйте их до переключения, особенно если создавали вручную.
- Доступ к сессиям других платформ расширяет область авторизации и должен оставаться opt-in и owner-scoped.
- Импорты модулей плагина должны сохранять package context; проверяйте загрузку через plugin loader, не только из CWD репозитория.
- Рендерер таблиц должен иметь fallback без Chromium; зависимости устанавливаются в Python-окружение процесса Hermes.

## Где искать детали

Defaults и переменные окружения: `docs/setup_RU.md`; security controls: `docs/security_RU.md`; внешние API факты и даты проверки: `docs/external-claims_RU.md`. Установка и эксплуатационные процедуры находятся в `skills/max-gateway/SKILL_RU.md`.
