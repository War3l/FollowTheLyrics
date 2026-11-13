import os

import pytest

from followthelyrics.desktop import ports
from followthelyrics.desktop.linux import boot
from followthelyrics.desktop.linux import session

mpris = pytest.importorskip("followthelyrics.desktop.linux.mpris")

SPOTIFY = {
    "PlaybackStatus": "Paused",
    "Position": 27_098_000,
    "Metadata": {
        "xesam:title": "Choral Chambers",
        "xesam:artist": ["Christopher Larkin"],
        "xesam:album": "Silksong",
        "mpris:length": 163_564_000,
        "mpris:artUrl": "https://i.scdn.co/image/abc",
        "xesam:url": "https://open.spotify.com/track/abc",
    },
}
FIREFOX = {
    "PlaybackStatus": "Playing",
    "Position": 0,
    "Metadata": {
        "xesam:title": "Clip",
        "xesam:artist": ["Chaine - Topic"],
        "xesam:url": "https://www.youtube.com/watch?v=abc",
    },
}


class FakeGuard:
    def __init__(self, refused=()):
        self.refused = set(refused)
        self.calls = []

    def allows(self, app_id, title, artist):
        self.calls.append((app_id, title, artist))
        return app_id not in self.refused, "site-" + app_id


def test_player_of_reads_mpris_properties():
    player = mpris.player_of("spotify", SPOTIFY)

    assert player.title == "Choral Chambers"
    assert player.artist == "Christopher Larkin"
    assert player.duration == pytest.approx(163.564)
    assert player.position == pytest.approx(27.098)
    assert not player.playing
    assert player.art_url == "https://i.scdn.co/image/abc"


def test_player_of_survives_empty_properties():
    player = mpris.player_of("vlc", {})

    assert player.title == ""
    assert player.duration == 0.0


def test_pick_prefers_playing_and_skips_blocked_and_refused():
    players = [
        mpris.player_of("spotify", SPOTIFY),
        mpris.player_of("firefox.instance_1", FIREFOX),
    ]

    picked, site = mpris.pick(players, (), FakeGuard())
    assert picked.app_id == "firefox.instance_1"
    assert site == "site-firefox.instance_1"

    picked, _site = mpris.pick(players, {"firefox.instance_1"}, None)
    assert picked.app_id == "spotify"

    guard = FakeGuard(refused={"firefox.instance_1"})
    picked, _site = mpris.pick(players, (), guard)
    assert picked.app_id == "spotify"


def test_site_hint_uses_page_host_for_known_sites():
    youtube = mpris.player_of("firefox.instance_1", FIREFOX)
    unknown = mpris.player_of("vlc", {"Metadata": {"xesam:artist": "Moi"}})

    assert mpris.site_hint(youtube) == "www.youtube.com"
    assert mpris.site_hint(unknown) == "Moi"


def test_now_playing_cleans_artist():
    player = mpris.player_of("firefox.instance_1", FIREFOX)

    playing = mpris.now_playing_of(player, "youtube")

    assert playing.artist == "Chaine"
    assert playing.playing
    assert playing.site == "youtube"


def test_load_cover_reads_local_files_and_rejects_other_schemes(tmp_path):
    art = tmp_path / "cover.jpg"
    art.write_bytes(b"\xff\xd8data")

    assert mpris.load_cover(art.as_uri()) == b"\xff\xd8data"
    assert mpris.load_cover((tmp_path / "absent.jpg").as_uri()) is None
    assert mpris.load_cover("ftp://example.com/cover.jpg") is None


def test_xdg_autostart_round_trip(tmp_path):
    autostart = session.XdgAutostart("FollowTheLyrics", str(tmp_path))
    (tmp_path / "LyricsOverlay.desktop").write_text("[Desktop Entry]\n")

    assert autostart.command() == ""
    assert autostart.enable('"/opt/ftl/FollowTheLyrics" --minimized')
    assert autostart.command() == '"/opt/ftl/FollowTheLyrics" --minimized'
    assert autostart.drop_legacy(["LyricsOverlay", "Absent"])
    assert not (tmp_path / "LyricsOverlay.desktop").exists()
    assert autostart.disable()
    assert autostart.command() == ""


def test_desktop_entry_shortcut_points_to_target(tmp_path):
    shortcuts = session.DesktopEntryShortcuts("FollowTheLyrics", "Old")
    link = str(tmp_path / "bureau" / "FollowTheLyrics.desktop")

    assert shortcuts.create("/opt/mon dossier/FollowTheLyrics", link)
    assert shortcuts.target(link) == "/opt/mon dossier/FollowTheLyrics"
    assert os.access(link, os.X_OK)


def test_config_home_follows_xdg():
    assert session.config_home({"XDG_CONFIG_HOME": "/x"}) == "/x"


@pytest.mark.parametrize(
    ("environ", "plugin"),
    [
        ({"WAYLAND_DISPLAY": "wayland-1", "DISPLAY": ":1"}, "xcb"),
        ({"WAYLAND_DISPLAY": "wayland-1"}, None),
        ({"DISPLAY": ":0"}, None),
        (
            {
                "WAYLAND_DISPLAY": "wayland-1",
                "DISPLAY": ":1",
                "QT_QPA_PLATFORM": "wayland",
            },
            None,
        ),
    ],
)
def test_platform_plugin_prefers_xwayland(environ, plugin):
    assert boot.platform_plugin(environ) == plugin


def test_x11_key_mapping():
    x11 = pytest.importorskip("followthelyrics.desktop.linux.x11")

    assert x11.keysym_name(ord("L")) == "l"
    assert x11.keysym_name(0x70) == "F1"
    assert x11.keysym_name(0x87) == "F24"
    assert x11.keysym_name(0x63) == "KP_3"
    assert x11.keysym_name(0x26) == "Up"
    assert x11.keysym_name(0xFE) is None
    mask = x11.modifier_mask(ports.MOD_CTRL | ports.MOD_ALT)
    assert mask == x11.X.ControlMask | x11.X.Mod1Mask
