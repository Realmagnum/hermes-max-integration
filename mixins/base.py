from __future__ import annotations

import asyncio
import logging

import httpx
from gateway.platforms.base import BasePlatformAdapter, MessageEvent

logger = logging.getLogger(__name__)

class MaxBaseMixin(BasePlatformAdapter):
    """
    Base mixin for MAX Platform Adapter.
    Holds core state and shared properties.
    """

    _http_client: httpx.AsyncClient | None
    _token: str
    _message_queue: asyncio.Queue[MessageEvent]
    _running: bool
    _stop: asyncio.Event
    _background_tasks: set[asyncio.Task]

    # Shared properties and utilities can be added here
