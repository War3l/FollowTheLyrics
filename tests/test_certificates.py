import ssl
import urllib.error

from followthelyrics.system import certificates


def only(*present):
    return lambda path: path in present


def test_fedora_bundle_is_used_when_debian_one_is_missing():
    env = {}
    bundle = certificates.point_openssl_at_system_store(
        env, only("/etc/pki/tls/certs/ca-bundle.crt")
    )
    assert bundle == "/etc/pki/tls/certs/ca-bundle.crt"
    assert env == {
        "SSL_CERT_FILE": "/etc/pki/tls/certs/ca-bundle.crt",
        "SSL_CERT_DIR": "/etc/pki/tls/certs",
    }


def test_first_matching_bundle_wins():
    present = only("/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt")
    assert certificates.find_bundle(present) == (
        "/etc/ssl/certs/ca-certificates.crt"
    )


def test_user_choice_is_kept():
    env = {"SSL_CERT_FILE": "/opt/my-ca.pem"}
    assert (
        certificates.point_openssl_at_system_store(
            env, only("/etc/ssl/cert.pem")
        )
        is None
    )
    assert env == {"SSL_CERT_FILE": "/opt/my-ca.pem"}


def test_existing_cert_dir_is_kept():
    env = {"SSL_CERT_DIR": "/opt/certs"}
    certificates.point_openssl_at_system_store(env, only("/etc/ssl/cert.pem"))
    assert env == {
        "SSL_CERT_FILE": "/etc/ssl/cert.pem",
        "SSL_CERT_DIR": "/opt/certs",
    }


def test_nothing_changes_without_a_bundle():
    env = {}
    assert certificates.point_openssl_at_system_store(env, only()) is None
    assert env == {}


def test_verification_error_is_recognised_through_urlerror():
    wrapped = urllib.error.URLError(ssl.SSLCertVerificationError(1, "bad"))
    assert certificates.is_verification_error(wrapped)
    assert not certificates.is_verification_error(
        urllib.error.URLError(OSError("network down"))
    )
