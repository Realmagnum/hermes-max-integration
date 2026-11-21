# Native upload portability and readiness checks

Run the Core-free native upload gate from the checkout root:

```sh
python -m pip install 'aiohttp>=3.14.3,<4'
python scripts/check-upload-portability.py
```

CI runs this exact production-module probe on Ubuntu, macOS and Windows with
Python 3.12. It creates synthetic binary files and a loopback multipart server;
no credentials, MAX account, Core installation or external upload is involved.
A missing Windows symlink privilege or junction fixture is a failure, not a skip.
A passing macOS probe does **not** certify Windows or Linux; native CI is required.

The probe checks exact SHA256/bytes, binary/non-inheritable descriptor identity,
64 KiB maximum reads off the event loop, no upload replay on HTTP 503,
replacement/symlink/special-file rejection without bytes, four worker-start
faults and cancellation with four late-owned workers returning capacity.
Windows additionally exercises a junction, DOS devices, ADS and a live named pipe.

Windows opens only ordinary local drive paths using `CreateFileW` with
`FILE_FLAG_OPEN_REPARSE_POINT`; it rejects non-disk handles, all final-component
reparse tags and directories before handing ownership to a binary,
non-inheritable CRT descriptor. The existing worker then checks that exact FD's
regular-file `fstat` dev/inode/size against admission before reading. UNC/device
namespaces and alternate data streams are unsupported. Parent directories are
trusted, matching the existing POSIX final-component `O_NOFOLLOW` boundary.
POSIX open flags are unchanged; there is no missing-flags-to-zero fallback.

## Attachment processing readiness

Adapter and standalone now share one readiness helper and validated settings:
`MAX_MEDIA_READY_ATTEMPTS` / `extra.media_ready_attempts` (default 8, bounds 1–12),
`MAX_MEDIA_READY_TIMEOUT` / `extra.media_ready_timeout` (default 90 seconds,
bounds 0.1–300). Environment values take precedence; invalid values fall back.
The readiness budget starts **after** the single CDN upload and includes POST
and sleep time. The first send is immediate, with retries after 2, 4, 8, then
at most 16 seconds. Each POST is limited to the remaining budget.

Only an explicit HTTP 400 JSON `code=attachment.not.ready` permits another
identical attachment POST, using the same token/body. Arbitrary 400s, 503s,
invalid JSON, transport errors and timeouts do not replay; cancellation propagates.
No change to Core timeout or production installation is part of this patch.

Targeted regressions (with the project's supported Core test environment):

```sh
python -m pytest tests/test_standalone_readiness.py tests/test_media_readiness.py \
  tests/test_file_send.py tests/test_core_send_router.py -q
```
