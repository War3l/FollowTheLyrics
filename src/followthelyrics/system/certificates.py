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
    chosen = env.get("SSL_CERT_FILE")
    if chosen and exists(chosen):
        return None
    bundle = find_bundle(exists)
    if bundle is None:
        logger.warning("no system certificate bundle found")
        return None
    if chosen:
        logger.warning(
            "SSL_CERT_FILE %s does not exist, using %s", chosen, bundle
        )
    env["SSL_CERT_FILE"] = bundle
    return bundle


def setup() -> None:
    if not (settings.FROZEN and sys.platform.startswith("linux")):
        return
    bundle = point_openssl_at_system_store(os.environ)
    if bundle:
        logger.info("certificates loaded from %s", bundle)


def is_verification_error(error: BaseException) -> bool:
    return isinstance(error, ssl.SSLCertVerificationError) or isinstance(
        getattr(error, "reason", None), ssl.SSLCertVerificationError
    )
