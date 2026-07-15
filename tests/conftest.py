"""Shared test fixtures for Max STT plugin."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def max_config():
    """Create a PlatformConfig for testing."""
    from gateway.config import PlatformConfig

    return PlatformConfig(
        enabled=True,
        token="test-token",
        extra={
            "token": "test-token",
            "stt_enabled": True,
        },
    )


@pytest.fixture
def max_config_no_stt():
    """PlatformConfig with STT disabled."""
    from gateway.config import PlatformConfig

    return PlatformConfig(
        enabled=True,
        token="test-token",
        extra={
            "token": "test-token",
            "stt_enabled": False,
        },
    )


@pytest.fixture
def sample_dm_update():
    """Sample direct message update from Max."""
    return {
        "update_type": "message_created",
        "message": {
            "sender": {"user_id": 42, "name": "Test User"},
            "recipient": {"chat_type": "dialog"},
            "body": {"mid": "mid-001", "text": "Hello!"},
        },
    }


@pytest.fixture
def sample_group_update():
    """Sample group chat update from Max."""
    return {
        "update_type": "message_created",
        "chat": {"chat_id": 777, "title": "Test Group"},
        "message": {
            "sender": {"user_id": 42, "name": "Test User"},
            "recipient": {"chat_id": 777},
            "body": {"mid": "mid-002", "text": "Hello group!"},
        },
    }


@pytest.fixture
def sample_audio_attachment():
    """Sample audio attachment payload."""
    return {
        "type": "audio",
        "payload": {
            "url": "https://cdn.max.ru/audio/test.ogg",
            "token": "aud-token-123",
            "id": "aud-001",
        },
    }


@pytest.fixture
def sample_bot_started():
    """Sample bot_started update."""
    return {
        "update_type": "bot_started",
        "chat_id": "12345",
        "user": {"user_id": 42, "name": "Test User"},
        "payload": "",
    }


@pytest.fixture
def mock_httpx_client():
    """Create a mock httpx.AsyncClient."""
    client = AsyncMock()
    client.aclose = AsyncMock()
    return client
