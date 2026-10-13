# Media caption fallback — Micro-Spec

[Russian version](media-caption_RU.md)

Source: user request, 2026-10-13: unnamed text for a file becomes its filename, otherwise `File`. Baseline: plugin `3df6518`; inspected Core `7157422022ff06f3e632d1dd394ee1253b17ad37` and upstream `4957bbd0a0f6a1c3fe8217dc4a66d072971f5b63`.

## Scope and contracts

Use the public `transform_llm_output` hook for MAX agent replies before Core media extraction. Normalize captions in direct adapter and standalone sends. Preserve authored text, other platforms, delivery errors, credentials and file validation. Do not patch Core. Direct `hermes send` and cron routes that do not invoke this hook still require caller-provided text; this plugin cannot intercept their earlier Core rejection. The hook needs Core to supply `platform=max`; an unknown platform is left unchanged.

| ID | Trigger | Observable result / acceptance | Status |
|---|---|---|---|
| CAP-001 | File caption is absent or whitespace | Use basename (including Windows paths), or explicit filename; no directory disclosure; unavailable name becomes `File` | Planned |
| CAP-002 | Caption contains authored text | Preserve it exactly; text-only sends remain unchanged | Planned |
| CAP-003 | MAX agent reply contains only MEDIA markers | Public hook adds first filename before Core extraction; real public router accepts transformed text plus file; other platforms and already-captioned replies unchanged | Planned |
| CAP-004 | Direct adapter/standalone sends an uncaptioned attachment | Outbound attachment payload carries fallback text; existing failure and partial-delivery semantics preserved | Planned |

## Evidence

Pending implementation and isolated tests. Live MAX delivery is not claimed. Direct CLI media-only limitation remains open under catalog MS-011.
