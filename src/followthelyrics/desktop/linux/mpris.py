import collections
import logging
import math
import os
import time
import urllib.parse
import urllib.request
import uuid
import weakref
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from PyQt6.QtCore import QObject
from PyQt6.QtCore import Qt
from PyQt6.QtCore import QThread
from PyQt6.QtCore import QTimer
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtCore import pyqtSlot
from PyQt6.QtDBus import QDBusConnection
from PyQt6.QtDBus import QDBusMessage

from followthelyrics.playback import events
from followthelyrics.playback import probe
from followthelyrics.playback import sites
from followthelyrics.playback import track

logger = logging.getLogger(__name__)

SERVICE_PREFIX = "org.mpris.MediaPlayer2."
OBJECT_PATH = "/org/mpris/MediaPlayer2"
PROPERTIES = "org.freedesktop.DBus.Properties"
PLAYER = "org.mpris.MediaPlayer2.Player"
CALL_TIMEOUT_MS = 1000
MAX_COVER_BYTES = 20_000_000
COVER_TIMEOUT_S = 5
MICROSECONDS = 1_000_000
WATCHED_KEYS = frozenset(("PlaybackStatus", "Rate", "Metadata", "Position"))
WAKE_INTERVAL_S = 0.2
POSITION_TIMEOUT_MS = 100
PROBE_READS_PER_SECOND = 20


@dataclass(frozen=True)
class Player:
    app_id: str
    title: str
    artist: str
    album: str
    duration: float
    position: float
    playing: bool
    art_url: str = ""
    page_url: str = ""
    read_at: float | None = None
    speed: float = 1.0
    service: str = ""


def _text(value):
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value if v)
    return str(value or "")


def _seconds(value):
    try:
        return max(0.0, float(value) / MICROSECONDS)
    except (TypeError, ValueError):
        return 0.0


def seek_of(microseconds, at, speed=1.0, track_key=None):
    if isinstance(microseconds, bool) or not isinstance(microseconds, int):
        return None
    position = track.valid_position(microseconds / MICROSECONDS)
    if position is None:
        return None
    return track.Seek(position, at, speed, track_key)


def metadata_key(metadata):
    metadata = metadata if isinstance(metadata, dict) else {}
    return (
        _text(metadata.get("xesam:title")).lower(),
        track.clean_artist(_text(metadata.get("xesam:artist"))).lower(),
    )


def player_of(app_id, properties, read_at=None, service=""):
    metadata = properties.get("Metadata") or {}
    return Player(
        app_id=app_id,
        title=_text(metadata.get("xesam:title")),
        artist=_text(metadata.get("xesam:artist")),
        album=_text(metadata.get("xesam:album")),
        duration=_seconds(metadata.get("mpris:length")),
        position=_seconds(properties.get("Position")),
        playing=properties.get("PlaybackStatus") == "Playing",
        art_url=_text(metadata.get("mpris:artUrl")),
        page_url=_text(metadata.get("xesam:url")),
        read_at=read_at,
        speed=track.playback_speed(properties.get("Rate", 1.0)),
        service=service,
    )


def site_hint(player):
    host = urllib.parse.urlsplit(player.page_url).hostname or ""
    if sites.site_of_host(host) not in (None, sites.OTHER):
        return host
    return player.artist


def pick(players, blocked, guard):
    candidates = [p for p in players if p.app_id not in blocked and p.title]
    for player in sorted(candidates, key=lambda p: not p.playing):
        site = ""
        if guard is not None:
            ok, site = guard.allows(
                player.app_id, player.title, site_hint(player)
            )
            if not ok:
                continue
        return player, site
    return None, ""


def now_playing_of(player, site):
    return track.NowPlaying(
        title=player.title,
        artist=track.clean_artist(player.artist),
        album=player.album,
        duration=player.duration,
        position=player.position,
        playing=player.playing,
        app=player.app_id,
        site=site,
        read_at=player.read_at,
        speed=player.speed,
        art_url=player.art_url if player.art_url.startswith("https://") else "",
    )


