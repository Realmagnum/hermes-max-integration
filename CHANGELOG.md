# Changelog

All notable changes to the hermes-max-integration plugin.

## [Unreleased]

- **Out-of-process media delivery:** `register_platform` now declares `StandaloneSendPolicy(media=True, captionable=True)`, so Core's public `_send_to_platform` routes attachments — including media-only requests — to the plugin's standalone sender. `hermes send -t max "MEDIA:/path"` and "send me file X to MAX" from another chat deliver without a Core patch or the output hook; a single file plus short text arrives as one message with the text as its caption. `_standalone_send` accepts Core's `caption` and reports `text_delivered=true` when the caption message lands. Live image and document delivery verified 2026-10-31. On a Core whose `PlatformEntry` has no `standalone_send` field (0.21.4), the keyword is omitted entirely instead of raising `TypeError` during registration; media there keeps the previous text-only behaviour.
- **Upload/attachment type match:** an image is now uploaded with `type=image` and sent as `{"type":"image"}`; MAX rejected the previous `type=file` token as `proto.payload — Invalid photo token provided`. Any other type falls back to `file` for both steps, so a token never travels under a mismatched attachment type. Regression: `tests/test_core_send_router.py::test_image_upload_type_matches_attachment_type`.
- **Install admission:** `tables` and `stt` now carry core's `sys_platform != 'android'` guard, and `playwright` is declared as a range (`>=1.62,<2`) instead of an exact `1.62.0` pin that collided with core's own `google-meet` pin — the plugin can be enabled again on current core, and a future core bump fails CI instead of the user's install. `scripts/setup-playwright.py` accepts any in-range version. [DEP-001–004](docs/specs/20261030-install-admission-markers.md).

- **Group access:** enforce group policy before every button callback; expose group/webhook fields in Desktop, correct numeric ID examples, persist safe onboarding defaults and document ID discovery, family and mixed groups. [GRP-001–004](docs/specs/20261022-group-access.md).

- **Session diagnostics:** explicit Core/picker reasons, safe logs, read-only post-install dispatch check, owner setting in manifest/Desktop and clarified MAX_CROSS_SESSION wording. User confirmed all live session scenarios on c5e41ac. [SLP-007–008](docs/specs/20261021-session-list-policy.md).

- **Session listing:** default count 10 and configurable MAX/all-platform default; fix `/sessions all` routing, filtering before LIMIT, refresh policy retention and long-list/button consistency. [SLP-001–006](docs/specs/20261021-session-list-policy.md).

