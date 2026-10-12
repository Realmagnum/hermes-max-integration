---
name: max-gateway
description: "Install and configure Hermes Agent access through Max messenger (voice transcription by the Hermes core, Hermes Desktop sidebar integration)."
version: 2.10.2
author: Realmagnum / Hermes Agent community
license: MIT
metadata:
  hermes:
    tags: [hermes, gateway, messaging, max, chatbot, voice]
---

# Max Gateway for Hermes

Use this skill when asked to install, configure, or troubleshoot this MAX adapter. This is a procedural guide; `docs/architecture.md` describes stable system behavior and trust boundaries.

## Before acting

1. Inspect the current repository and read `docs/setup.md`, `docs/security.md`, and `docs/troubleshooting.md`.
2. For MAX API details, follow current official documentation linked from `docs/external-claims.md`; re-check dated claims when they matter.
3. Do not ask for or expose bot tokens or webhook secrets. Never place secret values in shell arguments or examples.
4. Distinguish read-only inspection from consequential operations. Restarting a gateway, deleting subscriptions, or sending test messages requires user approval.

## Installation

1. Confirm Hermes is installed and identify the Python environment used by its gateway.
2. Install dependencies only into that environment, following the current `pyproject.toml` and Hermes package guidance.
3. Install/enable the plugin using the supported Hermes plugin command or the local checkout.
4. Obtain `MAX_BOT_TOKEN` through MAX's current official bot-creation process and store it in Hermes' protected `.env` or secret manager.
5. Verify package loading and adapter registration without printing secrets.

## Configure delivery mode

The adapter supports polling and webhooks. Confirm the current mode-selection logic in `adapter.py` before changing configuration. In polling mode, startup can remove existing webhook subscriptions; inspect current subscriptions first and never delete one without explicit approval.

For webhook mode, verify the endpoint is reachable over the required public HTTPS path, configure the matching `MAX_WEBHOOK_URL` and `MAX_WEBHOOK_SECRET`, and confirm fail-closed secret validation in `mixins/webhook.py`. Preserve TLS verification and do not expose the internal listener unnecessarily. Confirm startup registration behavior in the current source before creating subscriptions manually.

## Verify safely

1. Prefer `hermes gateway status`, local health checks, and redacted logs.
2. Confirm the intended polling/webhook mode and subscription state without changing it.
3. A `--send` smoke test sends a real message; use only after the user approves the recipient and content.
4. After approved changes, read back status and logs to verify the actual result.

## Voice and media

Voice transcription is provided by Hermes Core, not by this plugin. Check Core's current STT documentation/configuration. For media delivery or table rendering, inspect `docs/features.md` and the current implementation; do not assume optional browser/image dependencies are installed.

## Troubleshooting

Start with `docs/troubleshooting.md`. Preserve owner-scoped authorization, download limits, SSRF protections, and the rule against forwarding `Authorization` to unrelated origins. If current source or official API behavior differs from these notes, update the documentation pair after verification.
