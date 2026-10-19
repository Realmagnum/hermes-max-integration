# Interactive Session Picker with Buttons — Micro-Spec

[Russian version](20261016-interactive-sessions_RU.md)

Date: 2026-10-16. Status: specified, implementation in progress. Source: user request for interactive cross-platform session listing and selection via MAX inline buttons, message auto-cleanup on cancel/selection, and context restoration summary. Baseline commit: `877df52`; target deployment: SRV-TEST test gateway installation.

## Intent and boundaries

Replace the plain-text `/sessions` command output with an interactive inline keyboard picker. The list displays recent sessions across platforms (CLI, Telegram, MAX, Desktop, WebUI) formatted with visual spacing, bold numbering, platform emojis, representative quotes from the initial user prompt, timestamps formatted as `YYYY/MM/DD HH:MM`, and message counts. Selection buttons are organized 5 per row, plus an action row for Refresh and Cancel.

On selection or cancellation, the list message is removed via `delete_message` to avoid chat clutter. Upon choosing a session, the adapter switches the active session for the chat and sends a compact context reminder card containing the initial task and latest message exchange.

Non-goals:
- Modifying Hermes Core session switching logic or database schema.
- Exposing session selection to unauthorized non-owner callers (strict SEC-01 and SEC-05 enforcement).

## Contracts

| ID | Trigger / context | Required result | Acceptance evidence | Status |
|---|---|---|---|---|
| SESS-001 | Authorized owner sends `/sessions` or `/resume` (no args) | Query `SessionDB` (up to 20, default 15); format with bold numbers, source emojis, quotes from initial prompt, `YYYY/MM/DD HH:MM` timestamps, message counts, and empty line spacing between items | Unit test asserting rendered message text structure, date formatting, and spacing | Implemented |
| SESS-002 | Session picker message is posted | Message includes `inline_keyboard` attachment with 5 buttons per row (`{emoji} {i}`) and bottom action row (`🔄 Обновить`, `❌ Отмена`); callback payloads prefixed with `session:` (`session:pick:<id>`, `session:cancel`, `session:refresh`) | Unit test asserting keyboard rows, button count, button labels, and callback payloads | Implemented |
| SESS-003 | Any `session:*` callback arrives | Verify caller is authorized owner and callback matches registered message ID (SEC-01). Reject foreign users, expired states, or unowned prompts fail-closed | Unit tests for unauthorized user rejection, expired interaction state, and missing message ID | Implemented |
| SESS-004 | Owner presses `❌ Отмена` | Delete the picker message via `delete_message(chat_id, message_id)`; remove session picker state; do not switch session | Unit test asserting `delete_message` called with target `message_id` and no resume event returned | Implemented |
| SESS-005 | Owner presses `🔄 Обновить` | Re-query `SessionDB` and update the message with latest sessions and buttons | Unit test asserting session store re-query and message update/edit call | Implemented |
| SESS-006 | Owner presses a session button (`session:pick:<id>`) | Delete the picker message; send a compact context confirmation card (active session info, initial task quote, last message quote); return `MessageEvent` with `/resume --all <session_id>` to switch gateway session | Unit test asserting message deletion, context confirmation send, and returned `/resume --all <id>` event | Implemented |

## Implementation Anchors

- `mixins/sessions.py`: `_handle_cross_sessions`, session formatting, quote extraction, interactive keyboard construction.
- `adapter.py`: `_on_callback` dispatch for `prefix == "session"`, handler methods `_handle_session_callback`, `_handle_session_pick`, `_handle_session_cancel`, `_handle_session_refresh`.
- `tests/test_interactive_sessions.py`: complete unit test suite verifying SESS-001 through SESS-006.
