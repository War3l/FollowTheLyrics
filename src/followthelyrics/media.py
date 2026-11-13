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
    duration: float
    position: float
    playing: bool
    app: str
    site: str = ""

    @property
    def key(self):
        return (self.title.lower(), self.artist.lower())


def _clean_artist(artist: str) -> str:
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
    try:
        return sorted({_app_id(s) for s in manager.get_sessions() if _app_id(s)})
    except Exception:
        return []


def _is_playing(s) -> bool:
    try:
        info = s.get_playback_info()
        return bool(info and info.playback_status == PlaybackStatus.PLAYING)
    except Exception:
        return False


async def _pick_session(manager, blocked=(), guard=None):
    sessions = [s for s in manager.get_sessions() if _app_id(s) not in blocked]
    if not sessions:
        return None, None, ""
    try:
        cur = _app_id(manager.get_current_session())
    except Exception:
        cur = None
    order = sorted(sessions, key=lambda s: (not _is_playing(s), _app_id(s) != cur))
    for s in order:
        try:
            props = await s.try_get_media_properties_async()
        except Exception:
            props = None
        site = ""
        if guard is not None and props is not None:
            ok, site = guard.allows(_app_id(s), props.title or "", props.artist or "")
            if not ok:
                continue
        return s, props, site
    return None, None, ""


async def get_manager():
    return await SessionManager.request_async()


async def get_now_playing(manager=None, blocked=(), guard=None) -> NowPlaying | None:
    if manager is None:
        manager = await get_manager()
    session, props, site = await _pick_session(manager, blocked, guard)
    if session is None:
        return None

    info = session.get_playback_info()
    tl = session.get_timeline_properties()
    if props is None or not props.title:
        return None

    playing = bool(info and info.playback_status == PlaybackStatus.PLAYING)
    position = tl.position.total_seconds() if tl else 0.0
    duration = (tl.end_time - tl.start_time).total_seconds() if tl else 0.0

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
        site=site,
    )


async def get_thumbnail(manager=None, blocked=(), guard=None) -> bytes | None:
    from winrt.windows.storage.streams import Buffer, InputStreamOptions

    if manager is None:
        manager = await get_manager()
    session, props, _site = await _pick_session(manager, blocked, guard)
    if session is None:
        return None
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
