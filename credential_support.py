"""MAX credential reads through the active Hermes profile secret scope."""

import os


def get_max_secret(name: str, legacy_default: str = "") -> str:
    """A bound profile is authoritative, including a missing credential.

    Older single-profile Core versions without secret scopes retain config/env
    support. Scope lookup errors are never disguised as missing credentials.
    """
    try:
        from agent.secret_scope import current_secret_scope
        from gateway.platforms._shared import get_scoped_secret
    except ImportError:
        return str(os.getenv(name) or legacy_default or "").strip()

    scope = current_secret_scope()
    if scope is not None:
        return str(scope.get(name) or "").strip()
    # Core's platform helper supports unscoped DEFAULT-profile startup under
    # multiplexing. Routed profiles have an authoritative installed scope above.
    value = get_scoped_secret(name)
    return str(value or legacy_default or "").strip()
