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

## Scope and remaining acceptance gaps
This is not a claim of complete Bot API parity: image photos has ambiguous example vs CDN-map shape; request limits beyond public prose are conservative. Cross-destination agent raw attachment sends remain **blocked (F1)**: current official Hermes platform docs explicitly say send_message is not an agent-callable tool and plugins must not register an equivalent outbound model surface. Current Core ae2a81ccc00e9b7c06301523e5bb09608397149c and minimum0.21.4 source d337b736aa1e8ebecfab043842d13e4a2d2f48a3 confirm the intentional absence; public ctx.dispatch_tool cannot dispatch a missing tool. Public send_message_handler is a host-driven send extension, not authorization to add an equivalent model tool. No private Core helper import or new destination-policy bypass is introduced. Resolving F1 requires a supported host-authorized typed-send seam/decision from Core owners, or an explicitly accepted host-driven interface rather than claiming the requested agent workflow works. Image dimensions (7680×7680), audio duration (60min), and extension admission remain MAX-server enforced. No live delivery/readback occurred. Reused-dependency current Plugin Doctor passes; minimum admission is not proven (the isolated reused environment reports distribution version0.0.0 and the real version gate refuses registration; its Python3.14 also exceeds minimum Core's declared <3.14 range). The old manifest floor is not new compatibility evidence.

A retains baseline 50 MiB buffering/limits. Independent candidate B replaces that transport; do not advertise large uploads after installing A alone. A and B share a base but neither depends on the other; both touch `media_upload.py` in disjoint areas and require combined-candidate testing before deployment.

Sources: [NewMessageBody](https://dev.max.ru/docs-api/objects/NewMessageBody), [media](https://dev.max.ru/docs-api/use-cases/sending-messages/media), [other attachments](https://dev.max.ru/docs-api/use-cases/sending-messages/another-attachments), [keyboard](https://dev.max.ru/docs-api/use-cases/sending-messages/keyboard), [Hermes plugin API](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins), [public imports](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins/public-api).

Offline verification: `sh ../run-python -m pytest tests/test_attachment_tool.py tests/test_attachment_tool_extra.py tests/test_media_readiness.py tests/test_media_recipient_routing.py -q`. The workspace runner is a local evidence helper, not a dependency to distribute.
