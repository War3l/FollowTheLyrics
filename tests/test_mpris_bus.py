import os
import sys
import time
import uuid

import pytest
from PyQt6.QtCore import QCoreApplication
from PyQt6.QtCore import QMetaType
from PyQt6.QtCore import QVariant
from PyQt6.QtDBus import QDBusConnection
from PyQt6.QtDBus import QDBusMessage

if not sys.platform.startswith("linux"):
    pytest.skip("bus de session D-Bus Linux", allow_module_level=True)

mpris = pytest.importorskip("followthelyrics.desktop.linux.mpris")
probe = pytest.importorskip("followthelyrics.playback.probe")
events = pytest.importorskip("followthelyrics.playback.events")

SPOOFER = "ftl-spoof-" + uuid.uuid4().hex[:8]


def require_bus(reason):
    if os.environ.get("CI"):
        pytest.fail(reason)
    pytest.skip(reason)


@pytest.fixture
def bus():
    app = QCoreApplication.instance() or QCoreApplication([])
    connection = QDBusConnection.sessionBus()
    if not connection.isConnected():
        require_bus("pas de bus de session D-Bus")
    service = "org.mpris.MediaPlayer2.ftl" + uuid.uuid4().hex[:8]
    if not connection.registerService(service):
        require_bus("nom de service D-Bus indisponible")
    yield connection, service
    connection.unregisterService(service)
    app.processEvents()


@pytest.fixture
def spoofer():
    connection = QDBusConnection.connectToBus(
        QDBusConnection.BusType.SessionBus, SPOOFER
    )
    yield connection
    QDBusConnection.disconnectFromBus(SPOOFER)


@pytest.fixture
def make_session():
    sessions = []

    def make():
        session = mpris.MprisSession()
        sessions.append(session)
        return session

    yield make
    for session in sessions:
        session.close()


def int64(value):
    variant = QVariant(value)
    assert variant.convert(QMetaType(QMetaType.Type.LongLong.value))
    return variant


def seeked_signal(connection, microseconds):
    message = QDBusMessage.createSignal(
        mpris.OBJECT_PATH, mpris.PLAYER, "Seeked"
    )
    message.setArguments([int64(microseconds)])
    connection.send(message)


def string_list(values):
    variant = QVariant(values)
    assert variant.convert(QMetaType(QMetaType.Type.QStringList.value))
    return variant


def properties_changed(connection, interface, values):
    message = QDBusMessage.createSignal(
        mpris.OBJECT_PATH, mpris.PROPERTIES, "PropertiesChanged"
    )
    message.setArguments(
        [
            interface,
            QVariant({key: QVariant(value) for key, value in values.items()}),
            string_list([]),
        ]
    )
    connection.send(message)


def test_a_seek_of_the_followed_player_is_received_at_once(bus, make_session):
    connection, service = bus
    session = make_session()
    session._follow(service)
    seeked_signal(connection, 5_000_000)
    started = time.monotonic()
    session.wait(5.0)
    assert time.monotonic() - started < 2.0
    assert session._events.take_seek().position == pytest.approx(5.0)


def test_a_seek_sent_by_another_connection_is_not_received(
    bus, spoofer, make_session
):
    _connection, service = bus
    session = make_session()
    session._follow(service)
    seeked_signal(spoofer, 7_000_000)
    started = time.monotonic()
    session.wait(0.5)
    assert time.monotonic() - started >= 0.45
    assert session._events.take_seek() is None


def test_a_seek_is_not_received_once_the_player_is_unfollowed(
    bus, make_session
):
    connection, service = bus
    session = make_session()
    session._follow(service)
    session.close()
    seeked_signal(connection, 9_000_000)
    session.wait(0.3)
    assert session._events.take_seek() is None


def test_a_seek_is_dated_when_it_arrives_not_when_the_poll_ends(
    bus, make_session
):
    connection, service = bus
    session = make_session()
    session._follow(service)
    seeked_signal(connection, 5_000_000)
    emitted = time.monotonic()
    time.sleep(0.6)
    session.wait(2.0)
    assert session._events.take_seek().at - emitted < 0.1


