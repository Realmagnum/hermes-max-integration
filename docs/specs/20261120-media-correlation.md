# Outbound media correlation — Micro-Spec

Source: authorized PR10 diagnostics task, amended to one final completion/access-log summary. Baseline: `52be4464700073b1a3bd49d9c5ac863e041c9828`. Core: local source distribution0.0.0, exact SHA unavailable; not CI-matrix evidence. Previous multi-record pin acceptance is historical, not acceptance of this amended contract.

Scope: adapter image/video/audio/file, standalone, remote-image results and direct image batch upload→send/fallback correlation. No delivery/retry/type changes; no Core/config/launchd/logfile changes; no installation/restart/push by this builder. The parent owns later installation/live acceptance/publication after review.

| ID | Trigger / context | Required result | Acceptance / code anchors | Implementation | Verification |
|---|---|---|---|---|---|
| MS-MEDIA-CORR-001 | Success, failure or cancellation of an attachment | Exactly one compact final `MAX media:` INFO record, no start/intermediate/per-attempt plugin noise or modes | `tests/test_media_correlation.py`: both senders × four native types × success/error/cancel; preparation errors and remote image | Implemented | Targeted tests; exact pin/evidence in handoff |
| MS-MEDIA-CORR-002 | Audio normalization; generated artifact removed | Original source ID is computed before conversion and remains linked to admitted artifact/result | Same module: actual _upload_send, source ID before conversion, delete generated ogg then map surviving original; missing-file cases | Implemented | Targeted tests; see handoff |
| MS-MEDIA-CORR-003 | Repeated readiness and untrusted data | O(1) fixed state per attachment, <=2048-byte summary, fixed counters/timings, no content rereads/new queues/timers/tasks/workers, no raw paths/URLs/tokens/speech | Same module:100000 repeated updates, tracemalloc, no new threads, no intermediate records, saturation and failing logger | Implemented | Targeted tests; see handoff |
| MS-MEDIA-CORR-004 | Batch final send, fallback, partial success or cancel | One final per input with its actual result, source/artifact IDs, shared batch ID and send receipt; no premature upload-only record | Same module: direct success, send/CDN failure with original fallback preserved, partial fallback, cancellation | Implemented | Targeted tests; see handoff |

## Evidence and limits

The accumulator uses fixed fields/counters and the existing logging handlers, not an event cache or infrastructure. Batch owns one fixed accumulator per existing input until completion (O(N) inputs, O(1) each); no global registry. Hard-crash loss is accepted. Source IDs are guessable lexical-path mappings, not anonymity/content checksums. Before source/artifact observation, identities remain empty and size -1, including preparation errors and remote URL images. Counters/timings saturate; overlong message IDs are omitted from the summary only. Mapping and fields are documented in [troubleshooting](../troubleshooting.md#outbound-file-correlation). Live delivery, installation, new independent review and CI matrix remain pending.
