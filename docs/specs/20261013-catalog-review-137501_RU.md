# Ревью каталога MAX — Micro-Spec

[Английская версия](20261013-catalog-review-137501.md)

Дата: 2026-10-13. Реализация: [`71fb947`](https://github.com/Realmagnum/hermes-max-integration/commit/71fb947ea7e3ba0c2ffc8dc88b7606e9b879869d), ветка `fix/catalog-review-137501`. Документ фиксирует реализованное поведение и фактическую приёмку; завершение ревью или выпуска не заявляется.

## Цель и границы

Устранить четыре обязательных замечания и обработать четыре рекомендации [ревью 5501512593](https://github.com/NousResearch/hermes-agent/pull/137501#pullrequestreview-5501512593). База плагина: `9b4df24c07933968742edb156283a75bd43a6aa8`, версия 2.10.2. Сохранены исходные MS-ID плана. Специфицирована только эта дельта; посторонние функции и рефакторинг Core вне объёма. Историческая база аудита: `b004c573318f1d5e521255531d1943cc8a8b8b90`.

«Проверено» означает прохождение указанного объёма приёмки. «Частично» — реализация есть, но условие приёмки осталось. «Ожидает» — нужная публикация или наблюдение ещё не выполнены. Автоматическая проверка и живая доставка — разные доказательства.

Источник: `2026-10-13_hermes-max-catalog-review-microspec.md`, разделы «Контракты поведения» и «Evidence и критерий завершения»; датированные результаты взяты из отчёта выполнения. Исходный план остаётся отдельным документом. Запись в репозитории заменяет его устаревший blanket-отказ от unscoped и статус «запланировано»; уточнения явно зафиксированы ниже.

## Контракты поведения

| ID | Событие / условие | Требуемый наблюдаемый результат | Доказательство приёмки | Источник / реализация | Статус |
|---|---|---|---|---|---|
| MS-001 | Новый setup, ответ по умолчанию или отказ от публичного доступа | Доступ остаётся закрытым; существующий allowlist сохраняется до явного выбора allow-all | Setup fixtures проверяют false по умолчанию, сохранение ID и явный allow-all | Обязательное 1; `adapter.py`; [catalog security tests](../../tests/test_catalog_security.py) | Проверено |
| MS-002 | Пустой закрытый allowlist или запрещённый отправитель: сообщение, медиа, команда, callback, start/add | Отказ до скачивания, Core и approval; pending state владельца сохраняется | Матрица DM/групп; запрещённое медиа не вызывает download/dispatch; чужой callback не удаляет state | Обязательное 1 / рекомендация 1; [catalog security](../../tests/test_catalog_security.py), [callback authorization](../../tests/test_callback_auth.py), [group access](../../tests/test_group_access.py) | Проверено |
| MS-003 | В A установлен scope, env содержит B; default-профиль multiplex запускается без scope | Scope A авторитетен, включая отсутствие токена; default использует штатный helper Core; неожиданные ошибки распространяются | Реальный registry Core создаёт default-адаптер без подключения; пустой routed scope отклоняет env/config fallback; fixtures ошибок lookup | Обязательное 2; `credential_support.py`, `adapter.py`, `mixins/standalone.py`; [catalog security](../../tests/test_catalog_security.py), [file send](../../tests/test_file_send.py) | Проверено |
| MS-004 | Диагностика с MAX credentials окружения вызывающего процесса либо без них | Использовать caller env; не открывать credential-файлы и не выводить секреты/API bodies/token arguments | Чтение фиктивного credential-файла запрещено; маркеров секретов нет в выводе/arguments; отсутствующий env даёт ошибку | Обязательное 2; `scripts/diagnose.sh`; [diagnostic privacy](../../tests/test_diagnostics_privacy.py) | Проверено |
| MS-005 | Установка и документированные процедуры медиа | Нет bundled Core-editing script и его инструкций; ограничения public router описаны честно | Script удалён; docs checks проходят; прежний source admission safe/no Core override; повтор exact final admission остаётся в release gate | Обязательное 3; [Core router tests](../../tests/test_core_send_router.py), [архитектура](../architecture_RU.md) | Удаление script и isolated router проверены; final admission ожидает |
| MS-006 | Desktop default/en/ru/unknown locale и смена локали | Английский default/fallback, русский pack, даты локали через public SDK | Harness shipped JS проверяет loading/empty/error/search/date; реальные en/ru labels, даты и команды Cmd+K подтверждены; ручной визуальный осмотр подтвердил английский по умолчанию и русский языковой пакет. Зафиксированное ограничение: смена языка в Desktop не меняет описание плагина в Capabilities -> Plugins, так как Hermes Desktop отображает статическое описание из plugin.yaml/plugin.js без слоя перевода | Обязательное 4; `desktop/plugin.js`; [Desktop behavior](../../tests/test_desktop_locale_behavior.py), [locale manifest](../../tests/test_locales_manifest.py) | Проверено |
| MS-007 | Core запрашивает exec approval | Унаследованный entry point отправляет только предложенные choices; owner/chat/message/TTL блокируют чужое действие | Реальный entry point Core вызван; permitted choices отображены; непредложенный choice отклонён без удаления pending state | Рекомендация 2; `mixins/buttons.py`; [catalog security](../../tests/test_catalog_security.py), [interactive](../../tests/test_interactive.py), [callback authorization](../../tests/test_callback_auth.py) | Автоматически проверено; живые кнопки относятся к MS-011 |
| MS-008 | Создаются API/upload и download clients | Дополнительный CA только для API/upload; standard download TLS, SSRF/token isolation сохранены; README раскрывает расширение trust | Download verify=True; CA/DNS/origin/token fixtures проходят; disclosure есть в README EN/RU | Рекомендация 3; [TLS](../../tests/test_ssl_support.py), [SSRF](../../tests/test_ssrf_download.py), [token isolation](../../tests/test_download_token_leak.py), [catalog security](../../tests/test_catalog_security.py) | Проверено |
| MS-009 | Чистая установка и optional dependencies | Обычный resolver без несовместимых overrides; fixed Playwright/browser revision; честный audit | Minimum/current resolver и pip check проходят; setup fixtures проходят; PyJWT audit содержит14 advisories; полный final base/extras gate не закрыт | Рекомендация 4; `plugin.yaml`, `pyproject.toml`; [Playwright setup](../../tests/test_setup_playwright.py), [CI contracts](../../tests/test_ci_pinned_core.py) | Частично |
| MS-010 | Запускаются minimum и более поздние pinned Core | Явные Core/Python pins; collection и тесты; validator fallback не скрывает install failure | Полные minimum/current suites проходят; matrix и оба failure guards проверены; final remote CI/audit не подтверждён зелёным | Совместимость CI; [workflow](../../.github/workflows/ci.yml), [CI contracts](../../tests/test_ci_pinned_core.py), [lifecycle](../../tests/test_lifecycle.py) | Частично |
| MS-011 | Заявляется доставка text/media/approval | Указывать реальный объём доставки; partial attachments и rejected media-only router не считать полным успехом | Реальные registry/router tests; live standalone text+file API readback; live inbound доходит до Core и response dispatch; точное получение пользователем и live approval selection не подтверждены | Release gate; [Core router](../../tests/test_core_send_router.py), [file send](../../tests/test_file_send.py), [wire regressions](../../tests/test_wire_regressions.py) | Частично |
| MS-012 | Кандидат передаётся на повторное ревью | Каталог закрепляет проверенный immutable SHA; admission/schema/CI и ответ ревьюеру относятся к нему | Ветка отправлена; catalog repin, generic media issue, final admission/schema, ответ ревьюеру и повторное ревью ожидают | Публикация каталога; [PR](https://github.com/NousResearch/hermes-agent/pull/137501) | Ожидает |

## Существенные уточнения контрактов

- MS-003: blanket-отказ от unscoped multiplex был ошибочным. Core намеренно создаёт default platform без scope; `get_scoped_secret` поддерживает его startup env fallback. Установленный routed scope остаётся авторитетным. Пассивная проверка зависимостей не должна читать credentials.
- MS-006: у старых поддерживаемых Desktop SDK нет optional locale-change callback. Страница использует reactive plugin i18n; статические строки palette на таких SDK требуют reload. Private-store/DOM patch не используется.
- MS-010: заявленный Core >=0.20 заменён на >=0.21.4 после проверки точного released minimum. В Core 0.20 нет native exec-approval hook. Это проверенный floor поддержки, а не проверка всех промежуточных ревизий.
- MS-011: проверенный public Core router отклоняет media-only до dispatch плагина. Lower adapter умеет отправлять его; это не подтверждает generic Core routing. Патч Core не поставляется.

## Зафиксированные проверки

| Fixture / проверка | Фактический результат | Граница |
|---|---|---|
| Minimum Core 0.21.4: `d337b736aa1e8ebecfab043842d13e4a2d2f48a3`, isolated Python 3.12.10, Windows | Чистая установка Core+plugin/test/tables:87 разрешённых пакетов; pip check pass;776 тестов прошли за 62.51s | Нет несовместимых dependency overrides; Python 3.11 не проверен |
| Later Core source: `ca13a7828acd2ba8c75e1c1d1694cbc1aee7df3f`, Python 3.14.7, Windows | Final implementation:776 тестов прошли за 49.98s; Ruff, pip check, config/claims/parity и30 Markdown link checks pass | Фиксированный source fixture; не moving-main claim |
| Earlier baseline: `d0288be5b3330d2442e3907185b8e9d0958297bb` | Updated credential/security/file cases:60 passed | Общие совместимые зависимости; не clean full-suite proof финального кандидата |
| Source admission до final helper/floor updates | Dependency install успешен; safe; no Core override | Это не final 71fb947 admission evidence |
| Wheel build 71fb947: `uv build --wheel` | Build pass; adapter, credential_support, ssl_support и mixins упакованы | Только Python distribution, не полный Hermes directory bundle; warning deprecated setuptools license table |
| Bandit high-severity CI threshold | Pass на implementation snapshot | Low/medium findings остаются; не zero-findings audit |
| Dependency audit pinned later Core | 14 advisories PyJWT 2.13.0 | Ограничение upstream; нет ignore или incompatible override; см. [внешние утверждения](../external-claims_RU.md) |
| Installed Core `7157422022ff06f3e632d1dd394ee1253b17ad37`, webhook mode | Токен в `.env` активного профиля; helper совпадает с workspace; graceful restart подключает MAX; local/public health успешен; inbound доходит до Core/reply dispatch | Секреты, получатели и hosts исключены; получение marker пользователем и live approval selection не подтверждены |
| Registered standalone sender, installed Core | Text+file: success/media_delivered/media_sent=1; API readback HTTP200 подтвердил attachment/recipient | Только outbound evidence; не заменяет inbound/approval acceptance |

## Сверка исторического аудита

Это ранее выполненные исправления, присутствующие в кандидате; не все введены 71fb947. Исходный аудит сохранён в Git history; [changelog](../../CHANGELOG_RU.md) хранит историю выпусков. [Backlog](../../BACKLOG_RU.md) содержит только оставшуюся работу.

| Audit IDs | Текущее решение | Regression evidence |
|---|---|---|
| SEC-01 | Exec/slash/clarify defect закрыт; owner policy model picker остаётся CODE-06 | `test_callback_auth.py`, `test_catalog_security.py` |
| SEC-02, SEC-03, SEC-04 | Закрыты в проверенных token/DNS/webhook boundaries | `test_download_token_leak.py`, `test_ssrf_download.py`, `test_webhook_security.py` |
| SEC-05, SEC-06, SEC-07 | Закрыты в проверенных access/media boundaries | `test_cross_session.py`, `test_group_access.py`, `test_inbound_media_limits.py` |
| CODE-01, CODE-02, CODE-03, CODE-04 | Закрыты | `test_poll_backoff.py`, `test_chunking.py`, `test_streaming_isolation.py`, `test_model_picker.py` |
| CODE-05, CODE-07, CODE-08 | Закрыты в проверенных Core fixtures | `test_webhook_readiness.py`, `test_webhook_health_contract.py`, `test_lifecycle.py`, `test_backpressure.py` |
| CODE-06 | Частично: owner unowned group picker закрепляется первым нажатием | `test_model_picker.py`; strict original-requester binding не установлен |
| BUILD-01, BUILD-02 | Исходные packaging/path defects исправлены; final install/Python coverage checks сохранены | Clean minimum install/full tests, wheel build; `test_ci_pinned_core.py`, `tests/conftest.py` |
| BUILD-03, BUILD-04 | Gates/regression реализованы; remote audit и оставшаяся live acceptance сохранены | `test_wire_regressions.py`, `test_docs_api_examples.py`, `test_core_send_router.py` |
| DOC-01, DOC-02, DOC-03, DOC-04, DOC-06 | Single STT/config/webhook/wire/diagnostic documentation defects закрыты | Config checker; `test_webhook_mode_docs.py`, `test_docs_api_examples.py`, `test_diagnostics_privacy.py` |
| DOC-05, DOC-07, DOC-09 | Уточнены security caveats, EN/RU backlog и unreleased history; structural checks не доказывают полноту всех исторических переводов | Documentation checks; test counts 2.10 относятся только к тем выпускам |
| DOC-08, DOC-10 | Navigation/unsupported claims исправлены; remote-source install и renewed external verification остаются | Link checker, `test_doc_external_claims.py`; dated register не заменяет renewed verification |

## Воспроизведение и завершение

Используйте isolated checkout и exact Core fixture из CI. Устанавливайте Core отдельно, plugin с test/table extras — обычным resolver. Выполните pip check, pytest, Ruff, затем existing claims/config/parity/link checkers. В populated development checkout передайте tracked Markdown files link checker, чтобы исключить посторонние README окружений. Проверяйте admission logs вместе с exit status: minimum/later Core выводят разные dependency-install failure messages.

Живые проверки выполняются на согласованном боте/получателе. Фиксируйте input, observed output и Core/candidate revision без credential/personal-data dumps. Health, попытка send или mocked callbacks не доказывают полную доставку. Перед приёмкой соответствующих контрактов и заявлением готовности к повторному ревью нужно выполнить оставшиеся проверки backlog.
