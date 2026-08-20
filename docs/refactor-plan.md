# План рефакторинга adapter.py и Roadmap (v2.9.0+)

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
│   ├── table_renderer.py   # 🔄 Рендеринг таблиц — (в работе) переход с Pillow на HTML→PNG (Playwright)
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

Ниже представлены фичи, которые сделают плагин Enterprise-ready.

> **Обновлено 2026-08-20:** из исходного списка удалены неактуальные пункты —
> «Реакции» (MAX API их не поддерживает, эмуляция признана ненужной), «Оптимизация STT»
> (STT вынесен в ядро Hermes, faster-whisper в v2.8.0 удалён) и «Изоляция Тредов»
> (MAX не поддерживает треды, привязка «тред = сессия» не имеет смысла).

### Приоритет №1: Рендеринг таблиц 2.0 (HTML → PNG)

**Текущая реализация (Pillow `ImageDraw`) признана корявой:** ручной расчёт ширины через
`draw.textlength` + `wcwidth*0.6`-фолбэк даёт переполнение ячеек, текст наезжает на соседние,
эмодзи заменяются текстовыми костылями (`✅→✓`), кириллица зависит от наличия DejaVu на
дистрибутиве (`/usr/share/fonts/...`).

**Решение — HTML+CSS с последующей отрисовкой в PNG через headless-браузер.** Разметку
таблицы делает браузер (никогда не вылезает за ячейки), поддерживаются любые CSS-стили и
нативные цветные эмодзи.

- **Путь:** генерация `{md_path}.html` из парсера `_parse_table_rows` → скриншот `.wrap` через
  Playwright (Chromium/Chrome) с `device_scale_factor=2` → PNG → upload на MAX.
- **Прототипы готовы и проверены** (`/tmp/table-proto/`, будут перенесены в ветку/репозиторий):
  - `simple/emoji/urls/styled/numbers/longtext/very_long_url/dense/dense_dark` — 9 вариантов
    разной сложности; длинные URL и JSON переносятся внутри ячеек, нативные эмодзи, zebra-строки,
    выравнивание, тёмная тема.
- **Зависимость:** `playwright` + наличие Chrome/Chromium на машине Gateway. Если браузера нет —
  фоллбек на прежнюю Pillow-реализацию.
- **Кэш:** сохраняется (content-адресация по `table_<md5>.png`), меняется только способ отрисовки.
- **Ограничение ширины:** `table-layout: fixed` + явные `width` на каждую колонку (проценты считает
  Python из данных `_parse_table_rows`) + `overflow-wrap: break-word`. Это гарантированно не даёт
  коротким колонкам (номер/статус/адрес) ужиматься из-за «жадных» контентных колонок — в отличие от
  `table-layout: auto`, где браузер отдаёт всю ширину самой широкой ячейке и последние столбцы
  схлопываются. **Решено (2026-08-20): вариант A — `table-layout: fixed`.** (Прототипы `dense_cols_A_fixed`
  vs `dense_cols_C_hybrid` подтвердили: fixed даёт сбалансированные пропорции, hybrid пережимает колонки.)
  Ширина таблицы ограничена `max-width` (~820px) для мобильных.

### Голосовые ответы (TTS)

Использовать **встроенный TTS-механизм самого Hermes** (конфиг `tts` в `config.yaml`,
провайдеры edge/openai/mistral/xai/elevenlabs и др.), а не самописную генерацию внутри плагина.

- Агент (ядро) генерирует аудио через свой TTS → передаёт файл в плагин → плагин отправляет через
  уже реализованный метод `MaxAdapter.send_voice()` (см. `adapter.py`, обёртка над `_upload_send`)
  → подпись через ту же цепочку, что и обычные аудио-сообщения.
- Отдельная генерация аудио в плагине **не нужна** — только передача готового файла в канал MAX.

---
*Примечание для Агента:* При запуске новой сессии прочитайте этот файл для понимания текущего этапа рефакторинга и вектора развития.