def _read_capped(stream):
    data = stream.read(MAX_COVER_BYTES + 1)
    return data if 0 < len(data) <= MAX_COVER_BYTES else None


def load_cover(url):
    parts = urllib.parse.urlsplit(url)
    if parts.scheme == "file":
        path = urllib.request.url2pathname(parts.path)
        if not os.path.isfile(path):
            return None
        with open(path, "rb") as f:
            return _read_capped(f)
    if parts.scheme in ("http", "https"):
        request = urllib.request.Request(
            url, headers={"User-Agent": "FollowTheLyrics"}
        )
        with urllib.request.urlopen(request, timeout=COVER_TIMEOUT_S) as r:
            return _read_capped(r)
    return None


def _get_all(bus, service):
    message = QDBusMessage.createMethodCall(
        service, OBJECT_PATH, PROPERTIES, "GetAll"
    )
    message.setArguments([PLAYER])
    reply = bus.call(message, timeout=CALL_TIMEOUT_MS)
    if reply.type() != QDBusMessage.MessageType.ReplyMessage:
        return None
    arguments = reply.arguments()
    if not arguments or not isinstance(arguments[0], dict):
        return None
    return arguments[0]


def _get_position(bus, service):
    message = QDBusMessage.createMethodCall(
        service, OBJECT_PATH, PROPERTIES, "Get"
    )
    message.setArguments([PLAYER, "Position"])
    reply = bus.call(message, timeout=POSITION_TIMEOUT_MS)
    if reply.type() != QDBusMessage.MessageType.ReplyMessage:
        return None
    arguments = reply.arguments()
    return arguments[0] if arguments else None


def _connect_blocking(signal: Any, slot: Callable[..., Any]) -> None:
    connect: Callable[..., object] = signal.connect
    connect(slot, Qt.ConnectionType.BlockingQueuedConnection)


