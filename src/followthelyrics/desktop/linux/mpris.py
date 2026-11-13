import logging
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass

from PyQt6.QtDBus import QDBusConnection
from PyQt6.QtDBus import QDBusMessage

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


def _text(value):
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value if v)
    return str(value or "")


def _seconds(value):
    try:
        return max(0.0, float(value) / MICROSECONDS)
    except (TypeError, ValueError):
        return 0.0


def player_of(app_id, properties):
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


class MprisSession:
    def __init__(self):
        self._bus = QDBusConnection.sessionBus()
        if not self._bus.isConnected():
            raise OSError("bus de session D-Bus indisponible")

    def now_playing(self, blocked, guard):
        player, site = pick(self._players(), blocked, guard)
        return None if player is None else now_playing_of(player, site)

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
        pass

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
                players.append(player_of(app_id, properties))
        return players

    def _properties(self, service):
        message = QDBusMessage.createMethodCall(
            service, OBJECT_PATH, PROPERTIES, "GetAll"
        )
        message.setArguments([PLAYER])
        reply = self._bus.call(message, timeout=CALL_TIMEOUT_MS)
        if reply.type() != QDBusMessage.MessageType.ReplyMessage:
            return None
        arguments = reply.arguments()
        if not arguments or not isinstance(arguments[0], dict):
            return None
        return arguments[0]
