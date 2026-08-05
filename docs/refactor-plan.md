# План рефакторинга adapter.py

## Цель

Разделить монолитный `adapter.py` (~3100 строк) на модульную структуру. Каждый модуль отвечает за свою зону ответственности.

## Текущий статус

**Ветка разработки:** `feature/refactor-mixins-base`
**Сделано:** базовая структура mixins, table_renderer (543 строк), media_upload (197 строк со всей логикой upload/CDN), stt_processor (46 строк с реализацией); **шаг 7 завершён** — `STTProcessorMixin` подключён к `MaxAdapter`, Windows-фиксы STT синхронизированы (2026-08-05)

## Стратегия: единая feature-ветка

Ветка от `main`. Каждый коммит — один выделенный модуль. После завершения — merge в `main` с тегом.

## План модулей

```
hermes-max-integration/
├── adapter.py              # тонкая прослойка: импорты + общая логика
├── mixins/
│   ├── __init__.py
│   ├── base.py             # ✅ MaxBaseMixin — базовое состояние, http_client
│   ├── table_renderer.py   # ✅ Рендеринг таблиц (543 строк, полная реализация)
│   ├── media_upload.py     # ✅ Загрузка файлов (POST /uploads, CDN, retry, SSRF)
│   ├── buttons.py          # ⏳ send_buttons, send_action, _post_interactive
│   ├── stt_processor.py    # ✅ Обработка голосовых сообщений (STT, 46 строк)
│   ├── webhook.py          # ⏳ Вебхук-сервер (aiohttp, подписки)
│   ├── sessions.py         # ❌ TODO /sessions, /resume, cross-platform
│   └── standalone.py       # ❌ TODO standalone sender (_standalone_send)
├── tests/
│   ├── test_upload.py      # ❌ TODO — тесты из test_file_send.py
│   ├── test_buttons.py     # ❌ TODO — тесты из test_interactive.py
│   └── ...                 # остальные тесты остаются
```

## Очерёдность коммитов

| Шаг | Коммит | Что делает | Статус |
|-----|--------|-----------|--------|
| 1 | `refactor: add base mixin structure for adapter.py` | MaxBaseMixin — базовое состояние, core props | ✅ |
| 2 | `refactor: add stubs for remaining mixins` | Заглушки для всех модулей с корректными импортами | ✅ |
| 3 | `fix: use relative imports in all mixins` | `from mixins.base` → `from .base` во всех mixins | ✅ |
| 4 | `refactor: extract table rendering to table_renderer.py` | Перенос рендеринга таблиц из adapter.py | ✅ |
| 5 | `refactor: extract upload protocol to media_upload.py` | POST /uploads, CDN, retry, SSRF whitelist | ✅ |
| 6 | `refactor: extract button logic to buttons.py` | send_buttons, send_action, _post_interactive | ❌ |
| 7 | `refactor: extract STT logic to stt_processor.py` | Транскрипция голосовых сообщений | ✅ (подключён к MaxAdapter, 2026-08-05) |
| 8 | `refactor: extract webhook server to webhook.py` | aiohttp вебхук, подписки | ❌ |
| 9 | `refactor: extract session commands to sessions.py` | /sessions, /resume, cross-platform | ❌ |
| 10 | `refactor: extract standalone sender to standalone.py` | _standalone_send, _get_token, media handling | ❌ |
| 11 | `refactor: strip adapter.py to thin facade` | Оставить только оркестрацию + импорты из mixins | ❌ |

## Ключевые принципы

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

## Формат коммитов

Все коммиты в ветке — `refactor: ...` или `fix: ...`. Финальный — `chore: cleanup`. Merge в main — без squash (сохранить историю рефакторинга).

## После рефакторинга

```bash
bash scripts/release.sh v2.5.0
```
