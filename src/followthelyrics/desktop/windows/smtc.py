import asyncio
import logging
import sys
import time

from winrt.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionManager as SessionManager,
)
from winrt.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
)
from winrt.windows.storage.streams import Buffer
from winrt.windows.storage.streams import InputStreamOptions

from followthelyrics.playback import track

assert sys.platform == "win32"

logger = logging.getLogger(__name__)

MAX_COVER_BYTES = 20_000_000


def _app_id(session) -> str:
    try:
        return session.source_app_user_model_id or ""
    except Exception:
        logger.debug("_app_id failed", exc_info=True)
        return ""


def _is_playing(session) -> bool:
    try:
        info = session.get_playback_info()
        return bool(info and info.playback_status == PlaybackStatus.PLAYING)
    except Exception:
        logger.debug("_is_playing failed", exc_info=True)
        return False


class SmtcSession:
    def __init__(self):
        self._loop = asyncio.new_event_loop()
        self._manager = self._loop.run_until_complete(
            SessionManager.request_async()
        )

    def now_playing(self, blocked, guard):
        return self._loop.run_until_complete(self._now_playing(blocked, guard))

    def cover(self, blocked, guard):
        return self._loop.run_until_complete(self._cover(blocked, guard))

    def sources(self):
        try:
            return sorted(
                {_app_id(s) for s in self._manager.get_sessions() if _app_id(s)}
            )
        except Exception:
            logger.debug("sources failed", exc_info=True)
            return []

    def close(self):
        self._loop.close()

    async def _pick(self, blocked, guard):
        manager = self._manager
        sessions = [
            s for s in manager.get_sessions() if _app_id(s) not in blocked
        ]
        if not sessions:
            return None, None, ""
        try:
            current = _app_id(manager.get_current_session())
        except Exception:
            logger.debug("_pick failed", exc_info=True)
            current = None
        order = sorted(
            sessions,
            key=lambda s: (not _is_playing(s), _app_id(s) != current),
        )
        for session in order:
            try:
                props = await session.try_get_media_properties_async()
            except Exception:
                logger.debug("_pick failed", exc_info=True)
                props = None
            site = ""
            if guard is not None and props is not None:
                ok, site = guard.allows(
                    _app_id(session), props.title or "", props.artist or ""
                )
                if not ok:
                    continue
            return session, props, site
        return None, None, ""

    async def _now_playing(self, blocked, guard):
        session, props, site = await self._pick(blocked, guard)
        if session is None:
            return None
        info = session.get_playback_info()
        timeline = session.get_timeline_properties()
        if props is None or not props.title:
            return None
        playing = bool(info and info.playback_status == PlaybackStatus.PLAYING)
        position = timeline.position.total_seconds() if timeline else 0.0
        duration = (
            (timeline.end_time - timeline.start_time).total_seconds()
            if timeline
            else 0.0
        )
        if timeline and playing:
            try:
                elapsed = time.time() - timeline.last_updated_time.timestamp()
                if 0 < elapsed < 3600:
                    position += elapsed
            except Exception:
                logger.debug("_now_playing failed", exc_info=True)
        return track.NowPlaying(
            title=props.title,
            artist=track.clean_artist(props.artist or ""),
            album=props.album_title or "",
            duration=duration,
            position=position,
            playing=playing,
            app=session.source_app_user_model_id or "",
            site=site,
        )

    async def _cover(self, blocked, guard):
        session, props, _site = await self._pick(blocked, guard)
        if session is None or props is None or props.thumbnail is None:
            return None
        stream = await props.thumbnail.open_read_async()
        size = int(stream.size)
        if size <= 0 or size > MAX_COVER_BYTES:
            return None
        buffer = Buffer(size)
        out = await stream.read_async(
            buffer, size, InputStreamOptions.READ_AHEAD
        )
        data = bytes(memoryview(out))[: out.length]
        return data or None
