# Group access and MAX identifiers

## Find user and group IDs

On the checked Core fixture, an admitted user can send `/whoami` in the bot DM to see their user ID. This command still passes plugin authorization first: it cannot bootstrap a user denied by `MAX_ALLOWED_USERS`. Do not temporarily open the bot to everyone to discover an ID.

For a new user, ask them to send a harmless DM to the bot. The gateway operator can temporarily enable DEBUG for the plugin logger and read `MAX: ignoring message from unauthorized user <ID>` from the existing gateway log, then restore logging. This record contains only the denied sender ID. Do not publish the whole log or enable HTTP wire logging. The canonical incoming event field is `message.sender.user_id`; on callbacks it is `callback.user.user_id`.

To find a group ID, keep group access closed and ask an already globally allowed user to send a harmless group message. At INFO, the plugin logs `MAX: group message blocked: policy=allowlist user=<USER_ID> chat=<CHAT_ID>`. This yields both IDs without admitting the request to the agent. If group access is already open, use the operator's existing event diagnostics: `message.recipient.chat_id` identifies the group. A `bot_added` event also carries `chat_id`; the `user` there identifies whoever added the bot, not every group member. The plugin does not maintain a group directory.

Use numeric IDs in `MAX_ALLOWED_USERS`, `MAX_GROUP_ALLOWED_USERS` and `MAX_GROUP_ALLOWED_CHATS`, preserving a minus sign if present. Prefixes `user:` and `chat:` belong to delivery targets such as `MAX_HOME_CHANNEL`; they are not needed in these allowlists. A dialog also has a service chat ID: `recipient.chat_type=dialog` identifies it as a DM, not a group.

MAX currently has no ready API listing all groups/channels containing a bot. Reuse the gateway's existing event receiver; do not start a competing `GET /updates` consumer or replace webhook subscriptions just to discover IDs. Official contracts checked 2026-10-22: [ID discovery](https://dev.max.ru/docs-api/use-cases/getting-chat-id), [Update](https://dev.max.ru/docs-api/objects/Update), [Message](https://dev.max.ru/docs-api/objects/Message). `/whoami` was checked against Core `ca13a7828acd2ba8c75e1c1d1694cbc1aee7df3f`; older Core versions can differ.

## Trusted family and mixed groups

Both scenarios use the same explicit lists. Replace the placeholders with numeric IDs; only the trusted people belong in the user lists, even when other people are in the group.

```bash
MAX_ALLOW_ALL_USERS=false
MAX_ALLOWED_USERS=OWNER_ID,TRUSTED_ID_1,TRUSTED_ID_2
MAX_GROUP_POLICY=allowlist
MAX_GROUP_ALLOWED_USERS=OWNER_ID,TRUSTED_ID_1,TRUSTED_ID_2
MAX_GROUP_ALLOWED_CHATS=GROUP_ID
```

In a family-only group, list each family member you trust with the Hermes profile's agent/tools. In a mixed group, leave untrusted members out: their messages, commands and button callbacks are rejected. MAX membership or administrator status does not automatically grant agent access. An admitted user still cannot press another requester's approval or choice button.

Authorization order is global user access, then group access, then the existing action-specific checks. `MAX_GROUP_POLICY=closed` denies all group input; `open` skips only the group gate. Under `allowlist`, every configured list must match (AND); a single empty list leaves that dimension unrestricted, but both lists empty deny all group input. A chat-only list admits every globally allowed user in those chats; a user-only list allows those users in any group. These lists are bot-wide: there is no separate user list per group. Callbacks follow the current policy before consuming pending state; a denied press leaves it pending, subject to its normal expiry.

## Context, privacy and agent powers

Everyone in the group can see the bot's replies and delivered files, including people barred from requesting work. Use DMs for private tasks. Per-user group sessions separate conversation context when Core `group_sessions_per_user=true` (checked default); this is not file, credential or tool isolation. A plugin allowlist grants access to the shared Hermes profile, not a reduced family role. Core slash-command administration is a separate policy; plugin trust does not automatically make someone a Core administrator.

Keep `MAX_CROSS_SESSION_USERS` limited to owners who may access cross-platform history. Do not copy a family allowlist there automatically. Private session search and switching belong in DMs when results must remain private. The plugin provides no MAX mention-only gate; do not assume messages require an @mention. For different tool privileges or different people per group, use separately configured agent profiles/bots with independent resources.

## First-install defaults

A fresh adapter and CLI setup use the following safe defaults. CLI setup writes missing entries explicitly and preserves existing group/session settings on reconfiguration. Desktop exposes group policy/lists and the public webhook URL; leaving a field empty uses its runtime default.

| Variable | Fresh value | Consequence |
|---|---|---|
| `MAX_ALLOW_ALL_USERS` | `false` | Global allowlist required |
| `MAX_ALLOWED_USERS` | empty until entered | No incoming users admitted |
| `MAX_GROUP_POLICY` | `allowlist` | Explicit group permissions required |
| `MAX_GROUP_ALLOWED_USERS` | empty | No user dimension configured |
| `MAX_GROUP_ALLOWED_CHATS` | empty | Together with empty users, blocks groups |
| `MAX_CROSS_SESSION` | `false` | Core session commands by default |
| `MAX_CROSS_SESSION_USERS` | empty | No explicit picker owners |
| `MAX_SESSIONS_LIMIT` | `10` | List/search limit |
| `MAX_SESSIONS_DEFAULT_ALL` | `false` | MAX-only default when picker enabled |

Token-only installation receives events but rejects agent requests until user access is configured. The CLI warns when no user IDs are supplied. Group access and owner session picking are deliberate later opt-ins. `MAX_WEBHOOK_URL` empty selects polling; host/port/path alone do not enable webhook delivery. See [setup](setup.md) for transport and owner-picker configuration. Changes take effect after the gateway reload/restart through the normal profile workflow.
