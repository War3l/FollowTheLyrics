import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor

from PyQt6.QtCore import QThread
from PyQt6.QtCore import pyqtSignal

from followthelyrics import lyrics
from followthelyrics import sites

logger = logging.getLogger(__name__)


class MediaWorker(QThread):
    track = pyqtSignal(object)
    lyrics = pyqtSignal(object, object)
    translated = pyqtSignal(object)
    cover = pyqtSignal(object, object)
    sources = pyqtSignal(object)
    browsers = pyqtSignal(object)
    COVER_READS = (0.8, 3.5)
    MAX_DURATION = 20 * 60
    RETRY_DELAYS = (10, 30, 60, 120, 300)

    def __init__(self, blocked=(), sites_off=(), sites_other=False):
        super().__init__()
        self.guard = sites.SiteGuard(sites_off, sites_other)
        self._stop = False
        self._cache = {}
        self._retry = {}
        self._pending = set()
        self.blocked = set(blocked)

    def run(self):
        from followthelyrics import media

        loop = asyncio.new_event_loop()
        manager = loop.run_until_complete(media.get_manager())
        pool = ThreadPoolExecutor(max_workers=2)
        last_key = None
        last_sources = None
        last_seen = None
        changed_at, cover_step, last_cover = 0.0, 0, None
        while not self._stop:
            blocked = frozenset(self.blocked)
            try:
                np = loop.run_until_complete(
                    media.get_now_playing(manager, blocked, self.guard)
                )
            except Exception:
                logger.debug("run failed", exc_info=True)
                np = None
            self.track.emit(np)
            seen = dict(self.guard.seen)
            if seen != last_seen:
                last_seen = seen
                self.browsers.emit(seen)
            src = media.list_sources(manager)
            if src != last_sources:
                last_sources = src
                self.sources.emit(src)
            now = time.monotonic()
            if np and np.key != last_key:
                last_key = np.key
                changed_at, cover_step = now, 0
                if np.key in self._cache:
                    self.lyrics.emit(np.key, self._cache[np.key])
                    self.translated.emit(np.key)
                elif np.key not in self._pending:
                    self._pending.add(np.key)
                    pool.submit(self._fetch, np)
            elif (
                np
                and np.key in self._retry
                and np.key not in self._pending
                and now >= self._retry[np.key][0]
            ):
                self._pending.add(np.key)
                pool.submit(self._fetch, np)
            if (
                np
                and np.key == last_key
                and cover_step < len(self.COVER_READS)
                and now - changed_at >= self.COVER_READS[cover_step]
            ):
                cover_step += 1
                try:
                    data = loop.run_until_complete(
                        media.get_thumbnail(manager, blocked, self.guard)
                    )
                except Exception:
                    logger.debug("run failed", exc_info=True)
                    data = None
                if data and data != last_cover:
                    last_cover = data
                    self.cover.emit(np.key, data)
            time.sleep(0.4)
        pool.shutdown(wait=False)

    def _fetch(self, np):
        try:
            self._fetch_inner(np)
        finally:
            self._pending.discard(np.key)

    def _fetch_inner(self, np):
        if np.duration and np.duration > self.MAX_DURATION:
            self._cache[np.key] = None
            self.lyrics.emit(np.key, None)
            return
        found, lines = lyrics.cache_load(np.title, np.artist, np.duration)
        if found:
            self._cache[np.key] = lines
            self.lyrics.emit(np.key, lines)
            self.translated.emit(np.key)
            return
        try:
            lines, reliable = lyrics.fetch_lyrics_ex(
                np.title, np.artist, np.album, np.duration
            )
        except Exception:
            logger.warning("_fetch_inner failed", exc_info=True)
            lines, reliable = None, False
        if not reliable:
            n = self._retry.get(np.key, (0, 0))[1]
            if n < len(self.RETRY_DELAYS):
                self._retry[np.key] = (
                    time.monotonic() + self.RETRY_DELAYS[n],
                    n + 1,
                )
            else:
                self._retry.pop(np.key, None)
            self.lyrics.emit(np.key, None)
            return
        self._retry.pop(np.key, None)
        self._cache[np.key] = lines
        self.lyrics.emit(np.key, lines)
        translated_ok = True
        if lines:
            try:
                translated_ok = lyrics.translate_lines(lines) is not None
            except Exception:
                logger.warning("_fetch_inner failed", exc_info=True)
                translated_ok = False
            self.translated.emit(np.key)
        if translated_ok:
            lyrics.cache_save(np.title, np.artist, np.duration, lines)

    def stop(self):
        self._stop = True
        self.wait(2000)


class BeatBridge(QThread):
    beat = pyqtSignal(float)
