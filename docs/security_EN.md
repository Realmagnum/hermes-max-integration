# Honest security model

[Русский](security.md)

This document describes **what the plugin actually protects and what it does not**. It is
written from audit results and deliberately makes no promises of absolute security.

## Status and scope

| Parameter | Value |
|---|---|
| Scope | the `hermes-max-integration` plugin (adapter.py, mixins/, scripts, documentation) |
| Audit baseline | commit `b004c573318f1d5e521255531d1943cc8a8b8b90` (`main`) |
| Findings backlog | `BACKLOG.md`, `BACKLOG_EN.md` on branch `docs/audit-backlog`, commit `abd2f0f` (2026-09-15) |
| Document updated | 2026-09-16, branch `docs/doc-05-honest-security-model`, tree state `b0ea511` |
| What was checked | source and RU/EN guide reading (S), isolated execution of extracted methods with mocks (R), a local command (E) |
| What was NOT checked | real MAX E2E, full Hermes core, external links, platform rules, full secret history |

Evidence markers (as in the backlog): **S** — static code/document comparison, **R** —
isolated execution with mocks (not the complete plugin), **E** — actual local command,
**V** — hypothesis or external contract requiring verification.

> Absence of findings does not imply absence of vulnerabilities. The plugin is **not**
> intended for public or multi-user deployments until tasks SEC-01…07 are closed.

## Trust model

| Party | Assumed | Limitation |
|---|---|---|
| MAX Bot API | source of `message_created`, `message_callback`, `bot_started` events | event authenticity is confirmed only by the webhook secret; in long polling it relies on trusting the API |
| User/chat | identifiers come from the event | only user allowlists are enforced; callback approvals are incompletely authorized (SEC-01) |
| Hermes core | receives text and media and runs tools | the plugin is not a security boundary for the core |
| Network | any attachment URL contained in an event | only partially filtered (see below and SEC-02/SEC-03) |
| Gateway host | trusted | the filesystem, `.env` and the webhook port are protected by you, not by the plugin |

## Safe defaults and what you must override

| Setting | Default | Risk | Set it to |
|---|---|---|---|
| `MAX_ALLOW_ALL_USERS` | `false` | — | leave `false` |
| `MAX_ALLOWED_USERS` | empty | ⚠️ **an empty list with `MAX_ALLOW_ALL_USERS=false` does not close access**: anyone able to message the bot reaches the core (SEC-05/SEC-06) | always set your own MAX user_id |
| `MAX_CROSS_SESSION` | `true` | ⚠️ `/sessions` and `/resume` bypass the platform filter; until SEC-05 is closed, titles/previews/IDs of sessions from all platforms are exposed | `false` if more than one person uses the bot or it is reachable from a group |
| `MAX_WEBHOOK_SECRET` | empty | ⚠️ an empty secret only logs a warning while request processing continues; the sender is taken from the JSON body (SEC-04) | mandatory in webhook mode, plus network restrictions |
| `MAX_WEBHOOK_HOST` | `0.0.0.0` | ⚠️ the port listens on every interface | `127.0.0.1` behind a reverse proxy |
| `MAX_GROUP_POLICY` | `allowlist` | ⚠️ under the `allowlist` policy an empty list means "allowed" and lists combine with OR (SEC-06) | `closed`, or fill both lists |
| `MAX_TABLE_AS_IMAGE` | `false` | — | as needed |
| `MAX_AUTO_INSTALL_PLAYWRIGHT` | `false` | ⚠️ when `true` the plugin installs a package and a browser from the network at runtime | keep `false` unless that network installation is controlled |
| `MAX_INSECURE_SSL` | `false` | ⚠️ when `true` TLS verification is disabled | local tests only |

### Minimal single-owner configuration

