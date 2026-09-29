# External and unconfirmed claims — verification register (DOC-10)

**Verification date:** 2026-09-16.
**Scope:** README / README_EN / docs/setup* claims about the MAX API and platform requirements, Telegram capabilities, and Hermes core behaviour.
**Method:** reconciled against the official MAX documentation (`dev.max.ru/docs-api`), the official Telegram Bot API documentation (`core.telegram.org/bots/api`) and the actual Hermes 0.21.3 core source (`~/.hermes/hermes-agent`). No live API calls; no production tokens or messages were used.

## 1. Change summary

| Repository claim | Verdict | Source | Change |
|---|---|---|---|
| "Telegram supports markdown tables out of the box: `\| A \| B \|` with `format=markdown`" | **False** | core.telegram.org/bots/api, Bot API 10.1 (2026-06-11) | Rewritten: classic `parse_mode` has no tables; tables only via Rich Messages / `sendRichMessage` |
| "MAX supports only `*italic*`, `**bold**`, `` `code` ``, links, headings, quotes" | **Incomplete** | dev.max.ru/docs-api, text formatting | List aligned with the official set (strikethrough, underline, mention, highlight added) |
| "MAX CDN does not validate content, guaranteeing delivery for any safe extension" | **Unsupported absolute** | dev.max.ru/docs-api/methods/POST/uploads | Removed; official format/size limits stated instead |
| "Webhook required for production" | **Confirmed** | dev.max.ru/docs-api, API recommendations | Kept, with a citation and the port 443 requirement |
| "MAX uses Russian MinCifry CA certificates" | **Partially confirmed** | dev.max.ru/docs-api, POST /subscriptions | Clarified: trusted-CA **or** MinCifry cert; as of 2026-05-25 HTTP and self-signed are rejected |
| "`display.platforms.max.fresh_final_after_seconds: 10` fixes reasoning in MAX" | **False** | core 0.21.3, `gateway/run_turn.py` | Replaced with `streaming.fresh_final_after_seconds` + a Telegram-only caveat |
| `scripts/apply-core-fix.py` apply/revert | **Incompatible with core 0.21.3** | run against a core copy | Compatibility warning added |

## 2. MAX API — host and authorization

- **Host.** Since **July 19, 2026** requests must go to `https://platform-api2.max.ru` instead of `platform-api.max.ru`, and the MinCifry root certificate must be added to the trust store (dev.max.ru/docs-api/changelog-api).
  - The plugin still hardcodes `MAX_API_BASE = "https://platform-api.max.ru"` (`adapter.py:65`, `mixins/buttons.py:16`, `mixins/media_upload.py:22`, `mixins/standalone.py:19`) — recorded as a code follow-up, outside DOC-10.
- **Authorization.** Token-in-query is no longer supported; the `Authorization: <token>` header is required. The plugin already uses the header (`adapter.py:345` et al.) — compliant.
- **Token.** Issued when the bot is created at `business.max.ru/self` ("Чат-боты") or in the "MAX for business" mini-app.

## 3. Bot registration eligibility

Official requirements (dev.max.ru/help/platform_connection):

- Access is limited to **Russian residents**: legal entities, sole proprietors (ИП) and self-employed.
- **Individuals and non-residents cannot pass verification.**
- Bot limits: **2** for self-employed, **5** for organizations/sole proprietors.
- Profile confirmation: Gosuslugi only (self-employed) or Gosuslugi / banking services (organizations, sole proprietors).

> Documentation recommendation: state explicitly that a MAX bot requires a verified RU-resident profile — some users cannot register under platform rules.

## 4. Formatting and limits

Official Markdown set (dev.max.ru/docs-api): italic, bold, strikethrough, underline, monospace, links, mentions, highlight, headings, quotes. HTML is equivalent. **No tables** in either mode.

Limits (dev.max.ru/docs-api, POST /messages, POST /uploads):