def test_a_playback_change_of_the_followed_player_wakes_the_wait(
    bus, make_session
):
    connection, service = bus
    session = make_session()
    session._follow(service)
    properties_changed(connection, mpris.PLAYER, {"PlaybackStatus": "Paused"})
    started = time.monotonic()
    session.wait(5.0)
    assert time.monotonic() - started < 2.0


@pytest.mark.parametrize(
    "interface, values",
    [
        (mpris.PLAYER, {"Volume": 0.5}),
        ("org.mpris.MediaPlayer2.Playlists", {"PlaybackStatus": "Paused"}),
    ],
)
def test_a_change_that_is_not_about_playback_does_not_wake_the_wait(
    bus, make_session, interface, values
):
    connection, service = bus
    session = make_session()
    session._follow(service)
    properties_changed(connection, interface, values)
    started = time.monotonic()
    session.wait(0.5)
    assert time.monotonic() - started >= 0.45
    properties_changed(connection, mpris.PLAYER, {"PlaybackStatus": "Paused"})
    started = time.monotonic()
    session.wait(5.0)
    assert time.monotonic() - started < 2.0


def test_a_missing_bus_is_a_failure_under_ci(monkeypatch):
    monkeypatch.setenv("CI", "true")
    with pytest.raises(BaseException) as raised:
        require_bus("pas de bus")
    assert isinstance(raised.value, pytest.fail.Exception)


def test_a_missing_bus_is_a_skip_outside_ci(monkeypatch):
    monkeypatch.delenv("CI", raising=False)
    with pytest.raises(pytest.skip.Exception):
        require_bus("pas de bus")


def test_switching_the_player_drops_the_old_subscription(
    bus, spoofer, make_session
):
    connection, service = bus
    other = "org.mpris.MediaPlayer2.ftl" + uuid.uuid4().hex[:8]
    assert spoofer.registerService(other)
    session = make_session()
    session._follow(service)
    session._follow(other)
    seeked_signal(connection, 4_000_000)
    session.wait(0.3)
    assert session._events.take_seek() is None
    seeked_signal(spoofer, 6_000_000)
    session.wait(2.0)
    assert session._events.take_seek().position == pytest.approx(6.0)
    spoofer.unregisterService(other)


def test_a_change_inside_the_wake_window_is_delivered_when_the_window_ends(
    bus, make_session
):
    connection, service = bus
    session = make_session()
    session._follow(service)
    properties_changed(connection, mpris.PLAYER, {"PlaybackStatus": "Playing"})
    session.wait(2.0)
    session._events.begin()
    properties_changed(connection, mpris.PLAYER, {"PlaybackStatus": "Paused"})
    started = time.monotonic()
    session.wait(1.0)
    assert session._events.ready()
    assert time.monotonic() - started >= 0.1


def test_a_seek_keeps_the_track_it_was_sent_for(bus, make_session):
    connection, service = bus
    session = make_session()
    session._follow(service, ("first", "artist"))
    seeked_signal(connection, 5_000_000)
    properties_changed(
        connection,
        mpris.PLAYER,
        {"Metadata": {"xesam:title": "second", "xesam:artist": "artist"}},
    )
    time.sleep(0.3)
    assert session._events.take_seek().track_key == ("first", "artist")
    seeked_signal(connection, 8_000_000)
    time.sleep(0.3)
    assert session._events.take_seek().track_key == ("second", "artist")


def test_a_playback_status_change_is_dated_when_it_arrives(bus, make_session):
    connection, service = bus
    session = make_session()
    session._follow(service, ("first", "artist"))
    emitted = time.monotonic()
    properties_changed(connection, mpris.PLAYER, {"PlaybackStatus": "Playing"})
    time.sleep(0.3)
    session.wait(1.0)
    (edge,) = session._events.take_edges()
    assert edge.playing is True
    assert edge.track_key == ("first", "artist")
    assert 0.0 <= edge.at - emitted < 0.2


