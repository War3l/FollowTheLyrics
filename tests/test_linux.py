import os
import time

import pytest

from followthelyrics.desktop import ports
from followthelyrics.desktop.linux import boot
from followthelyrics.desktop.linux import session

mpris = pytest.importorskip("followthelyrics.desktop.linux.mpris")
QtWidgets = pytest.importorskip("PyQt6.QtWidgets")


@pytest.fixture(autouse=True)
def qt_application():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app
    app.processEvents()


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
        (
            {
                "WAYLAND_DISPLAY": "wayland-1",
                "DISPLAY": ":1",
                "QT_QPA_PLATFORM": "wayland;xcb",
            },
            "xcb",
        ),
        (
            {
                "WAYLAND_DISPLAY": "wayland-1",
                "DISPLAY": ":1",
                "QT_QPA_PLATFORM": "wayland;offscreen",
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


class FakeReply:
    def __init__(self, value=None):
        self._value = value
        self.isValid = lambda: value is not None
        self.value = lambda: value


class FakeInterface:
    def __init__(self, bus):
        self.serviceOwner = lambda service: FakeReply(bus.owners.get(service))


class FakeBus:
    def __init__(self, owners=None):
        self.owners = dict(owners or {})
        self.links = []
        self.isConnected = lambda: True
        self.interface = lambda: FakeInterface(self)

    def connect(self, service, path, interface, name, signature, slot):
        self.links.append((service, name, path, interface))
        return True

    def disconnect(self, service, path, interface, name, signature, slot):
        self.links.remove((service, name, path, interface))
        return True


def properties_of(service):
    return SPOTIFY if service.rsplit(".", 1)[-1] in ("spotify", "vlc") else {}


_OPENED_READERS = []


@pytest.fixture(autouse=True)
def close_opened_readers():
    yield
    while _OPENED_READERS:
        _OPENED_READERS.pop().close()


@pytest.fixture(autouse=True)
def no_initial_state(monkeypatch):
    monkeypatch.setattr(mpris, "_get_all", lambda bus, service: None)


def reader_with(monkeypatch, players, bus=None):
    reader = mpris.MprisSession(bus or FakeBus())
    _OPENED_READERS.append(reader)
    monkeypatch.setattr(reader, "_services", lambda: players)
    monkeypatch.setattr(reader, "_properties", properties_of)
    return reader


def test_each_player_is_dated_right_after_its_own_reading(monkeypatch):
    now = [0.0]

    def slow_properties(service):
        now[0] += 1.0
        return properties_of(service)

    monkeypatch.setattr(mpris.time, "monotonic", lambda: now[0])
    reader = reader_with(
        monkeypatch, {"spotify": "org.mpris.MediaPlayer2.spotify", "vlc": "vlc"}
    )
    monkeypatch.setattr(reader, "_properties", slow_properties)
    np = reader.now_playing(frozenset(), None)
    assert np.title == "Choral Chambers"
    assert np.read_at == 1.0


FIREFOX_SERVICES = {"firefox": "org.mpris.MediaPlayer2.firefox"}


def test_a_playing_player_read_on_a_whole_second_is_probed(monkeypatch):
    calls = []
    reader = reader_with(monkeypatch, FIREFOX_SERVICES)
    monkeypatch.setattr(reader, "_properties", lambda service: FIREFOX)
    monkeypatch.setattr(reader._listener, "probe", lambda: calls.append(True))
    reader.now_playing(frozenset(), None)
    assert calls == [True]


def test_a_playing_player_read_between_seconds_is_not_probed(monkeypatch):
    calls = []
    reader = reader_with(monkeypatch, FIREFOX_SERVICES)
    monkeypatch.setattr(reader._listener, "probe", lambda: calls.append(True))
    fractional = {**FIREFOX, "Position": 12_345_000}
    monkeypatch.setattr(reader, "_properties", lambda service: fractional)
    reader.now_playing(frozenset(), None)
    assert calls == []


def test_the_owner_of_the_picked_player_is_followed(monkeypatch):
    bus = FakeBus({"org.mpris.MediaPlayer2.spotify": ":1.42"})
    reader = reader_with(
        monkeypatch, {"spotify": "org.mpris.MediaPlayer2.spotify"}, bus
    )
    reader.now_playing(frozenset(), None)
    assert sorted(name for _, name, _, _ in bus.links) == [
        "PropertiesChanged",
        "Seeked",
    ]
    assert {service for service, *_ in bus.links} == {":1.42"}


def test_a_player_restarted_under_a_new_owner_is_followed_again(monkeypatch):
    bus = FakeBus({"org.mpris.MediaPlayer2.spotify": ":1.42"})
    reader = reader_with(
        monkeypatch, {"spotify": "org.mpris.MediaPlayer2.spotify"}, bus
    )
    reader.now_playing(frozenset(), None)
    bus.owners["org.mpris.MediaPlayer2.spotify"] = ":1.77"
    reader.now_playing(frozenset(), None)
    assert {service for service, *_ in bus.links} == {":1.77"}
    assert len(bus.links) == 2


def test_no_player_means_nothing_is_followed(monkeypatch):
    bus = FakeBus({"org.mpris.MediaPlayer2.spotify": ":1.42"})
    reader = reader_with(
        monkeypatch, {"spotify": "org.mpris.MediaPlayer2.spotify"}, bus
    )
    reader.now_playing(frozenset(), None)
    monkeypatch.setattr(reader, "_services", dict)
    assert reader.now_playing(frozenset(), None) is None
    assert bus.links == []


def test_closing_the_session_drops_its_subscriptions(monkeypatch):
    bus = FakeBus({"org.mpris.MediaPlayer2.spotify": ":1.42"})
    reader = reader_with(
        monkeypatch, {"spotify": "org.mpris.MediaPlayer2.spotify"}, bus
    )
    reader.now_playing(frozenset(), None)
    reader.close()
    assert bus.links == []


def test_a_playback_change_of_the_followed_player_wakes_the_wait(monkeypatch):
    bus = FakeBus({"org.mpris.MediaPlayer2.spotify": ":1.42"})
    reader = reader_with(
        monkeypatch, {"spotify": "org.mpris.MediaPlayer2.spotify"}, bus
    )
    reader.now_playing(frozenset(), None)
    reader._listener.changed(mpris.PLAYER, {"PlaybackStatus": "Paused"}, [])
    started = time.monotonic()
    reader.wait(5.0)
    assert time.monotonic() - started < 1.0
    assert reader.now_playing(frozenset(), None).seek is None


def test_a_seek_of_the_player_being_left_is_not_kept(monkeypatch):
    bus = FakeBus(
        {
            "org.mpris.MediaPlayer2.spotify": ":1.42",
            "org.mpris.MediaPlayer2.vlc": ":1.9",
        }
    )
    reader = reader_with(
        monkeypatch, {"spotify": "org.mpris.MediaPlayer2.spotify"}, bus
    )
    reader.now_playing(frozenset(), None)
    reader._listener.seeked(5_000_000)
    monkeypatch.setattr(
        reader, "_services", lambda: {"vlc": "org.mpris.MediaPlayer2.vlc"}
    )
    assert reader.now_playing(frozenset(), None).seek is None
    assert {service for service, *_ in bus.links} == {":1.9"}


def test_a_seek_of_the_followed_player_is_attached_to_the_next_reading(
    monkeypatch,
):
    bus = FakeBus({"org.mpris.MediaPlayer2.spotify": ":1.42"})
    reader = reader_with(
        monkeypatch, {"spotify": "org.mpris.MediaPlayer2.spotify"}, bus
    )
    reader.now_playing(frozenset(), None)
    reader._listener.seeked(5_000_000)
    np = reader.now_playing(frozenset(), None)
    assert np.seek.position == pytest.approx(5.0)
    assert reader.now_playing(frozenset(), None).seek is None


@pytest.mark.parametrize(
    ("value", "position"),
    [(0, 0.0), (5_000_000, 5.0), (86_400_000_000, 86_400.0)],
)
def test_a_seeked_position_is_read_in_microseconds(value, position):
    seek = mpris.seek_of(value, 3.0)
    assert seek.position == pytest.approx(position)
    assert seek.at == 3.0


@pytest.mark.parametrize(
    "value",
    [-1, 86_400_000_001, 1.5, "5", None, True, float("nan")],
)
def test_an_invalid_seeked_position_is_dropped(value):
    assert mpris.seek_of(value, 3.0) is None


def test_the_player_service_is_kept_on_the_player():
    assert mpris.player_of("spotify", SPOTIFY, service="s").service == "s"


def next_track_of(monkeypatch, reader):
    following = dict(
        SPOTIFY, Metadata={"xesam:title": "Next", "xesam:artist": "Someone"}
    )
    monkeypatch.setattr(reader, "_properties", lambda service: following)
    reader._listener.changed(
        mpris.PLAYER,
        {"Metadata": {"xesam:title": "Next", "xesam:artist": "Someone"}},
        [],
    )


def test_a_seek_of_the_previous_track_is_dropped(monkeypatch):
    bus = FakeBus({"org.mpris.MediaPlayer2.spotify": ":1.42"})
    reader = reader_with(
        monkeypatch, {"spotify": "org.mpris.MediaPlayer2.spotify"}, bus
    )
    reader.now_playing(frozenset(), None)
    reader._listener.seeked(5_000_000)
    next_track_of(monkeypatch, reader)
    assert reader.now_playing(frozenset(), None).seek is None


def test_a_seek_after_the_track_change_is_kept(monkeypatch):
    bus = FakeBus({"org.mpris.MediaPlayer2.spotify": ":1.42"})
    reader = reader_with(
        monkeypatch, {"spotify": "org.mpris.MediaPlayer2.spotify"}, bus
    )
    reader.now_playing(frozenset(), None)
    next_track_of(monkeypatch, reader)
    reader._listener.seeked(7_000_000)
    seek = reader.now_playing(frozenset(), None).seek
    assert seek.position == pytest.approx(7.0)
    assert seek.track_key == ("next", "someone")


@pytest.mark.parametrize(
    ("rate", "speed"), [(1.5, 1.5), (0.0, 1.0), ("x", 1.0), (None, 1.0)]
)
def test_the_player_speed_is_read_from_mpris(rate, speed):
    properties = dict(SPOTIFY, Rate=rate)
    player = mpris.player_of("spotify", properties)
    assert mpris.now_playing_of(player, "").speed == speed


def test_a_seek_received_before_the_wait_ends_it_at_once(monkeypatch):
    bus = FakeBus({"org.mpris.MediaPlayer2.spotify": ":1.42"})
    reader = reader_with(
        monkeypatch, {"spotify": "org.mpris.MediaPlayer2.spotify"}, bus
    )
    reader.now_playing(frozenset(), None)
    reader._listener.seeked(5_000_000)
    started = time.monotonic()
    reader.wait(5.0)
    assert time.monotonic() - started < 1.0


def test_a_seek_carries_the_rate_last_played(monkeypatch):
    reader = reader_with(monkeypatch, {})
    reader._listener.changed(mpris.PLAYER, {"Rate": 2.0}, [])
    reader._listener.changed(mpris.PLAYER, {"Rate": 0.0}, [])
    reader._listener.seeked(5_000_000)
    assert reader._events.take_seek().speed == 2.0


def test_a_burst_of_playback_changes_wakes_the_wait_once(monkeypatch):
    now = [10.0]
    monkeypatch.setattr(mpris.time, "monotonic", lambda: now[0])
    reader = reader_with(monkeypatch, {})
    reader._events.begin()
    reader._listener.changed(mpris.PLAYER, {"PlaybackStatus": "Paused"}, [])
    assert reader._events.ready()
    reader._events.begin()
    reader._listener.changed(mpris.PLAYER, {"PlaybackStatus": "Playing"}, [])
    assert not reader._events.ready()
    now[0] += 1.0
    reader._listener.changed(mpris.PLAYER, {"PlaybackStatus": "Paused"}, [])
    assert reader._events.ready()
