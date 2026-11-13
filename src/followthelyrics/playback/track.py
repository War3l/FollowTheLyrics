from dataclasses import dataclass

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

    @property
    def key(self):
        return (self.title.lower(), self.artist.lower())


def clean_artist(artist: str) -> str:
    for suffix in _ARTIST_SUFFIXES:
        if artist.endswith(suffix):
            artist = artist[: -len(suffix)].strip()
    return artist
