# Refactoring Plan for adapter.py

## Goal

Split monolithic `adapter.py` (~3100 lines) into a modular structure. Each module is responsible for its own domain.

## Strategy: single feature branch

Branch `feature/refactor-adapter` from `main`. Each commit extracts one module. After completion — merge into `main` with a release tag.

## Module layout

```
hermes-max-integration/
├── adapter.py              # thin facade: imports + shared logic
├── mixins/
│   ├── __init__.py
│   ├── upload.py           # file upload protocol (POST /uploads, CDN, retry)
│   ├── buttons.py          # send_buttons, send_action, _post_interactive
│   ├── sessions.py         # cross-platform sessions (/sessions, /resume)
│   └── standalone.py       # standalone sender (_standalone_send, _get_token)
├── tests/
│   ├── test_upload.py       # tests extracted from test_file_send.py
│   ├── test_buttons.py      # tests from test_interactive.py
│   └── ...                  # remaining tests stay as-is
```

## Commit order

| Step | Commit message | What it does | Tests |
|-----|----------------|-------------|-------|
| 1 | `refactor: copy adapter.py for blame preservation` | Copy `adapter.py` → temp preserve | — |
| 2 | `refactor: extract upload protocol to mixins/upload.py` | POST /uploads, CDN, retry, SSRF whitelist | `pytest tests/` ✅ |
| 3 | `refactor: extract button logic to mixins/buttons.py` | send_buttons, send_action, _post_interactive | `pytest tests/` ✅ |
| 4 | `refactor: extract session commands to mixins/sessions.py` | /sessions, /resume, cross-platform | `pytest tests/` ✅ |
| 5 | `refactor: extract standalone sender to mixins/standalone.py` | _standalone_send, _get_token, media handling | `pytest tests/` ✅ |
| 6 | `refactor: strip adapter.py to thin facade` | Keep only shared logic + mixin imports | `pytest tests/` ✅ |
| 7 | `chore: cleanup old adapter.py copy` | Delete temp copy | — |

## Key principles

1. **Blame preservation** — `cp` before cutting, not `git mv`. Each file inherits the history of its lines.
2. **Every commit green** — `pytest tests/` must pass after each step.
3. **Mixins/composition** — `MaxAdapter` inherits or uses mixins. Mixins preferred to minimize adapter.py changes.
4. **No logic changes** — pure refactoring. Code move only, no behavioral changes.
5. **Tests move with code** — if upload tests are scattered, regroup at the end.

## Commit format

All commits in the branch: `refactor: ...`. Final cleanup: `chore: cleanup`. Merge into main — no squash (preserve refactoring history).

## After refactoring

```bash
bash scripts/release.sh v2.5.0
```
