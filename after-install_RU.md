# Плагин MAX установлен

## Дальнейшие шаги

1. Установите runtime-зависимости в то же Python-окружение, которое использует Hermes Gateway. Ориентируйтесь на текущий `pyproject.toml` и инструкции Hermes; системный `pip` может указывать на другое окружение.
2. Выполните `hermes gateway setup` и настройте платформу MAX. Храните `MAX_BOT_TOKEN` в защищённом `.env` Hermes или secret manager; не вставляйте секреты в аргументы команд, документацию, логи или чат.
3. Распознавание голосовых выполняет Hermes Core. Настройте STT в Core; плагин лишь передаёт и кэширует аудио для Core.
4. Выберите режим доставки. По умолчанию используется polling. Webhook требует публичный HTTPS URL и соответствующий секрет. Перед переключением проверьте существующие подписки MAX: при старте polling плагин может удалить свои старые webhook-подписки.
5. Перезапуск gateway и изменение подписок имеют внешние последствия — заранее согласуйте их.
6. Проверьте `hermes gateway status` и локальный health endpoint. `scripts/diagnose.sh --send` отправляет реальное сообщение и требует согласованного адресата.

Подробности: `docs/setup_RU.md`, `docs/security_RU.md`, `docs/troubleshooting_RU.md`. Официальные источники MAX и даты их проверки указаны в `docs/external-claims_RU.md`.


## Список сессий владельца

Несмотря на имя, `MAX_CROSS_SESSION=true` включает и MAX-список с кнопками. Укажите `MAX_CROSS_SESSION_USERS` явно. Если флаг выключен или пользователь не является владельцем, `/sessions` и `/resume` остаются командами Core без кнопок плагина. При закрытом боте список разрешённых пользователей служит fallback владельцев; при `MAX_ALLOW_ALL_USERS=true` fallback отключён. Не включайте межплатформенный доступ всем посетителям.

После настройки и согласованного перезапуска используйте Python gateway и активный профиль:

```bash
python scripts/check-session-routing.py --user-id OWNER_MAX_USER_ID --load-profile-env
```

Замените placeholder своим ID. Ожидаются JSON `handler=plugin`, `reason=owner_picker_ready`, `dispatch_matches_policy=true`, exit 0. Проверка не отправляет сообщения и не читает историю; health и import недостаточны. Затем вручную проверьте `/sessions` и кнопки в MAX. Подробности: [диагностика](docs/troubleshooting_RU.md).
