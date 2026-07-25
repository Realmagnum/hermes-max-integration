from __future__ import annotations
import logging
from mixins.base import MaxBaseMixin

logger = logging.getLogger(__name__)

class ButtonsMixin(MaxBaseMixin):
    """
    Mixin for interactive buttons and forms logic.
    """
    async def _post_interactive(self, chat_id: str, text: str, buttons: list, reply_to: str = None):
        # Implementation to be moved from adapter.py
        pass
