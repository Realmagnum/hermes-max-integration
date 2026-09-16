"""SSRF hardening for media downloads (SEC-03).

The guard has three layers and every test below exercises one of them
without touching a real internal network — DNS is always either mocked or
never reached:

1. ``_validate_download_url`` / ``_parse_host_ip`` / ``_is_public_ip`` —
   synchronous origin and address checks (no DNS);
2. ``_resolve_public_addresses`` — all A/AAAA records must be public;
3. ``_pin_download_request`` / ``_prepare_download`` — the socket target is
   the address that was validated, so a second DNS answer (rebinding) cannot
   redirect the connection; the original Host/SNI are preserved.
"""

import ipaddress
import socket
from unittest.mock import AsyncMock

import httpx
import pytest
from gateway.config import PlatformConfig

import adapter

PUBLIC_V4 = "93.184.216.34"
PUBLIC_V6 = "2606:4700::1111"

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _max_adapter(extra: dict | None = None) -> "adapter.MaxAdapter":
    cfg = PlatformConfig(
        enabled=True,
        token="test-token",
        extra={"token": "test-token", **(extra or {})},
    )
    return adapter.MaxAdapter(cfg)


def _addresses(*addrs: str, port: int = 443) -> list[tuple]:
    """Build ``getaddrinfo``-shaped answers for *addrs*."""
    out = []
    for addr in addrs:
        family = socket.AF_INET6 if ":" in addr else socket.AF_INET
        out.append((family, socket.SOCK_STREAM, 6, "", (addr, port, 0, 0)))
    return out


def _public_dns(monkeypatch, *addrs: str, recorder: list | None = None):
    def fake_getaddrinfo(host, port, **kwargs):
        if recorder is not None:
            recorder.append((host, port))
        return _addresses(*addrs, port=port)

    monkeypatch.setattr(adapter.socket, "getaddrinfo", fake_getaddrinfo)


def _response(
    url: str,
    status_code: int = 200,
    content: bytes = PNG_BYTES,
    content_type: str = "image/png",
    headers: dict | None = None,
) -> httpx.Response:
    all_headers = {"content-type": content_type, **(headers or {})}
    return httpx.Response(
        status_code,
        content=content,
        headers=all_headers,
        request=httpx.Request("GET", url),
    )


# ── Layer 1: host/IP parsing ─────────────────────────────────────────────


class TestParseHostIp:
    """Non-canonical IP spellings must not pass as "just a hostname"."""

    @pytest.mark.parametrize(
        "host,expected",
        [
            ("127.0.0.1", "127.0.0.1"),
            ("10.0.0.5", "10.0.0.5"),
            ("169.254.169.254", "169.254.169.254"),
            ("2130706433", "127.0.0.1"),        # decimal loopback
            ("0x7f000001", "127.0.0.1"),        # hex loopback
            ("017700000001", "127.0.0.1"),      # octal loopback
            ("0177.0.0.1", "127.0.0.1"),        # octal-dotted loopback
            ("127.1", "127.0.0.1"),             # short form
            ("0", "0.0.0.0"),
            ("[::1]", "::1"),
            ("::ffff:127.0.0.1", "::ffff:127.0.0.1"),
            ("fe80::1%en0", "fe80::1"),         # scoped IPv6
        ],
    )
    def test_parses_addresses(self, host, expected):
        assert adapter._parse_host_ip(host) == ipaddress.ip_address(expected)

    @pytest.mark.parametrize(
        "host", ["cdn.max.ru", "max.ru", "metadata.google.internal", "", "not-an-ip"]
    )
    def test_hostnames_are_not_ips(self, host):
        assert adapter._parse_host_ip(host) is None


