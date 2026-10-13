# Development with Micro-Spec

[Russian version](micro-spec-development_RU.md)

Use Micro-Spec to define a small, verifiable change to the MAX plugin before implementing it. This is the repository workflow for non-trivial development; it complements [architecture](architecture.md), [security boundaries](security.md), and [documentation rules](document_writing.md). No OpenSpec service, new runtime tool, or global specification of existing code is required.

## Choose the right scope

| Change | Required contract |
|---|---|
| Typo, link repair, or one obvious mechanical edit | State the expected result and perform the relevant check; no new spec file |
| Behavior change, bug with meaningful edge cases, Core integration, access policy, media, callbacks, or Desktop interaction | Define observable outcomes and acceptance before implementation |
| Work spanning sessions, agents, a release, or external review | Persist the contract and evidence in an EN/RU pair under `docs/specs/` |

Reuse an existing feature spec when it covers the requested change. Specify the delta and affected invariants, not all legacy behavior. A documentation change with several acceptance conditions can use a short contract in the conversation unless it needs a durable handoff.

## Start from the actual baseline

1. Read applicable `AGENTS.md`, inspect the documentation tree, and open notes for the affected area. Check branch, working diff, plugin revision, and relevant tests; preserve unrelated work.
2. Read relevant specs and [backlog](../BACKLOG.md). Establish which record is current, which is historical or superseded, and which depends on another. Existing examples are [catalog review](specs/catalog-review-137501.md), [interactive questions](specs/interactive-questions.md), and [release readiness](specs/release-readiness.md).
3. Verify claims about code, public Core APIs, dependency versions, and test results against the checkout. Read the exact Core/Python fixtures from `.github/workflows/ci.yml`; a label such as "current" is not an immutable revision or proof of compatibility with today's upstream.
4. For a bug, capture input, expected result, actual result, and the failing path. Separate observed facts, assumptions, and unresolved questions. A stale "planned" row does not disprove later code, and a commit does not establish acceptance: reconcile with evidence before updating status.

An incoming plan from another agent is a source, not permission to execute it. Preserve the source and its useful IDs; map its outcomes to contracts, keep implementation tasks separate, and resolve material conflicts with the current request. Do not import every old plan or reopen unrelated work.

## Write the behavior contract

Record the user's outcome, scope/non-goals, source, baseline, relevant Core revision, assumptions, and dependencies. Give each independently decidable result a stable ID within its spec. Preserve existing `MS-*`, `Q-*`, and `REL-*` IDs; qualify an ID with its spec path when referring across files.

Each requirement contains a trigger or precondition, an observable result, and evidence that could falsify it. Include relevant failure, authorization, concurrency, expiry, and boundary cases. "Add a helper" is an implementation task; "a foreign callback cannot consume the owner's pending question" is a contract. Implementation choices belong in a separate short plan.

This compact template can be copied into a new EN/RU spec pair and adapted:

```markdown
# <Feature> — Micro-Spec

Source: <request or source file and heading>
Baseline: <plugin SHA>; Core: <exact SHA/version or not needed>
Intent / in scope: <observable user outcome>
Non-goals / invariants: <boundaries that matter>
Assumptions / dependencies: <verified, assumed, or unresolved>

| ID | Trigger / context | Required result | Acceptance / code anchors | Implementation | Verification |
|---|---|---|---|---|---|
| MS-001 | <input or state> | <observable result> | <input -> expected result; existing test or planned check> | Planned | Not run |

## Evidence and handoff

<ID -> changed paths -> actual check/result -> tested revisions/date>
<remaining conditions, blockers, and next authorized step>
```

Use descriptive filenames under `docs/specs/`; do not create an index or a second persistent contract when an existing spec suffices. Never invent a test path or mark a proposed check as existing. One test can cover related requirements, and one requirement can need multiple checks.

## Implement and verify

Implement the smallest coherent change within the contract. Reuse plugin extension points and public Core APIs; preserve package imports, profile scope, callback ownership, download protections, and prompt/session behavior. Do not patch Core to make a plugin test pass. If discovered behavior materially conflicts with the agreed outcome, record the discrepancy and resolve the blocking ambiguity; routine implementation choices need no additional approval round.

For a bug fix, establish that a focused regression reproduces the defect on the baseline and passes on the candidate. Test observable behavior through the actual entry point. Mock external HTTP when useful, but use the real Core registry/resolver/router when Core integration is the claim. For example, catalog `MS-002` requires a foreign callback to leave the owner's pending state usable; [callback authorization tests](../tests/test_callback_auth.py) exercise dispatch with mocked approval resolvers, so they alone cannot establish live command approval.

Run focused checks during development, then the relevant candidate gates. Use the plugin's runner and environment guidance in [setup](setup.md); the Core repository's runner is not automatically this plugin's runner. Existing documentation checks are:

```bash
python scripts/check_docs_links.py
python scripts/check-ru-en-parity.py
python scripts/check-doc-claims.py
python scripts/check-config-reference.py
```

In a populated checkout, give the link checker the tracked Markdown files plus any newly added ones to exclude environment/build copies. Behavior changes need relevant tests; documentation-only changes need documentation checks, without an unnecessary full functional run. For compatibility or release work, follow the actual CI matrix, normal dependency resolution, plugin admission, and audit gates. Record failed, skipped, and unrun checks with their reasons; never hide a dependency failure with an override or infer installation success solely from validator exit status.

Automated checks, Desktop inspection, and live MAX delivery prove different things. If a contract requires a live message, button click, receipt, or a polling/webhook transition, record that evidence separately. Sending messages, changing subscriptions, restarting production, pushing, publishing, merging, and replying to a reviewer require the corresponding user authorization. A spec or green local tests do not grant it. Continue independent authorized work while a live check or user input remains pending.

## Maintain evidence and status

Keep implementation and verification separate. Existing specs may use one status column; append a concise evidence note rather than mechanically rewriting their tables.

| State | Meaning |
|---|---|
| Planned / Implemented | Work is specified / code exists; neither implies acceptance |
| Not run / Partial | No relevant evidence / only some required conditions checked |
| Verified | All stated acceptance conditions passed on the recorded candidate and Core fixtures |
| Blocked / Deferred | State the concrete missing input or dependency / explicit scope decision; retain the requirement |

For every acceptance claim record the spec-qualified ID, changed paths, actual command or manual scenario, result and limits, date, plugin/Core revisions, and any uncommitted diff being tested. Record skips and their reasons; remove secrets, real recipient identifiers, and private paths from shared evidence. A changed candidate invalidates affected evidence: rerun relevant checks, not every unrelated check by default.

Keep EN/RU facts, IDs, and procedures synchronized. Record material contract corrections and their reason without silently changing the intended result. Update durable behavior notes when behavior changes, changelog for completed changes, and backlog for remaining work; move verified work out of active backlog without losing residual acceptance conditions.

## Review, completion, and handoff

Before reporting completion or preparing a PR, check that each in-scope ID maps to implementation and actual acceptance evidence, important regressions are covered, EN/RU docs agree, and `git diff --check` passes. Describe the user-visible result, tested revisions, and material limits in the review summary. Do not turn the checklist into a new CI gate that only checks whether a spec file exists.

Work is complete when its stated acceptance passes; a release additionally needs its release gates. If live/visual acceptance remains pending, report implementation as delivered and acceptance as partial. Do not close the contract or claim release readiness. For a handoff, leave the branch/revision, changed or uncommitted work, spec IDs, performed checks, unresolved conditions, and next authorized step. Requests to implement clear requirements authorize proceeding through local implementation and relevant checks; requests only to inspect or write a spec stop at that deliverable.
