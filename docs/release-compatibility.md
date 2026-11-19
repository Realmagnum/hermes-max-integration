# Release compatibility scope

The declared minimum remains Hermes Core 0.21.4; metadata is unchanged.

Core 0.21.4 exposes `PlatformEntry.send_message_handler` in
`gateway/platform_registry.py:97` and invokes it in
`tools/send_message_tool.py:730–734`. Typed CLI does not need an invented Core JSON
flag or a model destination tool. Two isolated Python3.12 native public CLI
location requests reached the real authorization/router and delivered the exact
location attachment to controlled loopback HTTP. No envelope was sent as text.
This proves that concrete typed path, **not** the complete minimum matrix.

Earlier 25-second failures came from the integration harness's outer
`Popen.communicate(timeout=25)` deadline, encompassing both root CLI discovery and
the producer's child CLI discovery. Historical logs show both discovery rounds
and the real policy input read, but no HTTP boundary. No historical child stack
was captured: the precise cause of its longer latency remains unestablished.
It is not evidence of a missing minimum public hook. Do not call it a proven
Core deadlock, bootstrap failure, or full minimum compatibility PASS.

Legacy ordinary standalone media is separately constrained by the absence of
`StandaloneSendPolicy`; retain its strict refusal. Do not substitute the typed
transport envelope as ordinary text on a host without its public handler.

The router regression test selects the real current `gateway.outbound.send` or
legacy `tools.send_message_tool` module without mocking the router, authorization,
or weakening its existing assertions. All16 router cases pass on current Core.
The independent minimum native matrix is now accepted: **16 PASS, 0 skip** on
Core0.21.4/Python3.12:9 typed contact/location/keyboard cases across local/API/MAX
origins, denied destination with zero HTTP, ordinary text,4 strict ordinary-media
refusals on legacy Core, and503/no automatic replay. This is not ordinary-media
parity, all9 attachment-type minimum coverage, or the full minimum plugin suite.

Current full suites from workspace-root cwd, in separate serial processes, now
pass: **A1060 PASS; combined1095 PASS;0 failures/errors/skips**. The repaired sibling
import is relative to its real test package. Clarify tests call the actual legacy
session API when available; on current Core they resolve the real session-owned
pending entry (including choice prompts), then call the ID-bound public API.
No-pending, foreign-session, replay, awaiting_text and exact tool-result assertions
remain. Targeted diagnostics/clarify tests:15 PASS on genuine minimum,15 PASS on
current Core. Production code, minimum metadata, and accepted B bytes are unchanged.

These are offline functional results, not clean dependency admission or remote CI.
The inherited current Core/browser-harness/Pillow conflict, parent gateway lifecycle,
delta review and PR/exact-head CI gates remain separate.