class TestIsPublicIp:
    @pytest.mark.parametrize(
        "addr",
        [
            "127.0.0.1",
            "127.1.2.3",
            "10.0.0.5",
            "192.168.1.10",
            "172.16.0.1",
            "169.254.169.254",
            "0.0.0.0",
            "100.64.0.1",          # CGNAT/shared address space
            "192.0.2.1",           # TEST-NET-1
            "198.18.0.1",          # benchmarking range
            "240.0.0.1",
            "255.255.255.255",
            "::1",
            "::",
            "::ffff:127.0.0.1",
            "::ffff:10.0.0.1",
            "fd00::1",             # unique-local
            "fe80::1",             # link-local
            "2001:db8::1",         # documentation
            "64:ff9b::7f00:1",     # NAT64-mapped loopback (Python calls it global)
            "2002:7f00:1::",       # 6to4 loopback
        ],
    )
    def test_non_public_rejected(self, addr):
        assert adapter._is_public_ip(ipaddress.ip_address(addr)) is False

    @pytest.mark.parametrize("addr", [PUBLIC_V4, "8.8.8.8", PUBLIC_V6, "::ffff:8.8.8.8"])
    def test_public_allowed(self, addr):
        assert adapter._is_public_ip(ipaddress.ip_address(addr)) is True


# ── Layer 1: URL validation ──────────────────────────────────────────────


class TestValidateDownloadUrl:
    @pytest.mark.parametrize(
        "url",
        [
            # schemes and shapes
            "http://cdn.max.ru/file.ogg",              # plaintext not allowed
            "ftp://cdn.max.ru/file.ogg",
            "file:///etc/passwd",
            "gopher://cdn.max.ru/x",
            "https://cdn.max.ru@evil.example/x",       # credentials
            "https://cdn.max.ru:pass@cdn.max.ru/x",
            "https:///no-host",
            "not-a-url",
            "",
            # hosts outside the MAX CDN allowlist
            "https://evil.example/x",
            "https://max.ru.evil.example/x",           # suffix must not match
            "https://cdn.max.ru.evil.example/x",
            "https://localhost:8646/health",
            "https://localhost.evil.example/x",
            "https://printer.local/file",
            "https://internal.corp/x",
            "https://metadata.google.internal/x",
            # public IP literal is not a MAX origin either
            "https://8.8.8.8/x",
            # legacy loopback spellings via an allowlisted-looking host
            "https://2130706433/x",
            "https://0x7f000001/x",
            "https://0177.0.0.1/x",
            "https://127.1/x",
        ],
    )
    def test_blocked(self, url):
        assert adapter.MaxAdapter._validate_download_url(url) is False

    @pytest.mark.parametrize(
        "url",
        [
            "https://cdn.max.ru/file.ogg",
            "https://iu.oneme.ru/file.jpg",
            "https://fu.oneme.ru/file.pdf",
            "https://storage.max.ru/a/b.ogg",
            "https://random.storage.max.ru/file.png",
            "https://max.ru/file.ogg",
            "https://oneme.ru/file.ogg",
            "https://CDN.MAX.RU/file.ogg",
        ],
    )
    def test_allowed(self, url):
        assert adapter.MaxAdapter._validate_download_url(url) is True

    def test_public_ip_literal_blocked_even_when_reachable(self):
        """An IP literal must satisfy both the allowlist and the public check."""
        assert adapter.MaxAdapter._validate_download_url("https://8.8.8.8/x") is False
        assert adapter.MaxAdapter._validate_download_url(
            "https://8.8.8.8/x", (".example.com",)
        ) is False

    def test_configured_suffix_extends_allowlist(self):
        assert adapter.MaxAdapter._validate_download_url(
            "https://media.example.net/x", (".example.net",)
        ) is True

    def test_configured_suffix_still_blocks_internal_address(self):
        """Layer 1 refuses a private literal even when its suffix is allowed."""
        assert adapter.MaxAdapter._validate_download_url(
            "https://2130706433/x", (".max.ru", "2130706433")
        ) is False
        assert adapter.MaxAdapter._validate_download_url(
            "https://10.1.2.3/x", (".max.ru", "10.1.2.3")
        ) is False

    def test_host_allowed_by_suffixes_exact_and_subdomain(self):
        suffixes = (".max.ru", ".oneme.ru")
        assert adapter._host_allowed_by_suffixes("max.ru", suffixes)
        assert adapter._host_allowed_by_suffixes("cdn.max.ru", suffixes)
        assert not adapter._host_allowed_by_suffixes("max.ru.evil.example", suffixes)
        assert not adapter._host_allowed_by_suffixes("xmax.ru", suffixes)

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("cdn.example.com", (".cdn.example.com",)),
            (".example.com", (".example.com",)),
            ("*.example.com", (".example.com",)),
            ("a.example.com, b.example.com", (".a.example.com", ".b.example.com")),
            ("a.example.com;b.example.com", (".a.example.com", ".b.example.com")),
            (["a.example.com"], (".a.example.com",)),
            ("", ()),
            (None, ()),
            (123, ()),
        ],
    )
    def test_normalize_host_suffixes(self, value, expected):
        assert adapter._normalize_host_suffixes(value) == expected

    def test_adapter_config_extends_download_allowlist(self):
        a = _max_adapter({"download_allowed_hosts": "media.example.net, *.cdn.example.org"})
        assert a._download_url_allowed("https://media.example.net/f.ogg") is True
        assert a._download_url_allowed("https://x.cdn.example.org/f.ogg") is True
        assert a._download_url_allowed("https://cdn.max.ru/f.ogg") is True
        assert a._download_url_allowed("https://other.example.org/f.ogg") is False


