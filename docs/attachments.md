# Outgoing MAX Bot API attachments (candidate A)

`max_send_attachments` is registered by the plugin's normal `register(ctx)` using the public `ctx.register_tool(..., is_async=True)` API. No Core patch. It is deliberately **current MAX conversation only**: destination comes from task-local `get_session_env`, not model arguments. In CLI/Desktop/other platforms it refuses rather than bypassing `send_message` destination policy. Existing MEDIA delivery and standalone media routing remain unchanged in this branch.

Call the tool with `{"text":"Optional caption", "attachments":[ATTACHMENT]}`. `format` may be `markdown`/`html`; `link` is `{"type":"reply"|"forward","mid":"..."}`. Official nullable text/format/link and nullable contact name/selectors or image/share selectors normalize to absence; multiple non-null selectors still fail. `notify` must be boolean: false is allowed for the user_id DM recipient contract; chat_id destinations require a successful GET/chats response confirming chat/group/dialog/dm. Channel or unknown metadata fails closed before upload/message. No automatic resend on uncertain failure. Only explicit HTTP400 attachment.not.ready uses the existing finite readiness budget.

| Type | ATTACHMENT variants | Combinations |
|---|---|---|
| image | `{"type":"image","payload":{"token":"..."}}`; payload alternatively `{"url":"https://example.com/image.png"}` or `{"photos":{"photo-id":{"token":"..."}}}`; local descriptor `{"type":"image","path":"/absolute/image.png"}` | image/video + at most one keyboard; 12 total |
| video | `{"type":"video","payload":{"token":"..."}}` or local `path` | as image |
| audio | `{"type":"audio","payload":{"token":"..."}}` or local `path` | one audio + optional keyboard (conservative policy) |
| file | `{"type":"file","payload":{"token":"..."}}` or local `path` | one file + optional keyboard |
| sticker | `{"type":"sticker","payload":{"code":"..."}}` or payload `{"url":"https://i.oneme.ru/getSmile?..."}` | sole attachment |
| contact | `{"type":"contact","payload":{"name":"Synthetic contact","contact_id":42}}` or `vcf_info` instead of contact_id | one contact + optional keyboard |
| inline_keyboard | `{"type":"inline_keyboard","payload":{"buttons":[[{"type":"message","text":"Hello"}]]}}` | at most one keyboard |
| location | `{"type":"location","latitude":0,"longitude":0}` (synthetic example) | sole attachment; combinations undocumented |
| share | `{"type":"share","payload":{"url":"https://example.com"}}` or payload token | sole attachment; combinations undocumented |

Keyboard buttons all require text (1..128 chars):
- callback: `{"type":"callback","text":"Choose","payload":"choice"}` (payload <=1024)
- link: `{"type":"link","text":"Open","url":"https://example.com"}` (URL <=2048)
- request_contact: `{"type":"request_contact","text":"Share contact"}`
- request_geo_location: `{"type":"request_geo_location","text":"Share location","quick":false}`
- open_app: `{"type":"open_app","text":"Open app","web_app":"example_bot","payload":"start"}`; alternatively numeric `contact_id`; optional payload
- message: `{"type":"message","text":"Hello"}`
- clipboard: `{"type":"clipboard","text":"Copy","payload":"example"}` (payload <=1024)

30 rows × 7 buttons; row maximum 3 if any link/open_app/request_geo_location/request_contact. Unknown fields and invalid combinations are rejected before HTTP; request JSON <=64 KiB. URLs are HTTPS-only, no credentials/private literals. These URLs are handed to MAX, not fetched locally. File access uses public `agent.file_safety.raise_if_read_blocked` before upload.

## Host-driven typed CLI (repair2)

Explicit operation: `hermes max send-attachments --to max:<destination> --body-file /absolute/body.json`.
This public `ctx.register_cli_command(name="max", setup_fn=...)` extension uses the platform's matching command name so current Core can materialize the deferred MAX platform during CLI discovery. It is not a new native Core JSON flag, model destination tool, or autonomous authorization to contact new recipients.

The producer validates the closed body grammar and file_safety, writes a private mode0600 temporary transport file (encoded envelope <=64KiB), and calls the standard public module CLI (`sys.executable -m hermes_cli.main`) for stock `hermes send --to ... --file ... --json`. Home/profile environment is retained; only the child's `HERMES_HOME` is explicitly pinned to the current resolved home, and `HERMES_MAX_TYPED_ENVELOPE_V1` points at the temporary file. The envelope is `HERMES_MAX_TYPED_V1:` followed by strict base64 of UTF-8 JSON `{ "version":1, "body": NewMessageBody }`; no destination is allowed in it. No credentials/body are put in argv. Both child output pipes together are bounded to64KiB plus one detection byte; timeout/overflow/ambiguous failure never triggers resend. Temporary transport is removed on completion/failure.

Only that explicit child opt-in installs the public `send_message_handler`. It binds the exact envelope text, revalidates the body after Core target resolution/egress authorization, and uses only Core's resolved `chat_id`. Unknown version/fields, changed message, threads/mentions, invalid fields/local files fail closed. Ordinary text, JSON documents and MEDIA/cron sends without opt-in retain the previous platform handler/fallback unchanged. Unmarked JSON is never a command. Explicit opt-in with an ordinary unmarked file also leaves the ordinary route unchanged.

The current MAX-conversation model tool remains unchanged and has no destination argument. Desktop/DM cross-destination access is the explicit host CLI above, as accepted by the parent; it is not an equivalent outbound model tool. Core authorization and MAX notify/recipient/file/security policy are not removed or replaced by a plugin allowlist. Local tests execute the real `hermes_cli.main.main()` in a subprocess, real host resolution/send engine and authorization, with synthetic policy state and final HTTP transport fixtures; this is not live MAX or installed-launcher admission.

## Scope and remaining acceptance gaps
Minimum plugin load/admission is checked on genuine Core0.21.4/Python3.12. The typed CLI requires public CLI registration and platform send_message_handler; the standard module CLI retains the interpreter/profile rather than depending on the newer chat_launch helper. Complete host/media delivery is exercised on Core0.23.2 (ae2a81ccc00e9b7c06301523e5bb09608397149c). The full minimum host matrix did not complete, so minimum typed-CLI parity remains unproven; existing legacy ordinary-media rejection is preserved, not advertised as delivery. The current reused dependency runtime has a pre-existing browser-harness/Pillow pin conflict; functional route tests are not a clean dependency-admission claim. Image photos has ambiguous example vs CDN-map shape; public prose limits remain conservative. Image dimensions (7680×7680), audio duration (60min), and extension admission remain MAX-server enforced. Independent critic, live delivery/readback and publication are not performed by the builder.

A retains baseline 50 MiB buffering/limits. Independent candidate B replaces that transport; do not advertise large uploads after installing A alone. A and B share a base but neither depends on the other; both touch `media_upload.py` in disjoint areas and require combined-candidate testing before deployment.

Sources: [NewMessageBody](https://dev.max.ru/docs-api/objects/NewMessageBody), [media](https://dev.max.ru/docs-api/use-cases/sending-messages/media), [other attachments](https://dev.max.ru/docs-api/use-cases/sending-messages/another-attachments), [keyboard](https://dev.max.ru/docs-api/use-cases/sending-messages/keyboard), [Hermes plugin API](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins), [public imports](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins/public-api).

Offline verification: `sh ../run-python -m pytest tests/test_attachment_tool.py tests/test_attachment_tool_extra.py tests/test_media_readiness.py tests/test_media_recipient_routing.py -q`. The workspace runner is a local evidence helper, not a dependency to distribute.
