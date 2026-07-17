# Changelog

All notable changes to the hermes-max-stt plugin.

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
