# Honest security model

This document describes **what the plugin actually protects and what it does not**. It has
been updated to reflect the audit findings and vulnerability resolutions in release v2.10.0,
and deliberately makes no promises of absolute security.

## Status and scope

| Parameter | Value |
|---|---|
| Scope | the `hermes-max-integration` plugin (adapter.py, mixins/, scripts, documentation) |
| Audit baseline | commit `b004c573318f1d5e521255531d1943cc8a8b8b90` (`main`) |
| Findings backlog | `BACKLOG_EN.md` (audit items SEC-01…SEC-07, CODE-01…CODE-08) |
| Document updated | 2026-10-01, release v2.10.2 (all SEC-01…07 tasks closed in v2.10.0) |
| What was checked | static code analysis, isolated tests, pytest regression suite (729 tests) |
| What was NOT checked | production E2E with real users, external platform rules, commit history prior to fork |

Evidence markers (as in the backlog): **S** — static code/document comparison, **R** —
isolated execution with mocks (not the complete plugin), **E** — actual local command,
**V** — hypothesis or external contract requiring verification.

> All security audit items **SEC-01…SEC-07** and reliability items **CODE-01…CODE-08** were resolved in release v2.10.0 and verified by regression tests.

## Trust model

| Party | Assumed | Limitation |
|---|---|---|
| MAX Bot API | source of `message_created`, `message_callback`, `bot_started` events | event authenticity is confirmed only by the webhook secret; in long polling it relies on trusting the API |
| User/chat | identifiers come from the event | authorized via allowlists; callback queries protected with strict owner binding (SEC-01) |
| Hermes core | receives text and media and runs tools | the plugin is not a security boundary for the core |
| Network | any attachment URL contained in an event | strict DNS pinning and private IP rejection (SEC-02/SEC-03) |
| Gateway host | trusted | the filesystem, `.env` and the webhook port are protected by you, not by the plugin |

## Safe defaults and what you must override

| Setting | Default | Risk | Set it to |
|---|---|---|---|
| `MAX_ALLOW_ALL_USERS` | `false` | — | leave `false` |
| `MAX_ALLOWED_USERS` | empty | ⚠️ empty list closes access (fail-closed, SEC-05/SEC-06) | set your own MAX user_id |
| `MAX_CROSS_SESSION` | `false` | ⚠️ cross-platform sessions disabled by default (SEC-05) | `false` (enable only for trusted `MAX_CROSS_SESSION_USERS`) |
| `MAX_WEBHOOK_SECRET` | empty | ⚠️ webhook will not start without secret (fail-closed, SEC-04) | mandatory in webhook mode, plus network restrictions |
| `MAX_WEBHOOK_HOST` | `0.0.0.0` | ⚠️ the port listens on every interface | `127.0.0.1` behind a reverse proxy |
| `MAX_GROUP_POLICY` | `allowlist` | ⚠️ policy uses AND semantics, empty list is closed (SEC-06) | `allowlist` with populated lists or `closed` |
| `MAX_TABLE_AS_IMAGE` | `false` | — | as needed |
| `MAX_AUTO_INSTALL_PLAYWRIGHT` | `false` | ⚠️ when `true` the plugin installs a package and browser from the network at runtime | keep `false` unless network installation is controlled |
| `MAX_WEBHOOK_INSECURE_DEV` | `false` | ⚠️ allows running webhook without secret only on loopback (127.0.0.1) | `false` for production, `true` for local development only |

### Minimal single-owner configuration

```bash
# ~/.hermes/.env
MAX_BOT_TOKEN=<bot token>
MAX_ALLOWED_USERS=<your MAX user_id>          # mandatory — otherwise access is closed (fail-closed)
MAX_CROSS_SESSION=false                       # session history from other platforms isolated
MAX_WEBHOOK_SECRET=<long random string>       # mandatory in webhook mode
MAX_WEBHOOK_HOST=127.0.0.1                    # when a reverse proxy fronts the gateway
```

With this configuration exactly one user can reach the bot, no inbound ports are open
(long polling), and session history from other platforms is not exposed. Also restrict
access to the host itself: the `.env` holding the token must be owner-readable only.

## Webhook, ingress, firewall

- **Long polling (default)** requires no inbound ports — the smallest attack surface. If
  you do not need a public ingress, keep polling.
- **Webhook** requires public HTTPS: MAX connects to port 443 only. TLS terminates on a
  reverse proxy (Caddy/Nginx/Traefik/Cloudflare Tunnel) while the plugin listener binds
  to `127.0.0.1:8646`.
- **Webhook secret** is sent by MAX as the raw value of the `X-Max-Bot-Api-Secret`
  header (not an HMAC signature); the plugin compares it with
  `secrets.compare_digest`. Without a valid secret, the handler responds with 403
  before parsing the request body (SEC-04).
- **Firewall**: port `8646` must not be reachable from outside. Allow inbound 443 to the
  reverse proxy only; deny the rest.
- **Built-in rate limiting** for the webhook is 30 requests / 10 seconds per IP, in
  process memory: it resets on restart and does not distinguish clients behind a proxy.
  It guards against bursts, not against a targeted attack.
- **`/health`** is served without authentication and only proves the process is up.
  Readiness to receive traffic is verified via `/ready` (CODE-05).

