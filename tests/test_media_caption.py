"""Fallback captions and scoped public response transformation."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from max.media_caption import media_caption, transform_max_media_output

import adapter


@pytest.mark.parametrize("text,path,name,expected", [
    (None, "/private/report.pdf", None, "report.pdf"),
    (" \n", r"C:\private\отчёт.pdf", None, "отчёт.pdf"),
    (None, "/private/internal.bin", "download.pdf", "download.pdf"),
    (None, None, None, "File"),
    (None, "/private/", None, "File"),
    (None, "..", None, "File"),
    ("  Authored text\n", "/private/a.pdf", None, "  Authored text\n"),
])
def test_caption_contract(text, path, name, expected):
    assert media_caption(text, path, name) == expected


@pytest.mark.parametrize("platform,text", [
    ("telegram", "MEDIA:/tmp/file.pdf"),
    ("", "MEDIA:/tmp/file.pdf"),
    ("max", "Here MEDIA:/tmp/file.pdf"),
    ("max", "Plain text"),
])
def test_transform_preserves_unrelated_responses(platform, text):
    assert transform_max_media_output(text, platform) is None


def test_transform_keeps_media_descriptors_and_is_idempotent():
    from gateway.platforms.base import BasePlatformAdapter
    original = "MEDIA:/tmp/report.pdf\nMEDIA:/tmp/second.png"
    transformed = transform_max_media_output(original, "max")
    original_files, _ = BasePlatformAdapter.extract_media(original)
    files, text = BasePlatformAdapter.extract_media(transformed)
    assert files == original_files
    assert text.strip() == "report.pdf"
    assert transform_max_media_output(transformed, "max") is None


def test_real_plugin_registration_exposes_output_hook(monkeypatch, tmp_path):
    from hermes_cli.plugins import PluginContext, PluginManager, PluginManifest

    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    manager = PluginManager()
    adapter.register(PluginContext(PluginManifest(name="max-platform", source="user", kind="platform"), manager))
    assert manager.invoke_hook("transform_llm_output", response_text="MEDIA:/tmp/report.pdf", platform="max") == [
        "report.pdf\nMEDIA:/tmp/report.pdf"
    ]


@pytest.mark.asyncio
async def test_direct_upload_has_filename_and_preserves_caption(max_config):
    instance = adapter.MaxAdapter(max_config)
    instance._http_client = AsyncMock()
    instance._upload = AsyncMock(return_value="fixture-upload")
    instance.send_action = AsyncMock()
    response = MagicMock(spec=httpx.Response)
    response.json.return_value = {"message": {"body": {"mid": "fixture"}}}
    instance._http_client.post.return_value = response
    for caption, expected in [("", "report.pdf"), ("Authored", "Authored")]:
        result = await instance._upload_send("user:42", "/tmp/report.pdf", "file", caption, None)
        assert result.success
        assert instance._http_client.post.call_args.kwargs["json"]["text"] == expected


@pytest.mark.asyncio
async def test_document_explicit_filename(max_config):
    instance = adapter.MaxAdapter(max_config)
    instance._upload_send = AsyncMock()
    await instance.send_document("user:42", "/tmp/internal.bin", file_name="report.pdf")
    assert instance._upload_send.call_args.args[3] == "report.pdf"
