import pytest

from followthelyrics.playback import sites


@pytest.mark.parametrize(
    ("tab", "sid"),
    [
        ("Song - YouTube Music", "ytmusic"),
        ("Song - YouTube", "youtube"),
        ("Song • Artist - Deezer", "deezer"),
        ("Just a page", None),
    ],
)
def test_site_of(tab, sid):
    assert sites.site_of(tab) == sid


@pytest.mark.parametrize(
    ("artist", "sid"),
    [
        ("music.youtube.com", "ytmusic"),
        ("www.youtube.com", "youtube"),
        ("open.spotify.com", "spotify"),
        ("example.org", sites.OTHER),
        ("Daft Punk", None),
    ],
)
def test_site_of_host(artist, sid):
    assert sites.site_of_host(artist) == sid


def test_core_title_drops_the_browser_suffix():
    assert (
        sites.core_title("Song - YouTube - Google Chrome") == "Song - YouTube"
    )
    assert sites.core_title("Plain title") == "Plain title"


def test_browser_detection():
    assert sites.is_browser("chrome.exe")
    assert not sites.is_browser("Spotify.exe")
    assert sites.browser_of("") is None


def guard(tabs, **kwargs):
    return sites.SiteGuard(titles=lambda exes: tabs, **kwargs)


def test_guard_matches_the_tab_playing_the_title():
    g = guard(["Song - YouTube Music - Google Chrome"], off={"ytmusic"})

    assert g.allows("chrome.exe", "Song", "Artist") == (False, "ytmusic")


def test_guard_lets_desktop_apps_through():
    g = guard([], off={"spotify"})

    assert g.allows("Spotify.exe", "Song", "Artist") == (True, "")


def test_guard_blocks_unknown_sites_unless_allowed():
    tabs = ["Some page - Google Chrome"]

    assert guard(tabs).allows("chrome.exe", "Song", "")[0] is False
    assert guard(tabs, other=True).allows("chrome.exe", "Song", "")[0] is True
