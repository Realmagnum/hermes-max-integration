"""Tests for media extraction."""

import pytest

import adapter


class TestFindFirstUrl:
    def test_direct_url(self):
        data = {"url": "https://cdn.example.com/image.jpg"}
        assert adapter.MaxAdapter._find_first_url(data) == "https://cdn.example.com/image.jpg"

    def test_nested_url(self):
        data = {
            "payload": {
                "download_url": "https://cdn.example.com/file.pdf",
            }
        }
        assert adapter.MaxAdapter._find_first_url(data) == "https://cdn.example.com/file.pdf"

    def test_not_url(self):
        assert adapter.MaxAdapter._find_first_url({"x": 1, "y": 2}) is None

    def test_non_http_url(self):
        assert adapter.MaxAdapter._find_first_url({"url": "ftp://files.example.com"}) is None

    def test_list_of_dicts(self):
        data = [
            {"x": 1},
            {"url": "https://cdn.example.com/file.ogg"},
        ]
        assert adapter.MaxAdapter._find_first_url(data) == "https://cdn.example.com/file.ogg"


class TestFindFirstFilename:
    def test_direct_filename(self):
        data = {"filename": "report.pdf"}
        assert adapter.MaxAdapter._find_first_filename(data) == "report.pdf"

    def test_file_name_alias(self):
        data = {"file_name": "data.csv"}
        assert adapter.MaxAdapter._find_first_filename(data) == "data.csv"

    def test_name_field(self):
        data = {"name": "image.png"}
        assert adapter.MaxAdapter._find_first_filename(data) == "image.png"

    def test_nested_filename(self):
        data = {"attachment": {"filename": "doc.pdf"}}
        assert adapter.MaxAdapter._find_first_filename(data) == "doc.pdf"

    def test_not_found(self):
        assert adapter.MaxAdapter._find_first_filename({"x": 1}) is None

    def test_path_stripped(self):
        data = {"filename": "/home/user/file.txt"}
        assert adapter.MaxAdapter._find_first_filename(data) == "file.txt"


class TestAttachmentKind:
    def test_audio_direct(self):
        att = {"type": "audio"}
        assert adapter.MaxAdapter._attachment_kind(att) == "audio"

    def test_voice_direct(self):
        att = {"type": "voice"}
        assert adapter.MaxAdapter._attachment_kind(att) == "voice"

    def test_image_direct(self):
        att = {"type": "image"}
        assert adapter.MaxAdapter._attachment_kind(att) == "image"

    def test_file_direct(self):
        att = {"type": "file"}
        assert adapter.MaxAdapter._attachment_kind(att) == "document"

    def test_payload_voice_key(self):
        att = {"type": "unknown", "payload": {"voice": {"url": "..."}}}
        assert adapter.MaxAdapter._attachment_kind(att) == "voice"

    def test_payload_audio_key(self):
        att = {"type": "unknown", "payload": {"audio": {"url": "..."}}}
        assert adapter.MaxAdapter._attachment_kind(att) == "audio"

    def test_by_mime_type(self):
        att = {"payload": {"mime_type": "audio/ogg"}}
        assert adapter.MaxAdapter._attachment_kind(att) == "audio"

    def test_by_filename_extension_document(self):
        # Bare filename without type/payload — doesn't identify as audio
        att = {"filename": "song.mp3"}
        assert adapter.MaxAdapter._attachment_kind(att) == ""
        # With audio mime_type it should work
        att2 = {"payload": {"mime_type": "audio/mpeg"}, "filename": "song.mp3"}
        assert adapter.MaxAdapter._attachment_kind(att2) == "audio"

    def test_ptt_prefix(self):
        att = {"type": "ptt"}
        assert adapter.MaxAdapter._attachment_kind(att) == "audio"


class TestDeriveMessageType:
    def test_text_only(self):
        assert adapter.MaxAdapter._derive_message_type("hello", []) == adapter.MessageType.TEXT

    def test_image_no_text(self):
        assert adapter.MaxAdapter._derive_message_type("", ["image/jpeg"]) == adapter.MessageType.PHOTO

    def test_image_with_text(self):
        assert adapter.MaxAdapter._derive_message_type("caption", ["image/png"]) == adapter.MessageType.TEXT

    def test_audio_no_text(self):
        assert adapter.MaxAdapter._derive_message_type("", ["audio/ogg"]) == adapter.MessageType.VOICE

    def test_document(self):
        assert adapter.MaxAdapter._derive_message_type("", ["application/pdf"]) == adapter.MessageType.DOCUMENT
