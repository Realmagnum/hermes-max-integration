# Outgoing MAX Bot API attachments (candidate A)

`max_send_attachments` is registered by the plugin's normal `register(ctx)` using the public `ctx.register_tool(..., is_async=True)` API. No Core patch. It is deliberately **current MAX conversation only**: destination comes from task-local `get_session_env`, not model arguments. In CLI/Desktop/other platforms it refuses rather than bypassing `send_message` destination policy. Existing MEDIA delivery and standalone media routing remain unchanged in this branch.

Call the tool with `{"text":"Optional caption", "attachments":[ATTACHMENT]}`. `format` may be `markdown`/`html`; `link` is `{"type":"reply"|"forward","mid":"..."}`. `notify` is omitted or true (channel identity cannot safely be inferred from a negative ID). No automatic resend on uncertain failure. Only explicit HTTP 400 `attachment.not.ready` uses the existing finite readiness budget.

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
This is not a claim of complete Bot API parity: nullable schema fields are intentionally narrowed, image `photos` has ambiguous example vs CDN-map shape, request limits beyond public prose are conservative, notify=false requires reliable target-kind discovery. Cross-destination raw attachment sends are **not** exposed; existing `send_message` still handles ordinary media. Image dimensions (7680×7680), audio duration (60 min), and extension admission remain MAX-server enforced, not a local metadata probe. No live delivery/readback or min-Core plugin admission was run.

A retains baseline 50 MiB buffering/limits. Independent candidate B replaces that transport; do not advertise large uploads after installing A alone. A and B share a base but neither depends on the other; both touch `media_upload.py` in disjoint areas and require combined-candidate testing before deployment.

Sources: [NewMessageBody](https://dev.max.ru/docs-api/objects/NewMessageBody), [media](https://dev.max.ru/docs-api/use-cases/sending-messages/media), [other attachments](https://dev.max.ru/docs-api/use-cases/sending-messages/another-attachments), [keyboard](https://dev.max.ru/docs-api/use-cases/sending-messages/keyboard), [Hermes plugin API](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins), [public imports](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins/public-api).

Offline verification: `sh ../run-python -m pytest tests/test_attachment_tool.py tests/test_attachment_tool_extra.py tests/test_media_readiness.py tests/test_media_recipient_routing.py -q`. The workspace runner is a local evidence helper, not a dependency to distribute.
