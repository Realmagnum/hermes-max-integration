# Session list policy — Micro-Spec

[Russian version](20261021-session-list-policy_RU.md)

Date: 2026-10-21. Baseline: `5144194cc281c899bccc744d39d0e8e33813ef0d`, branch `feature/microspec-pipeline`. Status: implemented; automated verification completed on 2026-10-21; live MAX acceptance not run. Source: current user request. This amendment supersedes the default cross-platform scope and fixed list size in [interactive sessions](20261016-interactive-sessions.md); SESS-002 through SESS-006 remain applicable. Existing unrelated working changes must be preserved.

## Intent and settings

Return recent eligible sessions up to a configurable count, with platform filtering before the limit. Proposed settings follow existing environment/extra configuration conventions: `MAX_SESSIONS_LIMIT` / `sessions_limit`, default `10`; `MAX_SESSIONS_DEFAULT_ALL` / `sessions_default_all`, default `false`. Environment overrides extra configuration. The count applies to ordinary listing, explicit all-platform listing and search. Proposed validation: integer 1–20; invalid, zero, negative or excessive values fall back to 10 with a diagnostic. The upper bound keeps the existing search ceiling; changing it requires explicit contract amendment. The singular `/session` in the request is interpreted as `/sessions`, not a new alias. Archived sessions remain excluded; existing owner authorization remains unchanged.

## Contracts

| ID | Trigger / context | Required result | Acceptance evidence | Implementation | Verification |
|---|---|---|---|---|---|
| SLP-001 | Settings absent or configured | Resolve limit and default scope with defaults and precedence above | Absent settings, environment/extra conflicts, limits 1/10/20 and invalid values; boolean true/false parsing | Implemented | Automated checks passed |
| SLP-002 | Authorized `/sessions` or no-argument `/resume`, default scope false | Return up to N recent MAX sessions; other platforms do not consume N slots | More than N newer non-MAX sessions followed by N older MAX sessions still yield N MAX results; fewer/zero eligible rows work | Implemented | Automated checks passed |
| SLP-003 | Authorized `/sessions all`, or ordinary listing with default scope true | Return up to N recent sessions across platforms; explicit all ignores default scope | Mixed sources, both default values, correct order and count; all-platform heading even when returned rows are all MAX | Implemented | Automated checks passed |
| SLP-004 | Authorized `/sessions search <query>` | Search all platforms and return up to N matches irrespective of default scope | Both default values, mixed-source matches, no matches and blank-query usage; literal search text preserved | Implemented | Automated checks passed |
| SLP-005 | Picker creation, refresh, selection or cancellation | Preserve effective scope/query/count on refresh; headings describe requested mode; rendered entries, buttons and stored selectable rows agree | Refresh every mode, config change after creation, empty refresh, long text, first/last selection, cancel and stale/foreign callbacks | Implemented | Automated checks passed |
| SLP-006 | Malformed command or denied caller | Exact command parsing; invalid arguments produce usage; unauthorized caller cannot query or switch sessions | Unknown argument, `searchfoo`, empty search, foreign caller and unauthorized callback leave owner state usable | Implemented | Automated checks passed |

## Implementation plan

1. Inspect the supported Core `SessionDB.list_sessions_rich` contract and CI-pinned Core versions. Prefer database source filtering before LIMIT; if unsupported, design a bounded compatible paginated retrieval that does not silently underfill. Do not alter Core or query only the newest N mixed rows.
2. Add both settings to adapter initialization, standalone/environment mapping, plugin manifest and paired setup/config references. Reuse existing coercion conventions and document validation.
3. Replace fixed 15/20 slicing with one resolved count. Parse explicit modes once; remove duplicate post-query filtering. Retain `/sessions max` as an explicit MAX override if supported by the baseline. Preserve authorization and archive policy.
4. Pass effective mode/query/count into picker state and refresh. Derive heading from mode, not row sources. Keep message length, labels, keyboard and stored rows consistent; avoid orphan usage messages after cancel/selection by putting guidance in the picker where appropriate.
5. Add focused regressions in existing session suites: `tests/test_cross_session.py`, `tests/test_interactive_sessions.py`, `tests/test_wire_regressions.py`; cover settings through the real adapter configuration path and query semantics through an actual temporary SessionDB where feasible. Establish baseline failures before claiming regression fixes.
6. Synchronize affected EN/RU setup, behavior and command documentation; amend the predecessor spec without removing its history. Update changelog only for delivered behavior. Preserve the separate deployment-stand plan/backlog changes and release draft.
7. Run focused tests, applicable lint and documentation checks, then relevant CI compatibility checks. Record candidate/Core revisions and actual evidence by SLP ID. Live MAX acceptance remains unverified until performed with authorization.
8. Commit only this feature using `realmagnum@gmail.com`. Publish the requested branch to upstream without force-pushing: first preserve the old remote branch under a verified unused archive name on each authorized target, then merge its divergent history with explicit file-by-file resolution retaining the current baseline and reviewed useful changes. Validate before normal push. Do not use a blanket ours/theirs resolution. If reconciliation introduces unrelated behavior or cannot preserve both histories safely, stop publication and report the specific conflict. Confirm remote HEAD equals the validated candidate; no merge into main or release is included.

## Publication boundary

Both `origin` (GitHub) and `gitea` currently contain a divergent branch with this name at `598d57b`; current main is `97e2053` on both. Upstream is provisionally `origin`, matching main's tracking configuration; publish the same candidate to Gitea as the requested Gitea destination. This is a future execution step, not a claim of publication. Implementation and branch publication were authorized by the user on 2026-10-21. No production installation, restart or test message is included.

## Verification evidence

Candidate: tracked changes on baseline `5144194`, before the implementation commit. Python 3.14, project `.venv-current`; pytest 9.1.1 and asyncio/mock dependencies are installed. Current pinned Core `ca13a7828acd2ba8c75e1c1d1694cbc1aee7df3f`: full suite 836 passed (one upstream deprecation warning). Focused session suites: 133 passed against each of minimum `d337b736aa1e8ebecfab043842d13e4a2d2f48a3` and baseline `d0288be5b3330d2442e3907185b8e9d0958297bb` source fixtures using the same Python 3.14 environment; this is source compatibility evidence, not the full Python 3.12 CI matrix. Regressions were established before implementation (25 failed, 1 passed; two new-test fixture issues were subsequently corrected). Ruff, package dependency check, EN/RU parity, configuration-reference and Markdown links passed; claims checker must match final collection count. Live delivery, real button clicks and production deployment were not performed.

After history reconciliation: final suite 837 passed. File resolutions and the additional retained checks are documented in [reconciliation evidence](20261021-branch-reconciliation.md). Session code is identical to implementation commit `20ca676`.