def test_a_playback_status_change_of_the_other_track_is_not_kept(
    bus, make_session
):
    connection, service = bus
    session = make_session()
    session._follow(service, ("first", "artist"))
    properties_changed(
        connection,
        mpris.PLAYER,
        {"Metadata": {"xesam:title": "second", "xesam:artist": "artist"}},
    )
    properties_changed(connection, mpris.PLAYER, {"PlaybackStatus": "Paused"})
    time.sleep(0.3)
    session.wait(1.0)
    (edge,) = session._events.take_edges()
    assert edge.track_key == ("second", "artist")


def test_unfollowing_drops_the_pending_playback_changes(bus, make_session):
    connection, service = bus
    session = make_session()
    session._follow(service, ("first", "artist"))
    properties_changed(connection, mpris.PLAYER, {"PlaybackStatus": "Paused"})
    time.sleep(0.3)
    session._follow(None)
    assert session._events.take_edges() == ()


def scripted_positions(monkeypatch, positions):
    script = iter(positions)
    last = [0]

    def get_position(bus, service):
        last[0] = next(script, last[0])
        return last[0]

    monkeypatch.setattr(mpris, "_get_position", get_position)


def test_the_probe_stops_after_two_transitions(bus, make_session, monkeypatch):
    connection, service = bus
    session = make_session()
    session._follow(service, ("first", "artist"))
    scripted_positions(
        monkeypatch,
        [
            12_000_000,
            12_000_000,
            13_000_000,
            13_000_000,
            14_000_000,
            15_000_000,
        ],
    )
    properties_changed(connection, mpris.PLAYER, {"PlaybackStatus": "Playing"})
    time.sleep(1.5)
    readings = session._events.take_readings()
    assert [r.position for r in readings] == [12.0, 12.0, 13.0, 13.0, 14.0]
    assert not session._listener._probe.isActive()
    assert all(r.track_key == ("first", "artist") for r in readings)


def test_the_probe_period_is_the_reciprocal_of_the_reported_rate(
    bus, make_session
):
    session = make_session()
    session._events.remember_rate(2.0)
    assert session._listener._probe_period() == pytest.approx(0.5)


def test_the_probe_ignores_a_player_that_reports_fractions(
    bus, make_session, monkeypatch
):
    connection, service = bus
    session = make_session()
    session._follow(service, ("first", "artist"))
    scripted_positions(monkeypatch, [12_345_000, 12_400_000])
    properties_changed(connection, mpris.PLAYER, {"PlaybackStatus": "Playing"})
    time.sleep(0.4)
    assert session._events.take_readings() == ()
    assert not session._listener._probe.isActive()


def test_the_probe_is_bounded_in_time(bus, make_session, monkeypatch):
    connection, service = bus
    session = make_session()
    session._follow(service, ("first", "artist"))
    monkeypatch.setattr(probe, "PROBE_SECONDS", 0.3)
    scripted_positions(monkeypatch, [12_000_000] * 1000)
    properties_changed(connection, mpris.PLAYER, {"PlaybackStatus": "Playing"})
    time.sleep(0.8)
    assert not session._listener._probe.isActive()
    count = len(session._events.take_readings())
    assert 3 <= count <= 8


def test_a_pause_stops_the_probe(bus, make_session, monkeypatch):
    connection, service = bus
    session = make_session()
    session._follow(service, ("first", "artist"))
    scripted_positions(monkeypatch, [12_000_000] * 1000)
    properties_changed(connection, mpris.PLAYER, {"PlaybackStatus": "Playing"})
    time.sleep(0.2)
    properties_changed(connection, mpris.PLAYER, {"PlaybackStatus": "Paused"})
    time.sleep(0.1)
    assert not session._listener._probe.isActive()


def test_unfollowing_stops_the_probe(bus, make_session, monkeypatch):
    connection, service = bus
    session = make_session()
    session._follow(service, ("first", "artist"))
    scripted_positions(monkeypatch, [12_000_000] * 1000)
    properties_changed(connection, mpris.PLAYER, {"PlaybackStatus": "Playing"})
    time.sleep(0.2)
    session._follow(None)
    assert not session._listener._probe.isActive()