# ── Layer 2: DNS answers ─────────────────────────────────────────────────


class TestResolvePublicAddresses:
    def test_all_public(self, monkeypatch):
        _public_dns(monkeypatch, PUBLIC_V4)
        assert adapter.MaxAdapter._resolve_public_addresses("cdn.max.ru", 443) == [PUBLIC_V4]

    def test_dual_stack_sorted(self, monkeypatch):
        _public_dns(monkeypatch, PUBLIC_V6, PUBLIC_V4)
        assert adapter.MaxAdapter._resolve_public_addresses("cdn.max.ru", 443) == sorted(
            [PUBLIC_V4, PUBLIC_V6]
        )

    @pytest.mark.parametrize(
        "bad",
        ["127.0.0.1", "10.0.0.5", "169.254.169.254", "100.64.0.1", "::1", "fe80::1", "::ffff:10.0.0.1"],
    )
    def test_any_non_public_address_rejects_answer(self, monkeypatch, bad):
        """A mixed public/private answer must not be usable at all."""
        _public_dns(monkeypatch, PUBLIC_V4, bad)
        assert adapter.MaxAdapter._resolve_public_addresses("cdn.max.ru", 443) is None

    def test_resolution_failure(self, monkeypatch):
        def boom(host, port, **kwargs):
            raise socket.gaierror("NXDOMAIN")

        monkeypatch.setattr(adapter.socket, "getaddrinfo", boom)
        assert adapter.MaxAdapter._resolve_public_addresses("cdn.max.ru", 443) is None

    def test_empty_answer(self, monkeypatch):
        _public_dns(monkeypatch)
        assert adapter.MaxAdapter._resolve_public_addresses("cdn.max.ru", 443) is None


# ── Layer 3: pinning ─────────────────────────────────────────────────────


class TestPinDownloadRequest:
    def test_ipv4(self):
        url, headers, extensions = adapter.MaxAdapter._pin_download_request(
            "https://cdn.max.ru/path/file.ogg?sig=abc", PUBLIC_V4
        )
        assert url == f"https://{PUBLIC_V4}/path/file.ogg?sig=abc"
        assert headers == {"Host": "cdn.max.ru"}
        assert extensions == {"sni_hostname": "cdn.max.ru"}

    def test_explicit_port_kept(self):
        url, headers, _ = adapter.MaxAdapter._pin_download_request(
            "https://cdn.max.ru:8443/file.ogg", PUBLIC_V4
        )
        assert url == f"https://{PUBLIC_V4}:8443/file.ogg"
        assert headers == {"Host": "cdn.max.ru:8443"}

    def test_ipv6_address_bracketed(self):
        url, headers, extensions = adapter.MaxAdapter._pin_download_request(
            "https://cdn.max.ru/file.ogg", PUBLIC_V6
        )
        assert url == f"https://[{PUBLIC_V6}]/file.ogg"
        assert headers == {"Host": "cdn.max.ru"}
        assert extensions == {"sni_hostname": "cdn.max.ru"}


