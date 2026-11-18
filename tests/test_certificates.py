import logging
import os
import ssl
import urllib.error
import urllib.request

import pytest

from followthelyrics.config import settings
from followthelyrics.lyrics import model
from followthelyrics.lyrics import providers
from followthelyrics.system import certificates
from followthelyrics.system import updater

DEBIAN = "/etc/ssl/certs/ca-certificates.crt"
FEDORA = "/etc/pki/tls/certs/ca-bundle.crt"


def only(*present):
    return lambda path: path in present


def certificate_failure(*args, **kwargs):
    raise urllib.error.URLError(ssl.SSLCertVerificationError(1, "bad"))


def test_fedora_bundle_is_used_when_debian_one_is_missing():
    env = {}
    bundle = certificates.point_openssl_at_system_store(env, only(FEDORA))
    assert bundle == FEDORA
    assert env == {"SSL_CERT_FILE": FEDORA}


@pytest.mark.parametrize(
    ("present", "expected"),
    [
        ((FEDORA, DEBIAN), DEBIAN),
        (("/etc/ssl/cert.pem", FEDORA), FEDORA),
        (
            ("/etc/ssl/cert.pem", "/etc/ssl/ca-bundle.pem"),
            "/etc/ssl/ca-bundle.pem",
        ),
    ],
)
def test_candidates_are_tried_in_order(present, expected):
    assert certificates.find_bundle(only(*present)) == expected


def test_existing_user_choice_is_kept():
    env = {"SSL_CERT_FILE": "/opt/my-ca.pem"}
    present = only("/opt/my-ca.pem", DEBIAN)
    assert certificates.point_openssl_at_system_store(env, present) is None
    assert env == {"SSL_CERT_FILE": "/opt/my-ca.pem"}


def test_missing_user_choice_is_replaced():
    env = {"SSL_CERT_FILE": "/gone/ca.pem"}
    assert (
        certificates.point_openssl_at_system_store(env, only(FEDORA)) == FEDORA
    )
    assert env == {"SSL_CERT_FILE": FEDORA}


def test_nothing_changes_without_a_bundle():
    env = {}
    assert certificates.point_openssl_at_system_store(env, only()) is None
    assert env == {}


@pytest.fixture
def restored_cert_file():
    initial = os.environ.get("SSL_CERT_FILE")
    yield
    assert os.environ.get("SSL_CERT_FILE") == initial


@pytest.mark.parametrize(
    ("frozen", "platform", "applied"),
    [
        (True, "linux", True),
        (False, "linux", False),
        (True, "win32", False),
    ],
)
def test_setup_only_touches_the_packaged_linux_app(
    restored_cert_file, monkeypatch, frozen, platform, applied
):
    monkeypatch.setenv("SSL_CERT_FILE", "")
    monkeypatch.delenv("SSL_CERT_FILE")
    monkeypatch.setattr(settings, "FROZEN", frozen)
    monkeypatch.setattr(certificates.sys, "platform", platform)
    monkeypatch.setattr(certificates, "find_bundle", lambda exists: FEDORA)
    certificates.setup()
    assert (certificates.os.environ.get("SSL_CERT_FILE") == FEDORA) is applied


@pytest.mark.parametrize(
    "error",
    [
        urllib.error.URLError(ssl.SSLCertVerificationError(1, "bad")),
        ssl.SSLCertVerificationError(1, "bad"),
    ],
)
def test_verification_error_is_recognised(error):
    assert certificates.is_verification_error(error)


def test_network_error_is_not_a_verification_error():
    error = urllib.error.URLError(OSError("network down"))
    assert not certificates.is_verification_error(error)


def test_lyrics_certificate_failure_has_its_own_log_line(monkeypatch, caplog):
    monkeypatch.setattr(urllib.request, "urlopen", certificate_failure)
    with caplog.at_level(logging.WARNING):
        assert providers._Session().get_json("https://lrclib.net/x", {}) is None
        assert providers.fetch_liriqo("t", "a") == (None, False)
        assert providers.translate_lines([model.Line(0.0, "bonjour")]) is None
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 3
    assert all("certificate verification failed" in r.message for r in errors)


def test_update_certificate_failure_has_its_own_log_line(monkeypatch, caplog):
    monkeypatch.setattr(updater, "fetch_latest", certificate_failure)
    check = updater.UpdateCheck(type("Release", (), {"asset": "x"})())
    outcomes = []
    check.nothing.connect(outcomes.append)
    with caplog.at_level(logging.WARNING):
        check.run()
    assert outcomes == [True]
    assert [r.levelno for r in caplog.records] == [logging.ERROR]