- **Catalog review submission:** original [PR #137501](https://github.com/NousResearch/hermes-agent/pull/137501) repinned to immutable v2.11.0 (commit `1321548cfe`), description and reviewer response updated; ready for repeat review. Temporary #138075 closed as a duplicate. Review decision pending. [MS-012](docs/specs/20261013-catalog-review-137501.md).

## [2.11.0] — 2026-10-14

Compared against the immutable `v2.10.2` tag (`bcbf7696a99e81db1679671f979726d5b5c2833b`). This release consolidates all changes since that version. [Compare with v2.10.2](https://github.com/Realmagnum/hermes-max-integration/compare/v2.10.2...v2.11.0).

### Added

- **File-only MAX agent replies:** public `transform_llm_output` hook inserts the first filename before Core delivery; direct attachment sends use basename or `File`, preserving authored captions. Platform instructions explain final `MEDIA:<absolute-file-path>` replies. User confirmed live file delivery on 2026-10-14. [CAP-001–005](docs/specs/20261013-media-caption.md).
- **Presentation and documentation:** banner, compact illustrated capability table and the existing PNG-table example in both READMEs; durable architecture notes, Micro-Spec contracts and acceptance/handoff records.
- **Clarify test compatibility:** the real tool-result regression uses the public single-question API on minimum/baseline Core and the batch API on later Core.
- **Regression coverage:** real Core send-router and clarify-queue tests, catalog access/security cases, diagnostics privacy, requester-bound picker and Desktop locale harness.

### Fixed

- **Profile isolation:** MAX token/webhook secret resolution uses Core's scoped-secret helper; multiplex default startup works without borrowing credentials from another profile. Dependency checks are passive.
- **Interactive questions:** callbacks pass choice text into Core's synchronous clarify resolver, continue the waiting turn once, and support Other text input. Invalid/foreign/replayed callbacks cannot consume a valid prompt; buttons use one option per row. Model picker/clarify were confirmed live.
- **Model picker:** binds to the original requester before sending, requires the matching prompt message, rejects unknown ownership and provides a Cancel button; no first-tapper ownership in groups.
- **Native command approvals:** adapter implements Core's execution-approval entry point and validates the actual offered choices and requester. Live execution-approval selection remains unverified.
- **Private setup and access:** preserves existing allowlists; denied media, commands, callbacks and bot-start events stop before downloading or dispatching to Core.
- **Delivery results:** missing files, upload/send failures and partially delivered attachments are reported as incomplete delivery, preserving counts and already-delivered text/file evidence.
- **Desktop localization:** English default, Russian language pack, translated UI strings and locale-aware dates; older SDK limitations are documented.
- **Platform identity:** adapter fallback no longer mutates Core's Platform enum maps.

### Changed

- **Core boundary:** removed `scripts/apply-core-fix.py` and its instructions. The plugin does not rewrite Core. Direct CLI/cron media-only requests without the output hook still need caller-provided text.
- **MAX API and TLS:** API endpoint uses `platform-api2.max.ru`. Bundled Russian Trusted Root CA is restricted to API/upload clients; attachment downloads keep standard TLS trust, host allowlisting and SSRF/DNS protections.
- **Supported runtime:** Hermes Core **>=0.21.4**, Python **>=3.12**; Python 3.11 is excluded. CI pins exact minimum/baseline/current Core fixtures; Playwright is pinned to 1.62.0, dependencies bounded and PyYAML included in test extras.
- **Operational tooling:** diagnostics do not read credential files or reveal token/API bodies; Playwright setup reports installation failures. CI rejects dependency-install fallback messages rather than relying on validator exit status alone.
- **Documentation:** English primary files with `_RU.md` counterparts, synchronized navigation and refreshed external claims; completed work tracked in changelog/specs, remaining acceptance in backlog. README keeps configuration details in docs while restoring the visual presentation of v2.10.2.

### Verification and limitations

- Full plugin suite: **796 passed** on Core `ca13a7828acd2ba8c75e1c1d1694cbc1aee7df3f`; subsequent instruction update: **27 focused tests passed**. Wheel build includes the caption helper. Earlier released-minimum Core 0.21.4/Python 3.12 checks remain dated evidence; exact release-candidate CI provides updated matrix evidence.
- User confirmed live file delivery, model picker and clarify; Desktop EN/RU/date inspection is recorded. Final remote-source admission, live execution-approval selection remain open.
- Pinned CI Core PyJWT 2.13.0 audit reports **14 advisories**. No vulnerability exclusions or incompatible overrides; this is an unresolved release constraint.
- **CAT-01 / MS-006:** static English description in Capabilities → Plugins is bound to the installed Desktop source build `0.0.0`, commit `7157422022ff06f3e632d1dd394ee1253b17ad37` (checked 2026-10-14); loader/renderer evidence and upgrade recheck conditions are in [Desktop features](docs/features.md). This is separate from older-SDK palette reload behavior. Visual acceptance stays closed. [Remaining work](BACKLOG.md).

## [2.10.2] — 2026-09-30

### Features & Desktop UI
- **Hermes Desktop Sessions Sidebar (`max-sessions-sidebar`):** added native MAX messenger sessions panel for the Hermes Desktop interface. Displays active conversations with MAX users, message counts, token consumption, formatted timestamps, and status badges.
- **Unified Package & Automatic Installation:** packaged as a unified bundle (backend + desktop UI). When the plugin is enabled in Hermes, `desktop/plugin.js` is automatically registered within the desktop application.
- **Localization Support:** introduced Russian/English locale packs; the later catalog follow-up fixes page strings and date locale behavior.
- **Public Repository:** the project is synchronized with the public GitHub repository [Realmagnum/hermes-max-integration](https://github.com/Realmagnum/hermes-max-integration).

### Fixed
- **`file://` URL Handling for Images:** fixed image dispatch in `adapter.py` by decoding `file://` URLs from Hermes Core, resolving 400 Bad Request responses when sending local generated files.

### Fixed
- **Chat Action & Typing Status Indicators in DMs:** fixed a critical regression where status indicators ("typing...", "sending photo...", "recording audio...") were missing in 1-on-1 direct messages. Hermes Core addresses DMs via scoped `user:<user_id>`, while MAX Bot API strictly requires the integer dialog `chat_id` on `/chats/{chat_id}/actions` and `/chats/{chat_id}` endpoints.
- **Bidirectional DM Routing Table:** implemented automatic resolution and caching of `user_id` ↔ `chat_id` mappings across incoming updates (`message_created`, `bot_started`, `message_callback`) and outbound API responses, along with `_resolve_chat_id`.
- **Media Upload Action Indicators:** added immediate emission of appropriate chat actions (`sending_photo`, `sending_video`, `sending_audio`, `sending_file`) prior to and during CDN file uploads.
- **Typing Indicator Clearing (`stop_typing`):** implemented `stop_typing` sending `typing_off` to cleanly clear the typing status once the agent finishes processing.

## [2.10.0] — 2026-09-29

### Security & Access Control
- **SEC-01 (Callback Authorization):** Exec, slash-confirm and clarify callbacks are scoped to owner (`owner_user_id`), chat, prompt message ID, and TTL; regression fixtures reject mismatched callbacks. Group model-picker first-tap ownership remains an explicit CODE-06 acceptance item.
- **SEC-02 / SEC-03 (SSRF & Download Origin Hardening):** Multi-layered inbound media download protection: strict fail-closed DNS pinning (blocking private/loopback/link-local IPs and DNS rebinding), isolated download client without propagating `Authorization` headers to untrusted origins, configurable `MAX_DOWNLOAD_ALLOWED_HOSTS` and `MAX_TRUSTED_DOWNLOAD_HOSTS`.
- **SEC-04 (Fail-closed Webhook):** Webhooks start strictly with a valid secret (or explicit local `MAX_WEBHOOK_INSECURE_DEV=true` on loopback). Timing-safe header validation (`X-Max-Bot-Api-Secret`) occurs before reading or parsing the payload (`_build_webhook_app`). DoS protection via body size ceiling (`WEBHOOK_MAX_BODY_BYTES` = 1 MiB).
- **SEC-05 (Cross-session Access):** Cross-platform session browsing disabled by default (`MAX_CROSS_SESSION=false`) and restricted to verified owners (`MAX_CROSS_SESSION_USERS` / `cross_session_users`).
- **SEC-06 (Group Policy):** Strict allowlist semantics (`MAX_GROUP_ALLOWED_USERS` and `MAX_GROUP_ALLOWED_CHATS`), AND-based combination, fail-closed rejection on empty allowlist; full support for `allowlist`, `closed`, and `open` policies.
- **SEC-07 (Inbound Media Limits):** Bounded attachment sizes (`MAX_INBOUND_MEDIA_MAX_BYTES` = 20 MiB), message-total attachment ceiling (`MAX_INBOUND_MEDIA_TOTAL_BYTES` = 50 MiB), max attachment count (`MAX_INBOUND_MEDIA_MAX_ATTACHMENTS` = 10), download timeouts, concurrency semaphores, and partial-download cleanup exercised by regression fixtures.

### Reliability & Transport
- **CODE-01 (Polling Backoff):** Exponential backoff with jitter on network/API errors, `Retry-After` header support, immediate fatal exit on 401 Unauthorized without log flooding.
- **CODE-02 (Lossless Chunking):** Message chunking algorithm preserving all whitespace, formatting, and fenced code blocks (`"".join(chunks) == original`); pre-partitioning numbering budgeting.
- **CODE-03 (Streaming Isolation & Flush):** Isolated streaming throttle state per `(chat_id, message_id)`, eliminating cross-chat suppression; guaranteed flush timer and immediate flush on `finalize=True`.
- **CODE-04 & CODE-06 (Model Picker Isolation):** Support for composite model IDs with colons (Ollama tags, OpenRouter free); stale-message and replay checks. An unowned group picker binds its owner on first tap; strict original-requester binding remains open.
- **CODE-05 (Webhook Health & Readiness Contract):** Clear separation of contracts: liveness (`GET /health` -> `{"status": "ok"}`), readiness (`GET /ready` -> 200 ready / 503 not_ready), and telemetry metrics (`GET /metrics`).
- **CODE-07 (Lifecycle & Teardown):** Clean connect/disconnect lifecycle with guaranteed await of cancelled background tasks, client closure, and Hermes core flag synchronization.
- **CODE-08 (Backpressure & Dedup):** Bounded ingress queue (`MAX_QUEUE_MAXSIZE` = 100), worker concurrency cap (`MAX_MAX_CONCURRENCY` = 4), configurable overload policy (`MAX_OVERLOAD_POLICY` = `drop_oldest` | `drop_newest`), LRU deduplication (`MAX_DEDUP_MAX`, `MAX_DEDUP_TTL`).

### Documentation & Quality
- **DOC-02 (Honest Configuration):** Checked references for environment variables (31 variables) and `platforms.max` keys (27 keys), removal of phantom settings, internal constants table.
- **DOC-07 & DOC-09 (Parity & Honest Claims):** structural RU/EN parity checks, automated validation of version and test count claims (720 tests), zero broken links.
- **Test Suite:** Test coverage expanded from 126 to a recorded 720-test release suite; later candidate results are reported separately.

## [2.9.0] — 2026-08-17

### Refactor

- **Monolithic `adapter.py` (~3000 lines) split into a modular `mixins/` structure** (branch `feature/refactor-mixins-base`, 27 commits, merge without squash). `MaxAdapter` is now a thin facade (2250 lines) over seven mixins:
  - `mixins/base.py` — shared state and `http_client`
  - `mixins/table_renderer.py` — table rendering (text + PNG)
  - `mixins/media_upload.py` — two-step upload to the MAX CDN
  - `mixins/buttons.py` — buttons, approval/clarify, send_action
  - `mixins/webhook.py` — aiohttp server, subscriptions, secret
  - `mixins/sessions.py` — cross-platform sessions
  - `mixins/standalone.py` — standalone sender for cron/send_message
- **Import rule:** only relative imports inside `mixins/` (`.base`); `adapter.py` → `from .mixins.xxx` — otherwise the plugin silently fails to load through the Hermes plugin system
- Removed dead `_seen_msgs` duplicate (SIM114), `next(iter(Platform))` instead of `list()[0]`, logging in "silent" except blocks

### Security

- **SSRF protection for media downloads:** new `_validate_download_url()` — public http(s) hosts only; loopback/private/link-local/reserved IPs (incl. `169.254.169.254`), `localhost` and `*.local` are blocked
- **Token leak on redirects closed:** removed `follow_redirects=True` from `_cache_audio/image/document_attachment` (the client already runs with `follow_redirects=False`; the explicit override re-enabled token-bearing redirects)
- **Warning when `MAX_WEBHOOK_SECRET` is empty:** startup logs a warning if the webhook runs without a secret — otherwise anyone could post events
- `hashlib.md5(..., usedforsecurity=False)` — MD5 is only used for the cache filename, not for cryptography
- Narrow JSON-parsing excepts: `(JSONDecodeError, TypeError, ValueError)` instead of blind `Exception`

### Fixed

- **Audio normalization before CDN upload:** wav/flac/m4a are transcoded to Ogg/Opus via ffmpeg (the MAX CDN rejects such containers with 415); ogg/mp3 pass through unchanged; idempotent
- **Blocking `open()` in async upload** replaced with `asyncio.to_thread(Path.read_bytes)` — the file is read off the event loop (media_upload, standalone)

### Performance

- **Table-PNG cache now works:** `_render_table_as_image` checks `table_<md5>.png` before rendering — repeated identical tables reuse the cached image instead of re-drawing

### Quality

- **Ruff: 220 → 0 errors** in `adapter.py`/`mixins/` (PEP 604/585 annotations, imports, auto-fixes); tests clean too
- **Bandit: High → 0** (only false-positive B105 — env var names, and intentional B104 — `0.0.0.0` for the webhook)
- **Tests: 154** (was 129): +11 SSRF-guard cases, +2 table cache, +12 audio normalization

### Docs

- `docs/refactor-plan.md` — refactoring plan marked complete (all 11 steps ✅)
- CHANGELOG, README, AGENTS.md synced (EN+RU)

## [2.8.0] — 2026-08-05

### Changed

- **STT moved out of the plugin into the Hermes core (>= 0.20.0).** The plugin no longer transcribes voice itself: the adapter downloads and caches audio, the core transcribes it per the `stt` config in `config.yaml` — providers `local`/`groq`/`openai` (whisper-1, gpt-transcribe)/`mistral`/`xai`/`elevenlabs`, unified language resolution, 🎙️ transcript echo, VAD-based anti-hallucination hardening.
- Removed `mixins/stt_processor.py` (`STTProcessorMixin`) and `scripts/transcribe_audio.py`; inline transcription removed from `adapter.py` (media is still downloaded and cached for the core).
- Removed `MAX_STT_ENABLED` / `MAX_STT_VENV` from code, `.env` docs, `plugin.yaml` and the interactive setup; `hermes gateway setup` no longer asks about STT.
- `plugin.yaml` → `version: 2.8.0`.

### Recommendations

- For Russian, set `stt.language: ru` in `config.yaml` (core default is `"en"`). Configure via `hermes tools` → STT category.

## [2.7.1] — 2026-08-05

### Fixed

- **STT on Windows: fixed 3 voice-transcription bugs** (in `mixins/stt_processor.py` and `scripts/transcribe_audio.py`):
  - `python3` on Windows is a Microsoft Store stub ("Python was not found"). Now `Scripts/python.exe` (Windows) / `bin/python3` (Linux) is looked up, then the gateway's own interpreter (`sys.executable`) — a dedicated STT venv is no longer required
  - `WhisperModel('base','cpu','int8')` — in faster-whisper >=1.x the 3rd positional arg is `device_index`, not `compute_type` → TypeError; fixed with keyword args `device='cpu', compute_type='int8'`
  - Audio path is passed via `argv` (adapter) / env var instead of embedding into the `-c` source: on Windows `C:\Users\...` broke parsing as a Unicode escape (`unicodeescape` SyntaxError). Command-injection protection preserved — evolution of the `shlex.quote` fix from 2.1.1

### Refactoring

- **Step 7 complete:** STT logic extracted to `mixins/stt_processor.py` (`STTProcessorMixin`) and wired into `MaxAdapter`; the inline `_transcribe_media` method removed from `adapter.py`

## [2.7.0] — 2026-07-25

### Added

- **MAX Bot API slash commands.** Registration of **20 slash commands** via `PATCH /me/commands` (analogous to Telegram `setMyCommands`). Commands are registered automatically on plugin start after successful token verification.
  - Core: `/start`, `/new`, `/status`, `/model`, `/resume`, `/sessions`, `/help`, `/stop`, `/config`, `/restart`
  - Advanced: `/retry`, `/undo`, `/title`, `/branch`, `/compress`, `/rollback`, `/background`, `/agents`, `/queue`, `/topic`
  - Aliases included in descriptions for discoverability
  - MAX limit: 32 commands (Telegram: 100)

- **Improved model picker.** Interactive two-step model selection:
  - Step 1: provider selection (buttons in row, current marked with ✅)
  - Step 2: model selection (1 button per row, current marked with ✅)
  - "← Back" button to return to provider list
  - Pagination for lists >15 models (counter "p. X/Y")

- **Dynamic column widths for tables.** Calculation MIN_COL_WIDTH = `textlength("abcdefghijklmnopqrst") + 44px` (~240px). Guarantees 20 non-wrappable characters per cell for any font (including bold header).

- **Inline markdown rendering in tables.** Support for `**bold**`, `*italic*`, `` `code` `` in table cells via MAX inline formatting.

- **diagnose.sh — MAX webhook diagnostic script.** Automatic mode detection (webhook vs long polling), port 8646 check, health endpoint, subscription status, token validity, reasoning configuration.

- **Reasoning display configuration.** `fresh_final_after_seconds` parameter (default: 10) — time to display reasoning before final response.

### Fixed

- **ModelPicker refactor revert.** Removed `model_picker.py`, logic returned to `adapter.py`. The refactor broke plugin initialization — plugin failed to load after extracting ModelPicker to a separate module.

### Documentation

- **README.md / README_RU.md** — new "MAX Slash Commands" section: full list of 20 commands, API limitations, curl example.
- **README.md / README_RU.md** — updated "Tables as Images" section with dynamic column widths and inline markdown descriptions.
- **README.md / README_RU.md** — added "Webhook Diagnostics" section with `diagnose.sh` reference.
- **README.md / README_RU.md** — documentation for `fresh_final_after_seconds` reasoning display setting.

### Changed

- `plugin.yaml` bumped to `2.7.0`
- `tests/` — added tests for model picker and diagnose.sh


## [2.6.0] — 2026-07-23

### 🐛 Bug Fixes

- **Callback acknowledgment delivery.** Exec-approval, slash-confirm, and clarify callbacks no longer create a `MessageEvent` that the AI sees as a new user message in the next turn — preventing the AI from responding with full Reasoning to the acknowledgment. The acknowledgment is now sent directly via the MAX API as a short message with no AI generation.
- **message_id extraction.** `send()` now correctly parses `body.mid` as a fallback, fixing progress message duplication.
- **Polling error logging.** Added `logger.warning()` to polling exception handlers — errors are now visible in logs instead of being silently swallowed.

### 📚 Documentation

- Webhook docs updated with reverse proxy setup guide and `nonlocal` pitfall description.


## [2.5.0] — 2026-07-23

### Added

- **Native audio/video delivery.** `_standalone_send()` uses `type=audio`/`type=video` for `POST /uploads`. Token obtained from `/uploads` response (not CDN), enabling native playback in MAX.
- **CDN fallback.** `_upload()` falls back to `type=file` when audio/video CDN fails — file still delivered as downloadable.
- **Retry on `attachment.not.ready`.** Up to 3 attempts with 5s delay in `_standalone_send()` (video needs transcoding time).
- **SSRF whitelist.** Upload URL validated against `.okcdn.ru`, `.cdn-max.ru`, `.oneme.ru`, `.max.ru`.

### Fixed

- **Audio/video token source.** `_upload()` previously expected token from CDN (returns XML `<retval>1</retval>`). Now correctly uses `token` from `POST /uploads` response.
- **MAX API response parsing.** Messages without `ok` field in response body are no longer rejected.
- **CDN token extraction for images.** `type=image` CDN returns token in `photos[photoId][token]`. Both formats parsed.

### Changed

- `plugin.yaml` bumped to `2.5.0`
- README.md / README_RU.md — new «Native File Delivery» section.
- **New API domain:** MAX docs recommend `platform-api2.max.ru` (backward compatible).
- `cliff-ru.toml` — added `Other` group postprocessor.


## [2.4.0] — 2026-07-22

### Added

- **`send_multiple_images()`** — batch image delivery in a single message. Uploads all images concurrently, then sends one message with all attachment tokens. Falls back to sequential `send_image_file()` on error.
- **`_standalone_send()` — native file delivery.** `hermes send MEDIA:/path/file` now uploads files via the 3-step MAX protocol (POST /uploads → POST multipart → POST /messages with token). Supports image, video, audio, file.
- **`_standalone_get_token()`** — extracted token resolution for the standalone path.

### Fixed

- **`_upload_send()` — retry on `attachment.not.ready`.** Exponential backoff (2/4/6s), up to 3 attempts. Replaces static `UPLOAD_DELAY`.
- **`_upload()` — added `fu.oneme.ru` to SSRF whitelist.** Actual file upload CDN for MAX.
- **`_standalone_send()`** — no longer ignores `media_files` (was `logger.warning` + discard).

### Changed

- `_upload_send()` — hard `UPLOAD_DELAY` replaced with adaptive retry

## [2.3.0] — 2026-07-22

### Added

- **Bilingual documentation policy** — all `*.md` files now follow RU-primary + EN-translation (`*_RU.md`) pattern:
  - `AGENTS.md` + `AGENTS_EN.md`
  - `CHANGELOG.md` + `CHANGELOG_EN.md`
  - `README.md` + `README_RU.md`
  - `docs/webhook.md` + `docs/webhook_EN.md`
  - `after-install.md` + `after-install_EN.md`
  - `skills/max-gateway/SKILL.md` + `skills/max-gateway/SKILL_EN.md`

### Fixed

- `send_buttons()` now wraps one button per row (full width) instead of 2 per row
- Button text auto-truncated to MAX API limits (40 chars callback, 64 chars link)
- `send_buttons()` — double-encoded JSON bug fix in `send_typing` (mentioned in v2.2.0)

### Changed

- `send_buttons()` — text duplicated in message body as fallback (mobile readability)
- `send_buttons()` — auto-numbering (`1.`, `2.`, `3.`...) when 3+ buttons
- `send_buttons()` — optional `label` field: full description in message body, short `text` on button

## [2.2.0] — 2026-07-22

### Added

- **Cross-platform session commands** — `/sessions` now shows sessions from ALL platforms (💻CLI, 📱Telegram, 🟣MAX, 🎮Discord, 🌐WebUI, 🔌API Server), not just MAX:
  - Rich output with source emoji, title preview, and abbreviated session ID
  - `/sessions search <query>` — full-text search across all platforms
  - `/resume <id>` automatically uses `--all` flag — resume any session from any platform
  - Configurable via `MAX_CROSS_SESSION=true|false` (default: true)
  - Requires `allow_admin_from` in config.yaml for the `max` platform (adds the user's MAX ID) to make core `--all` flag work
- **`send_action()`** — extended chat actions: `typing`, `typing_off`, `sending_photo`, `sending_video`, `sending_audio`, `sending_file`, `read`. Replaces the old `send_typing()` which now delegates to `send_action()`.
- **`send_buttons()`** — public method for sending messages with inline buttons of ANY type: `callback`, `link`, `message`, `request_contact`, `request_geo_location`.
  - One button per row (full width)
  - Button text auto-truncated to MAX API limits (40 chars callback, 64 chars link)
  - Auto-numbering (`1.`, `2.`, `3.`...) when 3+ buttons
  - Optional `label` field: full description text in message body (never truncated)
  - Fallback text with button content duplicated in message body
- **`plugin.yaml`** — added `MAX_CROSS_SESSION` optional env var

### Fixed

- `send_typing` had a double-encoded JSON bug (`json.dumps` wrapping a dict that `httpx` then serialised again) — fixed by passing the dict directly to `json=`.

### Notes

- When `MAX_CROSS_SESSION=false`, `/sessions` and `/resume` fall back to core gateway's default per-platform scoping (MAX only)
- Cross-platform resume (`/resume --all`) requires the user's MAX ID to be listed in `platforms.max.extra.allow_admin_from` in config.yaml

## [2.1.3] — 2026-07-17

### Security (audit finalization)

- **MEDIUM:** Sanitized 5 remaining `error=str(e)` returns in: `edit_message`, `send_image`, `_upload_send`, `_post_interactive`, `_standalone_send` (token/URL leak prevention in outbound methods)
- **MEDIUM:** Added per-IP rate limiting to webhook handler — 30 req/10s window, auto-cleanup at 1000+ entries
- **MEDIUM:** Hard 5000-entry cap on `_seen_msgs` dedup dictionary (memory exhaustion prevention under DDoS)
- **MEDIUM:** Strict validation of clarify callback `choice_idx`: `isdigit()` guard + bounds check (0–256)
- **LOW:** Removed unused `import hmac` (superseded by `secrets.compare_digest`)

## [2.1.2] — 2026-07-17

### Added

- **Tables as Images** (`MAX_TABLE_AS_IMAGE=true`): render pipe-markdown tables as Pillow-generated PNG images with colored status icons:
  - ✓ Done (green), ✗ Failed (red), ⚠ In review (orange), ◷ Pending (amber), ▶ Scheduled (blue)
  - Emoji variation selector normalization (U+FE0F/U+FE0E stripping)
  - Dark header (#1e293b) with white text, alternating row colors
  - Auto-fallback to text rendering when Pillow is missing
  - Image upload via two-step API (`POST /uploads` → PUT → token → send)

### Fixed

- **Markdown table rendering:** removed unsupported fenced code blocks (```) and `<pre>` tags — MAX supports neither. Tables now render as inline `code` spans for monospace text, or as PNG images when `MAX_TABLE_AS_IMAGE=true`
- **Upload domain whitelist:** added `iu.oneme.ru` and `*.oneme.ru` to SSRF allowlist (MAX image CDN)
- **Emoji rendering in table images:** replaced emoji with proper Unicode symbols that DejaVu Sans renders clearly (16×15px vs 8×8px blobs)

## [2.1.1] — 2026-07-17

### Security (audit + hardening)

- **CRITICAL:** Fixed command injection vector in STT subprocess — path now escaped via `shlex.quote()`
- **CRITICAL:** Added SSRF protection — file upload URLs validated against `*.max.ru` domain whitelist
- **HIGH:** Disabled `follow_redirects` on authenticated HTTP client (token leak prevention)
- **HIGH:** Removed `follow_redirects=True` from attachment download methods
- **HIGH:** Sanitized error messages returned to gateway (no raw exception strings with URLs)
- **HIGH:** Renamed `_verify_secret` → `_verify_raw_secret`, uses `secrets.compare_digest` for clarity
- **MEDIUM:** Removed `os.environ` mutation in `_apply_yaml_config` (side-effect risk)
- **LOW:** Audio cache created with `0700` permissions (voice message privacy)
- **LOW:** Health endpoint no longer discloses platform name
- **LOW:** `transcribe_audio.py`: `shlex.quote(model_name)` for defense-in-depth

### CI

- Added `bandit` SAST scan job
- Added `pip-audit` dependency vulnerability scan job

## [2.1.0] — 2026-07-15

### Added

- Initial release: MAX messenger platform adapter with STT voice transcription
- Dual mode: long polling + webhook
- Recursive media extraction and caching
- Two-step file upload
- Message streaming via `edit_message`
- Smart 4000-char message chunking
- Inline keyboard buttons (approval, clarify, model picker)
- Group access control policies
- Interactive `hermes gateway setup` flow
- Standalone sender for cron/send_message
- faster-whisper STT integration
