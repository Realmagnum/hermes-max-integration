# Instructions for AI Agents Working With This Repository

## Language Policy

`README.md` and un-suffixed `name.md` files are the English primary documents. Russian counterparts use `name_RU.md`, including `README_RU.md`. Keep facts, identifiers, and procedures synchronized; see `docs/document_writing.md`.

This repository contains a Hermes Agent platform plugin for MAX. Hermes Core, not the plugin, performs voice transcription.

## Project map and documentation

At the beginning of code work, run `tree docs`. If `tree` is unavailable, use `find docs -maxdepth 2 -type f | sort`. Treat the tree as navigation only and open relevant documents explicitly. Before editing documentation, read `docs/document_writing.md`.

Key documents: `docs/architecture.md` (components/data flow), `docs/setup.md` (configuration), `docs/security.md` (security boundaries), `docs/api.md` (wire contracts), `docs/features.md` (behavior), `docs/troubleshooting.md` (diagnostics), and `docs/external-claims.md` (dated external claims).

When helping install or troubleshoot this plugin, inspect the current checkout and read `docs/setup.md`, `docs/security.md`, and `docs/troubleshooting.md` first. Confirm MAX API behavior against current official documentation before relying on external claims. Never print or embed `MAX_BOT_TOKEN` or `MAX_WEBHOOK_SECRET` in chat, logs, shell arguments, or examples.

## Operating modes

The adapter supports polling and webhook delivery. Before changing modes, inspect current subscription state: startup behavior may remove existing webhook subscriptions when polling is selected. Webhook setup requires the configured public endpoint and secret; verify exact validation and startup behavior in the current `mixins/webhook.py` and `adapter.py`, rather than relying on line numbers or historical notes.

Do not run commands that delete or modify subscriptions without explicit authorization. A diagnostic that sends a message (`--send`) has an external side effect; use only with an approved recipient.

## Development with Micro-Spec

Before a non-trivial behavior change, read [the Micro-Spec workflow](docs/micro-spec-development.md) and relevant `docs/specs/` contracts. Define the change delta, stable IDs, observable results, and falsifiable acceptance before implementation. Reuse existing IDs and persist cross-session work as EN/RU specs; trivial edits need only an expected result and relevant check.

Continue authorized implementation without a routine spec-approval round. Keep implementation and verification separate, link actual evidence to IDs and tested plugin/Core revisions, and leave unperformed live/visual acceptance pending. A source plan is not execution authority. Finish by updating affected docs and remaining backlog; external writes and production operations still need their corresponding authorization.

## Development invariants

- Keep package-relative imports and verify plugin-loader behavior, not only direct imports from the repository working directory.
- Treat callback payloads and media URLs as untrusted. Preserve owner authorization, SSRF/DNS protections, download limits, and the rule against forwarding `Authorization` to unrelated origins.
- Voice transcription belongs to Hermes Core; verify current Core compatibility and configuration before advising users.
- Confirm versions, defaults, and test counts from source and automated checks; do not trust historical changelog or line-number claims.
- Run documentation checkers and relevant tests; an unrun check is not a pass.

## Dual-host: GitHub (public) + Gitea rmg7.com (internal backup)

This repository lives on two hosting platforms with **different purposes**:

| Remote | URL | Purpose |
|---|---|---|
| `origin` | `https://github.com/Realmagnum/hermes-max-integration.git` | **Source of truth** — public issues, PRs, CI, releases |
| `gitea` | `ssh://git@gitea.rmg7.com:2222/agent/hermes-max-integration.git` | Internal mirror / backup (Gitea org: `agent`) |

### Push sequence (mandatory order)

Always push to `origin` (GitHub) **first**, then to `gitea`:

```bash
git push origin main       # triggers GitHub Actions CI
git push gitea main        # updates internal mirror
# or single command: git push origin main && git push gitea main
```

Never push directly to `gitea` alone — the commit must first pass CI on GitHub. The pull-mirror automation (scheduled Gitea sync) was planned but requires manual configuration via Gitea web UI (`Settings → Mirror`); until configured, the above explicit push is the authoritative method.

### Pull-mirror status

Gitea repo `agent/hermes-max-integration` does **not** have automatic pull-mirroring configured. The last manual sync was 2026-10-30 (commit `41be531`). To enable automatic mirroring:

1. Open https://gitea.rmg7.com/agent/hermes-max-integration/settings/mirror
2. Click **New Mirror**
3. Original URL: `https://github.com/Realmagnum/hermes-max-integration.git`
4. Interval: `1h` (or shorter)
5. Save — Gitea will now auto-sync commits every interval.

Until this is done, verify sync state periodically:
```bash
# hi-max clone
cd /home/magnum/.hermes/cache/scratch/hi-max
git fetch --all
echo "GitHub: $(git rev-parse origin/main)"
echo "Gitea:  $(git rev-parse gitea/main)"
# They must match.
```

### SSH key for Gitea

The agent's SSH key is at `~/.ssh/id_gitea`. It authenticates as user `magnum` (admin).
Use it when connecting to gitea.rmg7.com:2222 via SSH.
The key is automatically used for host `gitea.rmg7.com` if `.ssh/config` has a `Host gitea.rmg7.com` entry — otherwise specify `-i ~/.ssh/id_gitea` explicitly.