## What is implemented — and how well it was verified

| Protection | State | Limitation |
|---|---|---|
| User allowlist | S/R | strict isolation: empty list denies access (fail-closed, SEC-05/SEC-06), verified by tests |
| Inbound media URL validation (`_validate_download_url`) | S/R | strict DNS pinning (blocks private/loopback/link-local IPs and guards against DNS rebinding, SEC-03) |
| Host allowlist for outbound uploads | S | applies to sending media to MAX (`*.max.ru`, `*.oneme.ru`), isolated download client |
| Token isolation during media download | S/R | download client without Authorization; token is not transmitted to external URLs (SEC-02) |
| Constant-time secret comparison | S | `secrets.compare_digest`, fail-closed check before reading request body (SEC-04) |
| Cache directory permissions | S | audio cache and PNG table directory created with `mode=0o700` |
| Log sanitization | S | userinfo and query strings stripped from URLs (`_safe_url_for_log`), token is never logged |
| Incoming media limits | S/R | limits on attachment size (`MAX_INBOUND_MEDIA_MAX_BYTES`), total size (`MAX_INBOUND_MEDIA_TOTAL_BYTES`), timeout (SEC-07) |
| CI checks and tests | E | 729 tests (pytest, ruff, bandit, pip-audit); coverage for adapter.py, mixins/ and scripts/ |

## Resolved security issues (backlog SEC-01…07)

Full statements and acceptance criteria: `BACKLOG_EN.md`.

| ID | Resolution in v2.10.0 |
|---|---|
| SEC-01 | Implemented universal callback query authorization bound to owner_user_id, scoped chat and TTL |
| SEC-02 | Isolated download client, bot token is never forwarded to arbitrary attachment URLs |
| SEC-03 | Enforced strict DNS pinning with pre-connect IP address validation against SSRF and DNS rebinding |
| SEC-04 | Webhook operates fail-closed: valid secret mandatory before parsing request body |
| SEC-05 | Access to /sessions and /resume restricted to trusted owners (`MAX_CROSS_SESSION=false` by default) |
| SEC-06 | Group allowlist semantics transitioned to fail-closed and AND-based combination |
| SEC-07 | Strict limits enforced for incoming attachment size, total media volume, attachment count and timeout |

With tasks SEC-01…07 resolved, usage modes are as follows:

- **supported**: personal use, group chats with user and chat allowlists, secure webhook with secret behind a reverse proxy;
- **requires attention**: public webhook without reverse proxy and firewall, granting bot access to untrusted individuals.

## Cache, data, logs

| Object | Location | What to consider |
|---|---|---|
| Audio cache | `$HERMES_HOME/cache/audio/` (`~/.hermes/cache/audio/`), directory `0o700` | voice messages stay until removed manually; this is private data |
| PNG tables | `~/.hermes/table_images/` | render cache whose key includes the engine |
| Message dedup | process memory (5 minutes) | not persistent, resets on restart |
| Sessions | Hermes core (SessionDB) | `/sessions` isolated from other platforms by default (SEC-05) |
| Logs | Hermes gateway log | URLs are logged without query and userinfo; message content is not redacted |
| Network | MAX API + PyPI (when Playwright auto-install is on) | the plugin makes no network calls other than the MAX API and dependency downloads |

## Audits performed: date, commit, scope

| Date | Commit | Scope | What it proves |
|---|---|---|---|
| 2026-07-17 | `e87ee64` | fixes for 10 vulnerabilities from a "full audit" (adapter.py and related code) | that the issues listed in that report were fixed |
| 2026-07-17 | `6e0f77a`, `beb4af2` | STT pipeline, README Security section, CHANGELOG v2.1.1 | accompanying changes |
| 2026-07-18 | `70eb490`, `d9626b5` | 5 remaining MEDIUM/LOW fixes, `nosec B104` annotation for bind-all | targeted fixes |
| 2026-08-17 | `e632014` | downloads no longer follow redirects, SSRF guard for inbound URLs, warning on an empty secret, 11 tests | current download behaviour |
| 2026-09-15 | `abd2f0f` | audit backlog of baseline `b004c573`: 7 SEC, 8 CODE, 4 BUILD, 10 DOC | audit backlog recording |
| 2026-09-16 | `b0ea511` | documentation alignment and initial tests (DOC-05, DOC-10) | accurate description of intermediate state |
| 2026-09-29 | `ad920e6` | Release v2.10.0: closed all vulnerabilities SEC-01…SEC-07, implemented CODE-01…CODE-08, 720 tests | resolved all audit backlog items |
| 2026-10-01 | `bcbf769` | Release v2.10.2: Desktop UI sidebar (max-sessions-sidebar), file:// URL handling, 729 tests | desktop integration and stabilization |

The complete test suite `pytest` (729 tests), Ruff, Bandit and pip-audit run regularly in CI.

## Disclaimer

- Neither this document nor past audits guarantee the complete absence of vulnerabilities.
- All implemented security protections are verified by static analysis and a comprehensive suite of 729 tests.
- Responsibility for ingress, secrets, firewall, host access, and `.env` contents remains with the deployment owner.
- Follow safe configuration practices when deploying in production environments.
