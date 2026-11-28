import asyncio
import logging
import sys
import time
from datetime import UTC
from datetime import datetime

from winrt.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionManager as SessionManager,
)
from winrt.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
)
from winrt.windows.storage.streams import Buffer
from winrt.windows.storage.streams import InputStreamOptions

from followthelyrics.playback import events
from followthelyrics.playback import timeline
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


def _unwatch(session, timeline_token, playback_token):
    try:
        session.remove_timeline_properties_changed(timeline_token)
        session.remove_playback_info_changed(playback_token)
    except Exception:
        logger.debug("_unwatch failed", exc_info=True)


class SmtcSession:
    def __init__(self):
        self._loop = asyncio.new_event_loop()
        self._manager = self._loop.run_until_complete(
            SessionManager.request_async()
        )
        self._events = events.PlayerEvents()
        self._watched: list[tuple] = []

    def now_playing(self, blocked, guard):
        self._events.begin()
        self._watch()
        return self._loop.run_until_complete(self._now_playing(blocked, guard))

    def wait(self, seconds):
        self._events.wait(seconds)

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
        for entry in self._watched:
            _unwatch(*entry[1:])
        self._watched = []
        self._loop.close()

    def _on_playback(self, _sender, _args):
        self._events.notify()

    def _on_timeline(self, session, anchor):
        try:
            timeline_properties = session.get_timeline_properties()
            info = session.get_playback_info()
            reading = timeline.read(
                timeline_properties.position.total_seconds(),
                timeline_properties.last_updated_time,
                getattr(info, "playback_rate", None),
                _is_playing(session),
            )
        except Exception:
            logger.debug("_on_timeline failed", exc_info=True)
            self._events.notify()
            return
        previous = anchor.get("reading")
        pending = anchor.get("pending")
        anchor["reading"] = reading
        anchor["pending"] = None
        if reading is None or not timeline.departs(previous, reading, pending):
            if reading is not None:
                anchor["pending"] = timeline.awaiting(
                    previous, reading, pending
                )
            self._events.notify()
            return
        self._events.notify(
            timeline.seek_of_timeline(
                reading.position,
                reading.updated,
                datetime.now(UTC),
                time.monotonic(),
                reading.rate,
            )
        )

    def _watch(self):
        try:
            sessions = list(self._manager.get_sessions())
        except Exception:
            logger.debug("_watch failed", exc_info=True)
            return
        keys = timeline.session_keys([_app_id(s) for s in sessions])
        kept, gone, fresh = timeline.partition_watched(
            self._watched, list(zip(keys, sessions, strict=True))
        )
        for entry in gone:
            _unwatch(*entry[1:])
        self._watched = kept
        for key, session in fresh:
            entry = self._subscribe(session)
            if entry is not None:
                self._watched.append((key, *entry))

    def _subscribe(self, session):
        anchor: dict = {}
        try:
            timeline_token = session.add_timeline_properties_changed(
                lambda _sender, _args: self._on_timeline(session, anchor)
            )
            playback_token = session.add_playback_info_changed(
                self._on_playback
            )
        except Exception:
            logger.debug("_subscribe failed", exc_info=True)
            return None
        return (session, timeline_token, playback_token)

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
            read_at=time.monotonic(),
            speed=track.playback_speed(
                getattr(info, "playback_rate", None) or 1.0
            ),
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
