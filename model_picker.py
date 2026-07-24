"""Model picker for MAX platform.

Handles interactive model selection with pagination.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

PAGE_SIZE = 15
MAX_MESSAGE_LENGTH = 4000


@dataclass
class ModelPickerState:
    """State for model picker session."""
    provider_msg_id: str = ""
    model_msg_id: str = ""
    providers: List[Dict[str, Any]] = field(default_factory=list)
    session_key: str = ""
    on_model_selected: Optional[Callable] = None
    current_model: str = ""
    current_provider: str = ""


class ModelPicker:
    """Interactive model picker for MAX platform."""

    def __init__(
        self,
        adapter,
        on_model_selected: Optional[Callable] = None,
        get_providers: Optional[Callable] = None,
    ):
        """Initialize model picker.

        Args:
            adapter: HTTP adapter for sending messages
            on_model_selected: Callback when model is selected
            get_providers: Callback to get list of providers
        """
        self.adapter = adapter
        self.on_model_selected = on_model_selected
        self.get_providers = get_providers
        self._state: Dict[str, ModelPickerState] = {}
        # Public attributes for adapter to set
        self.providers: List[Dict[str, Any]] = []
        self.current_model: str = ""
        self.current_provider: str = ""

    # ═════════════════════════════════════════════════════════════════════
    # Public API
    # ═════════════════════════════════════════════════════════════════════

    async def handle_callback(
        self, chat_id: str, payload: str, user_id: str
    ) -> Optional[str]:
        """Handle model picker callback.

        Args:
            chat_id: Chat identifier
            payload: Callback payload
            user_id: User identifier

        Returns:
            Optional text response or None
        """
        parts = payload.split(":")
        if len(parts) < 2:
            return None

        action = parts[0]

        if action == "provider":
            return await self._on_provider_selected(chat_id, parts[1])
        elif action == "pick":
            return await self._on_model_picked(chat_id, parts[1], parts[2])
        elif action == "page":
            page = int(parts[2]) if len(parts) > 2 else 0
            await self._on_page_selected(chat_id, parts[1], page)
            return None
        elif action == "back":
            await self._on_back(chat_id, user_id)
            return None
        else:
            return None

    async def show_providers(self, chat_id: str) -> None:
        """Show provider selection message."""
        providers = self.providers  # Set by adapter

        state = ModelPickerState(
            providers=providers,
            session_key=f"user:{chat_id}",
            on_model_selected=self.on_model_selected,
            current_model=self.current_model,
            current_provider=self.current_provider,
        )

        text = "⚙ **Model Configuration**\n\nSelect a provider:"
        buttons = self._build_provider_buttons(providers)

        result = await self.adapter._post_interactive(chat_id, text, buttons)
        if result.success:
            state.provider_msg_id = result.message_id
            self._state[str(chat_id)] = state

    # ═════════════════════════════════════════════════════════════════════
    # Callback handlers
    # ═════════════════════════════════════════════════════════════════════

    async def _on_provider_selected(
        self, chat_id: str, provider_slug: str
    ) -> Optional[str]:
        """Handle provider selection."""
        state = self._state.get(str(chat_id))
        if not state:
            return None

        providers = self.providers  # Set by adapter

        provider = next(
            (p for p in providers if p.get("slug") == provider_slug), None
        )
        if not provider:
            return f"❌ Provider `{provider_slug}` not found"

        models = provider.get("models", [])
        state.providers = providers
        state.current_provider = provider_slug
        # Save updated state
        self._state[str(chat_id)] = state

        await self._show_models(chat_id, provider_slug, models, page=0)
        return None

    async def _on_model_picked(
        self, chat_id: str, model_id: str, provider_slug: str
    ) -> Optional[str]:
        """Handle model selection."""
        state = self._state.pop(str(chat_id), None)
        if not state:
            return None

        # Delete both messages
        model_msg_id = state.model_msg_id
        provider_msg_id = state.provider_msg_id

        if model_msg_id:
            await self.adapter.delete_message(chat_id, model_msg_id)
        if provider_msg_id:
            await self.adapter.delete_message(chat_id, provider_msg_id)

        if not state.on_model_selected:
            return None

        try:
            result_text = await state.on_model_selected(
                chat_id, model_id, provider_slug
            )
        except Exception as e:
            result_text = f"❌ Error switching model: {e}"

        await self.adapter.send(chat_id, result_text)
        return result_text

    async def _on_page_selected(
        self, chat_id: str, provider_slug: str, page: int
    ) -> None:
        """Handle page navigation."""
        state = self._state.get(str(chat_id))
        if not state:
            return

        providers = self.providers  # Set by adapter

        provider = next(
            (p for p in providers if p.get("slug") == provider_slug), None
        )
        if not provider:
            return

        models = provider.get("models", [])
        await self._show_models(chat_id, provider_slug, models, page)

    async def _on_back(self, chat_id: str, user_id: str) -> None:
        """Go back to provider selection."""
        state = self._state.get(str(chat_id))
        if not state:
            return

        from hermes_cli.providers import get_label as _get_label

        try:
            provider_label = _get_label(state.current_provider)
        except Exception:
            provider_label = state.current_provider

        # Delete both messages
        model_msg_id = state.model_msg_id
        provider_msg_id = state.provider_msg_id

        if model_msg_id:
            await self.adapter.delete_message(chat_id, model_msg_id)
        if provider_msg_id:
            await self.adapter.delete_message(chat_id, provider_msg_id)

        # Show providers
        if self.get_providers:
            providers = await self.get_providers()
        else:
            providers = []

        text = (
            f"⚙ **Model Configuration**\n\n"
            f"Current: `{state.current_model or 'unknown'}` ({provider_label})\n\n"
            f"Select a provider:"
        )[:MAX_MESSAGE_LENGTH]

        buttons = self._build_provider_buttons(providers)

        result = await self.adapter._post_interactive(chat_id, text, buttons)
        if result.success:
            # Update state with new provider message
            state.provider_msg_id = result.message_id
            state.providers = providers
            self._state[str(chat_id)] = state

    # ═════════════════════════════════════════════════════════════════════
    # Model display
    # ═════════════════════════════════════════════════════════════════════

    async def _show_models(
        self,
        chat_id: str,
        provider_slug: str,
        models: List[str],
        page: int = 0,
        is_pagination: bool = False,
    ) -> None:
        """Show model selection message."""
        total_pages = max(1, (len(models) + PAGE_SIZE - 1) // PAGE_SIZE)
        page = max(0, min(page, total_pages - 1))

        start = page * PAGE_SIZE
        end = start + PAGE_SIZE
        page_models = models[start:end]

        state = self._state.get(str(chat_id))
        if not state:
            return

        try:
            from hermes_cli.providers import get_label as _get_label
            provider_label = _get_label(provider_slug)
        except Exception:
            provider_label = provider_slug

        page_info = f" (стр. {page + 1}/{total_pages})" if total_pages > 1 else ""
        text = (
            f"⚙ **{provider_label}** models{page_info}\n\n"
            f"Select a model:"
        )[:MAX_MESSAGE_LENGTH]

        buttons = self._build_model_buttons(page_models, provider_slug, page, total_pages)

        if is_pagination and state.model_msg_id:
            # Delete old model message, send new one
            await self.adapter.delete_message(chat_id, state.model_msg_id)

        result = await self.adapter._post_interactive(chat_id, text, buttons)
        if result.success:
            state.model_msg_id = result.message_id
            self._state[str(chat_id)] = state

    # ═════════════════════════════════════════════════════════════════════
    # Button builders
    # ═════════════════════════════════════════════════════════════════════

    def _build_provider_buttons(
        self, providers: List[Dict[str, Any]]
    ) -> List[List[Dict[str, str]]]:
        """Build provider selection buttons."""
        buttons: List[List[Dict[str, str]]] = []
        row: List[Dict[str, str]] = []

        for p in providers[:20]:
            slug = p.get("slug", "")
            name = p.get("name", slug)[:38]
            tag = " ✅" if p.get("is_current") else ""

            row.append({
                "type": "callback",
                "text": f"{name}{tag}"[:40],
                "payload": f"model:provider:{slug}",
            })

            if len(row) >= 2:
                buttons.append(row)
                row = []

        if row:
            buttons.append(row)

        return buttons

    def _build_model_buttons(
        self,
        models: List[str],
        provider_slug: str,
        current_page: int,
        total_pages: int,
    ) -> List[List[Dict[str, str]]]:
        """Build model selection buttons."""
        buttons: List[List[Dict[str, str]]] = []
        row: List[Dict[str, str]] = []

        for model in models:
            row.append({
                "type": "callback",
                "text": model[:38],
                "payload": f"model:pick:{model}:{provider_slug}",
            })

            if len(row) >= 2:
                buttons.append(row)
                row = []

        if row:
            buttons.append(row)

        # Navigation buttons
        nav_row: List[Dict[str, str]] = []

        if current_page > 0:
            nav_row.append({
                "type": "callback",
                "text": "⬅ Prev",
                "payload": f"model:page:{provider_slug}:{current_page - 1}",
            })

        if current_page < total_pages - 1:
            nav_row.append({
                "type": "callback",
                "text": "Next ➡",
                "payload": f"model:page:{provider_slug}:{current_page + 1}",
            })

        if nav_row:
            buttons.append(nav_row)

        # Back button
        buttons.append([{
            "type": "callback",
            "text": "← Back to providers",
            "payload": "model:back",
        }])

        return buttons
