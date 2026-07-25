from __future__ import annotations
import logging
from mixins.base import MaxBaseMixin

logger = logging.getLogger(__name__)

class WebhookMixin(MaxBaseMixin):
    """
    Mixin for aiohttp webhook server logic.
    """
    async def _start_webhook(self) -> bool:
        # Implementation to be moved from adapter.py
        pass
