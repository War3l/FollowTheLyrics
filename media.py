"""Lecture de la musique en cours via les controles media de Windows (SMTC).

Marche avec Spotify, YouTube Music (navigateur), Deezer, Apple Music...
sans aucune connexion a un compte.
"""
import asyncio
import time
from dataclasses import dataclass

from winrt.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionManager as SessionManager,
    GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
)


@dataclass
class NowPlaying:
    title: str
    artist: str
    album: str
    duration: float      # secondes
    position: float      # secondes, estimee "maintenant"
    playing: bool
    app: str

    @property
    def key(self):
        return (self.title.lower(), self.artist.lower())


def _clean_artist(artist: str) -> str:
    # YouTube Music dans le navigateur renvoie parfois "Artiste - Topic"
    for suffix in (" - Topic", " - Sujet", "VEVO"):
        if artist.endswith(suffix):
            artist = artist[: -len(suffix)].strip()
    return artist


def _app_id(session) -> str:
    try:
        return session.source_app_user_model_id or ""
    except Exception:
        return ""


def list_sources(manager) -> list[str]:
    """Les applis qui diffusent un media en ce moment (Spotify, navigateur...)."""
    try:
        return sorted({_app_id(s) for s in manager.get_sessions() if _app_id(s)})
    except Exception:
        return []


async def _pick_session(manager, blocked=()):
    sessions = [s for s in manager.get_sessions() if _app_id(s) not in blocked]
    if not sessions:
        return None
    # Priorite : une session qui joue, sinon la session "courante"
    for s in sessions:
        info = s.get_playback_info()
        if info and info.playback_status == PlaybackStatus.PLAYING:
            return s
    cur = manager.get_current_session()
    if cur is not None and _app_id(cur) not in blocked:
        return cur
    return sessions[0]


async def get_manager():
    return await SessionManager.request_async()


async def get_now_playing(manager=None, blocked=()) -> NowPlaying | None:
    if manager is None:
        manager = await get_manager()
    session = await _pick_session(manager, blocked)
    if session is None:
        return None

    props = await session.try_get_media_properties_async()
    info = session.get_playback_info()
    tl = session.get_timeline_properties()
    if props is None or not props.title:
        return None

    playing = bool(info and info.playback_status == PlaybackStatus.PLAYING)
    position = tl.position.total_seconds() if tl else 0.0
    duration = (tl.end_time - tl.start_time).total_seconds() if tl else 0.0

    # Windows donne la position au moment de la derniere mise a jour :
    # on rattrape le temps ecoule depuis si la musique joue.
    if tl and playing:
        try:
            updated = tl.last_updated_time.timestamp()
            elapsed = time.time() - updated
            if 0 < elapsed < 3600:
                position += elapsed
        except Exception:
            pass

    return NowPlaying(
        title=props.title,
        artist=_clean_artist(props.artist or ""),
        album=props.album_title or "",
        duration=duration,
        position=position,
        playing=playing,
        app=session.source_app_user_model_id or "",
    )


async def get_thumbnail(manager=None, blocked=()) -> bytes | None:
    """Image de la pochette (album) fournie par l'appli qui joue, en octets (JPEG/PNG)."""
    from winrt.windows.storage.streams import Buffer, InputStreamOptions

    if manager is None:
        manager = await get_manager()
    session = await _pick_session(manager, blocked)
    if session is None:
        return None
    props = await session.try_get_media_properties_async()
    if props is None or props.thumbnail is None:
        return None
    stream = await props.thumbnail.open_read_async()
    size = int(stream.size)
    if size <= 0 or size > 20_000_000:
        return None
    buf = Buffer(size)
    out = await stream.read_async(buf, size, InputStreamOptions.READ_AHEAD)
    data = bytes(memoryview(out))[: out.length]
    return data or None


if __name__ == "__main__":
    np = asyncio.run(get_now_playing())
    print(np if np else "Rien ne joue.")
    img = asyncio.run(get_thumbnail())
    print(f"pochette : {len(img)} octets, debut {img[:4]!r}" if img else "pas de pochette")
