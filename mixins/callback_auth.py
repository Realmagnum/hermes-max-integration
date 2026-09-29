"""Owner-bound authorization for interactive callback buttons (SEC-01).

MAX inline-keyboard callbacks carry only the *presser* identity, so before
this module existed any member of a group could press "Approve Always" on
somebody else's dangerous-command prompt: the handler trusted the callback's
``user_id`` to be nonempty, popped the pending state by id and called the
gateway resolver with the *owner's* session key.

Every pending prompt is therefore stored as a *bound* record:

  * ``owner_user_id`` — the user who caused the prompt (derived from the
    session that ran the turn / the DM scope);
  * ``chat_id``       — the scoped chat the prompt was rendered in;
  * ``message_id``    — the id of the prompt message the buttons live on;
  * ``expires_at``    — monotonic deadline (TTL), so a stale button cannot be
    replayed later.

``_consume_interaction`` is the single authorization gate: it resolves the
record, refuses presses from anyone but the owner (or from a different chat /
message), and only then pops it. Refusals deliberately leave the record in
place — the legitimate owner must still be able to use their own buttons
while a stranger cannot.

Ownership is learned from inbound traffic (``_remember_interaction_owner``)
because the gateway does not hand the requesting user to outbound prompts:
approval/clarify/picker sends receive only a session key and a scoped chat id.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from .base import MaxBaseMixin

logger = logging.getLogger(__name__)

#: Interaction kinds that keep bound state in ``_pending_interactions``.
INTERACTION_KINDS = ("exec", "sc", "clarify")

#: How long a prompt's buttons stay usable. Nothing legitimate resolves an
#: approval/clarify card after this window; keeping state forever just widens
#: the window in which a leaked or replayed button still works.
CALLBACK_TTL_SECONDS = 900.0


class CallbackAuthMixin(MaxBaseMixin):
    """Bound-state registry plus the shared callback authorization gate."""

    def _init_callback_auth(
        self,
        *,
        ttl: float | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._callback_ttl = CALLBACK_TTL_SECONDS if ttl is None else float(ttl)
        # Monotonic clock: TTLs must not be affected by wall-clock jumps.
        self._callback_clock: Callable[[], float] = clock or time.monotonic
        # kind -> interaction_id -> bound record. Aliased below as
        # _exec_approval_state / _slash_confirm_state / _clarify_state so the
        # familiar names keep working for introspection.
        self._pending_interactions: dict[str, dict[str, dict[str, Any]]] = {
            kind: {} for kind in INTERACTION_KINDS
        }
        self._exec_approval_state = self._pending_interactions["exec"]
        self._slash_confirm_state = self._pending_interactions["sc"]
        self._clarify_state = self._pending_interactions["clarify"]
        # session_key -> owner user id, learned from inbound messages.
        self._session_owners: dict[str, str] = {}
        # scoped chat id -> last inbound sender (group fallback when the
        # session key learned here and the key passed to an outbound prompt
        # disagree, e.g. when core runs with different session-key flags).
        self._chat_requesters: dict[str, str] = {}

    # ── ownership discovery ──────────────────────────────────────────────

    def _remember_interaction_owner(
        self, *, session_key: str, chat_id: str, user_id: str
    ) -> None:
        """Record who owns a conversation, from an inbound message."""
        if session_key:
            self._session_owners[session_key] = str(user_id)
        if chat_id:
            self._chat_requesters[str(chat_id)] = str(user_id)

    @staticmethod
    def _owner_from_scoped_chat(chat_id: str) -> str:
        """DMs are scoped as ``user:<id>`` — the scope *is* the owner."""
        scope, _, value = str(chat_id or "").partition(":")
        return value if scope == "user" else ""

    def _resolve_interaction_owner(
        self, session_key: str = "", chat_id: str = "", metadata: dict | None = None
    ) -> str:
        """Best-effort owner user id for an outbound prompt.

        Order: an explicit hint in ``metadata`` → the session owner learned
        from inbound traffic → the DM scope → the last sender seen in the
        chat. Returns ``""`` when nothing is known; a record with no owner is
        refused by the gate rather than trusted.
        """
        meta = metadata or {}
        for key in ("recipient_user_id", "user_id"):
            hint = str(meta.get(key) or "").strip()
            if hint:
                return hint
        if session_key and session_key in self._session_owners:
            return self._session_owners[session_key]
        owner = self._owner_from_scoped_chat(chat_id)
        if owner:
            return owner
        return self._chat_requesters.get(str(chat_id or ""), "")

    # ── state registration ───────────────────────────────────────────────

    def _prune_expired(self, kind: str | None = None) -> None:
        now = self._callback_clock()
        kinds = [kind] if kind else list(self._pending_interactions)
        for name in kinds:
            store = self._pending_interactions.get(name) or {}
            for key, record in list(store.items()):
                if now >= float(record.get("expires_at") or 0.0):
                    store.pop(key, None)

    def _register_interaction(
        self,
        kind: str,
        interaction_id: str,
        *,
        owner_user_id: str = "",
        chat_id: str = "",
        message_id: str = "",
        session_key: str = "",
        ttl: float | None = None,
        supersede: bool = True,
    ) -> dict[str, Any]:
        """Bind a freshly rendered prompt to its owner, chat and message.

        ``supersede`` drops earlier pending prompts of the same kind for the
        same owner+chat: their buttons are stale by definition, and dropping
        the records makes those buttons unable to resolve anything even when
        the client does not echo a message id.
        """
        store = self._pending_interactions.setdefault(kind, {})
        self._prune_expired(kind)
        owner = str(owner_user_id or "")
        chat = str(chat_id or "")
        if supersede:
            for key in [
                k
                for k, record in store.items()
                if k != interaction_id
                and str(record.get("owner_user_id") or "") == owner
                and str(record.get("chat_id") or "") == chat
            ]:
                store.pop(key, None)
                logger.info("MAX: superseded stale %s interaction %s", kind, key)
        now = self._callback_clock()
        record = {
            "kind": kind,
            "session_key": session_key,
            "owner_user_id": owner,
            "chat_id": chat,
            "message_id": str(message_id or ""),
            "created_at": now,
            "expires_at": now + (self._callback_ttl if ttl is None else float(ttl)),
        }
        store[interaction_id] = record
        if not owner:
            logger.warning(
                "MAX: %s interaction %s registered without an owner — "
                "its buttons will be refused", kind, interaction_id,
            )
        return record

    # ── authorization gate ───────────────────────────────────────────────

    def _is_callback_user_allowed(self, user_id: str) -> bool:
        """Mirror the inbound-message allowlist check.

        NOTE: the empty-allowlist semantics of the message path (an empty
        ``allowed_users`` currently opens access) are a separate finding
        (SEC-06) — this helper only reuses the existing rule so callbacks are
        never *weaker* than ordinary messages.
        """
        if getattr(self, "_allow_all_users", False):
            return True
        allowed = getattr(self, "_allowed_users_set", None) or set()
        return not allowed or str(user_id) in allowed

    def _interaction_deny_reason(
        self,
        record: dict[str, Any],
        *,
        user_id: str,
        chat_id: str = "",
        message_id: str = "",
    ) -> str:
        """Return why ``record`` must not be resolved by this press, or ""."""
        owner = str(record.get("owner_user_id") or "")
        if not owner:
            return "unbound interaction (owner unknown)"
        if str(user_id) != owner:
            return f"user {user_id} is not the owner ({owner})"
        bound_chat = str(record.get("chat_id") or "")
        if bound_chat and chat_id and bound_chat != str(chat_id):
            return f"chat {chat_id} does not match bound chat {bound_chat}"
        bound_mid = str(record.get("message_id") or "")
        # Some transports/tests do not echo the outbound message id. In that
        # case owner+scope remain enforceable; an echoed id must match.
        if bound_mid and message_id and bound_mid != str(message_id):
            return "stale button (message id mismatch)"
        return ""

    def _consume_interaction(
        self,
        kind: str,
        interaction_id: str,
        *,
        user_id: str,
        chat_id: str = "",
        message_id: str = "",
    ) -> tuple[dict[str, Any] | None, str]:
        """Authorize and consume a pending interaction.

        Returns ``(record, "")`` only for the owner pressing their own live
        button; the record is popped exactly in that case. Any other outcome
        returns ``(None, reason)`` with ``reason`` in ``unknown``, ``expired``
        or the deny reason — and leaves the record untouched, so a refused
        press cannot destroy the owner's pending prompt.
        """
        store = self._pending_interactions.get(kind) or {}
        record = store.get(interaction_id)
        if record is None:
            return None, "unknown"
        if not isinstance(record, dict):
            # Pre-SEC-01 shape (a bare session key) or foreign writer: it
            # carries no owner, so it must never authorize anything.
            store.pop(interaction_id, None)
            logger.warning(
                "MAX: dropping unbound %s interaction %s (legacy state shape)",
                kind, interaction_id,
            )
            return None, "unknown"
        now = self._callback_clock()
        if now >= float(record.get("expires_at") or 0.0):
            store.pop(interaction_id, None)
            logger.warning("MAX: expired %s interaction %s — dropped", kind, interaction_id)
            return None, "expired"
        reason = self._interaction_deny_reason(
            record, user_id=user_id, chat_id=chat_id, message_id=message_id
        )
        if reason:
            logger.warning(
                "MAX: refused %s callback %s from user=%s chat=%s: %s",
                kind, interaction_id, user_id, chat_id, reason,
            )
            return None, reason
        store.pop(interaction_id, None)
        return record, ""
