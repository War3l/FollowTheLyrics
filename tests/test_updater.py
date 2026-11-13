import pytest

from followthelyrics.system import updater


@pytest.mark.parametrize(
    ("text", "parsed"),
    [
        ("1.7.1", (1, 7, 1)),
        ("v2.0", (2, 0)),
        ("V1.2.3-beta", (1, 2, 3)),
        ("1.x", (1, 0)),
    ],
)
def test_parse_version(text, parsed):
    assert updater.parse_version(text) == parsed


@pytest.mark.parametrize(
    ("candidate", "current", "newer"),
    [
        ("1.7.2", "1.7.1", True),
        ("1.10.0", "1.9.9", True),
        ("v1.7", "1.7.0", False),
        ("1.7.0.1", "1.7", True),
        ("1.6.9", "1.7.0", False),
    ],
)
def test_is_newer(candidate, current, newer):
    assert updater.is_newer(candidate, current) is newer


def test_current_version_reads_the_packaged_file():
    assert updater.parse_version(updater.current_version()) > (0,)


def test_current_version_can_be_faked(monkeypatch):
    monkeypatch.setenv("FTL_FAKE_VERSION", "9.9.9")

    assert updater.current_version() == "9.9.9"
