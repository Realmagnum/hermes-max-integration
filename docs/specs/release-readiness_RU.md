# Готовность релиза — Micro-Spec

[Английская версия](release-readiness.md)

Дата: 2026-10-13. Статус: выполнение остановлено по просьбе пользователя; продолжить позже. База: `887611a3ec9a71a7db7d7726fa8382d14301b195`. Источник: поручение закрыть backlog и подготовить полноценный релиз до изменений каталожного PR и ответа ревьюеру. Уточняет [контракты каталога](catalog-review-137501_RU.md), сохраняя их ID.

## Объём и границы

Завершить независимо проверяемую приёмку backlog и подготовить воспроизводимый релиз. В этом этапе не менять каталожный PR и не отвечать ревьюеру. Не считать неуспешный audit или невыполненную live check пройденными. Сохранить резервную копию установки и изоляцию профилей; не включать credentials, реальные ID получателей и частные пути в release evidence. Выбор версии и публикация релиза — финальный шаг после приёмки, а не её доказательство.

## Контракты

| ID | Событие / условие | Наблюдаемый результат и приёмка | Существующая привязка | Статус |
|---|---|---|---|---|
| REL-001 | Пользователь группы открывает model picker | До отправки привязать к инициатору; неизвестный owner даёт безопасный отказ; чужой user/chat/message, replay и expiry не меняют state. Проверить двух пользователей и параллельные sessions; обычный DM работает | CODE-06; `adapter.py`, `tests/test_model_picker.py` | Проверено; коммит `7cf6516` обеспечивает привязку к инициатору и fail-closed изоляцию |
| REL-002 | Финальный immutable directory-plugin устанавливается из заявленного remote source | Полные assets/imports и штатная установка dependencies успешны; admission safe/no override; dependency fallback отклоняется даже при exit zero; записать exact SHA/source | BUILD-01 / DOC-08 / MS-005; manifest, CI | Финальная приёмка ожидает |
| REL-003 | Exact released minimum Core работает на Python 3.12 | Чистые resolver, pip check и полный suite проходят; матрица Python зафиксирована как >=3.12 (Python 3.11 исключён); Core >=0.21.4 | BUILD-02 / MS-010; Core `d337b736aa1e8ebecfab043842d13e4a2d2f48a3` | Проверено; pyproject.toml и документация требуют >=3.12 |
| REL-004 | Запускаются CI кандидата и audits base/test/table/STT | Записать exact SHA и каждый gate; только совместимые dependencies; не игнорировать vulnerabilities и не подменять Core несовместимо. Неисправленный upstream constraint блокирует утверждение о чистом audit | BUILD-03 / MS-009/010; `.github/workflows/ci.yml` | Частично; см. evidence |
| REL-005 | Публикуются изменяемые platform claims | Отдельно сверить official API host, правила регистрации, limits, webhook/TLS и Core contract; записать source/date/version, сохранить EN/RU parity | DOC-10; external-claims EN/RU | Проверено; реестр обновлён на дату 2026-10-13 |
| REL-006 | Desktop отображает default/en/ru/unknown locale | Наблюдать labels, dates, loading/empty/error/search и смену локали; записать SDK version и reload limits статических palette strings | CAT-01 / MS-006; Desktop/locale tests | Проверено; визуальная приёмка завершена. Ограничение: описание плагина в каталоге статично |
| REL-007 | Согласованный live bot получает text/file/approval input | Пользователь получает точный ответ и вложение; denied user не вызывает effects; offered approval choices однократно разрешаются в правильной session; чужие/повторные действия отклоняются | CAT-02 / MS-011; router/file/callback tests | Частично; текст/файл/clarify проверены вживую; живое подтверждение exec approval ожидает |
| REL-008 | После исправлений оценивается release gate | Version/manifest/package/changelog согласованы; clean artifact содержит нужные файлы каталога; checksums/install evidence относятся к exact source; release notes раскрывают ограничения. Готовность полноценного релиза определяется записанными gates | Release scripts, changelog, [interactive contracts](interactive-questions_RU.md) | Запланировано; релиз не создан |

## Доказательства и продолжение

- Remote CI exact `887611a`: [run 38408393501](https://github.com/Realmagnum/hermes-max-integration/actions/runs/38408393501). Minimum Python3.12, baseline/current Python3.14 и security успешны; audit base/extras не прошёл из-за14advisories PyJWT2.13.0. Это не полностью зелёный pipeline и не проверка более поздних local changes.
- Подготовлен frozen source snapshot `887611a`. Начата установка minimum-Core на Python3.11; до остановки результат и последующие тесты не собраны. Не считать успешной.
- Отдельный WIP-коммит содержит незавершённое изменение CODE-06 в `adapter.py`. Перед установкой проверить diff и завершить тесты; выполненная приёмка не заявляется.
- Субагенты прерваны. Изменений каталожного PR, ответа ревьюеру и публикации релиза не было. Далее: проверить local diff/background work, завершить isolated acceptance, затем согласованные live/visual tests. Обновить status/evidence и удалить только выполненные backlog items.

## Передача следующему агенту

Продолжать в `fix/catalog-review-137501` с отправленных коммитов передачи. Сначала прочитать инструкции репозитория и WIP-коммит; обновить тесты model picker до признания REL-001 реализованным. Проверить и исправить фактический контракт Core clarify по Q-001–006. Затем завершить admission, матрицу Python и аудит зависимостей, сверку внешних утверждений и визуальную/живую приёмку. Не перезапускать и не обновлять живой gateway ради восстановления контекста. Для живой приёмки нужны реальные сообщения и нажатия пользователя. Подготовить и опубликовать полноценный релиз только после прохождения его условий; правка каталожного PR и ответ ревьюеру остаются отложенными. Временные снимки исходников и окружения существуют только локально; при отсутствии создать заново. Прежние успешные тесты `71fb947`/`887611a` не проверяют WIP-изменение. Во время остановки и передачи функциональные тесты не запускались.