class _Listener(QObject):
    subscribe_request = pyqtSignal(str, object)
    unsubscribe_request = pyqtSignal()
    halt_request = pyqtSignal()
    track_request = pyqtSignal(object)
    probe_request = pyqtSignal()

    def __init__(self, player_events, bus):
        super().__init__()
        self._events = player_events
        self._bus = bus
        self._owner = None
        self._track_key = None
        self._ok = False
        self._last_wake = None
        self._trailing = QTimer(self)
        self._trailing.setSingleShot(True)
        self._trailing.timeout.connect(self._wake_now)
        self._probe = QTimer(self)
        self._probe.setTimerType(Qt.TimerType.PreciseTimer)
        self._probe.timeout.connect(self._probe_tick)
        self._schedule: probe.Probe | None = None
        self._probe_reads: collections.deque[float] = collections.deque()
        self._playing: bool | None = None
        self._timed = False
        _connect_blocking(self.probe_request, self._on_probe)
        _connect_blocking(self.subscribe_request, self._on_subscribe)
        _connect_blocking(self.unsubscribe_request, self._on_unsubscribe)
        _connect_blocking(self.halt_request, self._on_halt)
        _connect_blocking(self.track_request, self._on_track)

    def subscribe(self, owner, track_key=None):
        self.subscribe_request.emit(owner, track_key)
        return self._ok

    def track(self, track_key):
        self.track_request.emit(track_key)

    def unsubscribe(self):
        self.unsubscribe_request.emit()

    def halt(self):
        self.halt_request.emit()

    def probe(self):
        self.probe_request.emit()

    @pyqtSlot("qlonglong")
    def seeked(self, microseconds):
        now = time.monotonic()
        self._timed = False
        self._events.notify(
            seek_of(microseconds, now, self._events.rate(), self._track_key)
        )
        if self._playing:
            self._start_probe(now)

    @pyqtSlot("QString", "QVariantMap", "QStringList")
    def changed(self, interface, values, _invalidated):
        if interface != PLAYER or not WATCHED_KEYS.intersection(values):
            return
        now = time.monotonic()
        if "Rate" in values:
            self._events.remember_rate(values["Rate"])
        if "Metadata" in values:
            self._track_key = metadata_key(values["Metadata"])
        if "PlaybackStatus" in values:
            self._playing = values["PlaybackStatus"] == "Playing"
            self._events.record_edge(
                track.Edge(self._playing, now, self._track_key)
            )
            if self._playing:
                self._start_probe(now)
            else:
                self._stop_probe()
        elif "Metadata" in values and self._playing:
            self._start_probe(now)
        if (
            self._last_wake is not None
            and now - self._last_wake < WAKE_INTERVAL_S
        ):
            if not self._trailing.isActive():
                remaining = WAKE_INTERVAL_S - (now - self._last_wake)
                self._trailing.start(max(1, math.ceil(remaining * 1000)))
            return
        self._wake(now)

    def _wake(self, now):
        self._last_wake = now
        self._events.notify()

    @pyqtSlot()
    def _wake_now(self):
        self._wake(time.monotonic())

    @pyqtSlot(str, object)
    def _on_subscribe(self, owner, track_key):
        bus = self._bus
        self._owner = owner
        self._track_key = track_key
        self._timed = False
        seeked = bus.connect(
            owner, OBJECT_PATH, PLAYER, "Seeked", "x", self.seeked
        )
        changed = bus.connect(
            owner,
            OBJECT_PATH,
            PROPERTIES,
            "PropertiesChanged",
            "sa{sv}as",
            self.changed,
        )
        self._ok = bool(seeked and changed)
        if not self._ok:
            return
        properties = _get_all(bus, owner)
        if properties is None:
            return
        self._playing = properties.get("PlaybackStatus") == "Playing"
        if self._playing:
            self._start_probe(time.monotonic())

    def _start_probe(self, now):
        self._schedule = probe.Probe(self._probe_period())
        self._arm(self._schedule.start(now))

    def _probe_period(self) -> float:
        rate = self._events.rate()
        return 1 / rate if rate and rate > 0 else 1.0

    def _arm(self, when: float | None):
        if when is None:
            self._stop_probe()
            return
        delay_ms = max(0, math.ceil((when - time.monotonic()) * 1000))
        self._probe.start(delay_ms)

    def _stop_probe(self):
        self._probe.stop()
        self._schedule = None

    @pyqtSlot()
    def _probe_tick(self):
        schedule = self._schedule
        if self._owner is None or schedule is None:
            self._stop_probe()
            return
        now = time.monotonic()
        if not self._probe_budget_left(now):
            self._arm(schedule.next_read(now))
            return
        microseconds = _get_position(self._bus, self._owner)
        at = time.monotonic()
        if not isinstance(microseconds, int) or microseconds % MICROSECONDS:
            self._stop_probe()
            return
        whole = microseconds // MICROSECONDS
        self._events.record_reading(
            track.Reading(float(whole), at, self._track_key)
        )
        when = schedule.record(at, whole)
        self._timed = schedule.timed
        self._arm(when)

    @pyqtSlot()
    def _on_probe(self):
        if self._owner is None or self._timed or self._probe.isActive():
            return
        self._start_probe(time.monotonic())

    def _probe_budget_left(self, now: float) -> bool:
        while self._probe_reads and now - self._probe_reads[0] >= 1.0:
            self._probe_reads.popleft()
        if len(self._probe_reads) >= PROBE_READS_PER_SECOND:
            return False
        self._probe_reads.append(now)
        return True

    @pyqtSlot()
    def _on_unsubscribe(self):
        if self._owner is None:
            return
        owner, self._owner = self._owner, None
        self._track_key = None
        self._playing = None
        self._stop_probe()
        self._trailing.stop()
        self._bus.disconnect(
            owner, OBJECT_PATH, PLAYER, "Seeked", "x", self.seeked
        )
        self._bus.disconnect(
            owner,
            OBJECT_PATH,
            PROPERTIES,
            "PropertiesChanged",
            "sa{sv}as",
            self.changed,
        )

    @pyqtSlot(object)
    def _on_track(self, track_key):
        self._track_key = track_key
        self._timed = False

    @pyqtSlot()
    def _on_halt(self):
        self._on_unsubscribe()


