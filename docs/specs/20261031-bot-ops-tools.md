# MAX bot operations tools (history, chats, members, pins) — Micro-Spec

Source: operator request, 2026-10-31. Baseline: `78d9abf`. Core: live tree at `/home/magnum/.hermes/hermes-agent` (Core ≥ 0.21.4).

Scope: add a plugin-provided toolset that exposes the MAX Bot API operations the adapter currently does not use — message history, chat metadata, members/admins, pins. Read operations ship enabled; mutating operations are opt-in and owner-only. Delivery semantics of the existing adapter (send/receive, chunking, media, callbacks) must not change.

## Why this seam

`send_message`/`hermes send` already cover outbound delivery, and the adapter covers ingress. What the agent cannot do today is *inspect and administer* a chat: read what was said before it joined, list chats it participates in, discover who is an admin, pin a decision. Those are ordinary Bot API calls (`GET /messages`, `GET /chats`, `GET /chats/{id}/members`, `POST .../members/admins`, `PUT /chats/{id}/pin`), not a new transport — so they belong to the plugin as a tool, not to Core and not to a separate MCP server.

## Contracts

| ID | Trigger / context | Required result | Acceptance |
|---|---|---|---|
| OPS-001 | Agent needs earlier conversation in a chat | `max_get_messages` returns messages for `chat_id` (with `count` ≤ 100, optional `from`/`to` ms bounds) or for an explicit `message_ids` list; both forms are mutually exclusive and an empty argument set is a validation error | `tests/test_ops.py`; mocked transport asserts query shape (`message_ids` comma-joined, not repeated params) |
| OPS-002 | Agent needs one message by id | `max_get_message` returns that message; unknown id surfaces the API error verbatim instead of an empty success | `tests/test_ops.py` |
| OPS-003 | Agent enumerates where the bot is present | `max_get_chats` returns group chats with `marker` passthrough for pagination; `max_get_chat` returns one chat's details | `tests/test_ops.py`; marker round-trip asserted |
| OPS-004 | Agent inspects membership | `max_get_members` and `max_get_admins` return users with roles/permissions; `count`/`marker` forwarded | `tests/test_ops.py` |
| OPS-005 | Agent pins a decision | `max_pin_message` / `max_unpin_message` succeed and return the API result; a pin in a dialog (non-group) is rejected locally with a clear message instead of an opaque API error | `tests/test_ops.py` |
| OPS-006 | Mutating operation requested | `max_edit_chat`, `max_set_admin`, `max_remove_admin`, `max_add_members`, `max_remove_member` are registered only when `MAX_ADMIN_TOOLS=1`; without it the tool is absent from the schema, not merely refused at call time | `tests/test_ops.py`; two registration fixtures (flag on/off) |
| OPS-007 | Any tool call | Every handler rejects a caller that is not in `MAX_ALLOWED_USERS` (or is not the `MAX_HOME_CHANNEL` owner) before any HTTP request; rejection is logged without the token | `tests/test_ops.py`; `tests/test_catalog_security.py` pattern |
| OPS-008 | Transport behaviour | All calls use `MAX_API_BASE`, `get_max_ssl_context()`, the raw token from `get_max_secret()`; a non-2xx is retried at most twice on 429/5xx with the `Retry-After` delay, and each error text is redacted of the token | `tests/test_ops.py`; no token in captured logs |
| OPS-009 | Long read | Message bodies are truncated per-item at a documented `MAX_OPS_TEXT_LIMIT` (default 2000 chars) with an explicit `truncated: true` flag, so a huge chat cannot flood the model context | `tests/test_ops.py` |
| OPS-010 | Operator enablement | `MAX_ADMIN_TOOLS` documented in `plugin.yaml` (`optional_env`), `docs/setup.md`, `docs/features.md` and both READMEs; default off | `scripts/check-config-reference.py`; `scripts/check-ru-en-parity.py` |

## Non-goals

- No new ingress: `get_updates` is not exposed as a polling tool — the adapter owns the update stream and a second consumer would steal updates from it.
- No media upload/download through these tools; `MEDIA:` and the adapter's media mixin remain the only media path.
- No Core change and no override of an existing tool name.

## Files

| Path | Change |
|---|---|
| `ops/client.py` | Thin MAX API client: shared httpx client, retry/backoff, token redaction, pagination helpers |
| `ops/tools.py` | Tool schemas + handlers, read set always, admin set behind `MAX_ADMIN_TOOLS` |
| `adapter.py` | `ctx.register_toolset("max_ops")` + registration in `register()`; no change to the send path |
| `tests/test_ops.py` | Transport-mocked contracts OPS-001…009 |
| `plugin.yaml`, `docs/*`, `README*.md` | `MAX_ADMIN_TOOLS` documentation pair |

## Evidence plan

1. Unit: `tests/test_ops.py` green against the live Core tree; existing suite unchanged (no sends touched).
2. Live readback with the real token on one group chat the bot already belongs to: `get_chats` → `get_chat` → `get_members` → `get_messages(count=5)`; record ids and timestamps, no message bodies.
3. Mutating operations verified only against a throwaway chat with an explicit operator go-ahead; a `remove_admin` that returns `success: true` without effecting the change is reported as an API-side bug, not as success.
