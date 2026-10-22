# Group access and first-install configuration — Micro-Spec

Source: user request, 2026-10-22. Baseline: a8cce41. Core fixture: ca13a7828acd2ba8c75e1c1d1694cbc1aee7df3f.

Scope: apply existing group authorization to every callback; expose group settings in Desktop; persist safe missing onboarding defaults and document group operation. Preserve existing configuration, owner-bound interactions and Core behavior. No live subscriptions, messages or production configuration changes.

| ID | Trigger / context | Required result | Acceptance | Status |
|---|---|---|---|---|
| GRP-001 | Group callback denied by current policy | Stop before routing, interaction consumption or delivery; all five callback families covered | tests/test_group_access.py; tests/test_catalog_security.py; documentation checks | Implemented; automated checks passed |
| GRP-002 | Allowed group or direct callback | Keep global authorization, requester/message binding and dialog routing; denied callback leaves pending interaction usable | tests/test_group_access.py; tests/test_catalog_security.py; documentation checks | Implemented; automated checks passed |
| GRP-003 | Fresh or repeated setup | Persist missing safe access/session defaults; preserve existing explicit settings; expose group fields with numeric ID examples | tests/test_group_access.py; tests/test_catalog_security.py; documentation checks | Implemented; automated checks passed |
| GRP-004 | Operator configures groups | Document family/mixed scenarios, ID discovery, AND semantics, shared resources and visible replies | tests/test_group_access.py; tests/test_catalog_security.py; documentation checks | Implemented; automated checks passed |

## Evidence and limits

Verified 2026-10-22 on Python 3.14: current Core fixture `ca13a7828acd2ba8c75e1c1d1694cbc1aee7df3f`, full suite 891 passed, one upstream deprecation warning. GRP-001 regression reproduced 24 failures before the callback gate; policy matrix, five families, dialog routing and pending-state recovery pass after it. Existing ownership/Core/wire fixtures now explicitly permit groups so their authorization assertions reach the intended handler. GRP-003 setup tests cover fresh and existing values, closed-by-default and explicit open access; runtime defaults are checked separately. Desktop manifest includes group policy/lists and MAX_WEBHOOK_URL; numeric ID placeholders corrected. GRP-004 documentation links, language parity, claims and configuration reference checks pass; Ruff passes.

The minimum Core source fixture `d337b736aa1e8ebecfab043842d13e4a2d2f48a3` and baseline `d0288be5b3330d2442e3907185b8e9d0958297bb` each passed 211 focused cases via PYTHONPATH in the same Python 3.14 environment. This is source compatibility, not a full Python 3.12 dependency-installation check. No live group messages, callbacks, gateway restart or production configuration changes were performed. Post-push CI is recorded separately; local tests do not establish dependency-audit success.