def _stop(listener, thread):
    listener.halt()
    thread.quit()
    thread.wait()


class MprisSession:
    def __init__(self, bus=None):
        self._bus = bus or QDBusConnection.sessionBus()
        if not self._bus.isConnected():
            raise OSError("bus de session D-Bus indisponible")
        self._private_name = None
        if bus is None:
            self._private_name = "ftl-" + uuid.uuid4().hex[:12]
            listener_bus = QDBusConnection.connectToBus(
                QDBusConnection.BusType.SessionBus, self._private_name
            )
        else:
            listener_bus = bus
        try:
            self._start_listener(listener_bus)
        except BaseException:
            self._release_private_connection()
            raise
        self._followed = None

    def _start_listener(self, listener_bus):
        self._events = events.PlayerEvents()
        self._listener = _Listener(self._events, listener_bus)
        self._thread = QThread()
        self._listener.moveToThread(self._thread)
        self._thread.start()
        self._stop_thread = weakref.finalize(
            self, _stop, self._listener, self._thread
        )

    def now_playing(self, blocked, guard):
        self._events.begin()
        player, site = pick(self._players(), blocked, guard)
        if player is None:
            self._follow(None)
            return None
        np = now_playing_of(player, site)
        self._follow(player.service, np.key)
        if player.playing:
            self._events.remember_rate(player.speed)
            if float(player.position).is_integer():
                self._listener.probe()
        seek = self._events.take_seek()
        np.seek = (
            seek if seek is not None and seek.track_key == np.key else None
        )
        np.edges = tuple(
            edge
            for edge in self._events.take_edges()
            if edge.track_key == np.key
        )
        np.readings = tuple(
            reading
            for reading in self._events.take_readings()
            if reading.track_key == np.key
        )
        return np

    def wait(self, seconds):
        self._events.wait(seconds)

    def cover(self, blocked, guard):
        player, _site = pick(self._players(), blocked, guard)
        if player is None or not player.art_url:
            return None
        try:
            return load_cover(player.art_url)
        except (OSError, ValueError):
            logger.debug("cover failed", exc_info=True)
            return None

    def sources(self):
        return sorted(self._services())

    def close(self):
        self._unfollow()
        self._stop_thread()
        self._release_private_connection()

    def _release_private_connection(self):
        if self._private_name is not None:
            QDBusConnection.disconnectFromBus(self._private_name)
            self._private_name = None

    def _follow(self, service, track_key=None):
        owner = self._owner_of(service) if service else None
        if (service, owner) == self._followed:
            self._listener.track(track_key)
            return
        self._unfollow()
        self._events.take_seek()
        self._events.take_edges()
        if owner is None:
            return
        self._followed = (service, owner)
        if not self._listener.subscribe(owner, track_key):
            self._unfollow()

    def _owner_of(self, service):
        interface = self._bus.interface()
        if interface is None:
            return None
        reply = interface.serviceOwner(service)
        if not reply.isValid() or not reply.value():
            return None
        return reply.value()

    def _unfollow(self):
        if self._followed is None:
            return
        self._followed = None
        self._listener.unsubscribe()

    def _services(self):
        interface = self._bus.interface()
        if interface is None:
            return {}
        reply = interface.registeredServiceNames()
        if not reply.isValid():
            return {}
        return {
            name[len(SERVICE_PREFIX) :]: name
            for name in reply.value()
            if name.startswith(SERVICE_PREFIX)
        }

    def _players(self):
        players = []
        for app_id, service in self._services().items():
            properties = self._properties(service)
            if properties is not None:
                players.append(
                    player_of(app_id, properties, time.monotonic(), service)
                )
        return players

    def _properties(self, service):
        return _get_all(self._bus, service)
