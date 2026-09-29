"""SEC-02 regressions: the bot token must not follow arbitrary attachment URLs.

Attachment download URLs arrive inside inbound events (long polling *or* an
unprotected webhook), so the sender of a message can influence them. Before
this fix the audio/image/document downloads reused the shared API client,
whose default ``Authorization`` header — plus a per-request copy of it — was
sent to whatever origin the attachment pointed at. These tests pin the
post-fix contract:

* the download client carries no default credentials;
* ``Authorization`` is added per request only for explicitly trusted HTTPS
  origins (MAX infrastructure or an operator-configured host);
* redirects are not followed, so a trusted URL cannot bounce the token to an
  attacker-controlled host;
* the token never reaches logs, even when the transport error echoes it.

Everything runs over ``httpx.MockTransport`` — no real network is touched.
"""

from __future__ import annotations

import contextlib
import logging

import httpx
import pytest
from gateway.config import PlatformConfig

import adapter
from mixins.media_upload import _ALLOWED_UPLOAD_HOSTS

TOKEN = "leak-canary-token-0123456789"
UNTRUSTED_URL = "https://attacker.example.com/attachment.bin"

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
OGG_BYTES = b"OggS\x00\x02" + b"\x00" * 64
PDF_BYTES = b"%PDF-1.4\n" + b"0" * 64

# kind -> (body, content-type) served by the mock transport
_BODY = {
    "audio": (OGG_BYTES, "audio/ogg"),
    "image": (PNG_BYTES, "image/png"),
    "document": (PDF_BYTES, "application/pdf"),
}


@pytest.fixture(autouse=True)
def _clean_trust_env(monkeypatch):
    """Keep origin policy deterministic; network is always mocked."""
    monkeypatch.delenv("MAX_TRUSTED_DOWNLOAD_HOSTS", raising=False)
    monkeypatch.delenv("MAX_DOWNLOAD_ALLOWED_HOSTS", raising=False)
    monkeypatch.setattr(
        adapter.MaxAdapter,
        "_resolve_public_addresses",
        staticmethod(lambda _host, _port: ["93.184.216.34"]),
    )


def make_adapter(**extra) -> adapter.MaxAdapter:
    """Build an adapter with a distinctive token and optional extra config."""
    cfg = PlatformConfig(
        enabled=True,
        token=TOKEN,
        extra={"token": TOKEN, **extra},
    )
    a = adapter.MaxAdapter(cfg)
    a._token = TOKEN
    return a