| Parameter | Value |
|---|---|
| Message text | up to 4000 characters |
| Messages to one dialog/chat/channel | no more than 2 per second |
| Requests to `platform-api2.max.ru` | up to 30 rps (per integration, total) |
| Bot commands (`PATCH /me/commands`) | up to 32 items |
| Attachments per message | up to 12; `file` only with a keyboard attachment, 1 file per message |
| `image` | JPG/JPEG/PNG/GIF/TIFF/BMP/HEIC, ≤50 MB and ≤7680×7680 |
| `video` | MP4/MOV/MKV/WEBM, ≤250 MB |
| `audio` | MP3/WAV/M4A etc., ≤256 MB and ≤60 min |
| `file` | "common formats" (TXT, DOC, PDF etc.), ≤4 GB |

- An unsupported file type returns `File extension is forbidden`; the "guaranteed delivery for any extension" claim is false.
- `type=photo` is no longer supported — use `type=image`.
- `GET /chats` was removed in June 2026; list the bot's chats/channels via `POST /subscriptions`.

## 5. Webhook: port, TLS, CA

Official requirements (dev.max.ru/docs-api/methods/POST/subscriptions):

- The endpoint must be reachable over **HTTPS on port 443 only**; the port must not appear in the URL. The plugin binds to `8646` (`DEFAULT_WEBHOOK_PORT`), so a reverse proxy must publish it on 443 (Caddy/Traefik examples already exist in `docs/setup.md`).
- Since **May 25, 2026** HTTP webhooks and self-signed certificates are unsupported. The certificate must come from a trusted CA **or** MinCifry; CN/SAN must match the domain; the full chain must be served.
- The endpoint must return HTTP 200 within 30 seconds. Retries: up to 10 with growing intervals; no success for 8 hours → automatic unsubscribe.
- `X-Max-Bot-Api-Secret` header (when `secret` is set, 5–256 chars `[A-Za-z0-9_-]`).
- **Production = Webhook only.** Long Polling is rate- and retention-limited and is documented as unsuitable for production.
- `MAX_INSECURE_SSL` is not used by the plugin code (see DOC-02): disabling certificate validation with that flag does not work.

## 6. Telegram and native tables

- Classic modes (`Markdown`, `MarkdownV2`, `HTML`) support bold/italic/underline/strikethrough/spoiler/quote/code/links and contain no tables.
- **Bot API 10.1 (June 11, 2026)** added Rich Messages: `RichBlockTable`, `RichBlockTableCell`, the `sendRichMessage` method, and the `rich_message` field on `Message`. Tables are available only through that path.

## 7. Hermes core 0.21.3 — local verification

- **Reasoning / fresh-final.** The key is read only from the top-level `streaming:` section (`gateway/config.py`, `StreamingConfig.from_dict`) and applied to **Telegram only**: `gateway/run_turn.py:2492` forces `0.0` for every other platform. The README's `display.platforms.max.fresh_final_after_seconds` shape works neither by key path nor by platform.
- **`scripts/apply-core-fix.py`.** The script looks for the markers `# --- Non-media platforms ---` and `if media_files and not message.strip()`. Core 0.21.3 has neither (the section was reworked and now has a `_PLUGIN_STANDALONE_MEDIA` registry), so apply and revert both end with `❌ Could not find insertion marker in core file.` A run against a **copy** of core (the live file was untouched; sha256 identical before and after) confirmed the live install is not modified and media-only delivery is not enabled.
- **Text limit.** `MAX_MESSAGE_LENGTH = 4000` in `adapter.py` matches the official MAX limit (4000 characters).

## 8. Follow-ups (outside DOC-10)

1. Move `MAX_API_BASE` to `platform-api2.max.ru` in `adapter.py`/`mixins/*` and ensure the MinCifry certificate is trusted.
2. Adapt `scripts/apply-core-fix.py` to the 0.21.3 core layout (or replace it with a supported mechanism).

## 9. Verifiability

The regression test `tests/test_doc_external_claims.py` pins the removal of the retracted absolutes and the presence of the verified wording/references in the README and setup docs (RU/EN).
