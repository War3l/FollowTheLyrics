import logging
import os
import ssl
import sys
from collections.abc import Callable
from collections.abc import MutableMapping

from followthelyrics.config import settings

logger = logging.getLogger(__name__)

BUNDLE_CANDIDATES = (
    "/etc/ssl/certs/ca-certificates.crt",
    "/etc/pki/tls/certs/ca-bundle.crt",
    "/etc/ssl/ca-bundle.pem",
    "/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem",
    "/etc/ssl/cert.pem",
)


def find_bundle(exists: Callable[[str], bool] = os.path.isfile) -> str | None:
    return next((path for path in BUNDLE_CANDIDATES if exists(path)), None)


def point_openssl_at_system_store(
    env: MutableMapping[str, str],
    exists: Callable[[str], bool] = os.path.isfile,
) -> str | None:
    if env.get("SSL_CERT_FILE"):
        return None
    bundle = find_bundle(exists)
    if bundle is None:
        logger.warning("no system certificate bundle found")
        return None
    env["SSL_CERT_FILE"] = bundle
    env.setdefault("SSL_CERT_DIR", os.path.dirname(bundle))
    return bundle


def setup() -> None:
    if not (settings.FROZEN and sys.platform.startswith("linux")):
        return
    bundle = point_openssl_at_system_store(os.environ)
    if bundle:
        logger.info("certificates loaded from %s", bundle)


def is_verification_error(error: BaseException) -> bool:
    reason = getattr(error, "reason", error)
    return isinstance(reason, ssl.SSLCertVerificationError)