```bash
# ~/.hermes/.env
MAX_BOT_TOKEN=<bot token>
MAX_ALLOWED_USERS=<your MAX user_id>          # mandatory — otherwise access is open to everyone
MAX_CROSS_SESSION=false                       # until SEC-05 is closed
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
  `secrets.compare_digest`. An empty secret does **not** make request handling fail — it
  only logs a warning (SEC-04), so close the perimeter at the network level.
- **Firewall**: port `8646` must not be reachable from outside. Allow inbound 443 to the
  reverse proxy only; deny the rest.
- **Built-in rate limiting** for the webhook is 30 requests / 10 seconds per IP, in
  process memory: it resets on restart and does not distinguish clients behind a proxy.
  It guards against bursts, not against a targeted attack.
- **`/health`** is served without authentication and only proves the process is up (not
  readiness to process messages, see CODE-05).

## What is implemented — and how well it was verified

| Protection | State | Limitation |
|---|---|---|
| User allowlist | S | an empty list does not close access (SEC-05/SEC-06) |
| Inbound media URL validation (`_validate_download_url`) | S | rejects non-http(s) schemes, literal private/loopback/link-local/reserved/multicast/unspecified IPs, `localhost`, `*.local`; **host names that are not literal IPs are accepted without any DNS check**, so a private address behind DNS is not filtered (SEC-03) |
| Host allowlist for **outbound** uploads | S | applies to sending media to MAX (`*.max.ru`, `*.oneme.ru`, `*.cdn-max.ru`), not to inbound URLs |
| Redirects on media downloads | S | the HTTP client is created with `follow_redirects=False`; the `Authorization` header is still sent to the original attachment URL (SEC-02) |
| Constant-time secret comparison | S | `secrets.compare_digest` |
| Cache directory permissions | S | the audio cache and the PNG table directory are created with `mode=0o700` (the effective mode is limited by umask); per-file permissions are not set explicitly |
| Log sanitization | S | userinfo and query strings are stripped from URLs (`_safe_url_for_log`) and the token itself is never logged; there is no guarantee that third-party exception texts contain no secrets |
| Incoming media limits | S | 50 MB applies to **uploads**; a GET response body is buffered whole, with no streaming cap and no overall deadline (SEC-07) |
| CI checks | S | `.github/workflows/ci.yml` runs ruff, pytest, bandit and pip-audit, but ruff/bandit cover `adapter.py`, `tests/`, `scripts/` and **not `mixins/`**; triggering is limited to push/PR on `main`; actual execution on the hosting runner is unverified |

## Known issues (open at the time of writing)

Full statements and acceptance criteria: `BACKLOG.md` (branch `docs/audit-backlog`, commit `abd2f0f`).

| ID | Security impact |
|---|---|
| SEC-01 | a dangerous-command approval in a group can be clicked by another participant (a nonempty user_id suffices) |
| SEC-02 | the bot token is sent to an arbitrary attachment URL contained in an event |
| SEC-03 | media downloads are SSRF-prone through DNS: private addresses behind a host name are not checked |
| SEC-04 | a secretless webhook does not refuse processing; `user_id` is taken from the request JSON |
| SEC-05 | access to global `/sessions` and `/resume` leaks titles and previews of sessions from all platforms |
| SEC-06 | group list semantics: an empty list allows, lists combine with OR |
| SEC-07 | no limit on the size or duration of incoming media (whole response buffered) |

Until these are closed, use the plugin as follows:

- **acceptable**: single-owner personal use, long polling, allowlist populated,
  `MAX_CROSS_SESSION=false`, no public webhook;
- **not acceptable**: a public webhook without a secret and firewall, a shared chat/group
  with access to dangerous tools, or the bot as a shared service for several owners.

## Cache, data, logs

| Object | Location | What to consider |
|---|---|---|
| Audio cache | `$HERMES_HOME/audio_cache` (`~/.hermes/audio_cache`), directory `0o700` | voice messages stay until removed manually; this is private data |
| PNG tables | `~/.hermes/table_images/` | render cache whose key includes the engine |
| Message dedup | process memory (5 minutes) | not persistent, resets on restart |
| Sessions | Hermes core (SessionDB) | `/sessions` bypasses the platform filter when `MAX_CROSS_SESSION=true` (SEC-05) |
| Logs | Hermes gateway log | URLs are logged without query and userinfo; message content is not redacted |
| Network | MAX API + PyPI (when Playwright auto-install is on) | the plugin makes no network calls other than the MAX API and dependency downloads |

## Audits performed: date, commit, scope

| Date | Commit | Scope | What it proves |
|---|---|---|---|
| 2026-07-17 | `e87ee64` | fixes for 10 vulnerabilities from a "full audit" (adapter.py and related code) | that the issues listed in that report were fixed; the report itself is not preserved in the repository |
| 2026-07-17 | `6e0f77a`, `beb4af2` | STT pipeline, README Security section, CHANGELOG v2.1.1 | accompanying changes |
| 2026-07-18 | `70eb490`, `d9626b5` | 5 remaining MEDIUM/LOW fixes, `nosec B104` annotation for bind-all | targeted fixes |
| 2026-08-17 | `e632014` | downloads no longer follow redirects, SSRF guard for inbound URLs, warning on an empty secret, 11 tests | current download behaviour |
| 2026-09-15 | `abd2f0f` | audit backlog of baseline `b004c573`: 7 SEC (open), 8 CODE, 4 BUILD, 10 DOC | the list of known issues; contains no fixes |
| 2026-09-16 | DOC-05 (this document) | documentation aligned with the code | documentation accuracy only; no code changed |

Full `pytest`, Ruff, Bandit and pip-audit were **not run** at audit time (batch execution
was not approved) and no real MAX E2E was performed.

## Disclaimer

- Neither this document nor any past audit is a guarantee that no vulnerabilities exist.
- The "implemented protections" above were verified statically and partially with mocks —
  not by a complete test suite or an external audit.
- Ingress, secrets, firewall, host access and the contents of `.env` remain the
  responsibility of the deployment owner.
- Do not use the plugin in a public or multi-user deployment until SEC-01…07 are closed.
