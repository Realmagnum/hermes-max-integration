# Согласование истории ветки

[English version](20261021-branch-reconciliation.md)

Дата: 2026-10-21. Текущий кандидат `20ca676` сохраняет базу `5144194`; входящая ветка `598d57b` отделилась от текущей линии на `2682f49`. Старый HEAD сохранён в `archive/microspec-pipeline-20261021` на GitHub и Gitea. Истории объединены обычным merge без force-push, с рассмотрением файлов по таблице. Это не откат к 2.10.2 и не новая релизная приёмка.

## Решения по файлам

| Пути | Решение |
|---|---|
| `BACKLOG.md`, `BACKLOG_EN.md` | Сохранён текущий EN/RU backlog; старые отметки готовности 2.10.2 остаются в архивной истории. |
| `CHANGELOG.md`, `CHANGELOG_EN.md` | Сохранены история 2.11.0 и новая правка сессий вместо дубликатов 2.10.2. |
| `README.md`, `README_EN.md` | Сохранены английский основной README, русский парный и актуальные сведения. |
| `adapter.py` | Сохранены текущие model picker с привязкой владельца и Core hook медиа. Перенесены диагностические логи send_action; старая регистрация send_message_handler не возвращается. |
| `mixins/media_upload.py` | Перенесён debug-лог сбоя action поверх текущих загрузки и защиты. |
| `mixins/standalone.py` | Сохранены текущая политика загрузки file/image и проверенный fallback; старое изменение типа image выходит за задачу сессий и требует отдельной wire/API-проверки. |
| `mixins/plugin_media_handler.py`, `tests/test_plugin_media_handler.py`, `tests/test_plugin_media_handler_contract.py` | Альтернативные разбор медиа и регистрация не возвращаются; актуальная архитектура покрыта тестами Core send-router и output hook. |
| `plugin.yaml` | Сохранены версия 2.11.0, регистрация YAML-локалей ru/en и новые настройки сессий. |
| `pyproject.toml` | Сохранены ограниченные зависимости и Python >=3.12. Источник hermes-agent только для workspace не добавляется: самостоятельному плагину такая зависимость не нужна. |
| `locales/en-US.json`, `locales/ru-RU.json` | Несовместимая JSON-схема не возвращается; действуют текущие ru/en YAML-пакеты и реальный Desktop harness. |
| `docs/specs/.state.json`, `docs/specs/README.md`, `docs/specs/01-sec-audit.md`, `docs/specs/02-code-transport.md`, `docs/specs/03-model-picker.md`, `docs/specs/04-native-media.md`, `docs/specs/05-locales-desktop.md`, `docs/specs/06-build-ci.md` | Сохранены датированные двуязычные спецификации и правила evidence; исходные старые контракты доступны по архивному коммиту. Старые статусы не считаются текущей приёмкой. |
| `tests/test_cross_session.py` | Сохранены регрессии новой политики сессий; не переносится тест, лишь повторяющий Desktop-фильтр на Python вместо проверки Desktop-кода. |
| `tests/test_model_picker.py` | Перенесена регрессия удаления сообщения провайдеров через реальный callback. |
| `tests/test_ru_en_parity.py` | Сохранены текущие проверки YAML, manifest и реального Desktop; тесты устаревшей JSON-схемы и локальной тестовой функции fallback не переносятся. |
| `tests/test_webhook_security.py` | Перенесён динамический выбор тестового порта вместо порта работающего gateway. |

## Проверка

Итоговое дерево отличается от `20ca676` только документированными логами action, регрессией model picker, изоляцией порта, количеством собираемых тестов и этой записью. Итоговая проверка 2026-10-21: 837 тестов пройдены на Core ca13a782 (Python 3.14), одно предупреждение upstream; Ruff, проверки версий/числа тестов, конфигурации, EN/RU-парности, 46 Markdown-файлов и git diff --check пройдены. Production и MAX-сообщения не затрагиваются. Файлы отдельного плана стенда и рабочий backlog не включены. См. [политику сессий](20261021-session-list-policy_RU.md).
