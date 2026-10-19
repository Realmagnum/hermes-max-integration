from __future__ import annotations

import asyncio
import logging
import re
import uuid
from datetime import UTC, datetime

from .base import MaxBaseMixin

logger = logging.getLogger(__name__)
MAX_MESSAGE_LENGTH = 4000
MAX_SESSIONS = 15
SEARCH_SESSIONS = 20
PICKER_TTL_SECONDS = 900.0
QUOTE_LIMIT = 96
CONTEXT_QUOTE_LIMIT = 280
SOURCE_EMOJI = {
    "cli": "💻", "telegram": "📱", "max": "🟣", "discord": "🎮",
    "webui": "🌐", "desktop": "🖥️", "api_server": "🔌", "cron": "⏰",
    "slack": "💬", "matrix": "🧩",
}


def _clean_text(value: object, limit: int) -> str:
    """Collapse whitespace and drop markdown controls in user-controlled text."""
    text = " ".join(str(value or "").split())
    text = re.sub(r"[_*`\\\[\]]", "", text)
    return text[:limit]


def _format_timestamp(value: object) -> str:
    try:
        if isinstance(value, (int, float)):
            dt = datetime.fromtimestamp(value, tz=UTC).astimezone()
        else:
            raw = str(value)
            dt = datetime.fromisoformat(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            dt = dt.astimezone()
        return dt.strftime("%Y/%m/%d %H:%M")
    except (TypeError, ValueError, OSError, OverflowError):
        return "время неизвестно"


class SessionsMixin(MaxBaseMixin):
    """Owner-only cross-platform session picker with context restoration."""

    def _session_picker_card(
        self, rows: list[dict], search: str | None = None, interaction_id: str = "",
    ) -> tuple[str, list[list[dict[str, str]]]]:
        rows = rows[:MAX_SESSIONS]
        header = (f"🔍 **Сессии по запросу «{_clean_text(search, 80)}»**" if search
                  else "📋 **Выбор сессии** (все платформы / all platforms):")
        lines = [header, ""]
        keyboard: list[list[dict[str, str]]] = []
        buttons: list[dict[str, str]] = []
        for index, session in enumerate(rows, 1):
            source = str(session.get("source") or "?")
            emoji = SOURCE_EMOJI.get(source, "📄")
            title = _clean_text(session.get("title") or "(без названия)", 60)
            raw_quote = " ".join(str(session.get("preview") or "").split())
            quote = _clean_text(raw_quote, QUOTE_LIMIT)
            stamp = _format_timestamp(session.get("last_active") or session.get("started_at"))
            sid = str(session.get("id") or "")[:12]
            try:
                count = int(session.get("message_count") or 0)
            except (ValueError, TypeError):
                count = 0
            lines.append(f"**{index}.** {emoji} **{_clean_text(source, 20)}** — {title}")
            if quote:
                suffix = "…" if len(raw_quote) > QUOTE_LIMIT else ""
                lines.append(f"   _«{quote}{suffix}»_")
            lines.append(f"   🕒 `{stamp}` • 💬 {count} сообщ.")
            if sid:
                lines.append(f"   `{sid}...`")
            lines.append("")
            buttons.append({
                "type": "callback", "text": f"{emoji} {index}",
                "payload": f"session:{interaction_id}:pick:{index}",
            })
            if len(buttons) == 5:
                keyboard.append(buttons)
                buttons = []
        if buttons:
            keyboard.append(buttons)
        keyboard.append([
            {"type": "callback", "text": "🔄 Обновить",
             "payload": f"session:{interaction_id}:refresh"},
            {"type": "callback", "text": "❌ Отмена",
             "payload": f"session:{interaction_id}:cancel"},
        ])
        lines.append("Нажмите кнопку с номером нужной сессии.")
        text = "\n".join(lines)
        if len(text) > MAX_MESSAGE_LENGTH - 100:
            text = text[:MAX_MESSAGE_LENGTH - 120] + "…"
        return text, keyboard

    @staticmethod
    def _query_sessions(search: str | None) -> list[dict]:
        from hermes_state import SessionDB

        kwargs: dict = {
            "limit": SEARCH_SESSIONS if search else MAX_SESSIONS,
            "include_archived": False,
            "order_by_last_active": True,
        }
        if search:
            kwargs["search_query"] = search
        return SessionDB().list_sessions_rich(**kwargs)

    @staticmethod
    def _session_context(session_id: str) -> tuple[str, str, str]:
        """Return (first user message, latest user/assistant message and role)."""
        from hermes_state import SessionDB

        first = last = role = ""
        try:
            messages = SessionDB().get_messages(session_id, include_ancestors=True)
        except Exception:  # noqa: BLE001 — context reminder is best-effort
            return first, last, role
        for message in messages:
            content = message.get("content")
            if not isinstance(content, str) or not content.strip():
                continue
            msg_role = str(message.get("role") or "")
            if msg_role == "user" and not first:
                first = content
            if msg_role in {"user", "assistant"}:
                last, role = content, msg_role
        return first, last, role

    async def _handle_cross_sessions(
        self, text: str, chat_id: str, user_id: str = "",
    ) -> None:
        """Handle /sessions and /resume (no-arg) with an owner-only picker."""
        if not self._cross_session_allowed(user_id):
            logger.warning("MAX: cross-session request denied: user=%r chat=%r", user_id, chat_id)
            return
        args = text[len("/sessions"):].strip()
        search: str | None = None
        if args.lower() == "search" or args.lower().startswith("search "):
            search = args[6:].strip()
            if not search:
                await self.send(chat_id, "Usage: `/sessions search <query>`")
                return
        try:
            rows = await asyncio.to_thread(self._query_sessions, search)
        except ImportError:
            await self.send(chat_id, "⚠️ Session store not available")
            return
        except Exception as exc:  # noqa: BLE001 — adapter must not crash on store errors
            logger.warning("MAX: SessionDB query failed: %s", exc)
            await self.send(chat_id, "⚠️ Не удалось получить список сессий.")
            return
        if not rows:
            await self.send(chat_id, "📭 **Сессии не найдены** (No sessions found)")
            return
        await self._post_session_picker(chat_id, user_id, rows, search)

    async def _post_session_picker(
        self, chat_id: str, user_id: str, rows: list[dict], search: str | None,
    ) -> dict | None:
        interaction_id = uuid.uuid4().hex[:12]
        body, keyboard = self._session_picker_card(rows, search, interaction_id)
        result = await self._post_interactive(chat_id, body, keyboard)
        if not result.success or not result.message_id:
            await self.send(chat_id, body)
            await self.send(
                chat_id,
                "`/resume <id>` — переключиться на сессию\n"
                "`/sessions search <query>` — поиск по сессиям",
            )
            return None
        record = self._register_interaction(
            "session", interaction_id,
            owner_user_id=str(user_id), chat_id=chat_id, message_id=result.message_id,
            ttl=PICKER_TTL_SECONDS,
        )
        record["rows"] = rows[:MAX_SESSIONS]
        record["search"] = search
        return record

    async def _handle_session_callback(
        self, data: str, user_id: str, scoped_chat: str, message_id: str = "",
    ):
        """Handle session pick, refresh and cancel via SEC-01-bound state."""
        parts = data.split(":")
        if len(parts) < 3 or not self._cross_session_allowed(user_id):
            return None
        interaction_id, action = parts[1], parts[2]
        pending = self._session_picker_state.get(interaction_id)
        if not pending or not message_id:
            return None
        index = 0
        if action == "pick":
            if len(parts) != 4 or not parts[3].isdigit():
                return None
            index = int(parts[3])
            if not 1 <= index <= len(pending.get("rows") or []):
                return None
        elif action not in {"refresh", "cancel"}:
            return None
        record, _reason = self._consume_interaction(
            "session", interaction_id,
            user_id=user_id, chat_id=scoped_chat, message_id=message_id,
        )
        if record is None:
            return None

        if action == "cancel":
            await self._remove_picker_message(scoped_chat, message_id, "❌ Выбор сессии отменён")
            return None
        if action == "refresh":
            search = record.get("search")
            try:
                fresh = await asyncio.to_thread(self._query_sessions, search)
            except Exception as exc:  # noqa: BLE001 — adapter must not crash
                logger.warning("MAX: session refresh failed: %s", exc)
                fresh = []
            await self._remove_picker_message(scoped_chat, message_id, "🔄 Обновление…")
            if fresh:
                await self._post_session_picker(scoped_chat, user_id, fresh, search)
            else:
                await self.send(scoped_chat, "📭 **Сессии не найдены**")
            return None

        row = record["rows"][index - 1]
        session_id = str(row.get("id") or "")
        if not session_id:
            return None
        try:
            first, last, role = await asyncio.to_thread(self._session_context, session_id)
        except Exception as exc:  # noqa: BLE001 — context reminder is best-effort
            logger.debug("MAX: session context unavailable: %s", exc)
            first = last = role = ""
        await self._remove_picker_message(scoped_chat, message_id, "")
        event = self._session_resume_event(scoped_chat, user_id, session_id, interaction_id)

        try:
            session_key = self._source_session_key(event.source)
        except Exception:  # noqa: BLE001 — callbacks must fail safely on source conversion errors
            session_key = ""

        confirmation = self._session_confirmation(row, first, last, role)
        if session_key and hasattr(self, "register_post_delivery_callback"):
            async def _post_card() -> None:
                await self.send(scoped_chat, confirmation)

            self.register_post_delivery_callback(session_key, _post_card)
            event._max_session_confirmation = confirmation
        else:
            await self.send(scoped_chat, confirmation)
        return event

    async def _remove_picker_message(self, chat_id: str, message_id: str, fallback: str) -> None:
        """Delete picker; if MAX refuses deletion, neutralise it by editing text."""
        result = await self.delete_message(chat_id, message_id)
        if not getattr(result, "success", False) and fallback:
            await self.edit_message(chat_id, message_id, fallback, finalize=True)

    def _session_confirmation(self, row: dict, first: str, last: str, role: str) -> str:
        source = str(row.get("source") or "?")
        emoji = SOURCE_EMOJI.get(source, "📄")
        title = _clean_text(row.get("title") or "(без названия)", 80)
        stamp = _format_timestamp(row.get("last_active") or row.get("started_at"))
        lines = [
            f"✅ **Активная сессия:** {emoji} {title}",
            f"🕒 `{stamp}` • источник: **{_clean_text(source, 20)}**",
        ]
        if first:
            lines.append(f"\n📌 **Задача:** _«{_clean_text(first, CONTEXT_QUOTE_LIMIT)}»_")
        if last and last != first:
            who = "🤖" if role == "assistant" else "👤"
            lines.append(f"\n{who} **Последнее:** _«{_clean_text(last, CONTEXT_QUOTE_LIMIT)}»_")
        return "\n".join(lines)[:MAX_MESSAGE_LENGTH]

    def _session_resume_event(
        self, scoped_chat: str, user_id: str, session_id: str, interaction_id: str,
    ):
        """Build the internal command that Core routes through normal /resume policy."""
        from gateway.platforms.base import MessageEvent, MessageType

        chat_type = "dm" if scoped_chat.startswith("user:") else "group"
        source = self.build_source(
            chat_id=scoped_chat, chat_name=scoped_chat, chat_type=chat_type,
            user_id=str(user_id), user_name=str(user_id),
        )
        return MessageEvent(
            text=f"/resume --all {session_id}", message_type=MessageType.TEXT,
            source=source, message_id=f"session_pick_{interaction_id}",
        )
