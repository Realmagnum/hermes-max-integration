# adapter.py Refactoring Plan

## Goal

Split the monolithic `adapter.py` (~3100 lines) into a modular structure. Each module owns its responsibility area.

## Current Status

**Dev branch:** `feature/refactor-mixins-base`
**Done:** base mixin structure, table_renderer (543 lines), media_upload (197 lines with full upload/CDN logic), stt_processor (46 lines with impl)

## Strategy: single feature branch

Branch off `main`. Each commit extracts one module. Merge into `main` with a tag upon completion.

## Module layout

```
hermes-max-integration/
├── adapter.py              # thin facade: imports + orchestration
├── mixins/
│   ├── __init__.py
│   ├── base.py             # ✅ MaxBaseMixin — core state, http_client
│   ├── table_renderer.py   # ✅ Table rendering (543 lines, full impl)
│   ├── media_upload.py     # ✅ File upload (POST /uploads, CDN, retry, SSRF)
│   ├── buttons.py          # ⏳ send_buttons, send_action, _post_interactive
│   ├── stt_processor.py    # ✅ Voice message processing (STT, 46 lines)
│   ├── webhook.py          # ⏳ Webhook server (aiohttp, subscriptions)
│   ├── sessions.py         # ❌ TODO /sessions, /resume, cross-platform
│   └── standalone.py       # ❌ TODO standalone sender (_standalone_send)
├── tests/
│   ├── test_upload.py      # ❌ TODO — moved from test_file_send.py
│   ├── test_buttons.py     # ❌ TODO — moved from test_interactive.py
│   └── ...                 # remaining tests stay
```

## Commit order

| Step | Commit | What | Status |
|------|--------|------|--------|
| 1 | `refactor: add base mixin structure for adapter.py` | MaxBaseMixin — core state, core props | ✅ |
| 2 | `refactor: add stubs for remaining mixins` | Stubs for all modules with correct imports | ✅ |
| 3 | `fix: use relative imports in all mixins` | `from mixins.base` → `from .base` across all mixins | ✅ |
| 4 | `refactor: extract table rendering to table_renderer.py` | Move table rendering from adapter.py | ✅ |
| 5 | `refactor: extract upload protocol to media_upload.py` | POST /uploads, CDN, retry, SSRF whitelist | ✅ |
| 6 | `refactor: extract button logic to buttons.py` | send_buttons, send_action, _post_interactive | ❌ |
| 7 | `refactor: extract STT logic to stt_processor.py` | Voice transcription | ✅ |
| 8 | `refactor: extract webhook server to webhook.py` | aiohttp webhook, subscriptions | ❌ |
| 9 | `refactor: extract session commands to sessions.py` | /sessions, /resume, cross-platform | ❌ |
| 10 | `refactor: extract standalone sender to standalone.py` | _standalone_send, _get_token, media handling | ❌ |
| 11 | `refactor: strip adapter.py to thin facade` | Keep only orchestration + imports from mixins | ❌ |

## Key principles

1. **Blame preservation** — `cp` before cutting, not `git mv`. Each file inherits its line history.
2. **Green every commit** — `pytest tests/` must pass after each step.
3. **Mixins/composition** — `MaxAdapter` inherits mixins. Prefer composition to minimize adapter.py changes.
4. **No logic changes** — pure refactoring, no behavior changes.
5. **Tests move with code** — if tests are scattered, group them at the end.

## 🚨 Important: imports in mixins

**All imports inside mixins/ MUST use relative imports (`.module`), NOT absolute (`module`).**

Absolute imports (`from mixins.base import ...`) work in local testing (CWD == plugin directory), but fail silently when loaded through the Hermes plugin system (CWD != plugin directory). The error is logged with `exc_info=False`, so no traceback appears in journalctl.

**Rule:**
- `adapter.py` → `from .mixins.xxx import YYY`
- `mixins/*.py` → `from .base import ZZZ` (not `from mixins.base import ZZZ`)

## Commit format

All branch commits: `refactor: ...` or `fix: ...`. Final: `chore: cleanup`. Merge into main WITHOUT squash (preserve refactoring history).

## After refactoring

```bash
bash scripts/release.sh v2.5.0
```
