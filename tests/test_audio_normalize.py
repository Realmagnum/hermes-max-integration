"""Tests for audio container normalization (idempotent w.r.t. input format).

The Max CDN rejects some audio containers (wav -> 415) and decides the
format from the uploaded filename. normalize_audio_for_max must turn ANY
provider output (wav/mp3/ogg/flac/m4a/...) into a Max-accepted container
with an honest extension (ogg/opus or mp3) and must be idempotent: ogg/mp3
inputs pass through byte-for-byte unchanged, and re-running on a normalized
file is a no-op.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from max.mixins.media_upload import (
    _AUDIO_PASSTHROUGH_CONTAINERS,
    _sniff_audio_container,
    normalize_audio_for_max,
)

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="ffmpeg required to build fixtures"
)

FFMPEG = shutil.which("ffmpeg")


def _make_tone(path: Path, fmt: str, extra: list | None = None) -> Path:
    """Render a 1s sine tone into the requested container via ffmpeg."""
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        FFMPEG, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
        *((extra or []) + [str(path)]),
    ]
    # for libopus codec we need explicit -c:a; for others default encoder
    if fmt == "opus":
        cmd.insert(-1, "-c:a")
        cmd.insert(-1, "libopus")
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
    assert proc.returncode == 0, f"ffmpeg {fmt} failed: {proc.stderr[-500:]}"
    assert path.exists() and path.stat().st_size > 0
    return path


@pytest.fixture(scope="module")
def fixtures(tmp_path_factory) -> dict[str, Path]:
    d = tmp_path_factory.mktemp("audio_fixtures")
    return {
        "wav": _make_tone(d / "t.wav", "wav"),
        "mp3": _make_tone(d / "t.mp3", "mp3"),
        "ogg": _make_tone(d / "t.ogg", "ogg", ["-c:a", "libopus"]),
        "flac": _make_tone(d / "t.flac", "flac"),
        "m4a": _make_tone(d / "t.m4a", "m4a"),
    }


def _copy(src: Path, suffix: str) -> Path:
    """Copy fixture bytes into a fresh standalone file."""
    p = src.with_name(src.stem + suffix)
    p.write_bytes(src.read_bytes())
    return p


# ── Sniffer ──────────────────────────────────────────────────────────────


class TestSniff:
    @pytest.mark.parametrize(
        "fmt,expected",
        [("wav", "wav"), ("mp3", "mp3"), ("ogg", "ogg"), ("flac", "flac"), ("m4a", "m4a")],
    )
    def test_sniff_detects(self, fixtures, fmt, expected):
        assert _sniff_audio_container(str(fixtures[fmt])) == expected


# ── Normalization ────────────────────────────────────────────────────────


class TestNormalize:
    @pytest.mark.parametrize("fmt", ["wav", "flac", "m4a"])
    def test_non_accepted_containers_become_ogg(self, fixtures, fmt):
        src = _copy(fixtures[fmt], f"_{fmt}")
        before = src.read_bytes()
        out = normalize_audio_for_max(str(src))
        assert out.endswith(".ogg"), out
        assert out != str(src)
        # source untouched, normalized sibling has honest extension
        assert src.read_bytes() == before
        assert Path(out).exists()
        assert _sniff_audio_container(out) == "ogg"
        # still valid audio with a real duration
        probe = subprocess.run(
            [FFMPEG, "-i", out, "-f", "null", "-"],
            capture_output=True, text=True, timeout=60, check=False,
        )
        assert "Duration:" in probe.stderr

    @pytest.mark.parametrize("fmt", ["ogg", "mp3"])
    def test_accepted_containers_pass_through_unchanged(self, fixtures, fmt):
        src = _copy(fixtures[fmt], f"_{fmt}")
        before = src.read_bytes()
        out = normalize_audio_for_max(str(src))
        assert out == str(src)  # same path
        assert src.read_bytes() == before  # byte-for-byte idempotent
        assert _sniff_audio_container(out) == fmt

    def test_normalize_is_idempotent_on_result(self, fixtures):
        """Normalizing an already-normalized wav is a no-op (same bytes)."""
        src = _copy(fixtures["wav"], "_wav")
        out1 = normalize_audio_for_max(str(src))
        assert _sniff_audio_container(out1) == "ogg"
        once = Path(out1).read_bytes()
        out2 = normalize_audio_for_max(out1)
        assert out2 == out1  # same path, no re-transcode churn
        assert Path(out2).read_bytes() == once

    def test_all_fixtures_after_normalization_accepted(self, fixtures):
        """Every input format ends up in the passthrough allowlist."""
        for fmt, path in fixtures.items():
            src = _copy(path, f"_{fmt}")
            out = normalize_audio_for_max(str(src))
            assert _sniff_audio_container(out) in _AUDIO_PASSTHROUGH_CONTAINERS, fmt
