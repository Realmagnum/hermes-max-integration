from __future__ import annotations

import asyncio
import logging
import re
import uuid
from datetime import UTC, datetime

from .base import MaxBaseMixin

logger = logging.getLogger(__name__)
MAX_MESSAGE_LENGTH = 4000
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
        *, include_all: bool = True, limit: int | None = None,
    ) -> tuple[str, list[list[dict[str, str]]]]:
        rows = rows[:self._sessions_limit if limit is None else limit]
        header = (f"🔍 **Сессии по запросу «{_clean_text(search, 80)}»**" if search
                  else ("📋 **Выбор сессии** (все платформы / all platforms):" if include_all
                        else "📋 **Выбор сессии** (только MAX):"))
        lines = [header, ""]
        keyboard: list[list[dict[str, str]]] = []
        buttons: list[dict[str, str]] = []
        item_budget = (MAX_MESSAGE_LENGTH - 550) // max(1, len(rows))
        title_limit = min(60, max(16, item_budget // 4))
        quote_limit = min(QUOTE_LIMIT, max(0, item_budget - 160))
        for index, session in enumerate(rows, 1):
            source = str(session.get("source") or "?")
            emoji = SOURCE_EMOJI.get(source, "📄")
            title = _clean_text(session.get("title") or "(без названия)", title_limit)
            raw_quote = " ".join(str(session.get("preview") or "").split())
            quote = _clean_text(raw_quote, quote_limit)
            stamp = _format_timestamp(session.get("last_active") or session.get("started_at"))
            sid = str(session.get("id") or "")[:12]
            try:
                count = int(session.get("message_count") or 0)
            except (ValueError, TypeError):
                count = 0
            lines.append(f"**{index}.** {emoji} **{_clean_text(source, 20)}** — {title}")
            if quote:
                suffix = "…" if len(raw_quote) > quote_limit else ""
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
        lines.append("`/resume <id>` — переключиться • `/sessions all` — все платформы")
        lines.append("`/sessions search <query>` — поиск по сессиям")
        text = "\n".join(lines)
        return text, keyboard

    @staticmethod
    def _query_sessions(search: str | None, include_all: bool = False, limit: int = 10) -> list[dict]:
        from hermes_state import SessionDB

        kwargs: dict = {
            "limit": limit,
            "include_archived": False,
            "order_by_last_active": True,
        }
        if search:
            kwargs["search_query"] = search
        if not include_all and not search:
            kwargs["source"] = "max"
        db = SessionDB()
        try:
            return db.list_sessions_rich(**kwargs)[:limit]
        finally:
            db.close()

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

    async def _handle_cross_sessions(self, text: str, chat_id: str, user_id: str = "") -> None:
        """Handle /sessions and /resume (no-arg) with an owner‑only picker.
        Supports:
        - `/sessions` → only MAX platform sessions.
        - `/sessions all` → all platforms.
        - `/sessions search <query>` → search across all platforms.
        """
        if not self._cross_session_allowed(user_id):
            logger.warning("MAX: cross-session request denied: user=%r chat=%r", user_id, chat_id)
            return
        parts = text.split(maxsplit=1)
        args = parts[1].strip() if len(parts) > 1 else ""
        mode_parts = args.split(maxsplit=1)
        mode = mode_parts[0] if mode_parts else ""
        query = mode_parts[1] if len(mode_parts) > 1 else ""
        mode = mode.lower()
        search = query.strip() if mode == "search" else None
        if not parts or parts[0] != "/sessions" or mode not in {"", "max", "all", "search"} or (mode == "search" and not search) or (mode in {"all", "max"} and query):
            await self.send(chat_id, "Usage: `/sessions [max|all]` or `/sessions search <query>`; `/resume <id>`")
            return
        include_all = mode in {"all", "search"} or (not mode and self._sessions_default_all)
        limit = self._sessions_limit
        try:
            rows = await asyncio.to_thread(self._query_sessions, search, include_all=include_all, limit=limit)
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
        await self._post_session_picker(chat_id, user_id, rows, search, include_all=include_all, limit=limit)

    async def _post_session_picker(
        self, chat_id: str, user_id: str, rows: list[dict], search: str | None,
        include_all: bool = False, limit: int | None = None,
    ) -> dict | None:
        interaction_id = uuid.uuid4().hex[:12]
        limit = self._sessions_limit if limit is None else limit
        rows = rows[:limit]
        body, keyboard = self._session_picker_card(rows, search, interaction_id, include_all=include_all, limit=limit)
        result = await self._post_interactive(chat_id, body, keyboard)
        if not result.success or not result.message_id:
            await self.send(chat_id, body)
            return None
        record = self._register_interaction(
            "session", interaction_id,
            owner_user_id=str(user_id), chat_id=chat_id, message_id=result.message_id,
            ttl=PICKER_TTL_SECONDS,
        )
        record["rows"] = rows
        record["limit"] = limit
        record["search"] = search
        record["include_all"] = include_all or bool(search)
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
        elif action not in {"refresh", "cancel"} or len(parts) != 3:
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
                fresh = await asyncio.to_thread(
                    self._query_sessions, search, include_all=bool(record.get("include_all")),
                    limit=record.get("limit", self._sessions_limit),
                )
            except Exception as exc:  # noqa: BLE001 — adapter must not crash
                logger.warning("MAX: session refresh failed: %s", exc)
                await self._remove_picker_message(scoped_chat, message_id, "⚠️ Не удалось обновить список сессий.")
                await self.send(scoped_chat, "⚠️ Не удалось обновить список сессий. Повторите /sessions.")
                return None
            await self._remove_picker_message(scoped_chat, message_id, "🔄 Обновление…")
            if fresh:
                await self._post_session_picker(scoped_chat, user_id, fresh, search,
                                                include_all=bool(record.get("include_all")),
                                                limit=record.get("limit", self._sessions_limit))
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
        await self._remove_picker_message(scoped_chat, message_id, "✅ Сессия выбрана")
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
