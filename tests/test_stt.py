"""Tests for STT audio download."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import adapter


class TestDownloadAudio:
    """Tests for _download_audio."""

    def _make_adapter(self, stt_enabled=True):
        from gateway.config import PlatformConfig
        extra = {"token": "test-token", "stt_enabled": stt_enabled}
        cfg = PlatformConfig(enabled=True, token="test-token", extra=extra)
        a = adapter.MaxAdapter(cfg)
        a._http_client = AsyncMock()
        return a

    @pytest.mark.asyncio
    async def test_download_audio_success(self, tmp_path):
        a = self._make_adapter(stt_enabled=True)
        # Override AUDIO_CACHE_DIR for test
        import adapter as adp
        old_cache = adp.AUDIO_CACHE_DIR
        adp.AUDIO_CACHE_DIR = tmp_path / "audio_cache"

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"fake-ogg-data"
        a._http_client.get = AsyncMock(return_value=mock_resp)

        result = await a._download_audio("https://cdn.max.ru/audio/test.ogg", "msg-001")

        assert result is not None
        assert "msg-001" in result
        assert result.endswith(".ogg")
        assert Path(result).exists()

        adp.AUDIO_CACHE_DIR = old_cache

    @pytest.mark.asyncio
    async def test_download_audio_http_error(self, tmp_path):
        a = self._make_adapter(stt_enabled=True)
        import adapter as adp
        old_cache = adp.AUDIO_CACHE_DIR
        adp.AUDIO_CACHE_DIR = tmp_path / "audio_cache"

        mock_resp = MagicMock()
        mock_resp.status_code = 404
        a._http_client.get = AsyncMock(return_value=mock_resp)

        result = await a._download_audio("https://cdn.max.ru/audio/missing.ogg", "msg-002")
        assert result is None

        adp.AUDIO_CACHE_DIR = old_cache

    @pytest.mark.asyncio
    async def test_download_audio_disabled(self):
        a = self._make_adapter(stt_enabled=False)
        result = await a._download_audio("https://cdn.max.ru/audio/test.ogg", "msg-003")
        assert result is None

    @pytest.mark.asyncio
    async def test_audio_extension_mp3(self, tmp_path):
        a = self._make_adapter(stt_enabled=True)
        import adapter as adp
        old_cache = adp.AUDIO_CACHE_DIR
        adp.AUDIO_CACHE_DIR = tmp_path / "audio_cache"

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"fake-mp3-data"
        a._http_client.get = AsyncMock(return_value=mock_resp)

        result = await a._download_audio("https://cdn.max.ru/audio/test.mp3", "msg-004")
        assert result is not None
        assert result.endswith(".mp3")

        adp.AUDIO_CACHE_DIR = old_cache

    @pytest.mark.asyncio
    async def test_audio_extension_opus(self, tmp_path):
        a = self._make_adapter(stt_enabled=True)
        import adapter as adp
        old_cache = adp.AUDIO_CACHE_DIR
        adp.AUDIO_CACHE_DIR = tmp_path / "audio_cache"

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"fake-opus-data"
        a._http_client.get = AsyncMock(return_value=mock_resp)

        result = await a._download_audio("https://cdn.max.ru/audio/test.opus", "msg-005")
        assert result is not None
        assert result.endswith(".opus")

        adp.AUDIO_CACHE_DIR = old_cache
