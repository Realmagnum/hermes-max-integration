# План рефакторинга adapter.py

## Цель

Разделить монолитный `adapter.py` (~3100 строк) на модульную структуру. Каждый модуль отвечает за свою зону ответственности.

## Стратегия: единая feature-ветка

Ветка `feature/refactor-adapter` от `main`. Каждый коммит — один выделенный модуль. После завершения — merge в `main` с тегом.

## План модулей

```
hermes-max-integration/
├── adapter.py              # тонкая прослойка: импорты + общая логика
├── mixins/
│   ├── __init__.py
│   ├── upload.py           # протокол загрузки файлов (POST /uploads, CDN, retry)
│   ├── buttons.py          # send_buttons, send_action, _post_interactive
│   ├── sessions.py         # кросс-платформенные сессии (/sessions, /resume)
│   └── standalone.py       # standalone sender (_standalone_send, _get_token)
├── tests/
│   ├── test_upload.py       # тесты вынесены из test_file_send.py
│   ├── test_buttons.py      # тесты из test_interactive.py
│   └── ...                  # остальные тесты остаются
```

## Очерёдность коммитов

| Шаг | Коммит | Что делает | Тесты |
|-----|--------|-----------|-------|
| 1 | `refactor: copy adapter.py for blame preservation` | Копия `adapter.py` → временно сохранить | — |
| 2 | `refactor: extract upload protocol to mixins/upload.py` | POST /uploads, CDN, retry, SSRF whitelist | `pytest tests/` ✅ |
| 3 | `refactor: extract button logic to mixins/buttons.py` | send_buttons, send_action, _post_interactive | `pytest tests/` ✅ |
| 4 | `refactor: extract session commands to mixins/sessions.py` | /sessions, /resume, cross-platform | `pytest tests/` ✅ |
| 5 | `refactor: extract standalone sender to mixins/standalone.py` | _standalone_send, _get_token, media handling | `pytest tests/` ✅ |
| 6 | `refactor: strip adapter.py to thin facade` | Оставить только общую логику + импорты из mixins | `pytest tests/` ✅ |
| 7 | `chore: cleanup old adapter.py copy` | Удалить временную копию | — |

## Ключевые принципы

1. **Blame preservation** — `cp` перед вырезанием, не `git mv`. Каждый файл наследует историю своих строк.
2. **Каждый коммит зелёный** — `pytest tests/` должен проходить после каждого шага.
3. **Миксины/композиция** — `MaxAdapter` наследует или использует mixins. Миксины предпочтительнее для минимизации изменений в adapter.py.
4. **Никакого изменения логики** — рефакторинг без изменения поведения. Чистый перенос кода.
5. **Тесты переносятся вместе с кодом** — если тесты для upload-логики разбросаны, сгруппировать в конце.

## Формат коммитов

Все коммиты в ветке — `refactor: ...`. Финальный — `chore: cleanup`. Merge в main — без squash (сохранить историю рефакторинга).

## После рефакторинга

```bash
bash scripts/release.sh v2.5.0
```