class TestPrepareDownload:
    async def test_pins_validated_address(self, monkeypatch):
        calls: list = []
        _public_dns(monkeypatch, PUBLIC_V4, recorder=calls)
        a = _max_adapter()
        prepared = await a._prepare_download("https://cdn.max.ru/file.ogg")
        assert prepared is not None
        request_url, headers, extensions = prepared
        assert request_url == f"https://{PUBLIC_V4}/file.ogg"
        assert headers == {"Host": "cdn.max.ru"}
        assert extensions == {"sni_hostname": "cdn.max.ru"}
        assert calls == [("cdn.max.ru", 443)]

    async def test_private_dns_answer_rejected(self, monkeypatch):
        _public_dns(monkeypatch, "10.0.0.5")
        a = _max_adapter()
        assert await a._prepare_download("https://cdn.max.ru/file.ogg") is None

    async def test_blocked_origin_never_resolves(self, monkeypatch):
        """Layer 1 rejects before any DNS traffic leaves the process."""
        calls: list = []
        _public_dns(monkeypatch, PUBLIC_V4, recorder=calls)
        a = _max_adapter()
        assert await a._prepare_download("https://evil.example/file.ogg") is None
        assert calls == []

    async def test_rebinding_second_answer_cannot_change_target(self, monkeypatch):
        """The target is resolved once and pinned, so a later answer is unused."""
        answers = [[("93.184.216.34", 443)], [("127.0.0.1", 443)]]
        calls: list = []

        def fake_getaddrinfo(host, port, **kwargs):
            calls.append((host, port))
            addrs = answers[min(len(calls) - 1, len(answers) - 1)]
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", (addr, port, 0, 0))
                for addr, _ in addrs
            ]

        monkeypatch.setattr(adapter.socket, "getaddrinfo", fake_getaddrinfo)
        a = _max_adapter()
        prepared = await a._prepare_download("https://cdn.max.ru/file.ogg")
        assert prepared is not None
        assert prepared[0] == "https://93.184.216.34/file.ogg"
        assert len(calls) == 1  # no second lookup happens at connect time

    async def test_literal_public_ip_allowed_when_suffix_matches(self):
        a = _max_adapter({"download_allowed_hosts": "8.8.8.8"})
        prepared = await a._prepare_download("https://8.8.8.8/file.ogg")
        assert prepared is not None
        assert prepared[0] == "https://8.8.8.8/file.ogg"

    async def test_literal_loopback_ip_blocked_when_suffix_matches(self):
        a = _max_adapter({"download_allowed_hosts": "2130706433, 127.0.0.1"})
        assert await a._prepare_download("https://2130706433/file.ogg") is None
        assert await a._prepare_download("https://127.0.0.1/file.ogg") is None


# ── End-to-end: the download helpers use the guard ───────────────────────


@pytest.fixture
def fake_client():
    a = _max_adapter()
    a._http_client = AsyncMock()
    return a


