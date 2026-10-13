# Hermes MAX Gateway

![Hermes MAX messenger integration](assets/banner.jpg)

> Русская документация: [README_RU.md](README_RU.md). Этот файл — основная английская версия; синхронизируйте факты и ссылки в обеих версиях.

Hermes Agent platform plugin for the MAX messenger. It provides polling and webhook transports, streaming and chunked replies, interactive callbacks, media handling, access controls, table images, and an optional Hermes Desktop sessions sidebar. Voice transcription is provided by Hermes Core STT, not by this plugin.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Hermes Agent](https://img.shields.io/badge/Hermes-Agent-8A2BE2)](https://hermes-agent.nousresearch.com/docs)

## Features

- MAX platform adapter with long polling or HTTPS webhook transport.
- Streaming replies, lossless message chunking, and chat actions.
- Interactive callbacks and buttons; model selection, execution approval, slash confirmation, and clarify flows.
- Media download and upload, native image/video/audio/document methods, and standalone `hermes send` integration.
- Optional Markdown-table rendering to PNG (Playwright/Chromium, Pillow fallback).
- User/group access policies, webhook secret validation, and callback-owner authorization.
- Optional owner-authorized cross-platform `/sessions` and `/resume`.
- Optional Hermes Desktop sessions sidebar with RU/EN UI localization.
- Voice messages enter Hermes Core’s STT pipeline; transcription is configured in Core, not in this plugin.
- `hermes gateway setup` integration and MAX slash-command registration.

## Documentation map

For a compact document map, run `tree docs`. Read [docs/architecture.md](docs/architecture.md) for component relationships; [docs/setup.md](docs/setup.md) for setup/configuration; [docs/security.md](docs/security.md) for security boundaries; [docs/api.md](docs/api.md) for wire/API contracts; [docs/features.md](docs/features.md) for feature behavior; [docs/troubleshooting.md](docs/troubleshooting.md) for diagnostics; and [docs/external-claims.md](docs/external-claims.md) for dated external evidence. Documentation rules are in [docs/document_writing.md](docs/document_writing.md).

Project documents use English `name.md` with Russian `name_RU.md` counterparts. `README.md` is English and `README_RU.md` is Russian.

[Micro-Spec and acceptance evidence](docs/specs/catalog-review-137501.md); [outstanding work](BACKLOG.md); [change history](CHANGELOG.md).

## Quick start

Requires Hermes Core **>=0.21.4**. The released minimum is verified at `d337b736aa1e8ebecfab043842d13e4a2d2f48a3` (0.21.4, Python 3.12), alongside later baseline/current source fixtures in CI. Core 0.20 lacks the native execution-approval entry point required by this plugin.

```bash
hermes plugins install Realmagnum/hermes-max-integration --enable
hermes gateway setup
```

Create a MAX bot and obtain its token using the current official [MAX documentation](https://dev.max.ru/). `hermes gateway setup` guides token and access configuration. By default, the plugin uses long polling. To use a webhook, configure `MAX_WEBHOOK_URL` and `MAX_WEBHOOK_SECRET`, expose the configured path through public HTTPS, then restart the gateway. **Before changing modes, check existing MAX subscriptions:** polling startup attempts to remove stale webhook subscriptions.

See [docs/setup.md](docs/setup.md) before changing a production gateway. Never commit bot tokens or webhook secrets.

## Configuration

For the complete environment-variable reference, defaults, and `platforms.max` YAML keys, see [docs/setup.md](docs/setup.md).

## Slash commands

The plugin registers 20 commands with MAX when possible; registration failure is non-fatal. MAX allows up to 32 commands.

Core: `/start`, `/new` (`/reset`), `/status`, `/model`, `/resume`, `/sessions`, `/help`, `/stop`, `/config`, `/restart`.

Additional: `/retry`, `/undo [N]`, `/title [name]`, `/branch` (`/fork`), `/compress` (`/compact`), `/rollback [number]`, `/background` (`/bg`, `/btw`), `/agents` (`/tasks`), `/queue` (`/q`), `/topic`.

## Optional table images

Telegram Bot API 10.1+ offers tables through the separate `sendRichMessage` API; this plugin targets MAX, which has no equivalent table message format in its current API contract.

Reasoning-display configuration in Hermes Core uses `streaming:
  fresh_final_after_seconds`, but Core currently applies that option only to Telegram, not MAX. Check [docs/features.md](docs/features.md) before using it as a workaround.

Set `MAX_TABLE_AS_IMAGE=true` to render Markdown tables as PNG. Playwright/Chromium is preferred; Pillow is the fallback. Install optional dependencies in the same Python environment as the Hermes gateway. See [docs/features.md](docs/features.md) and [docs/troubleshooting.md](docs/troubleshooting.md).

## Security and privacy

The plugin bundles a Russian Trusted Root CA and adds it to the MAX API and upload clients only. This extends their normal trusted CA set. Attachment downloads use standard TLS trust without that additional CA and retain SSRF protections. See [docs/security.md](docs/security.md).

The tested Core dependency set currently pins PyJWT 2.13.0; the dependency audit reports 14 advisories for that version. The audit remains failing until the upstream Core constraint is fixed; no audit exclusions or incompatible dependency overrides are used. See [docs/external-claims.md](docs/external-claims.md).

Outbound API requests go only to the MAX Bot API endpoint fixed in the plugin (`MAX_API_BASE`, `https://platform-api2.max.ru`) and official MAX media hosts (`*.max.ru`, `*.oneme.ru`). Downloaded media and rendered table images are stored locally under `HERMES_HOME`. The plugin includes no telemetry, analytics, or self-updating code; webhook mode requires `MAX_WEBHOOK_SECRET` (fail-closed). See [docs/security.md](docs/security.md).

## Troubleshooting and checks

See [docs/troubleshooting.md](docs/troubleshooting.md). `scripts/diagnose.sh --send` sends a real outbound test message; use it only when the recipient is explicitly approved.

```bash
python scripts/check_docs_links.py
python scripts/check-ru-en-parity.py
python scripts/check-doc-claims.py
python scripts/check-config-reference.py
python -m pytest tests/ -q
```

## Project layout

```text
adapter.py                  MAX gateway adapter and lifecycle
mixins/                      Webhook, media, buttons, callbacks, sessions, table rendering
desktop/plugin.js            Hermes Desktop sessions sidebar companion
locales/                     Plugin and desktop locale manifests
scripts/                     Setup, release, diagnostics, and documentation checks
tests/                       Unit, wire-contract, security, and docs tests
docs/                        Durable project notes; Russian translations use `_RU.md`
skills/max-gateway/          Install and operation workflow skill
plugin.yaml                  Hermes plugin metadata
pyproject.toml               Python package and test configuration
```

## License

MIT. See `LICENSE`.

## Credits

- [Hermes Agent](https://hermes-agent.nousresearch.com/docs) — agent framework.
- [vladimiraldushin/hermes-max-platform](https://github.com/vladimiraldushin/hermes-max-platform) — architectural starting point for the MAX integration.
