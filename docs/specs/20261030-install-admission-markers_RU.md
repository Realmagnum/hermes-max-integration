# Допуск при установке: платформенные маркеры и pin playwright — Micro-Spec

Источник: upstream-issue [Realmagnum/hermes-max-integration#1](https://github.com/Realmagnum/hermes-max-integration/issues/1), проверено 2026-10-30 на Core `aad60e1ac67` (локальный checkout) и `origin/main` (`fa78e686faf`).

Область: сделать плагин устанавливаемым через plugin manager Hermes, не меняя поведение рантайма. Здесь ничего не выбирает extras `tables` или `stt`; изменение лишь убирает причины, по которым резолвер отклоняет набор кандидатов.

## Проблема

Hermes резолвит core и все включённые плагины как один uv-воркспейс и лочит **все** extras участников. Ломалось на двух независимых декларациях, из-за чего admission отвечал `enable refused: Plugin 'max-platform' conflicts with the dependencies pinned by Hermes core…`:

1. `tables` (playwright) и `stt` (faster-whisper → ctranslate2) были объявлены без маркера core `sys_platform != 'android'`. Ни один из пакетов не публикует Android-колёс, поэтому на ядрах, которые ещё резолвят Android, падал весь lock из-за платформы, где плагин не работает.
2. `tables` и `plugin.yaml` пинили `playwright==1.62.0` точно. Core пинит тот же дистрибутив точно в своём extra `google-meet` и поднял pin с `1.62.0` до `1.64.0` (коммит core `65a82c53f94`, 2026-10-23). Два разных точных пина не могут сосуществовать, поэтому плагин оставался неустанавливаемым на любом ядре с этого коммита — в том числе после того, как собственный Android-фикс core (`91c86af0551`, `db5b65607e3`, 2026-10-24) убрал причину 1.

Причина 1 сама по себе закрыта в core для хостов, устанавливающих на одну платформу, но плагин по-прежнему объявляет `requires_hermes >=0.21.4`, а выпущенные ядра `≤ v0.22.5` резолвят Android. Поэтому маркер сохранён: он корректен для тех ядер и совпадает с тем, что core объявляет для тех же пакетов.

## Изменение

| ID | Триггер / контекст | Требуемый результат | Приёмка | Статус |
|---|---|---|---|---|
| DEP-001 | extras `tables` / `stt`, `plugin.yaml` | `playwright` и `faster-whisper` несут `sys_platform != 'android'`, как у core | `tests/test_install_admission_markers.py`; lock воркспейса с seed-локом на Core `v0.22.5` | Реализовано |
| DEP-002 | Core пинит playwright точно | Плагин объявляет `playwright>=1.62,<2`: нижняя граница — самый старый поддерживаемый pin core, верхняя — ниже следующей мажорной версии | `tests/test_install_admission_markers.py`; lock воркспейса с seed-локом на Core `aad60e1ac67` | Реализовано |
| DEP-003 | `scripts/setup-playwright.py` | Принимать и ставить любую версию внутри объявленного диапазона вместо принудительного `1.62.0`; не конфликтовать с версией, уже стоящей в шлюзе | `tests/test_setup_playwright.py` (случаи диапазона, команда установки) | Реализовано |
| DEP-004 | Core поднимает playwright за пределы диапазона | CI падает с указанием проблемного требования вместо отказа admission у пользователей | `tests/test_install_admission_markers.py::test_plugin_range_accepts_core_exact_pin` читает `pyproject.toml` установленного core | Реализовано |

## Подтверждение и ограничения

Воспроизведено на PM-пине `uv 0.13.5` и CPython 3.14.9 на сгенерированном воркспейсе, повторяющем `pm/workspace.py::_generate_pyproject`: root `pyproject.toml` ядра без `exclude-newer`, `[tool.uv] workspace.members` указывает на копию плагина и — как делает `pm/packages.py` (`seed = project / "uv.lock"`) — коммитнутый lock ядра скопирован как seed.

| Core | Декларации плагина | Результат |
|---|---|---|
| `v0.22.5`, environments без сужения | коммит `78d9abf` | **отказ**, дословно воспроизводит [issue #1](https://github.com/Realmagnum/hermes-max-integration/issues/1): `playwright==1.62.0 has no 'python_full_version >= 3.14'-compatible wheels` в сплите `sys_platform == 'android'` |
| `v0.22.5`, environments без сужения | это изменение | lock резолвится, 330 пакетов, участник присутствует |
| `aad60e1ac67`, environments без сужения | коммит `78d9abf` | **отказ** в non-Android сплите: `hermes-agent[google-meet] depends on playwright==1.64.0` против `hermes-max-integration[tables] depends on playwright==1.62.0` |
| `aad60e1ac67`, environments без сужения | это изменение | lock резолвится, 348 пакетов, playwright 1.64.0 |
| `aad60e1ac67`, environments сужены до хоста установки (`pm/workspace.py::_solve_only_for`) | это изменение | lock резолвится, 348 пакетов, playwright 1.64.0, faster-whisper 1.2.1 |

Две последние строки важны вместе: фикс **не зависит** от core-коммита с сужением воркспейса. Обе причины устранены в самих декларациях, поэтому плагин допускается и на выпущенных ядрах, которые ещё резолвят Android (`≤ v0.22.5`, случай из issue #1), и на текущем core, где оставался только конфликт пинов.

Первая итерация harness шла без seed-лока и дала ошибку сборки `spacy 2.0.17` из sdist. Это артефакт резолва «с нуля», а не свойство core: с seed-локом (как делает PM) оба ядра лочатся чисто. Зафиксировано здесь, чтобы позже эту ошибку не приняли за evidence.

Не проверялось здесь: живой `hermes plugins install` из опубликованного релиза, хосты Windows/macOS, сборка `sdist`/wheel и реальная установка на Android (Termux). Advisories `dependency-audit` в core к этому изменению не относятся и остаются в BUILD-03.
