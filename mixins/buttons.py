from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

import httpx
from gateway.platforms.base import SendResult

from .base import MaxBaseMixin

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────

MAX_API_BASE = "https://platform-api.max.ru"
MAX_MESSAGE_LENGTH = 4000


class ButtonsMixin(MaxBaseMixin):
    """
    Mixin for interactive buttons and forms logic.

    Sending side of the inline-keyboard flow: chat actions, interactive
    posts, plain button rows, exec-approval / slash-confirm / clarify
    prompts. Callback PRESS handling stays in adapter.py (_on_callback).
    """

    async def send_typing(self, chat_id: str, metadata=None) -> None:
        """Send typing indicator (delegates to send_action)."""
        await self.send_action(chat_id, "typing")

    async def send_action(self, chat_id: str, action: str = "typing", metadata=None) -> None:
        """Send a chat action indicator. Best-effort (silent on failure).

        Supported actions (mapped to MAX API):
          typing / typing_on  — показать «печатает»
          typing_off          — скрыть «печатает»
          sending_photo       — отправляет фото
          sending_video       — отправляет видео
          sending_audio       — отправляет аудио
          sending_file        — отправляет файл
          read                — отметить как прочитано

        Args:
            chat_id: Scoped chat ID (e.g. 'chat:123' or 'user:456').
            action: Action type string from the list above.
            metadata: Optional platform-specific context (ignored for MAX).
        """
        if not self._http_client:
            return

        # Normalise action name to MAX API format
        action_map = {
            "typing": "typing_on",
            "typing_on": "typing_on",
            "typing_off": "typing_off",
            "sending_photo": "sending_photo",
            "sending_video": "sending_video",
            "sending_audio": "sending_audio",
            "sending_file": "sending_file",
            "read": "read",
        }
        api_action = action_map.get(action.lower().strip(), "typing_on")

        parts = chat_id.split(":", 1)
        target_id = parts[1] if len(parts) > 1 else chat_id

        try:
            await self._http_client.post(
                f"{MAX_API_BASE}/chats/{target_id}/actions",
                json={"action": api_action},
                timeout=httpx.Timeout(3.0),
            )
        except Exception:
            pass

    async def _post_interactive(
        self, chat_id: str, text: str, buttons: List[List[Dict[str, str]]],
        reply_to: Optional[str] = None,
    ) -> SendResult:
        """Send a message with inline keyboard buttons.

        MAX inline_keyboard format:
          attachments: [{
            type: "inline_keyboard",
            payload: { buttons: [[{type: "callback", text: "...", payload: "..."}]] }
          }]
        """
        if not self._http_client:
            return SendResult(success=False, error="Not connected")

        parts = chat_id.split(":", 1)
        target_type = parts[0] if len(parts) > 1 else "user"
        target_id = parts[1] if len(parts) > 1 else chat_id
        params = {"chat_id": target_id} if target_type == "chat" else {"user_id": target_id}

        body: Dict[str, Any] = {
            "text": text[:MAX_MESSAGE_LENGTH],
            "format": "markdown",
            "attachments": [{
                "type": "inline_keyboard",
                "payload": {"buttons": buttons},
            }],
        }
        if reply_to:
            body["link"] = {"type": "REPLY", "mid": reply_to}

        try:
            resp = await self._http_client.post(
                f"{MAX_API_BASE}/messages", params=params, json=body,
            )
            resp.raise_for_status()
            d = resp.json()
            mid = str((d.get("message", {}).get("body", {}) or {}).get("mid", ""))
            return SendResult(success=True, message_id=mid, raw_response=d)
        except Exception as e:
            logger.error("MAX: interactive send failed: %s", e)
            return SendResult(success=False, error="Interactive send failed (see logs)")

    async def send_buttons(
        self, chat_id: str, text: str,
        buttons: List[Dict[str, str]],
        reply_to: Optional[str] = None,
    ) -> SendResult:
        """Send a message with inline buttons of ANY type.

        Reuses _post_interactive, which accepts all MAX button types.
        Each button dict may include an optional "label" key with the
        full description text for the fallback in the message body.
        If "label" is omitted, "text" is used for both.

          - callback  → {"type": "callback", "text": "...", "payload": "...", "label": "..."}
          - link      → {"type": "link", "text": "...", "url": "...", "label": "..."}
          - message   → {"type": "message", "text": "...", "payload": "...", "label": "..."}
          - request_contact → {"type": "request_contact", "text": "...", "label": "..."}
          - request_geo_location → {"type": "request_geo_location", "text": "...", "label": "..."}

        Features:
        - One button per row (full width)
        - Buttons auto-numbered when 3+
        - Button text duplicated in the message body as fallback
          (MAX mobile may truncate button text visually; the "label"
           field provides the full description that always stays readable)

        Example:
            await adapter.send_buttons(
                chat_id="chat:123",
                text="Выберите тариф:",
                buttons=[
                    {"type": "callback", "text": "Базовый", "label": "Базовый — 500₽/мес, 10GB", "payload": "basic"},
                    {"type": "callback", "text": "Стандарт", "label": "Стандарт — 1000₽/мес, 50GB", "payload": "std"},
                ],
            )
        """
        # Number buttons if 3+ for clarity
        numbered = len(buttons) >= 3

        # Build keyboard (one button per row)
        limited = buttons[:10]  # MAX API limit ~10 buttons per message
        keyboard: List[List[Dict[str, str]]] = []
        for i, btn in enumerate(limited, 1):
            b = dict(btn)
            # Remove label from the button payload (MAX API doesn't use it)
            b.pop("label", None)
            if numbered:
                prefix = f"{i}. "
                if not b.get("text", "").startswith(prefix):
                    b["text"] = f"{prefix}{b['text']}"
            keyboard.append([b])

        # Build fallback text from full labels (untruncated)
        fallback_lines: List[str] = []
        for i, btn in enumerate(limited, 1):
            desc = btn.get("label") or btn.get("text", "")
            if numbered:
                fallback_lines.append(f"{i}. {desc}")
            else:
                fallback_lines.append(f"• {desc}")
        fallback_text = "\n".join(fallback_lines)

        full_text = f"{text}\n\n{fallback_text}" if fallback_lines else text
        if len(full_text) > MAX_MESSAGE_LENGTH - 200:
            full_text = full_text[:MAX_MESSAGE_LENGTH - 200]

        return await self._post_interactive(chat_id, full_text, keyboard, reply_to=reply_to)

    async def send_exec_approval(
        self,
        chat_id: str,
        command: str,
        session_key: str,
        description: str = "dangerous command",
        metadata: Optional[Dict[str, Any]] = None,
        *args,
        **kwargs,
    ) -> SendResult:
        """Render a dangerous-command approval prompt with native buttons.

        Four buttons: Approve Once / Approve Session / Approve Always / Deny.
        Button callbacks route through _on_callback → resolve_gateway_approval.
        """
        if not self._http_client:
            return SendResult(success=False, error="Not connected")

        approval_id = uuid.uuid4().hex[:12]
        cmd_preview = (command or "")[:300] + "..." if len(command or "") > 300 else (command or "")

        text = (
            f"⚠️ **Command Approval Required**\n\n"
            f"```\n{cmd_preview}\n```\n\n"
            f"Reason: {description}"
        )

        reply_to = (metadata or {}).get("reply_to_message_id") if metadata else None

        buttons = [[
            {"type": "callback", "text": "✅ Approve Once", "payload": f"exec:once:{approval_id}"},
            {"type": "callback", "text": "🔄 Session", "payload": f"exec:session:{approval_id}"},
        ], [
            {"type": "callback", "text": "🔒 Always", "payload": f"exec:always:{approval_id}"},
            {"type": "callback", "text": "❌ Deny", "payload": f"exec:deny:{approval_id}"},
        ]]

        result = await self._post_interactive(chat_id, text, buttons, reply_to=reply_to)
        if result.success:
            self._exec_approval_state[approval_id] = session_key
        return result

    async def send_slash_confirm(
        self,
        chat_id: str,
        title: str,
        message: str,
        session_key: str,
        confirm_id: str,
        metadata: Optional[Dict[str, Any]] = None,
        *args,
        **kwargs,
    ) -> SendResult:
        """Render a 3-button slash-command confirmation prompt.

        Buttons: Approve Once / Always Approve / Cancel.
        Mirrors Telegram's send_slash_confirm.
        """
        if not self._http_client:
            return SendResult(success=False, error="Not connected")

        text = f"**{title}**\n\n{message}"[:MAX_MESSAGE_LENGTH]
        reply_to = (metadata or {}).get("reply_to_message_id") if metadata else None

        buttons = [[
            {"type": "callback", "text": "✅ Approve Once", "payload": f"sc:once:{confirm_id}"},
            {"type": "callback", "text": "🔒 Always", "payload": f"sc:always:{confirm_id}"},
            {"type": "callback", "text": "❌ Cancel", "payload": f"sc:cancel:{confirm_id}"},
        ]]

        result = await self._post_interactive(chat_id, text, buttons, reply_to=reply_to)
        if result.success:
            self._slash_confirm_state[confirm_id] = session_key
        return result

    async def send_clarify(
        self,
        chat_id: str,
        question: str,
        choices: Optional[list],
        clarify_id: str,
        session_key: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Send a clarify prompt with inline choice buttons.

        Each choice becomes a callback button. The last button is always
        "Other…" for free-text input.
        """
        if not self._http_client:
            return SendResult(success=False, error="Not connected")

        reply_to = (metadata or {}).get("reply_to_message_id") if metadata else None

        if choices and len(choices) > 0:
            # Render choice buttons (up to 3 per row)
            buttons: List[List[Dict[str, str]]] = []
            row: List[Dict[str, str]] = []
            for i, choice in enumerate(choices):
                btn_text = str(choice)[:40]
                if len(str(choice)) > 40:
                    btn_text = btn_text[:37] + "..."
                row.append({
                    "type": "callback",
                    "text": btn_text,
                    "payload": f"clarify:{clarify_id}:{i}",
                })
                if len(row) >= 3:
                    buttons.append(row)
                    row = []
            if row:
                buttons.append(row)
            # Add "Other…" button
            buttons.append([{
                "type": "callback",
                "text": "💬 Other…",
                "payload": f"clarify:{clarify_id}:other",
            }])

            text = f"**{question}**"[:MAX_MESSAGE_LENGTH]
            result = await self._post_interactive(chat_id, text, buttons, reply_to=reply_to)
            if result.success:
                self._clarify_state[clarify_id] = session_key
            return result
        else:
            # Open-ended — just send the question as plain text
            return await self.send(chat_id, question, reply_to=reply_to, metadata=metadata)
