# Интерактивные вопросы MAX — Micro-Spec

[Английская версия](20261013-interactive-questions.md)

Дата: 2026-10-13. Статус: специфицировано, реализация ожидает. Источник: просьба пользователя предоставить MAX-агенту интерактивный вопрос и вернуть ответ кнопки в ту же session. База `887611a`; согласованный live target — существующая тестовая установка. Методы рендера уже есть, но это не доказывает наличие инструмента и корректную обработку callback.

## Цель и границы

Использовать существующий public Core `clarify` и gateway hook, если доступны. Не дублировать tool только из-за того, что модель его не вызвала. Сначала проверить effective toolsets и регистрацию callback. Generic `send_buttons` — отдельная альтернатива, только если существующий путь не покрывает контракт. Сохранить credential isolation и callback authorization; не патчить source Core. Полноценный релиз предшествует правкам каталожного PR/ответу ревьюеру.

## Контракты

| ID | Событие / условие | Требуемый результат | Доказательство приёмки | Статус |
|---|---|---|---|---|
| Q-001 | MAX-агенту нужно решение пользователя | Effective model schema содержит `clarify` с настоящим gateway callback; unavailable/disabled route явно диагностируется | Проверить effective toolsets/config, вызвать real registered handler в gateway context и наблюдать adapter dispatch | Проверено |
| Q-002 | Tool задаёт вопрос с choices | Отправить inline choices и Other в активный чат; связать question ID с exact session, owner и отправленным message | Зафиксировать actual HTTP payload; две sessions не разрешают чужие вопросы; unknown owner даёт безопасный отказ | Проверено |
| Q-003 | Владелец нажимает разрешённый choice | Однократно разрешить Core question текстом варианта и продолжить ожидающего агента; не создавать второй user turn | Real Core resolver/queue; result равен label, не index; нет duplicate MessageEvent; replay/foreign/stale/invalid indices не удаляют legitimate state | Проверено |
| Q-004 | Владелец нажимает Other либо вопрос открытый | Следующий разрешённый text отвечает на тот же pending question; нет преждевременного numeric/default answer и захвата чужой session | Real pending-question text interception; foreign click отклонён; timeout/cancel имеют явный outcome | Проверено |
| Q-005 | Send failure, поздний callback или Core question expired | Честно сообщить failure/timeout и очистить state; не выдавать actionable success для недоставленного вопроса | Failed SendResult, expired Core entry и delayed callback fixtures; секреты не выводятся | Проверено |
| Q-006 | Согласованный live agent вызывает tool | Пользователь видит inline keyboard (по 1 кнопке в ряду); selected answer становится tool result в том же run; Other/text и duplicate/foreign rejection подтверждены | Реальная MAX delivery, нажатие кнопки («Бета»), ввод текста Other («мой вариант»), gateway/tool result и продолжение агента подтверждены вживую | Проверено |

## Проверенные исходные наблюдения

- Core уже регистрирует `clarify`; gateway реализует send/register/wait. Effective visibility в указанной live session ещё не проверена.
- Plugin `send_clarify` рисует choices/Other и регистрирует callback state. Текущий handler делает await синхронного boolean `resolve_gateway_clarify`, передаёт index вместо текста choice, удаляет state до проверки choice и пытается создать synthetic user MessageEvent. Эти статические находки требуют regression tests с actual Core до закрытия.
- Существующие mocked clarify tests используют async resolver и не доказывают actual Core contract. Нужны meaningful real-registry/queue tests; проверки foreign-user protection сохраняются.
- Привязки реализации: `mixins/buttons.py`, clarify methods в `adapter.py`, `mixins/callback_auth.py`; Core `tools/clarify_tool.py`, `tools/clarify_gateway.py`, gateway clarify hook. Предложенный `tests/test_clarify_gateway_contract.py` пока не существует.

## Завершение

Записать tested Core/plugin revisions, effective tool exposure и actual outcomes. Обновлять feature/setup/security docs EN/RU, changelog и backlog только после прохождения соответствующих contracts. Для live tests нужны сообщение и нажатие пользователя; остановка действует до возобновления работы.
