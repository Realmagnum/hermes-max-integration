"""Shared test fixtures for Max platform plugin."""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

# The plugin is a *package* whose modules use relative imports
# (`adapter.py` does `from .mixins.media_upload import ...`), while the tests
# import it as a plain top-level module (`import adapter`). Bootstrap it here
# by directory path so the suite works in every checkout layout.
#
# Two things a path-based bootstrap must not assume:
#
# * The checkout directory name. Hermes installs a directory plugin under the
#   sanitized `plugin.yaml` name (`plugins/max-platform/`), a `git clone` of
#   the repo lands as `hermes-max-integration/`, and CI checks out
#   `hermes-max-integration/`. None of those is `max`, so importing
#   `max.adapter` fails everywhere.
# * The absolute location of the plugin root, so the parent directory must
#   never be added to `sys.path` — that would shadow unrelated top-level
#   modules.
#
# Load `__init__.py` under a fixed private namespace instead, then alias the
# resulting `adapter` submodule to the top-level name the tests expect.
_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
_NAMESPACE = "hermes_max_plugin_under_test"

if _NAMESPACE not in sys.modules:
    _spec = importlib.util.spec_from_file_location(
        _NAMESPACE,
        _PLUGIN_ROOT / "__init__.py",
        submodule_search_locations=[str(_PLUGIN_ROOT)],
    )
    if _spec is None or _spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"Cannot load plugin package from {_PLUGIN_ROOT}")
    _plugin = importlib.util.module_from_spec(_spec)
    _plugin.__package__ = _NAMESPACE
    _plugin.__path__ = [str(_PLUGIN_ROOT)]
    sys.modules[_NAMESPACE] = _plugin
    _spec.loader.exec_module(_plugin)

adapter = importlib.import_module(f"{_NAMESPACE}.adapter")
# Register under the flat name the tests use, and expose the plugin package
# under `max` so `from max.mixins...` imports keep resolving.
sys.modules.setdefault("adapter", adapter)
sys.modules.setdefault("max", sys.modules[_NAMESPACE])
sys.modules.setdefault("max.adapter", adapter)

# Mirror every already-loaded submodule to the `max.` alias as well.
#
# Aliasing only the package is not enough: a later `import
# max.mixins.table_renderer` would execute the source a second time and create
# a *separate* module object with its own globals. Tests that patch
# `max.mixins.table_renderer._playwright_importable` would then patch that
# doppelgänger while `adapter` keeps calling the real module's globals — the
# patch silently has no effect (only attributes reached through shared
# singletons, e.g. `subprocess.run`, still appear to work, which makes the
# failure look like a product bug). Register the same objects under both names.
if sys.modules.get("max") is sys.modules[_NAMESPACE]:
    _PREFIX = _NAMESPACE + "."
    for _name, _module in list(sys.modules.items()):
        if _name.startswith(_PREFIX) and _module is not None:
            sys.modules["max." + _name[len(_PREFIX):]] = _module


@pytest.fixture
def max_config():
    """Create a PlatformConfig for testing."""
    from gateway.config import PlatformConfig

    return PlatformConfig(
        enabled=True,
        token="test-token",
        extra={
            "token": "test-token",
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
