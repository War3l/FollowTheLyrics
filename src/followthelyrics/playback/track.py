from dataclasses import dataclass

MAX_SPEED = 16.0
_ARTIST_SUFFIXES = (" - Topic", " - Sujet", "VEVO")


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

    @property
    def key(self):
        return (self.title.lower(), self.artist.lower())


def playback_speed(value) -> float:
    try:
        speed = float(value)
    except (TypeError, ValueError):
        return 1.0
    return speed if 0.0 < speed <= MAX_SPEED else 1.0


def clean_artist(artist: str) -> str:
    for suffix in _ARTIST_SUFFIXES:
        if artist.endswith(suffix):
            artist = artist[: -len(suffix)].strip()
    return artist
