# Interactive MAX questions — Micro-Spec

[Russian version](20261013-interactive-questions_RU.md)

Date: 2026-10-13. Status: specified, implementation pending. Source: the user's request to expose an interactive question action to the MAX agent and return button answers to the same session. Baseline `887611a`; approved live target is the existing test installation. Rendering methods already exist; their presence does not prove tool availability or correct callback handling.

## Intent and boundaries

Use the existing public Core `clarify` tool and gateway hook if available. Do not duplicate the tool merely because a model did not call it. Diagnose effective toolsets and callback registration first. A generic `send_buttons` action is a separate alternative only if the existing route cannot satisfy the contract. Preserve credential isolation and callback authorization; no Core source patch. Full release precedes catalog PR edits/reviewer response.

## Contracts

| ID | Trigger / context | Required result | Acceptance evidence | Status |
|---|---|---|---|---|
| Q-001 | A MAX agent turn needs a user decision | Effective model tool schema contains `clarify`, with a real gateway callback; unavailable/disabled route is diagnosed explicitly | Inspect effective toolsets/config; invoke real registered handler in gateway context and observe adapter dispatch | Verified |
| Q-002 | Tool asks a question with choices | Send inline callback choices and Other to the active chat; bind question ID to exact session, owner and sent message | Capture actual HTTP payload; two sessions do not cross-resolve; unknown owner fails safely | Verified |
| Q-003 | Owner clicks a valid offered choice | Resolve pending Core question once with the actual choice text, then continue the waiting agent; do not invent a second user turn | Exercise real Core resolver/queue; result equals offered label, not index; no duplicate MessageEvent; replay/foreign/stale/invalid indices cannot consume legitimate state | Verified |
| Q-004 | Owner clicks Other or an open-ended question is asked | Next authorized text resolves the same pending question; no premature numeric/default answer or unrelated-session capture | Real pending-question text interception; foreign click rejected; timeout/cancel has explicit outcome | Verified |
| Q-005 | Sending fails, callback arrives late, or Core question expired | Report failure/timeout truthfully and retire state appropriately; do not show an actionable success for an undelivered question | Failed SendResult, expired Core entry and delayed callback fixtures; no secrets in output | Verified |
| Q-006 | Approved live agent invokes the tool | User sees inline keyboard (single button per row); selected answer becomes tool result in that same run; Other/text and duplicate/foreign rejection confirmed | Real MAX delivery, user button press ("Бета"), Other text input ("мой вариант"), gateway/tool result and agent continuation observed live | Verified |

## Verified baseline findings

- Core already registers `clarify`; the gateway implements a send/register/wait path. Effective visibility in the reported live session has not yet been inspected.
- Plugin `send_clarify` renders choices/Other and registers callback state. Its current handler awaits Core's synchronous boolean `resolve_gateway_clarify`, passes an index instead of choice text, consumes state before validating the choice, and attempts a synthetic user MessageEvent. These static findings require regression tests against actual Core before closure.
- Existing mocked clarify tests use an async resolver and therefore do not prove the actual Core contract. Replace that seam with meaningful real-registry/queue tests; keep foreign-user protection tests.
- Implementation anchors: `mixins/buttons.py`, clarify methods in `adapter.py`, `mixins/callback_auth.py`; Core `tools/clarify_tool.py`, `tools/clarify_gateway.py`, gateway clarify hook. Proposed test file `tests/test_clarify_gateway_contract.py` does not exist yet.

## Completion

Record tested Core/plugin revisions, effective tool exposure and actual outcomes. Update feature/setup/security docs EN/RU, changelog and backlog only after the corresponding contracts pass. Live tests need the user's message and click; stop remains in force until work is resumed.
