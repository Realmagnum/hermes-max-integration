# Hermes MAX Gateway Architecture

## Integration boundary

The plugin implements the MAX platform adapter for Hermes Gateway and registers it through the package entry point. Hermes Core owns the agent loop, session storage, and speech-to-text; the plugin translates MAX events into the Hermes platform contract.

## Modules

- `adapter.py` owns configuration, lifecycle, polling, event normalization, and mixin coordination.
- `mixins/base.py` provides shared state and transport helpers.
- `mixins/webhook.py` implements the aiohttp endpoint, subscription registration, and request validation.
- `mixins/media_upload.py` and `mixins/standalone.py` handle MAX CDN uploads and standalone media delivery.
- `mixins/buttons.py` and `mixins/callback_auth.py` implement interactive messages, callback acknowledgements, and actor authorization.
- `mixins/sessions.py` provides optional cross-platform `/sessions` and `/resume`.
- `mixins/table_renderer.py` renders Markdown tables to PNG using Playwright/Chromium with a Pillow fallback.
- `desktop/plugin.js` and `locales/` provide the optional Hermes Desktop sidebar and translations.

Use the current source to verify class names and imports; this map is not a substitute for code inspection.

## Data flows

### Inbound messages

MAX delivers updates through polling or webhooks. The adapter normalizes the event, applies deduplication and access policy, downloads permitted attachments with limits, and passes the message to Hermes Core. Core performs STT for voice audio; the plugin does not contain a separate STT engine.

### Outbound messages

Core invokes platform methods. The adapter formats and chunks text, throttles streaming edits, optionally renders Markdown tables as PNG, then uploads and sends media through MAX APIs and CDN. The registered `standalone_sender_fn` supports standalone delivery when Core routes a request to it. Media-only routing depends on the selected Core version; the plugin never patches Core to enable it.

## Non-obvious invariants

- MAX API expects the raw bot token in `Authorization`, without a `Bearer` prefix.
- Public webhooks require HTTPS and a secret; secretless development mode is limited to explicitly allowed loopback.
- Upload/CDN hostnames and redirects are security boundaries: never forward `Authorization` to an unrelated origin.
- Polling startup removes discovered webhook subscriptions; inspect them before switching modes, especially if manually created.
- Cross-platform session access expands authorization scope and must remain opt-in and owner-scoped.
- Plugin imports must preserve package context; verify loading through the plugin loader, not only from the repository working directory.
- The table renderer must retain a no-Chromium fallback; install dependencies in the Python environment used by Hermes.

## Further reading

Configuration and defaults: `setup.md`; security controls: `security.md`; dated external contract evidence: `external-claims.md`. Installation and operation procedures live in `skills/max-gateway/SKILL.md`.