def test_the_probe_is_not_started_by_a_track_change_while_paused(
    bus, make_session, monkeypatch
):
    connection, service = bus
    session = make_session()
    session._follow(service, ("first", "artist"))
    scripted_positions(monkeypatch, [12_000_000] * 1000)
    properties_changed(connection, mpris.PLAYER, {"PlaybackStatus": "Paused"})
    properties_changed(
        connection,
        mpris.PLAYER,
        {"Metadata": {"xesam:title": "second", "xesam:artist": "artist"}},
    )
    time.sleep(0.2)
    assert not session._listener._probe.isActive()


def test_a_timed_player_is_not_probed_again(bus, make_session, monkeypatch):
    connection, service = bus
    session = make_session()
    session._follow(service, ("first", "artist"))
    scripted_positions(monkeypatch, [12_000_000, 13_000_000, 14_000_000])
    properties_changed(connection, mpris.PLAYER, {"PlaybackStatus": "Playing"})
    time.sleep(1.5)
    assert session._listener._timed
    session._listener.probe()
    assert not session._listener._probe.isActive()


def test_a_new_track_lets_a_timed_player_be_probed_again(
    bus, make_session, monkeypatch
):
    connection, service = bus
    session = make_session()
    session._follow(service, ("first", "artist"))
    scripted_positions(monkeypatch, [12_000_000, 13_000_000, 14_000_000])
    properties_changed(connection, mpris.PLAYER, {"PlaybackStatus": "Playing"})
    time.sleep(1.5)
    session._follow(service, ("second", "artist"))
    assert not session._listener._timed
    session._listener.probe()
    assert session._listener._probe.isActive()


def test_a_seek_lets_a_timed_player_be_probed_again(
    bus, make_session, monkeypatch
):
    connection, service = bus
    session = make_session()
    session._follow(service, ("first", "artist"))
    scripted_positions(monkeypatch, [12_000_000, 13_000_000, 14_000_000])
    properties_changed(connection, mpris.PLAYER, {"PlaybackStatus": "Playing"})
    time.sleep(1.5)
    assert session._listener._timed
    seeked_signal(connection, 14_000_000)
    time.sleep(0.2)
    assert not session._listener._timed


def test_a_seek_while_paused_lets_a_timed_player_be_probed_again(
    bus, make_session, monkeypatch
):
    connection, service = bus
    session = make_session()
    session._follow(service, ("first", "artist"))
    scripted_positions(monkeypatch, [12_000_000, 13_000_000, 14_000_000])
    properties_changed(connection, mpris.PLAYER, {"PlaybackStatus": "Playing"})
    time.sleep(1.5)
    assert session._listener._timed
    properties_changed(connection, mpris.PLAYER, {"PlaybackStatus": "Paused"})
    time.sleep(0.1)
    seeked_signal(connection, 14_000_000)
    time.sleep(0.1)
    assert not session._listener._timed
    session._listener.probe()
    assert session._listener._probe.isActive()


def test_a_player_followed_again_is_probed_again(
    bus, make_session, monkeypatch
):
    connection, service = bus
    session = make_session()
    session._follow(service, ("first", "artist"))
    scripted_positions(monkeypatch, [12_000_000, 13_000_000, 14_000_000])
    properties_changed(connection, mpris.PLAYER, {"PlaybackStatus": "Playing"})
    time.sleep(1.5)
    assert session._listener._timed
    session._follow(None)
    session._follow(service, ("first", "artist"))
    assert not session._listener._timed


def test_closing_a_session_releases_its_private_connection(make_session):
    session = make_session()
    name = session._private_name
    assert QDBusConnection(name).isConnected()
    session.close()
    assert not QDBusConnection(name).isConnected()


