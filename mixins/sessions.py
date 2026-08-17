from __future__ import annotations

import logging

from .base import MaxBaseMixin

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────

MAX_MESSAGE_LENGTH = 4000


class SessionsMixin(MaxBaseMixin):
    """
    Mixin for cross-platform session commands (/sessions, /resume).

    Lists sessions from ALL platforms (CLI, Telegram, Discord, WebUI...)
    directly from MAX, bypassing the core gateway's per-platform scoping.
    """

    async def _handle_cross_sessions(self, text: str, chat_id: str) -> None:
        """Handle /sessions and /resume (no-arg) — list sessions from ALL platforms.

        Bypasses the core gateway's per-platform scoping so the user can see
        CLI, Telegram, Discord, WebUI and other sessions directly from MAX.
        """
        try:
            from hermes_state import SessionDB
        except ImportError:
            await self.send(chat_id, "⚠️ Session store not available")
            return

        args = text[len('/sessions'):].strip()
        search = None
        if args.lower().startswith('search '):
            search = args[6:].strip()
            if not search:
                await self.send(chat_id, "Usage: `/sessions search <query>`")
                return

        db = SessionDB()

        try:
            if search:
                rows = db.list_sessions_rich(
                    limit=20,
                    include_archived=False,
                    order_by_last_active=True,
                    search_query=search,
                )
            else:
                rows = db.list_sessions_rich(
                    limit=15,
                    include_archived=False,
                    order_by_last_active=True,
                )
        except Exception as e:
            logger.warning("MAX: SessionDB query failed: %s", e)
            await self.send(chat_id, f"⚠️ Failed to query sessions: {e}")
            return

        if not rows:
            await self.send(chat_id, "📭 **No sessions found**")
            return

        # Emoji map for known sources
        source_emoji = {
            'cli': '💻', 'telegram': '📱', 'max': '🟣',
            'discord': '🎮', 'webui': '🌐', 'api_server': '🔌',
            'cron': '⏰', 'slack': '💬', 'matrix': '🧩',
        }

        max_preview = 45

        if search:
            header = f"🔍 **Sessions matching \"{search}\":**"
        else:
            header = f"📋 **Recent Sessions** (all platforms):"

        lines = [header]
        for i, s in enumerate(rows[:15], 1):
            source = str(s.get('source', '') or '?')
            emoji = source_emoji.get(source, '📄')
            title = str(s.get('title') or '').strip() or '(unnamed)'
            sid = str(s.get('id', ''))[:12]
            preview = str(s.get('preview', '') or '')[:max_preview].replace('\n', ' ').strip()
            lines.append(
                f"{i}. {emoji} **{source}** — {title[:40]}"
            )
            if preview:
                lines.append(f"   _{preview}..._")
            lines.append(f"   `{sid}...`")

        total = len(rows)
        if total > 15:
            lines.append(f"\n...and {total - 15} more sessions")

        msg = '\n'.join(lines)

        # MAX has 4000 char limit — chunk if needed
        if len(msg) > MAX_MESSAGE_LENGTH - 100:
            msg = '\n'.join(lines[:1] + lines[1:11])  # Keep header + first 10
            msg += f'\n\n...truncated ({total} total)'

        await self.send(chat_id, msg)
        await self.send(
            chat_id,
            "`/resume <id>` — переключиться на сессию\n"
            "`/sessions search <query>` — поиск по сессиям"
        )
