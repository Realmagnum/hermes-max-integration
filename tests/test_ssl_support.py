"""Tests for MinCifry SSL certificates bundle and SSLContext generation."""

from pathlib import Path
import ssl

import httpx
import pytest

from ssl_support import get_max_ssl_context, get_mincifry_bundle_path


def test_bundle_file_exists():
    path = get_mincifry_bundle_path()
    assert path is not None
    assert path.is_file()
    content = path.read_text(encoding="utf-8")
    assert "-----BEGIN CERTIFICATE-----" in content
    assert "-----END CERTIFICATE-----" in content


def test_ssl_context_creates_successfully():
    ctx = get_max_ssl_context()
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.verify_mode == ssl.CERT_REQUIRED
