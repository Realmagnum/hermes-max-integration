from __future__ import annotations
import logging
from .base import MaxBaseMixin

logger = logging.getLogger(__name__)

class MediaUploadMixin(MaxBaseMixin):
    """
    Mixin for CDN file upload logic.
    """
    async def _upload_send(self, chat_id: str, fp, media_type: str, caption: str, reply_to: str = None):
        # Implementation to be moved from adapter.py
        pass
