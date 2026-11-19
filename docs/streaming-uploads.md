# Streaming upload limits (independent candidate B)

This branch starts at `9818b642a53425116478030c49cd4663f22177c2` and does not require the new attachment tool/types. It replaces whole-file reads in **both** gateway `_upload` and standalone `_standalone_send` with the same single-attempt `aiohttp` multipart streaming payload.

| Upload type | Local conservative ceiling |
|---|---:|
| image | 50,000,000 bytes |
| video | 250,000,000 bytes |
| audio | 256,000,000 bytes |
| file | 4,000,000,000 bytes |

Official docs say MB/GB but do not define binary vs decimal units. These decimal ceilings are explicitly conservative, not a claim of exact vendor byte limits. Zero-byte/non-regular files and names >200 chars are rejected. Image dimensions <=7680×7680, audio <=60 minutes and extension rules are still enforced by MAX; no new local decoder/probe is introduced.

Each disk read is <=64 KiB, off the event loop, without read-all, prefetch or replay. Admission carries dev/inode/size from lstat through both senders to the payload. The worker opens with O_NONBLOCK|O_NOFOLLOW|O_CLOEXEC, then fstat must confirm regular mode and the exact admitted identity/size before any read. A FIFO or same-size inode replacement fails; final-component symlinks are conservatively rejected. Intermediate-path replacement cannot admit another inode. Concurrent in-place content modification is still unsupported (identity is not a content snapshot).

One daemon worker exclusively owns each opened FD and closes it itself. Cancellation/timeout does NOT wait indefinitely for an OS syscall and does NOT close an FD underneath a running read. Disk waits are capped at10s and the payload has an absolute size-based deadline; caller cancellation returns promptly. If the OS syscall is stuck, its worker retains its own FD until it returns and then closes it. A shared nonblocking semaphore caps admission/file workers, including late cleanup, at4 per process. Exhaustion fails new uploads immediately; there is no queued executor backlog, expanding reaper or automatic retry. A permanently stuck kernel call can retain a slot/FD until process exit: this is explicitly bounded resource retention, not a promise to cancel a syscall or complete cleanup within10s. Controlled probes release and join every worker before finishing. No thread outside the owner may close/reuse that FD.

Truncation fails and growth is not uploaded beyond the admitted size. Memory is O(chunk + bounded HTTP buffers), not O(file size). No automatic upload retry/resumption; CDN failures do not result in sending an unconfirmed audio/video token. Unknown transport outcomes are never automatically replayed.

Both paths use a shared size-scaled finite total timeout: 60s overhead plus size/500,000 seconds, clamped to120..3600s; connect30s and response idle120s. Redirects are disabled; upload URL must be HTTPS without credentials/fragment and still passes the sender's existing MAX-domain allowlist. CDN response is bounded at64KiB. TLS context/certificate validation is unchanged. Remote-download guards and their separate limits are unchanged. The existing gateway readiness budget and standalone's three-attempt explicit400-only readiness loop are retained.

Use normal `MEDIA:/absolute/path` gateway replies or existing `send_message` media delivery. No configuration/secret/production installation is part of this artifact. To rollback use the original base commit; do not overwrite an active installation during verification.

Verification commands from this checkout:
```
sh ../run-python -m pytest tests/test_streaming_upload.py tests/test_streaming_extra.py -q -s --basetemp=../pytest-stream-proof
```
The controlled local HTTP server proves actual aiohttp multipart bytes through gateway and standalone for a finite51MiB file with success and CDN503 cases; public API traffic is mocked, and the approved CDN URL is mapped to loopback only inside the test. The checksum and byte count must match; actual file.read calls are tracked with maximum64KiB and non-loop thread IDs. Python heap peak is asserted <16MiB and process RSS high-water growth <24MiB. The latter is an incremental same-process measurement, not absolute RSS. Sparse exact-limit files test admission without reading/transferring4GB. Cancellation tests cover descriptor cleanup during open/read. Existing routing/CDN test doubles were updated only for bounded-response reads, explicit redirect argument and payload identity rather than prebuffered bytes. Nothing here proves liveMAX/4GB delivery.

Sources: [uploads](https://dev.max.ru/docs-api/methods/POST/uploads), [media](https://dev.max.ru/docs-api/use-cases/sending-messages/media). Historical50MiB was introduced in `25ab65c294945484331ebb49ce3f9330b9471e0b`; its original motivation is unknown. That version used an open file; the current baseline's `read_bytes` and its memory-cap comment establish a present dependency, not the original author's reasoning.
