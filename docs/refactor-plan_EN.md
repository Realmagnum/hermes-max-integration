# Refactoring Plan for adapter.py and Roadmap (v2.9.0+)

This document contains the up-to-date refactoring plan for the `adapter.py` monolith (~3700 lines of code) and the development roadmap. The document provides context for AI agents so they can continue work in new sessions.

## Current status (2026-08-17)

**Refactoring completed ✅** (branch `feature/refactor-mixins-base`, merged into main in v2.9.0).

- adapter.py: 2997 → 2250 lines; mixins/ ~1630 lines in total.
- **Step 7 cancelled** — STT was delegated to the Hermes core v0.20.0, and the `stt_processor.py` mixin was removed (2026-08-05).
- Tests: 154 passing, conftest switched to package import `max.adapter`.
- All plan steps below are marked ✅ — the plan is complete.

## Progress (What has already been done)

- [x] **Isolation of bases and structure:** Created the `mixins/` directory; base state moved to `mixins/base.py`. (Branch: `feature/refactor-mixins-base`)
- [x] **STT vulnerability:** Fixed a critical logic vulnerability (replaced use of `shlex.quote` with the safe `sys.argv[1]`) in `stt_processor.py`. (Branch: `feature/stt-security-fix`)
- [x] **Table Renderer extraction:** Extracted 500 lines of Markdown-table-to-image conversion logic into `mixins/table_renderer.py`. (Branch: `feature/refactor-table-renderer`)
- [x] **Module skeletons:** Created initial skeletons for `webhook.py`, `media_upload.py`, and `buttons.py`.

## Module plan

```
hermes-max-integration/
├── adapter.py              # thin layer (multiple mixin inheritance)
├── mixins/
│   ├── __init__.py
│   ├── base.py             # ✅ MaxBaseMixin — base state, http_client
│   ├── table_renderer.py   # 🔄 Table rendering — (in progress) migration from Pillow to HTML→PNG (Playwright)
│   ├── media_upload.py     # ✅ File upload (POST /uploads, CDN, retry, SSRF)
│   ├── buttons.py          # ✅ Buttons: send_buttons, send_action, _post_interactive, approval/clarify
│   ├── stt_processor.py    # ❌ removed — STT in the Hermes core (v0.20.0+)
│   ├── webhook.py          # ✅ Webhook server (aiohttp, subscriptions, _verify_raw_secret)
│   ├── sessions.py         # ✅ /sessions, /resume, cross-platform
│   └── standalone.py       # ✅ standalone sender (_standalone_send, media)
├── tests/
│   ├── test_interactive.py # ✅ buttons/actions (13 tests) — a separate test_buttons.py was not needed
│   ├── test_file_send.py   # ✅ upload + standalone sender (including SSRF)
│   └── ...                 # conftest: package import max.adapter (fixed 2026-08-17)
```

## Commit sequence (completed)

| Step | Commit | What it does | Status |
|-----|--------|--------------|--------|
| 1 | `refactor: add base mixin structure for adapter.py` | MaxBaseMixin — base state, core props | ✅ |
| 2 | `refactor: add stubs for remaining mixins` | Stubs for all modules with correct imports | ✅ |
| 3 | `fix: use relative imports in all mixins` | `from mixins.base` → `from .base` in all mixins | ✅ |
| 4 | `refactor: extract table rendering to table_renderer.py` | Move table rendering from adapter.py | ✅ |
| 5 | `refactor: extract upload protocol to media_upload.py` | POST /uploads, CDN, retry, SSRF whitelist | ✅ |
| 6 | `refactor: extract button logic to buttons.py` | send_buttons, send_action, _post_interactive | ✅ 56f1ed5 |
| 7 | `refactor: extract STT logic to stt_processor.py` | Voice transcription | ⏭️ superseded — STT is in the Hermes core v0.20.0; the mixin was removed (2026-08-05) |
| 8 | `refactor: extract webhook server to webhook.py` | aiohttp webhook, subscriptions | ✅ 1a07f87 |
| 9 | `refactor: extract session commands to sessions.py` | /sessions, /resume, cross-platform | ✅ 06e02f3 |
| 10 | `refactor: extract standalone sender to standalone.py` | _standalone_send, _get_token, media handling | ✅ 8db4fb7 |
| 11 | `refactor: strip adapter.py to thin facade` | Leave only orchestration + imports from mixins | ✅ 3de0cf5 |

