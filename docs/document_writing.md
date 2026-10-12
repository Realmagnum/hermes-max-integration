# Documentation Rules

Keep durable, non-obvious knowledge about plugin behavior and design in `docs/` — context that is hard to recover from a function name or obvious code.

## Navigation

Run `tree docs` at the start of a task. Filenames are the primary map: name files for the question they answer, such as `webhook-lifecycle.md`, `media-security.md`, or `desktop-sessions.md`. If `tree` is unavailable, use `find docs -maxdepth 2 -type f | sort`.

Open the relevant note before changing its area of the code. Do not assume the entire tree is automatically loaded into context: this depends on the agent and environment. Read a file explicitly when its details matter.

## What to document

- Non-obvious invariants, trust boundaries, lifecycle ordering, and rationale.
- MAX/Hermes API contracts where the schema or types alone are insufficient.
- Edge cases, platform constraints, and verified diagnostic methods.
- Mutable external claims with their source and verification date.

Do not restate obvious code, copy whole implementations, or use notes as release history instead of `CHANGELOG.md`.

## Separate documentation roles

- `docs/` — durable system knowledge and contracts.
- README.md is the concise English introduction, and `README_RU.md` is its Russian counterpart; detailed references stay in `docs/`.
- `skills/` — reproducible agent procedures: prerequisites, commands, checks, rollback, and escalation conditions. A skill does not replace system-design notes.
- `AGENTS.md` — concise repository navigation/work rules, not a duplicate feature reference.
- `BACKLOG.md` — future work; do not leave completed work listed as a roadmap.

## Languages

All primary documents use English filenames such as `name.md`; Russian counterparts use `name_RU.md`. README follows the same rule: `README.md` is English and `README_RU.md` is Russian. Update each pair together. The parity checker validates matching heading levels/order, table shapes, code-fence languages, environment-variable names, and locale-correct links. Do not translate commands or identifiers.

## Updating and verification

When updating documentation:

1. Check claims against code, tests, metadata, and current upstream contracts; do not treat an old document as the source of truth.
2. Remove stale instructions and move still-needed content to the right document before deleting the old one.
3. Keep tokens, personal data, and real recipient addresses out of docs and examples.
4. Do not send real messages or change external infrastructure during documentation verification.
5. Run `python scripts/check_docs_links.py`, `python scripts/check-ru-en-parity.py`, `python scripts/check-doc-claims.py`, `python scripts/check-config-reference.py`, then relevant tests.

Write Markdown without manual line wrapping inside paragraphs. Use tables only for genuinely tabular references. Use relative internal links without a leading `/` or `../` when a repository-root-relative path works. State uncertainty plainly; include a source and verification date for external or version-dependent claims.
