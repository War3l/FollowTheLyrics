import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from PyQt6.QtCore import QThread
from PyQt6.QtCore import pyqtSignal

from followthelyrics.lyrics import cache
from followthelyrics.lyrics import providers
from followthelyrics.playback import sites

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
    UPGRADE_TRIES = 3
    UPGRADE_WAIT = 12.0

    def __init__(
        self,
        media,
        titles,
        blocked=(),
        sites_off=(),
        sites_other=False,
        upgrade=False,
    ):
        super().__init__()
        self.upgrade = bool(upgrade)
        self._upgrade_lock = threading.Lock()
        self.media = media
        self.guard = sites.SiteGuard(sites_off, sites_other, titles)
        self._stop = False
        self._cache = {}
        self._retry = {}
        self._pending = set()
        self.blocked = set(blocked)

    def run(self):
        if self.media is None:
            return
        try:
            session = self.media.open()
        except Exception:
            logger.warning("run failed", exc_info=True)
            return
        try:
            self._poll(session)
        finally:
            session.close()

    def _poll(self, session):
        pool = ThreadPoolExecutor(max_workers=2)
        last_key = None
        last_sources = None
        last_seen = None
        changed_at, cover_step, last_cover = 0.0, 0, None
        while not self._stop:
            blocked = frozenset(self.blocked)
            try:
                np = session.now_playing(blocked, self.guard)
            except Exception:
                logger.debug("run failed", exc_info=True)
                np = None
            self.track.emit(np)
            seen = dict(self.guard.seen)
            if seen != last_seen:
                last_seen = seen
                self.browsers.emit(seen)
            src = session.sources()
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
                    data = session.cover(blocked, self.guard)
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
        found, lines = cache.cache_load(np.title, np.artist, np.duration)
        if found:
            self._cache[np.key] = lines
            self.lyrics.emit(np.key, lines)
            self.translated.emit(np.key)
            if not cache.cache_is_final(np.title, np.artist):
                self._upgrade(np, lines)
            return
        try:
            lines, reliable = providers.fetch_lyrics_ex(
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
                translated_ok = providers.translate_lines(lines) is not None
            except Exception:
                logger.warning("_fetch_inner failed", exc_info=True)
                translated_ok = False
            self.translated.emit(np.key)
        if translated_ok:
            cache.cache_save(
                np.title,
                np.artist,
                np.duration,
                lines,
                final=providers.has_words(lines),
            )
        self._upgrade(np, lines)

    def _upgrade(self, np, lines):
        if not self.upgrade or providers.has_words(lines):
            return
        better, settled = None, False
        with self._upgrade_lock:
            for attempt in range(self.UPGRADE_TRIES):
                if self._stop or not self.upgrade:
                    return
                try:
                    better, settled = providers.fetch_liriqo(
                        np.title,
                        np.artist,
                        np.duration,
                        want_words=bool(lines),
                    )
                except Exception:
                    logger.warning("_upgrade failed", exc_info=True)
                    better, settled = None, False
                if settled:
                    break
                if attempt + 1 < self.UPGRADE_TRIES:
                    self._sleep(self.UPGRADE_WAIT)
        if not settled:
            return
        if not better:
            cache.cache_save(
                np.title, np.artist, np.duration, lines, final=True
            )
            return
        self._cache[np.key] = better
        self.lyrics.emit(np.key, better)
        try:
            providers.translate_lines(better)
        except Exception:
            logger.warning("_upgrade failed", exc_info=True)
        self.translated.emit(np.key)
        cache.cache_save(np.title, np.artist, np.duration, better, final=True)

    def _sleep(self, seconds):
        until = time.monotonic() + seconds
        while not self._stop and time.monotonic() < until:
            time.sleep(0.2)

    def stop(self):
        self._stop = True
        self.wait(2000)


class BeatBridge(QThread):
    beat = pyqtSignal(float)