def attach_transport(a, requests, body, content_type, redirect_from=None):
    """Attach a real httpx client over MockTransport and record requests.

    The client is installed as BOTH the API client and the download client so
    that the pre-fix code path (which used ``_http_client`` for downloads)
    reaches the same transport as the fixed one (``_download_client``). The
    client is deliberately created *without* default credentials — the
    per-request ``Authorization`` header is what these tests inspect.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        # The production code pins the connection to a validated IP, so the
        # request URL no longer contains the original hostname.
        if redirect_from is not None:
            return httpx.Response(
                302, headers={"location": "https://attacker.example.com/steal"}
            )
        return httpx.Response(200, content=body, headers={"content-type": content_type})

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    )
    a._download_client = client
    a._http_client = client
    return client


async def download(a, url, kind):
    """Drive the production download path for *kind*; caching errors ignored."""
    if kind == "audio":
        return await a._cache_audio_attachment(
            {"type": "audio", "payload": {"url": url}}, "audio"
        )
    if kind == "image":
        return await a._cache_image_attachment({"type": "image", "payload": {"url": url}})
    return await a._cache_document_attachment(
        {"type": "file", "filename": "report.pdf", "payload": {"url": url}}
    )


async def run_download(a, url, kind, requests, redirect_from=None):
    """Run one download against a recording transport and return the requests."""
    body, content_type = _BODY[kind]
    client = attach_transport(a, requests, body, content_type, redirect_from)
    try:
        with contextlib.suppress(Exception):
            await download(a, url, kind)
    finally:
        await client.aclose()
    return requests


def assert_token_absent(requests):
    assert requests, "download was not attempted — test setup is broken"
    for request in requests:
        assert "authorization" not in request.headers, (
            f"bot token header leaked to {request.url}"
        )
        assert TOKEN not in str(request.headers), "token leaked via headers"
        assert TOKEN not in str(request.url), "token leaked via URL"


# ── The leak itself ───────────────────────────────────────────────────────


class TestTokenNotForwardedToUntrustedOrigins:
    @pytest.mark.parametrize("kind", ["audio", "image", "document"])
    async def test_no_authorization_for_third_party_origin(self, kind):
        a = make_adapter()
        requests = await run_download(a, UNTRUSTED_URL, kind, [])
        assert_token_absent(requests)

    async def test_no_authorization_for_max_lookalike_host(self):
        """Suffix matching must respect the dot boundary."""
        for url in (
            "https://evil-max.ru/a.png",
            "https://cdn.max.ru.attacker.example.com/a.png",
            "https://evil-cdn-max.ru/a.png",
            "https://cdn-max.ru.attacker.example.com/a.png",
            "https://notcdn-max.ru/a.png",
        ):
            a = make_adapter()
            requests = await run_download(a, url, "image", [])
            assert_token_absent(requests)

    async def test_trusted_host_over_plain_http_gets_no_authorization(self):
        a = make_adapter(trusted_download_hosts="files.partner.example")
        requests = await run_download(a, "http://files.partner.example/a.png", "image", [])
        # Credential trust is HTTPS-only, and media downloads themselves reject
        # plaintext HTTP before the download client can issue a request.
        assert requests == []

    async def test_download_client_built_by_connect_has_no_default_credentials(self, monkeypatch):
        """connect() must build a separate, credential-free download client."""
        created: list[dict] = []

        class RecordingClient:
            def __init__(self, **kwargs):
                created.append(kwargs)

            async def get(self, url, **kwargs):
                return httpx.Response(401, request=httpx.Request("GET", url))

            async def aclose(self):
                pass

        monkeypatch.setattr(adapter.httpx, "AsyncClient", RecordingClient)
        a = make_adapter()
        assert await a.connect() is False  # 401 → fatal, no polling started

        api_clients = [
            kw for kw in created if "Authorization" in (kw.get("headers") or {})
        ]
        download_clients = [
            kw for kw in created if "Authorization" not in (kw.get("headers") or {})
        ]
        assert len(api_clients) == 1, created
        assert len(download_clients) == 1, (
            "connect() must create exactly one credential-free attachment client"
        )
        assert download_clients[0].get("follow_redirects") is False


# ── Explicitly trusted origins ────────────────────────────────────────────


class TestTrustedOriginsReceiveAuthorization:
    def test_config_entries_are_normalized(self):
        a = make_adapter(
            trusted_download_hosts="https://Files.Partner.Example:8443/path, *.cdn.example"
        )
        assert a._trusted_download_hosts == {
            "files.partner.example",
            "*.cdn.example",
        }

    def test_default_trust_list_is_empty(self, monkeypatch):
        monkeypatch.delenv("MAX_TRUSTED_DOWNLOAD_HOSTS", raising=False)
        assert make_adapter()._trusted_download_hosts == set()

    async def test_host_match_ignores_case_and_trailing_dot(self):
        a = make_adapter(trusted_download_hosts="Files.Partner.Example.")
        requests = await run_download(
            a, "https://FILES.partner.example./a.png", "image", []
        )
        assert requests[0].headers["authorization"] == TOKEN

    async def test_max_cdn_is_trusted_by_default(self):
        a = make_adapter()
        requests = await run_download(a, "https://cdn.max.ru/a.png", "image", [])
        assert requests[0].headers["authorization"] == TOKEN

    async def test_cdn_max_ru_subdomains_are_trusted_by_default(self):
        """`.cdn-max.ru` is MAX infrastructure on the upload path too."""
        for url in (
            "https://files.cdn-max.ru/a.png",
            "https://cdn-max.ru/a.png",  # apex is not covered, see below
        ):
            a = make_adapter()
            requests = await run_download(a, url, "image", [])
            if url.startswith("https://files."):
                assert requests[0].headers["authorization"] == TOKEN
            else:
                # Dot-boundary parity with the upload path: the apex itself is
                # never allow-listed, only hosts under the suffix.
                assert_token_absent(requests)

    @pytest.mark.parametrize("host", sorted(_ALLOWED_UPLOAD_HOSTS))
    async def test_known_upload_hosts_are_download_trusted(self, host):
        """Every host the plugin uploads to must also be safe to download from.

        Keeps the SEC-02 download trust list from drifting behind the upload
        allow-list (the `.cdn-max.ru` gap this test now pins).
        """
        a = make_adapter()
        requests = await run_download(a, f"https://{host}/a.png", "image", [])
        assert requests[0].headers["authorization"] == TOKEN

    async def test_configured_host_is_trusted(self):
        a = make_adapter(trusted_download_hosts="files.partner.example")
        requests = await run_download(a, "https://files.partner.example/a.png", "image", [])
        assert requests[0].headers["authorization"] == TOKEN

    async def test_env_configured_host_is_trusted(self, monkeypatch):
        monkeypatch.setenv("MAX_TRUSTED_DOWNLOAD_HOSTS", "files.partner.example")
        a = make_adapter()
        requests = await run_download(a, "https://files.partner.example/a.png", "image", [])
        assert requests[0].headers["authorization"] == TOKEN

    async def test_wildcard_entry_matches_subdomains_only(self):
        a = make_adapter(trusted_download_hosts="*.partner.example")
        requests = await run_download(a, "https://cdn.partner.example/a.png", "image", [])
        assert requests[0].headers["authorization"] == TOKEN

        for url in (
            "https://partner.example/a.png",
            "https://notpartner.example/a.png",
        ):
            a = make_adapter(trusted_download_hosts="*.partner.example")
            requests = await run_download(a, url, "image", [])
            assert_token_absent(requests)


# ── Redirects ─────────────────────────────────────────────────────────────


class TestRedirects:
    async def test_trusted_redirect_is_not_followed(self):
        """A trusted host answering 302 must not hand the token to the target."""
        a = make_adapter()
        url = "https://cdn.max.ru/redirect"
        requests = await run_download(
            a, url, "image", [], redirect_from=url
        )
        assert len(requests) == 1, "download followed a redirect with credentials"
        assert requests[0].headers["authorization"] == TOKEN
        assert all("attacker.example.com" not in str(r.url) for r in requests)


# ── Secrets in logs ───────────────────────────────────────────────────────


class TestTokenNeverLogged:
    @pytest.mark.parametrize("kind", ["audio", "image", "document"])
    async def test_transport_error_message_is_redacted(self, kind, caplog):
        a = make_adapter()
        requests = []

        def exploding_handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            raise httpx.ConnectError(
                f"cannot connect to {request.url} (Authorization: {TOKEN})",
                request=request,
            )

        client = httpx.AsyncClient(
            transport=httpx.MockTransport(exploding_handler), follow_redirects=False
        )
        a._download_client = client
        a._http_client = client
        caplog.set_level(logging.WARNING, logger=adapter.logger.name)
        try:
            with contextlib.suppress(Exception):
                await download(a, UNTRUSTED_URL, kind)
        finally:
            await client.aclose()

        assert requests, "download was not attempted — test setup is broken"
        assert TOKEN not in caplog.text, "bot token appeared in the logs"
