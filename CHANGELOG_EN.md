# Changelog

All notable changes to the hermes-max-integration plugin.

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

- **README.md / README_EN.md** — new "MAX Slash Commands" section: full list of 20 commands, API limitations, curl example.
- **README.md / README_EN.md** — updated "Tables as Images" section with dynamic column widths and inline markdown descriptions.
- **README.md / README_EN.md** — added "Webhook Diagnostics" section with `diagnose.sh` reference.
- **README.md / README_EN.md** — documentation for `fresh_final_after_seconds` reasoning display setting.

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
- README.md / README_EN.md — new «Native File Delivery» section.
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

- **Bilingual documentation policy** — all `*.md` files now follow RU-primary + EN-translation (`*_EN.md`) pattern:
  - `AGENTS.md` + `AGENTS_EN.md`
  - `CHANGELOG.md` + `CHANGELOG_EN.md`
  - `README.md` + `README_EN.md`
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
