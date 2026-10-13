# Оставшаяся работа

[Английская версия](BACKLOG.md)

Сверено 2026-10-13 с реализацией `71fb947`. Выполненные задачи удалены из списка; audit IDs и доказательства сохранены в [Micro-Spec](docs/specs/20261013-catalog-review-137501_RU.md) и [журнале изменений](CHANGELOG_RU.md). Исходный аудит `b004c573318f1d5e521255531d1943cc8a8b8b90` остаётся в истории Git. Старые галочки не доказывают существование дефектов сейчас.

## Незавершённая приёмка

Выполнение возобновлено 2026-10-13. Завершённые задачи (CODE-06, BUILD-02, DOC-10, CAT-01, INT-01) проверены и перенесены в [журнал изменений](CHANGELOG_RU.md) и [микроспеки](docs/specs/). Оставшаяся приёмка и повторное ревью каталога после публикации v2.11.0:

- [ ] **BUILD-01 / DOC-08 · P1 — Финальный admission каталога плагина и установка из удалённого источника.** Чистая установка minimum-Core и сборка wheel проходят; admission прежнего снимка успешен. **Приёмка:** проверить финальный immutable candidate через `hermes plugins validate <plugin-path> --install-deps`, отклонять оба сообщения dependency-failure fallback; подтвердить assets/import и записать remote repository/SHA. Python wheel не является полным каталогом Hermes-плагина. Эквивалентность GitHub/Gitea не проверена.
- [ ] **BUILD-03 / MS-009 / MS-010 · P1 — Финальные CI и аудит зависимостей.** Покрытие workflow и обнаружение install failure реализованы; закреплённый Core PyJWT 2.13.0 даёт 14 advisories. **Приёмка:** записать CI exact candidate и audits base/test/table/STT, совместимо исправить upstream constraint. Не игнорировать advisories и не подменять зависимости несовместимо. Прежнее условие Gitea runner не проверено; указать фактическую remote platform.
- [ ] **CAT-02 / MS-011 · P1 — Завершить живую доставку и approvals.** Доставка текста, файлов, выбор модели и вопросы clarify подтверждены в MAX; standalone text+file подтверждён API readback. **Приёмка:** проверить живой выбор подтверждения shell-команд (`_send_exec_approval_prompt`) с реальными вариантами ответа в работающем gateway. Не сохранять реальные credentials/recipients в репозитории.
- [ ] **CAT-03 / MS-012 · Отложено до релиза — Публикация каталога и повторное ревью.** Пользователь явно отложил правку каталожного PR и ответ ревьюеру до полноценного релиза. После него закрепить релизные SHA/image/docs, проверить schema/admission и приложить точные CI/evidence links. Подготовка generic Core media issue остаётся открытой; во время паузы ничего не опубликовано.

## Недавно закрыто в этом цикле (evidence зафиксировано)

- **INT-01 / Q-001–006:** Нативные варианты `clarify` с разрешением через gateway Core, размещение по 1 кнопке в ряду, перехват текста Other, устранение дублирующего MessageEvent и живая проверка пользователем в чате.
- **CODE-06 / REL-001:** Привязка model picker к инициатору и fail-closed обработка для групповых сессий без владельца (`tests/test_model_picker.py`).
- **BUILD-02 / REL-003:** Матрица поддерживаемых версий Python закреплена как `>=3.12` (Python 3.11 исключён); Core >=0.21.4 проверен.
- **CAT-01 / MS-006:** Завершена визуальная приёмка Desktop UI (английский по умолчанию, русский языковой пакет, локализация дат); зафиксировано ограничение статичности описания плагина в манифесте.
- **DOC-10 / REL-005:** Реестр проверки внешних утверждений обновлён на дату 2026-10-13 (`docs/external-claims_RU.md`).

Историческая проверка CI для документационного снимка `887611a`: [GitHub Actions run 38408393501](https://github.com/Realmagnum/hermes-max-integration/actions/runs/38408393501) — minimum Python 3.12, baseline/current Python 3.14 и security прошли; dependency audit завершился ошибкой с 14 advisories PyJWT 2.13.0. BUILD-03 открыт. Проверка Python 3.11 позднее заменена подтверждённой поддержкой Python >=3.12; BUILD-02 закрыт.

Публикация релиза завершена 2026-10-14: [v2.11.0](https://github.com/Realmagnum/hermes-max-integration/releases/tag/v2.11.0), коммит тега `50c7a9a7c16b6207a079b7b883718dd863e9e951`, английское описание, полный ZIP каталога, wheel и SHA256SUMS. [CI точного кандидата](https://github.com/Realmagnum/hermes-max-integration/actions/runs/38473952610) прошёл minimum/baseline/current tests, admission каталога и security; audit не прошёл с 14 upstream advisories PyJWT. Публикация не закрывает BUILD-03, установку удалённого источника и живую приёмку execution approval.

## Закрытие задачи

Закрывайте только независимо подтверждённую приёмку. Обновите MS status/evidence и changelog EN/RU, удалите выполненные пункты отсюда. Остатки сохраняйте явно вместо исправленных дефектов roadmap. Неуспешный audit и невыполненная live check остаются открытыми.
