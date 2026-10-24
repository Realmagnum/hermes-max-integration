# Smart Pagination for Long MAX Messages — Micro-Spec

[Russian version](20261024-smart-document-pagination_RU.md)

Date: 2026-10-24. Status: specified; implementation not started. Source: user request after observing cron output truncation in MAX. Baseline: current upstream `main` at `78d9abf`. Scope: MAX plugin only unless verification proves a Core contract change is required.

## Problem

Long cron/document output can be truncated before it reaches the MAX plugin. Hermes Core `gateway/delivery.py::_cap_oversized_output()` uses `MAX_PLATFORM_OUTPUT` and only passes oversized content through when the resolved adapter declares `splits_long_messages = True`. The MAX plugin currently does not declare this capability. It therefore receives a shortened payload, with an audit-file truncation footer, and cannot reconstruct the missing text.

The plugin's normal adapter path already has numbered, lossless chunking (`_numbered_outbound_chunks`) with a nominal 3900-character chunk budget, but its segmentation currently prioritizes lines/words rather than document structure. The standalone sender also slices text to `MAX_MESSAGE_LENGTH` (4000), potentially discarding the remainder. These routes need separate verification and a shared behavior contract.

## Goal

Deliver long text documents through MAX as ordered, numbered pages within the platform's verified message limit. Preserve all source content and make boundaries readable: prefer complete Markdown sections/headings and thematic blocks, then paragraphs, then complete sentences, then line/word boundaries. Hard-split only when no safe boundary fits. Never silently lose or invent source text.

## Non-goals

- Converting messages to HTML or images as a prerequisite; HTML is not assumed to be accepted by MAX or Hermes.
- Changing Hermes Core, its global output cap, or other platform adapters without evidence that a plugin-only capability declaration cannot solve the issue.
- Summarizing, rewriting, or dropping content to fit a page.
- Guaranteeing a document section remains whole when it is larger than the platform limit.

## Contracts

| ID | Trigger / context | Required behavior | Acceptance evidence |
|---|---|---|---|
| PAG-001 | MAX adapter registration and oversized cron delivery | Verify the actual resolved adapter exposes `splits_long_messages = True`, so Core forwards the full payload to MAX rather than applying generic truncation. If runtime registration wraps the adapter, the capability must be visible on the object inspected by Core. | Regression test at the Core/plugin integration seam with >4000 chars: full original reaches MAX send path; no `[truncated, full output saved to ...]` footer is injected. |
| PAG-002 | Long plain text or Markdown document | Split into numbered pages `(i/N)`; account for prefixes and any formatting wrappers before finalizing boundaries; every outgoing payload stays within the current verified MAX API limit, measured using the API's actual limit semantics (characters vs UTF-8 bytes must be confirmed). | Boundary tests at limit-1, limit, limit+1 and multi-page payloads; assert each payload fits and numbering is complete/stable. |
| PAG-003 | Document has Markdown headings/TOC/section separators | Prefer cuts before a heading or at a section separator when the resulting page stays within budget. Keep heading with its following content where feasible. Do not split a table of contents entry/link. | Fixture with `#`, `##`, `###`, horizontal rules and TOC; assert cuts prefer those boundaries and exact text round-trips after removing page prefixes. |
| PAG-004 | Document has paragraphs and prose | If no section boundary fits, prefer paragraph boundaries, then sentence-ending punctuation plus following whitespace, then line/word boundaries. Do not split a sentence if a prior/following safe boundary fits. Sentence detection must be conservative for abbreviations, initials, decimals, URLs, versions, quoted text, and multilingual punctuation. | RU/EN fixtures with abbreviations, decimals, links, versions, quotes and `!?…`; assert no avoidable mid-sentence split and lossless round-trip. |
| PAG-005 | Fenced code block spans pages | Preserve the source text exactly. Prefer moving the whole block when it fits; if it does not, split at line boundaries and balance/reopen fences only if the implementation can preserve exact source reconstruction and valid rendering. Any synthetic fence tokens are tracked separately from source text and included in the page budget. | Long code-fence fixtures; all requests fit; rendered chunks have balanced fences; removing explicitly modeled synthetic wrappers and page prefixes reconstructs the exact source. |
| PAG-006 | Standalone/cron sender path | Remove silent `message[:MAX_MESSAGE_LENGTH]` loss. Use the same tested pagination policy or explicitly return a failure before sending; send pages sequentially and propagate partial-send failure without claiming complete delivery. Preserve media ordering and captions. | Mocked API test for long standalone text: all chunks sent in sequence, no source omission; injected failure on page k reports partial delivery and does not resend pages 1..k-1. |
| PAG-007 | Any input including empty text, giant unbroken token, Unicode/emoji, whitespace, tables and Markdown links | Pagination is deterministic, bounded, and lossless; only giant indivisible tokens may require a hard split. Do not mutate original content; do not emit an empty extra page. | Property-based or parameterized round-trip tests over Unicode, whitespace, paragraph separators, long tokens and boundary sizes. |
| PAG-008 | MAX API rejects a page or delivery fails mid-document | Return/record a failure that identifies the failed page and whether earlier pages were delivered; never report full success for partial delivery. | Simulated API rejection/timeout test; verify accurate `SendResult`/partial-delivery semantics and no duplicate restart of already accepted pages. |

