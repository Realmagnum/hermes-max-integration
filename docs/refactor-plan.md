# План рефакторинга adapter.py и Roadmap (v2.7.0+)

Этот документ содержит актуализированный план рефакторинга монолита `adapter.py` (~3700 строк кода) и дорожную карту развития (Roadmap). Документ служит контекстом для ИИ-агентов, чтобы продолжать работу в новых сессиях.

## Текущий статус (2026-08-17)

**Рефакторинг завершён ✅** (ветка `feature/refactor-mixins-base`, merge в main в v2.9.0).

- adapter.py: 2997 → 2250 строк; mixins/ суммарно ~1630 строк.
- **Шаг 7 отменён** — STT делегирован ядру Hermes v0.20.0, миксин `stt_processor.py` удалён (2026-08-05).
- Тесты: 154 зелёных, conftest переведён на пакетный импорт `max.adapter`.
- Все шаги плана ниже отмечены ✅ — план выполнен.

## Прогресс (Что уже сделано)

- [x] **Изоляция баз и структуры:** Создана директория `mixins/`, базовое состояние вынесено в `mixins/base.py`. (Ветка: `feature/refactor-mixins-base`)
- [x] **Уязвимость STT:** Исправлена критическая логическая уязвимость (использование `shlex.quote` заменено на безопасный `sys.argv[1]`) в `stt_processor.py`. (Ветка: `feature/stt-security-fix`)
- [x] **Вынесение Table Renderer:** 500 строк логики конвертации Markdown-таблиц в картинки вынесено в `mixins/table_renderer.py`. (Ветка: `feature/refactor-table-renderer`)
- [x] **Скелеты модулей:** Созданы начальные заготовки для `webhook.py`, `media_upload.py`, `buttons.py`.

## План модулей

```
hermes-max-integration/
├── adapter.py              # тонкая прослойка (множественное наследование миксинов)
├── mixins/
│   ├── __init__.py
│   ├── base.py             # ✅ MaxBaseMixin — базовое состояние, http_client
│   ├── table_renderer.py   # ✅ Рендеринг таблиц (543 строк, полная реализация)
│   ├── media_upload.py     # ✅ Загрузка файлов (POST /uploads, CDN, retry, SSRF)
│   ├── buttons.py          # ✅ Кнопки: send_buttons, send_action, _post_interactive, approval/clarify
│   ├── stt_processor.py    # ❌ удалён — STT в ядре Hermes (v0.20.0+)
│   ├── webhook.py          # ✅ Вебхук-сервер (aiohttp, подписки, _verify_raw_secret)
│   ├── sessions.py         # ✅ /sessions, /resume, cross-platform
│   └── standalone.py       # ✅ standalone sender (_standalone_send, media)
├── tests/
│   ├── test_interactive.py # ✅ кнопки/actions (13 тестов) — отдельный test_buttons.py не потребовался
│   ├── test_file_send.py   # ✅ upload + standalone sender (включая SSRF)
│   └── ...                 # conftest: пакетный импорт max.adapter (починено 2026-08-17)
```

## Очерёдность коммитов (выполнено)

| Шаг | Коммит | Что делает | Статус |
|-----|--------|-----------|--------|
| 1 | `refactor: add base mixin structure for adapter.py` | MaxBaseMixin — базовое состояние, core props | ✅ |
| 2 | `refactor: add stubs for remaining mixins` | Заглушки для всех модулей с корректными импортами | ✅ |
| 3 | `fix: use relative imports in all mixins` | `from mixins.base` → `from .base` во всех mixins | ✅ |
| 4 | `refactor: extract table rendering to table_renderer.py` | Перенос рендеринга таблиц из adapter.py | ✅ |
| 5 | `refactor: extract upload protocol to media_upload.py` | POST /uploads, CDN, retry, SSRF whitelist | ✅ |
| 6 | `refactor: extract button logic to buttons.py` | send_buttons, send_action, _post_interactive | ✅ 56f1ed5 |
| 7 | `refactor: extract STT logic to stt_processor.py` | Транскрипция голосовых сообщений | ⏭️ заменён — STT в ядре Hermes v0.20.0, миксин удалён (2026-08-05) |
| 8 | `refactor: extract webhook server to webhook.py` | aiohttp вебхук, подписки | ✅ 1a07f87 |
| 9 | `refactor: extract session commands to sessions.py` | /sessions, /resume, cross-platform | ✅ 06e02f3 |
| 10 | `refactor: extract standalone sender to standalone.py` | _standalone_send, _get_token, media handling | ✅ 8db4fb7 |
| 11 | `refactor: strip adapter.py to thin facade` | Оставить только оркестрацию + импорты из mixins | ✅ 3de0cf5 |

## Ключевые принципы разработки агентом

1. **Blame preservation** — `cp` перед вырезанием, не `git mv`. Каждый файл наследует историю своих строк.
2. **Каждый коммит зелёный** — `pytest tests/` должен проходить после каждого шага.
3. **Миксины/композиция** — `MaxAdapter` наследует mixins. Композиция предпочтительнее для минимизации изменений в adapter.py.
4. **Никакого изменения логики** — рефакторинг без изменения поведения. Чистый перенос кода.
5. **Тесты переносятся вместе с кодом** — если тесты разбросаны, сгруппировать в конце.

## 🚨 Важно: импорты в mixins

**Все импорты внутри mixins/ должны быть относительными (`.module`), а не абсолютными (`module`).**

Абсолютные импорты (`from mixins.base import ...`) работают при локальном тестировании (CWD == папка плагина), но бесшумно проваливаются при загрузке через систему плагинов Hermes (CWD != папка плагина). Ошибка логируется с `exc_info=False`, поэтому в journalctl нет traceback.

**Правило:**
- `adapter.py` → `from .mixins.xxx import YYY`
- `mixins/*.py` → `from .base import ZZZ` (а не `from mixins.base import ZZZ`)

## Roadmap (Дорожная карта будущих доработок)

Ниже представлены фичи, которые сделают плагин Enterprise-ready:

- [ ] **Рендеринг таблиц 2.0:** Отказ от хардкода путей к системным шрифтам (`/usr/share/fonts/...`). Добавление шрифтов (Inter, Roboto) в `assets/fonts/` и интеграция библиотеки `pilmoji` для автоматической отрисовки нативных Apple-эмодзи вместо текстовых костылей `[OK]`, `[WARN]`.
- [ ] **Голосовые ответы (TTS):** Добавление возможности агенту отвечать голосовыми сообщениями (генерация аудио через внешние TTS-провайдеры и отправка через метод `send_voice`).
- [ ] **Реакции (Виртуальные):** Эмуляция реакций на сообщения (так как MAX API их не поддерживает) через временные сообщения (например, эмодзи ⏳), которые удаляются после получения ответа.
- [ ] **Оптимизация STT (Hardware):** Добавление в README явных требований к ОЗУ (минимум 2-4 ГБ) для `faster-whisper` во избежание OOM.
- [ ] **Изоляция Тредов (Sessions):** Доработка логики управления сессиями — строгая привязка "Один тред (topic) = Одна сессия агента", чтобы в одном чате можно было вести параллельные дискуссии.

---
*Примечание для Агента:* При запуске новой сессии прочитайте этот файл для понимания текущего этапа рефакторинга и вектора развития.
