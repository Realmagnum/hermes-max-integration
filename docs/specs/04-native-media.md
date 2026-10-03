# Micro-Specs: Группа MEDIA (MAX Native Media — Plugin-Only)

Стандарт: Micro-Spec («OpenSpec без OpenSpec»). Источник: планы `2026-09-30_021051-max-plugin-only-native-media.md` и `2026-09-30_015255-max-native-media.md`.

---

### ID: MEDIA-CONTRACT-01
* **Требование:** Плагин MAX регистрирует кастомный `send_message_handler` в `ctx.register_platform()`, способный обрабатывать медиа-запросы.
* **Условие:** Gateway или CLI вызывает отправку сообщения в платформу `max` через `tools/send_message_tool.py`.
* **Ожидаемый результат:** `platform_registry` находит зарегистрированный `send_message_handler` и передаёт ему кортеж `(args, chat_id, platform_name, pconfig)`.
* **Проверка:** `pytest -q tests/test_plugin_media_handler_contract.py -k "test_max_registers_send_message_handler"` завершается с кодом 0.
* **Не входит:** Модификация core-файлов Hermes Agent.

---

### ID: MEDIA-PARSE-01
* **Требование:** Парсер плагина извлекает пути `MEDIA:<path>`, очищает текст сообщения от служебных директив и определяет флаг `[[as_document]]`.
* **Условие:** На вход хендлера поступает строка вида `"Отчёт за день MEDIA:/tmp/chart.png [[as_document]]"`.
* **Ожидаемый результат:** Функция `extract_plugin_media_request` возвращает `caption="Отчёт за день"`, список файлов `[("/tmp/chart.png", False)]` и `force_document=True`.
* **Проверка:** `pytest -q tests/test_plugin_media_handler.py -k "test_extract_plugin_media_directives"` завершается с кодом 0.
* **Не входит:** Загрузка файлов из сети по HTTP(S) ссылкам.

---

### ID: MEDIA-VALID-01
* **Требование:** Парсер отклоняет несуществующие пути, директории и неподдерживаемые типы файлов до обращения к сети.
* **Условие:** В директиве `MEDIA:` передан несуществующий файл (`/path/to/missing.png`) или путь к каталогу (`/tmp/`).
* **Ожидаемый результат:** Хендлер не падает с unhandled exception, а возвращает статус с `success=False` или предупреждением об отсутствующем файле; сетевой запрос к MAX API не создаётся.
* **Проверка:** `pytest -q tests/test_plugin_media_handler.py -k "test_missing_media_path_rejected"` завершается с кодом 0.
* **Не входит:** Конвертация форматов изображений на лету.

---

### ID: MEDIA-UPLOAD-01
* **Требование:** Плагин загружает файл в MAX Bot API через `POST /uploads?type={type}` multipart-формой с полем `data` и токеном без префикса `Bearer`.
* **Условие:** Валидный локальный файл передаётся в функцию отправки вложений.
* **Ожидаемый результат:** Отправляется HTTP POST multipart запрос на правильный URL (`type=image|file|audio|video`), заголовок `Authorization: {token}` (без `Bearer`), в ответе извлекается `token` загруженного файла.
* **Проверка:** `pytest -q tests/test_file_send.py -k "test_upload_file_multipart_protocol"` завершается с кодом 0.
* **Не входит:** Параллельная чанковая докачка больших файлов (resumable upload).

---

### ID: MEDIA-SEND-01
* **Требование:** Сообщение с полученным токеном вложения отправляется в чат, а результат честно отражает статус доставки вложений (`media_delivered=True/False`).
* **Условие:** Файл успешно загружен в `/uploads`, отправляется `POST /messages` с `attachments: [{"type": ..., "token": ...}]`.
* **Ожидаемый результат:** При успехе возвращается результат с `media_delivered=True`; при ошибке отправки вложения `media_delivered=False`, а пользователь получает понятное описание сбоя.
* **Проверка:** `pytest -q tests/test_file_send.py -k "test_send_message_with_attachment_truthful_result"` завершается с кодом 0.
* **Не входит:** Автоматическая отправка уведомления в Telegram при сбое доставки в MAX.