def test_a_failed_start_releases_the_private_connection(monkeypatch):
    fixed = uuid.UUID(int=0x5EED)
    name = "ftl-" + fixed.hex[:12]
    monkeypatch.setattr(mpris.uuid, "uuid4", lambda: fixed)

    def broken_listener(*_args):
        raise RuntimeError("listener")

    monkeypatch.setattr(mpris, "_Listener", broken_listener)
    with pytest.raises(RuntimeError):
        mpris.MprisSession()
    assert not QDBusConnection(name).isConnected()


def test_a_poll_for_the_same_player_refreshes_its_track_key(
    monkeypatch, make_session
):
    session = make_session()
    calls = []

    class Recorder:
        def subscribe(self, owner, track_key=None):
            calls.append(("subscribe", owner, track_key))
            return True

        def track(self, track_key):
            calls.append(("track", track_key))

        def unsubscribe(self):
            calls.append(("unsubscribe",))

    session._listener = Recorder()
    monkeypatch.setattr(session, "_owner_of", lambda service: "owner")
    session._follow("svc", ("first", "artist"))
    session._follow("svc", ("second", "artist"))
    assert calls == [
        ("subscribe", "owner", ("first", "artist")),
        ("track", ("second", "artist")),
    ]


def test_a_player_already_playing_when_followed_is_probed(
    bus, make_session, monkeypatch
):
    session = make_session()
    _, service = bus
    monkeypatch.setattr(
        mpris, "_get_all", lambda _bus, _service: {"PlaybackStatus": "Playing"}
    )
    scripted_positions(monkeypatch, [12_000_000, 13_000_000])
    session._follow(service, ("first", "artist"))
    time.sleep(0.4)
    positions = [r.position for r in session._events.take_readings()]
    assert positions[:2] == [12.0, 13.0]


def test_a_read_refused_by_the_budget_is_retried_later(
    bus, make_session, monkeypatch
):
    connection, service = bus
    session = make_session()
    session._follow(service, ("first", "artist"))
    monkeypatch.setattr(mpris, "PROBE_READS_PER_SECOND", 5)
    scripted_positions(monkeypatch, [12_000_000] * 1000)
    properties_changed(connection, mpris.PLAYER, {"PlaybackStatus": "Playing"})
    time.sleep(1.3)
    assert len(session._events.take_readings()) > 5


def test_the_probe_reads_are_capped_per_second(bus, make_session, monkeypatch):
    connection, service = bus
    session = make_session()
    session._follow(service, ("first", "artist"))
    monkeypatch.setattr(mpris, "PROBE_READS_PER_SECOND", 5)
    scripted_positions(monkeypatch, [12_000_000] * 1000)
    properties_changed(connection, mpris.PLAYER, {"PlaybackStatus": "Playing"})
    time.sleep(0.6)
    assert len(session._events.take_readings()) <= 5


class StallingBus:
    def __init__(self, stall_ms):
        self.stall_ms = stall_ms
        self.timeouts = []

    def call(self, _message, timeout):
        self.timeouts.append(timeout)
        if timeout < self.stall_ms:
            time.sleep(timeout / 1000)
            return Reply(QDBusMessage.MessageType.ErrorMessage, [])
        time.sleep(self.stall_ms / 1000)
        return Reply(QDBusMessage.MessageType.ReplyMessage, [12_000_000])


class Reply:
    def __init__(self, kind, arguments):
        self._kind = kind
        self._arguments = arguments

    def type(self):
        return self._kind

    def arguments(self):
        return self._arguments


def test_the_position_probe_gives_up_after_100_milliseconds():
    bus = StallingBus(stall_ms=1000)
    assert mpris._get_position(bus, "svc") is None
    assert bus.timeouts == [mpris.POSITION_TIMEOUT_MS]
    assert mpris.POSITION_TIMEOUT_MS <= 100


def test_a_stalled_player_does_not_hold_the_listener_for_a_second():
    QCoreApplication.instance() or QCoreApplication([])
    listener = mpris._Listener(
        events.PlayerEvents(), StallingBus(stall_ms=1000)
    )
    listener._owner = "svc"
    listener._start_probe(time.monotonic())
    started = time.monotonic()
    listener._probe_tick()
    assert time.monotonic() - started < 0.5