## Key development principles

1. **Blame preservation** — `cp` before cutting, not `git mv`. Each file inherits the history of its lines.
2. **Every commit green** — `pytest tests/` must pass after every step.
3. **Mixins/composition** — `MaxAdapter` inherits mixins. Composition is preferred to minimize changes in adapter.py.
4. **No logic changes** — refactoring without changing behavior. Pure code movement.
5. **Tests move with code** — if tests are scattered, group them at the end.

## 🚨 Important: imports in mixins

**All imports inside mixins/ MUST use relative imports (`.module`), not absolute imports (`module`).**

Absolute imports (`from mixins.base import ...`) work in local testing (CWD == plugin directory), but fail silently when loaded through the Hermes plugin system (CWD != plugin directory). The error is logged with `exc_info=False`, so no traceback appears in journalctl.

**Rule:**
- `adapter.py` → `from .mixins.xxx import YYY`
- `mixins/*.py` → `from .base import ZZZ` (not `from mixins.base import ZZZ`)

## Roadmap (Future development work)

The features below will make the plugin Enterprise-ready.

### Priority #1: Table rendering 2.0 (HTML → PNG) — **in development**

**The current implementation (Pillow `ImageDraw`) is considered clumsy:** manual width calculation using
`draw.textlength` + `wcwidth*0.6` fallback causes cells to overflow, text to overlap neighboring cells,
and emojis are replaced with textual workarounds (`✅→✓`); Cyrillic depends on DejaVu being available on
the distribution (`/usr/share/fonts/...`).

**Solution — HTML+CSS followed by rendering to PNG through a headless browser.** The browser lays out the
table (it never spills outside cells), any CSS styles are supported, and native color emojis are supported.
Branch: `feature/table-render-html-png`.

- **Path:** generate HTML from parser `_parse_table_rows` (`mixins/table_renderer.py::_build_table_html`)
  → screenshot `.wrap` through **Playwright** (Chromium/Chrome) with `device_scale_factor=2` → PNG → upload to MAX.
- **Rendering:** **Playwright is primary** (universal: both desktop and Linux Gateway), **Pillow is the only
  fallback** when the browser is unavailable. (Using the built-in Hermes browser was rejected: `browser_exec` is
  an agent tool unavailable to the plugin in the gateway process.)
- **Cache:** retained (content addressing via `table_<md5>.png`); only the rendering method changes.
- **Width constraint:** `table-layout: fixed` + explicit `width` for each column (percentages calculated
  by Python from `_parse_table_rows` data) + `overflow-wrap: break-word`. This guarantees that short columns
  (number/status/address) are not compressed by “greedy” content columns — unlike `table-layout: auto`, where
  the browser gives all width to the widest cell and the last columns collapse. Table width is limited to
  `max-width` (~820px) for mobile devices.

### Voice responses (TTS)

Use **Hermes itself’s built-in TTS mechanism** (the `tts` config in `config.yaml`,
providers edge/openai/mistral/xai/elevenlabs and others), rather than custom generation inside the plugin.

- The agent (core) generates audio through its TTS → passes the file to the plugin → the plugin sends it through
  the already implemented `MaxAdapter.send_voice()` method (see `adapter.py`, a wrapper around `_upload_send`)
  → signing uses the same chain as ordinary audio messages.
- Separate audio generation in the plugin is **not needed** — only pass the ready file to the MAX channel.

---
*Note for the Agent:* When starting a new session, read this file to understand the current refactoring stage and development direction.