## Implementation method

1. **Verify the live upstream baseline first.** Fetch Gitea `main` and GitHub mirror, compare SHAs, inspect current `plugin.yaml`, adapter registration, `MaxAdapter.send`, `_numbered_outbound_chunks`, standalone sender, and Core `_cap_oversized_output`. Do not base implementation on a stale feature branch or assume earlier observations remain current.
2. **Prove the truncation seam with a focused test.** Reproduce a >4000-character cron payload and assert whether Core hands the full text to the registered MAX adapter. Distinguish the adapter's normal send path from `send_message_handler`/`standalone_sender_fn`; do not assume the capability flag protects plugin-owned sender hooks.
3. **Confirm MAX's actual send constraints.** Check current official MAX Bot API documentation for text length semantics, formatting mode, and multi-message ordering. Test with a disposable/test bot if docs do not settle character-vs-byte counting or delivery behavior. Do not switch to HTML without verified API support and a separate rendering contract.
4. **Write failing tests first.** Cover Core capability propagation, adapter pagination, standalone pagination, exact round-trip reconstruction, section/paragraph/sentence preference, code fences, Unicode boundaries, and partial failures. Existing chunking tests are regression baselines; extend rather than weaken them.
5. **Implement the smallest plugin-scoped fix.** Declare the long-message capability only on the resolved adapter path that actually performs chunking. Refactor shared splitting into a plugin helper usable by both `MaxAdapter.send` and standalone sending. Use a deterministic hierarchy of candidate boundaries (section → paragraph → sentence → line → word → hard split), choosing the latest safe boundary that fits the remaining page budget. Keep numbering in the budget calculation. Preserve source slices exactly; do not normalize whitespace.
6. **Handle markdown carefully.** Do not attempt fragile regex sentence parsing across code spans, fenced code, links, tables and blockquotes. Add a lightweight state-aware scanner or restrict advanced boundaries to safe unformatted prose regions; fall back to line/word boundaries whenever structure is ambiguous. If synthetic code-fence closure/reopening is used, test both valid rendering and exact source recovery.
7. **Verify sequential delivery and failure semantics.** Send pages serially. Retain platform response IDs where available. On failure, report partial delivery; do not retry the entire document blindly and duplicate prior pages.
8. **Run gates and inspect diff.** Run focused pagination and standalone tests, the full plugin test suite, `ruff check .`, `python3 scripts/check_docs_links.py`, `python3 scripts/check-ru-en-parity.py`, `python3 scripts/check-doc-claims.py`, and `python3 scripts/check-config-reference.py`. Update bilingual docs, changelog and backlog only after implementation evidence exists.
9. **Upstream workflow.** Work on a clean branch based on freshly fetched upstream `main`; do not stage unrelated working-tree files. Push only the explicitly intended branch/remote, verify remote SHA, and report CI honestly.

## Acceptance gate

The feature is complete only when an oversized cron document arrives in MAX in full, as numbered messages within MAX's verified limit; boundaries prefer semantic structure; concatenating page contents after removing pagination metadata reconstructs the original exactly; standalone sends do not truncate; and partial failures are reported truthfully. A locally passing unit test alone does not prove the Core-to-plugin cron path.
