"""Caption fallback and public pre-delivery transformation for MAX media."""

from pathlib import PureWindowsPath


def media_caption(text: str | None, path: str | None, file_name: str | None = None) -> str:
    """Preserve authored text; otherwise expose a basename, never a directory."""
    if text and text.strip():
        return text
    source = str(file_name or path or "").strip()
    name = "" if not source or source.endswith(("/", "\\")) else PureWindowsPath(source).name
    name = "".join(c for c in name if c.isprintable()).strip()
    return name if name not in ("", ".", "..") else "File"


def transform_max_media_output(response_text: str, platform="", **_context) -> str | None:
    """Add text before Core extracts MEDIA markers; leave other platforms alone."""
    if getattr(platform, "value", platform) != "max":
        return None
    from gateway.platforms.base import BasePlatformAdapter

    files, text = BasePlatformAdapter.extract_media(response_text)
    if not files or text.strip():
        return None
    # Prevent a filename from introducing another MEDIA marker into Core parsing.
    label = media_caption(None, files[0][0]).replace("MEDIA:", "MEDIA\\:")
    return f"{label}\n{response_text}"
