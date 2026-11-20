# Background Session Notifications in MAX — Micro-Spec

[Russian version](20261119-background-session-notifications_RU.md)

Date: 2026-11-19. Status: Planned; no implementation or acceptance run. Source: user request and supplied Telegram screenshot showing a concise background-session notification with an “Open session” button. Plugin baseline: `69717984d5ee2c81007d4b59242765c8db6bcd69`; Core checkout inspected locally, but its runtime revision is not a pinned compatibility target for this contract.

## Intent and boundaries

When a parallel/background Hermes session produces a user-visible assistant result associated with the MAX owner, post a separate concise notification in that owner's MAX DM, labeled with the session title and containing an “Open session” inline button. On activation, show the session's first user message and the latest user-visible message/result that caused the notification, and switch the active gateway conversation to that session so subsequent turns use its context.

The notification is a bot-originated message, not an OS-level/system toast and not an input to the model. Preserve MAX's callback owner/chat/message/expiry checks and Core's session-resume authorization. Do not notify arbitrary users or expose another owner's session. Existing normal in-session completion delivery remains unchanged unless the user explicitly enables or selects this behavior.

## Contract

| ID | Trigger / context | Required result | Acceptance evidence | Implementation | Verification |
|---|---|---|---|---|---|
| MSN-001 | An eligible parallel/background session produces a user-visible assistant result routed to the configured MAX owner | Deliver a distinct concise MAX message containing a short notification, session title (fallback to a stable short identifier), and an inline “Открыть сессию” button; do not inject notification text as a user turn | Core-to-plugin integration test proves one notification with the expected target/session identity and no extra user message; ordinary foreground results are not misclassified | Planned | Not run |
| MSN-002 | The session result is available | Notification/button state identifies the exact resumable session and owner, not a mutable list position or prompt-text match; duplicate/replayed delivery does not create unsafe cross-session actions | Test stable session identity, duplicate delivery behavior, stale/unknown ID and missing session; document at-least-once or deduplication semantics | Planned | Not run |
| MSN-003 | Owner presses “Открыть сессию” on a valid notification | Validate owner, scoped chat, source message ID and expiry; retrieve the first user message and latest user-visible message/result for the identified session; present both in a context card and switch the gateway's active session | Exercise real MAX `_on_callback` dispatch with forged user/chat/message, expired state, malformed ID and valid action; assert only valid action resumes exact session and card contains first/latest excerpts | Planned | Not run |
| MSN-004 | Notification/result has no title, no readable message, expired/deleted session, or retrieval/resume fails | Fail safely with a useful short status; do not switch to another session or claim a context was restored; notification delivery failure must not break the completed parent turn | Failure-path tests for missing title/messages/session, Core rejection, MAX API error and stale button | Planned | Not run |
| MSN-005 | The feature is disabled, sender is not the configured owner, or the result belongs to an unrelated/foreground session | No notification and no session data disclosure; preserve current default behavior | Authorization and configuration matrix through Core routing and plugin callback entry points | Planned | Not run |

## Design constraints and investigation findings

- MAX Bot API documents `inline_keyboard` callback buttons; user presses arrive as `message_callback`. `POST /answers` can answer a callback and update a message. Official references: https://dev.max.ru/docs-api/use-cases/sending-messages/keyboard/ , https://dev.max.ru/docs-api/objects/Update/ , https://dev.max.ru/docs-api/methods/POST/answers (checked 2026-11-19).
- MAX plugin already has callback dispatch, owner/chat/message/TTL-bound interaction state, session listing/picking, first/latest context extraction, and `/resume --all` event generation. Reuse these mechanisms; do not create a parallel authorization scheme.
- Hermes Core routes process/delegation completion notices to the owning session through `gateway/run_notifications.py`; current MAX `send()` sends plain text and has no notification-card/callback metadata contract. A Core-to-adapter seam is required to carry stable resumable session identity and the result/title, or an equivalent adapter capability. Confirm the exact producer and delivery routes for each eligible type (background process vs async delegation) before implementation; do not assume every child session is independently resumable.
- The existing `/resume --all` pathway has an owner/admin boundary. Callback-triggered switching must use that established policy and must not weaken cross-platform or per-session authorization.
- Limit notification content to a concise title/summary; the button context card shows the exact first and latest user-visible messages (safely truncated for MAX's message limit). Do not expose tool transcripts or internal notification markers as the latest result.

## Implementation plan

1. Trace eligible Core producers, completion event fields, owner/source routing, delivery admission, and the actual MAX adapter send/callback path for supported Core revisions. Set the target event types and policy before coding.
2. Define the smallest compatible Core-to-adapter contract for an actionable completion card while preserving the generic notification path for other adapters and guaranteeing notification text is non-user input.
3. Add MAX owner-scoped, bounded/expiring callback state keyed to the session identity and emitted message; validate user, chat, message and existing Core resume authorization at the callback entry point.
4. Reuse session history extraction and resume mechanism; format a compact card with initial user request and latest user-visible result, then switch to the exact target session. Define safe behavior where the result transcript is unavailable.
5. Add Core integration and plugin tests for eligible/ineligible events, exact ownership/session routing, deduplication/replay, callback misuse/expiry, truncation and delivery/resume failures. Run focused tests and applicable docs/config checks on recorded plugin/Core revisions.
6. Keep live MAX delivery and button-click acceptance separate from automated tests; record them only when actually performed. Do not restart or deploy production as part of this contract.

## Handoff

Open work. No files or runtime behavior have been changed for this feature. Implementation requires a Core seam and plugin work; the final Core compatibility floor and exact background event types remain to be established by tracing the supported CI Core fixtures.
