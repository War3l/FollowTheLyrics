import math
from dataclasses import dataclass

MAX_SPEED = 16.0
MAX_POSITION = 24 * 3600.0
_ARTIST_SUFFIXES = (" - Topic", " - Sujet", "VEVO")


@dataclass(frozen=True)
class Seek:
    position: float
    at: float
    speed: float = 1.0
    track_key: tuple[str, str] | None = None


@dataclass(frozen=True)
class Edge:
    playing: bool
    at: float
    track_key: tuple[str, str] | None = None


@dataclass(frozen=True)
class Reading:
    position: float
    at: float
    track_key: tuple[str, str] | None = None


def valid_position(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    seconds = float(value)
    if not math.isfinite(seconds) or not 0.0 <= seconds <= MAX_POSITION:
        return None
    return seconds


@dataclass
class NowPlaying:
    title: str
    artist: str
    album: str
    duration: float
    position: float
    playing: bool
    app: str
    site: str = ""
    read_at: float | None = None
    speed: float = 1.0
    art_url: str = ""
    seek: Seek | None = None
    edges: tuple[Edge, ...] = ()
    readings: tuple[Reading, ...] = ()

    @property
    def key(self):
        return (self.title.lower(), self.artist.lower())


def positive_speed(value) -> float | None:
    try:
        speed = float(value)
    except (TypeError, ValueError):
        return None
    return speed if 0.0 < speed <= MAX_SPEED else None


def playback_speed(value) -> float:
    speed = positive_speed(value)
    return 1.0 if speed is None else speed


def bounded_position(position: float, duration: float) -> float:
    if duration <= 0.0:
        return position
    return min(position, duration)


def clean_artist(artist: str) -> str:
    for suffix in _ARTIST_SUFFIXES:
        if artist.endswith(suffix):
            artist = artist[: -len(suffix)].strip()
    return artist
