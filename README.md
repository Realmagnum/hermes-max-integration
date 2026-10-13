# Hermes MAX Gateway

![Hermes + MAX](assets/banner.jpg)

**Your Hermes agent, in MAX.** Streaming replies, voice messages, interactive buttons and files — with an optional Desktop sessions sidebar.

[Русский](README_RU.md) · [Setup](docs/setup.md) · [Changelog](CHANGELOG.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Hermes Core](https://img.shields.io/badge/Hermes_Core-≥0.21.4-8A2BE2)](docs/setup.md)
[![Python](https://img.shields.io/badge/Python-≥3.12-3776AB)](pyproject.toml)

## 📚 Documentation map

| Need | Read |
|---|---|
| Install, configure or diagnose | [Setup](docs/setup.md) · [Troubleshooting](docs/troubleshooting.md) |
| Understand behavior and internals | [Features](docs/features.md) · [Architecture](docs/architecture.md) · [API](docs/api.md) |
| Develop or verify a change | [Micro-Spec workflow](docs/micro-spec-development.md) · [Catalog contracts](docs/specs/20261013-catalog-review-137501.md) · [Backlog](BACKLOG.md) |

`scripts/diagnose.sh --send` sends a real message; use only an approved recipient. Offline checks and test instructions are in [setup](docs/setup.md).

## ✨ What you get

| | Capability | In your chat |
|---|---|---|
| 💬 | **Streaming replies** | Progressive edits, typing indicators and long-message chunking |
| 🔘 | **Interactive controls** | Model picker, command approvals and clarify choices, including Other |
| 📎 | **Native attachments** | Images, video, audio and documents; file-only agent replies gain a filename caption |
| 🎤 | **Voice messages** | Downloaded and passed to Hermes Core STT; transcription is configured in Core |
| 📊 | **Readable tables** | Optional Markdown → PNG, with Playwright/Chromium and a Pillow fallback |
| 📡 | **Two transports** | Long polling by default, or HTTPS webhook with secret validation |
| 🔒 | **Access controls** | User/group allowlists and callback ownership checks |
| 🖥️ | **Desktop companion** | MAX sessions sidebar, English default and Russian localization |

Optional cross-platform `/sessions` and `/resume` require explicit owner authorization. See [feature behavior](docs/features.md).

## 🚀 Quick start

Requires **Hermes Core ≥0.21.4** and **Python ≥3.12**. The configured minimum/baseline/current Core fixtures are recorded in [setup](docs/setup.md).

```bash
hermes plugins install Realmagnum/hermes-max-integration --enable
hermes gateway setup
```

Create a bot using the official [MAX guide](https://dev.max.ru/docs/chatbots/bots-create); setup prompts for `MAX_BOT_TOKEN` and access rules. Long polling needs no public endpoint. For webhooks, configure `MAX_WEBHOOK_URL` and `MAX_WEBHOOK_SECRET` with public HTTPS. **Check existing subscriptions before switching modes:** polling startup attempts to remove stale webhooks.

Configuration, optional dependencies and production procedures: [setup](docs/setup.md). Keep tokens and secrets out of Git.

## 📊 Tables that stay readable

Enable `MAX_TABLE_AS_IMAGE=true` to turn Markdown tables into a shareable PNG. Install the renderer in the gateway's Python environment; [renderer setup and fallback](docs/features.md).

**Source table:**

```markdown
| Server   | Status | Load | IP       |
|----------|--------|------|----------|
| web-01   | ✓ OK   | 23%  | 10.0.1.10 |
| web-02   | ✓ OK   | 67%  | 10.0.1.11 |
| db-main  | ✗ Down | 0%   | 10.0.2.5  |
| cache-01 | ⚠ High | 92%  | 10.0.3.1  |
```

**Example image delivered to MAX:**

![Table rendering example: colored status icons and aligned columns](assets/table_sample.png)

Useful for task lists, monitoring summaries and reports. Rendering is optional; this image illustrates the feature, not a live monitoring result.

## 📎 Sending a file

Ask the agent to create and send a file. It returns `MEDIA:<absolute-file-path>` in its final reply; the gateway uploads the attachment. With no authored text, the plugin adds its filename, or `File` if unavailable. Live file delivery was confirmed by the user on 2026-10-14.

Direct `hermes send` and cron paths without the output hook still need text: `report.pdf MEDIA:/path/report.pdf`. See [caption contracts](docs/specs/20261013-media-caption.md).

## ⌨️ Slash commands

20 commands are registered when possible; registration failure is non-fatal.

**Core:** `/start`, `/new` (`/reset`), `/status`, `/model`, `/resume`, `/sessions`, `/help`, `/stop`, `/config`, `/restart`.

**Additional:** `/retry`, `/undo [N]`, `/title [name]`, `/branch` (`/fork`), `/compress` (`/compact`), `/rollback [number]`, `/background` (`/bg`, `/btw`), `/agents` (`/tasks`), `/queue` (`/q`), `/topic`.

## 🛡️ Security and compatibility

- Tokens follow the active Hermes profile; webhook and callback checks fail closed. Media downloads retain host allowlisting and SSRF protection.
- The bundled Russian Trusted Root CA extends trust **only for MAX API/upload clients**. Attachment downloads use standard TLS trust.
- Local media stays under `HERMES_HOME`. No plugin telemetry or self-updating code. API endpoint: `MAX_API_BASE` (`https://platform-api2.max.ru`); official media hosts: `*.max.ru`, `*.oneme.ru`.
- The pinned CI Core dependency audit reports 14 PyJWT 2.13.0 advisories. This remains an open upstream constraint; no audit exclusions or incompatible overrides are used.

Details: [security](docs/security.md), [dated compatibility evidence](docs/external-claims.md) and [outstanding work](BACKLOG.md). Changes since `v2.10.2` are **unreleased**; see the [changelog](CHANGELOG.md).

## License and credits

[MIT](LICENSE) · Built for [Hermes Agent](https://hermes-agent.nousresearch.com/docs), based on the architectural starting point of [hermes-max-platform](https://github.com/vladimiraldushin/hermes-max-platform).
