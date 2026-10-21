# Max plugin installed

## Next steps

1. Install runtime dependencies into the same Python environment used by Hermes Gateway. Use the current `pyproject.toml` and Hermes installation instructions; do not assume the host `pip` targets the gateway environment.
2. Run `hermes gateway setup` and configure the MAX platform. Store `MAX_BOT_TOKEN` in the protected Hermes `.env` or secret manager; never paste secret values into shell arguments, docs, logs, or chat.
3. Voice transcription is performed by Hermes Core. Configure STT in the Core settings; this plugin only delivers/caches audio for Core.
4. Choose the delivery mode. Polling is the default. Webhook requires public HTTPS, the configured URL, and a matching secret. Before switching, inspect existing MAX subscriptions because startup in polling mode may remove them.
5. Restarting the gateway or modifying subscriptions has external effects; obtain approval before doing so.
6. Verify with `hermes gateway status` and the local health endpoint. `scripts/diagnose.sh --send` sends a real message and requires an approved recipient.

See `docs/setup.md`, `docs/security.md`, and `docs/troubleshooting.md` for current details. Official MAX references and last-checked dates are tracked in `docs/external-claims.md`.

## Owner session picker

Despite its name, `MAX_CROSS_SESSION=true` also enables the MAX-only button picker. Configure `MAX_CROSS_SESSION_USERS` explicitly. When disabled or when the caller is not an owner, `/sessions` and `/resume` remain Core commands without plugin buttons. A closed bot may use its user allowlist as the owner fallback; `MAX_ALLOW_ALL_USERS=true` disables that fallback. Never grant cross-platform history access to every visitor.

After configuration and an authorized restart, use the gateway Python and active profile:

```bash
python scripts/check-session-routing.py --user-id OWNER_MAX_USER_ID --load-profile-env
```

Replace the placeholder with your ID. Expect JSON `handler=plugin`, `reason=owner_picker_ready`, `dispatch_matches_policy=true`, exit 0. The check sends no messages and reads no history; health and import are insufficient. Then verify `/sessions` and buttons manually in MAX. See [diagnostics](docs/troubleshooting.md).
