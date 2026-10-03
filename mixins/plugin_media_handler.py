from __future__ import annotations

import re
from pathlib import Path
from typing import Any

MEDIA_PATTERN = re.compile(r"MEDIA:([^\s]+)")
AS_DOCUMENT_PATTERN = re.compile(r"\[\[as_document\]\]", re.IGNORECASE)
AUDIO_VOICE_PATTERN = re.compile(r"\[\[audio_as_voice\]\]", re.IGNORECASE)


def extract_plugin_media_request(
    args: dict[str, Any],
) -> tuple[str, list[tuple[str, bool]], bool]:
    """Extract (caption, media_files, force_document) from a send_message request dict."""
    msg = args.get("message") or ""
    if not isinstance(msg, str):
        return str(msg), [], False

    force_document = bool(AS_DOCUMENT_PATTERN.search(msg))
    audio_as_voice = bool(AUDIO_VOICE_PATTERN.search(msg))

    media_paths = MEDIA_PATTERN.findall(msg)
    cleaned = AS_DOCUMENT_PATTERN.sub("", msg)
    cleaned = AUDIO_VOICE_PATTERN.sub("", cleaned)
    cleaned = MEDIA_PATTERN.sub("", cleaned).strip()

    media_files: list[tuple[str, bool]] = []
    for path_str in media_paths:
        p = Path(path_str)
        # Validate that path exists and is an actual file (not a directory)
        if p.exists() and p.is_file():
            is_voice = audio_as_voice and p.suffix.lower() in {
                ".ogg",
                ".opus",
                ".mp3",
                ".wav",
                ".m4a",
            }
            media_files.append((str(p.resolve()), is_voice))

    return cleaned, media_files, force_document
