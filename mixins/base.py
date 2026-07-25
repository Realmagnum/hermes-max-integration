from __future__ import annotations

import asyncio
import logging
from typing import Optional, Set

import httpx
from gateway.platforms.base import BasePlatformAdapter, MessageEvent

logger = logging.getLogger(__name__)

class MaxBaseMixin(BasePlatformAdapter):
    """
    Base mixin for MAX Platform Adapter.
    Holds core state and shared properties.
    """

    _http_client: Optional[httpx.AsyncClient]
    _token: str
    _stt_enabled: bool
    _message_queue: asyncio.Queue[MessageEvent]
    _running: bool
    _stop: asyncio.Event
    _background_tasks: set[asyncio.Task]
    
    @property
    def http_client(self) -> httpx.AsyncClient:
        """Get the HTTP client."""
        if self._http_client is None:
            raise RuntimeError("HTTP client not initialized")
        return self._http_client