class TestDownloadHelpersGuard:
    async def test_blocked_host_is_never_fetched(self, fake_client, monkeypatch):
        calls: list = []
        _public_dns(monkeypatch, PUBLIC_V4, recorder=calls)
        attachment = {"type": "image", "url": "https://169.254.169.254/latest/meta-data/"}
        assert await fake_client._cache_image_attachment(attachment) is None
        fake_client._http_client.get.assert_not_called()
        assert calls == []

    async def test_noncanonical_loopback_is_never_fetched(self, fake_client, monkeypatch):
        _public_dns(monkeypatch, PUBLIC_V4)
        for url in ("https://2130706433/x.png", "https://0x7f000001/x.png", "https://127.1/x.png"):
            assert await fake_client._cache_image_attachment({"type": "image", "url": url}) is None
        fake_client._http_client.get.assert_not_called()

    async def test_private_dns_answer_is_never_fetched(self, fake_client, monkeypatch):
        _public_dns(monkeypatch, "192.168.1.10")
        attachment = {"type": "image", "url": "https://cdn.max.ru/x.png"}
        assert await fake_client._cache_image_attachment(attachment) is None
        fake_client._http_client.get.assert_not_called()

    async def test_image_download_is_pinned_and_token_scoped(self, fake_client, monkeypatch):
        _public_dns(monkeypatch, PUBLIC_V4)
        fake_client._http_client.get = AsyncMock(
            return_value=_response("https://cdn.max.ru/x.png")
        )
        with monkeypatch.context() as mp:
            mp.setattr(adapter, "cache_image_from_bytes", lambda data, ext: f"/tmp/x{ext}")
            result = await fake_client._cache_image_attachment(
                {"type": "image", "url": "https://cdn.max.ru/x.png?token=abc"}
            )
        assert result == ("/tmp/x.png", "image/png")
        args, kwargs = fake_client._http_client.get.call_args
        assert args[0] == f"https://{PUBLIC_V4}/x.png?token=abc"
        assert kwargs["headers"]["Host"] == "cdn.max.ru"
        assert kwargs["extensions"] == {"sni_hostname": "cdn.max.ru"}
        assert kwargs["headers"]["Authorization"] == "test-token"

    async def test_audio_download_is_pinned(self, fake_client, monkeypatch):
        _public_dns(monkeypatch, PUBLIC_V4)
        fake_client._http_client.get = AsyncMock(
            return_value=_response(
                "https://cdn.max.ru/v.ogg", content=b"OggSxxx", content_type="audio/ogg"
            )
        )
        with monkeypatch.context() as mp:
            mp.setattr(adapter, "cache_audio_from_bytes", lambda data, ext: f"/tmp/v{ext}")
            result = await fake_client._cache_audio_attachment(
                {"type": "voice", "url": "https://iu.oneme.ru/v.ogg"}, "voice"
            )
        assert result is not None
        args, kwargs = fake_client._http_client.get.call_args
        assert args[0] == f"https://{PUBLIC_V4}/v.ogg"
        assert kwargs["extensions"] == {"sni_hostname": "iu.oneme.ru"}

    async def test_document_download_is_pinned(self, fake_client, monkeypatch):
        _public_dns(monkeypatch, PUBLIC_V4)
        fake_client._http_client.get = AsyncMock(
            return_value=_response(
                "https://cdn.max.ru/f.pdf",
                content=b"%PDF-1.4",
                content_type="application/pdf",
            )
        )
        with monkeypatch.context() as mp:
            mp.setattr(
                adapter, "cache_document_from_bytes", lambda data, name: f"/tmp/{name}"
            )
            result = await fake_client._cache_document_attachment(
                {"type": "file", "url": "https://cdn.max.ru/f.pdf", "filename": "f.pdf"}
            )
        assert result == ("/tmp/f.pdf", "application/pdf")
        args, kwargs = fake_client._http_client.get.call_args
        assert args[0] == f"https://{PUBLIC_V4}/f.pdf"
        assert kwargs["headers"]["Host"] == "cdn.max.ru"

    @pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
    async def test_redirect_is_refused(self, fake_client, monkeypatch, status):
        """A redirect must not be followed, and its body must not be cached."""
        _public_dns(monkeypatch, PUBLIC_V4)
        fake_client._http_client.get = AsyncMock(
            return_value=_response(
                "https://cdn.max.ru/x.png",
                status_code=status,
                headers={"location": "http://169.254.169.254/latest/meta-data/"},
            )
        )
        cached: list = []
        with monkeypatch.context() as mp:
            mp.setattr(
                adapter,
                "cache_image_from_bytes",
                lambda data, ext: cached.append(data) or "/tmp/x.png",
            )
            assert await fake_client._cache_image_attachment(
                {"type": "image", "url": "https://cdn.max.ru/x.png"}
            ) is None
        assert cached == []
