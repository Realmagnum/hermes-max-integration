"""SSL utilities for MAX API integration.

Provides preconfigured SSLContext including Russian Trusted Root CA
(Минцифры) certificates bundled with the plugin to ensure seamless
connection to platform-api2.max.ru on any OS without requiring system-level
certificate installation.
"""

from __future__ import annotations

import logging
from pathlib import Path
import ssl
from typing import Optional

try:
    import certifi
except ImportError:  # pragma: no cover
    certifi = None

logger = logging.getLogger(__name__)

_CA_BUNDLE_FILENAME = "mincifry_bundle.pem"


def get_mincifry_bundle_path() -> Optional[Path]:
    """Return path to the bundled MinCifry certificate authority file."""
    # Look in assets/certs relative to this file's parent or package root
    candidate = Path(__file__).resolve().parent / "assets" / "certs" / _CA_BUNDLE_FILENAME
    if candidate.exists():
        return candidate
    return None


def get_max_ssl_context() -> ssl.SSLContext:
    """Create an SSLContext configured with default CA certificates plus MinCifry CA."""
    try:
        if certifi:
            ctx = ssl.create_default_context(cafile=certifi.where())
        else:
            ctx = ssl.create_default_context()
    except Exception as exc:
        logger.debug("Failed to create default SSL context with certifi: %s", exc)
        ctx = ssl.create_default_context()

    bundle_path = get_mincifry_bundle_path()
    if bundle_path and bundle_path.exists():
        try:
            ctx.load_verify_locations(cafile=str(bundle_path))
            logger.debug("Loaded MinCifry root CA bundle from %s", bundle_path)
        except Exception as exc:
            logger.warning("Could not load MinCifry CA bundle from %s: %s", bundle_path, exc)

    return ctx
