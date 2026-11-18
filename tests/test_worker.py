import threading
import time
import types

import pytest
from PyQt6.QtCore import Qt

from followthelyrics.lyrics import cache
from followthelyrics.lyrics import model
from followthelyrics.lyrics import providers
from followthelyrics.playback import worker


@pytest.fixture
def media_worker(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(
        providers, "translate_lines", lambda lines, t="fr": "fr"
    )
    w = worker.MediaWorker(None, lambda exes: [], upgrade=True)
    w.UPGRADE_WAIT = 0.05
    yield w
    w.stop()


def _track(title):
    return types.SimpleNamespace(
        title=title, artist="Groupe", album="", duration=200, key=(title, "g")
    )


def test_a_busy_fallback_never_delays_the_normal_search(
    media_worker, monkeypatch
):
    release = threading.Event()

    def slow_fallback(*args, **kwargs):
        release.wait(5)
        return None, False

    line = [model.Line(1.0, "Monte le son")]
    monkeypatch.setattr(providers, "fetch_liriqo", slow_fallback)
    monkeypatch.setattr(
        providers, "fetch_lyrics_ex", lambda *a, **k: (line, True)
    )
    seen = []
    media_worker.lyrics.connect(lambda key, lines: seen.append(key))

    started = time.monotonic()
    for title in ("un", "deux", "trois"):
        np = _track(title)
        media_worker._playing_key = np.key
        media_worker._fetch(np)
    elapsed = time.monotonic() - started
    release.set()

    assert [key[0] for key in seen] == ["un", "deux", "trois"]
    assert elapsed < 1.0


def test_fallback_is_skipped_once_the_track_has_changed(
    media_worker, monkeypatch
):
    calls = []
    monkeypatch.setattr(
        providers,
        "fetch_liriqo",
        lambda *a, **k: calls.append(a) or (None, True),
    )
    media_worker._playing_key = ("autre", "g")

    media_worker._upgrade(_track("un"), [model.Line(1.0, "Monte le son")])

    assert calls == []


def test_the_search_for_word_timing_is_announced_then_closed(
    media_worker, monkeypatch
):
    line = [model.Line(1.0, "Monte le son")]
    monkeypatch.setattr(
        providers, "fetch_lyrics_ex", lambda *a, **k: (line, True)
    )
    monkeypatch.setattr(providers, "fetch_liriqo", lambda *a, **k: (None, True))
    events = []
    done = threading.Event()

    def record(key, active):
        events.append(active)
        if not active:
            done.set()

    media_worker.upgrading.connect(record, Qt.ConnectionType.DirectConnection)
    np = _track("un")
    media_worker._playing_key = np.key
    media_worker._fetch(np)

    assert done.wait(3)
    assert events == [True, False]


def test_nothing_is_announced_when_words_are_already_there(
    media_worker, monkeypatch
):
    words = [model.Line(1.0, "Monte", chars=[(1.0, 1.2)] * 5)]
    monkeypatch.setattr(
        providers, "fetch_lyrics_ex", lambda *a, **k: (words, True)
    )
    events = []
    media_worker.upgrading.connect(lambda key, active: events.append(active))
    np = _track("un")
    media_worker._playing_key = np.key
    media_worker._fetch(np)

    assert events == []


def test_nothing_is_sent_for_translation_when_it_is_off(
    media_worker, monkeypatch
):
    calls = []
    monkeypatch.setattr(
        providers,
        "translate_lines",
        lambda lines, t="fr": calls.append(1) or "fr",
    )
    lines = [model.Line(1.0, "Monte le son")]

    media_worker.translate = False
    assert media_worker._translate(lines) is True
    assert calls == []

    media_worker.translate = True
    assert media_worker._translate(lines) is True
    assert calls == [1]


class OnePollSession:
    def __init__(self, media_worker, np):
        self.media_worker = media_worker
        self.np = np

    def now_playing(self, blocked, guard):
        self.media_worker._stop = True
        return self.np

    def sources(self):
        return []

    def cover(self, blocked, guard):
        return None


def test_each_reading_carries_the_time_it_was_taken(media_worker, monkeypatch):
    monkeypatch.setattr(worker.time, "sleep", lambda s: None)
    np = types.SimpleNamespace(key=("titre", "groupe"), read_at=None)
    monkeypatch.setattr(media_worker, "_fetch", lambda np: None)
    sent = []
    media_worker.track.connect(sent.append, Qt.ConnectionType.DirectConnection)
    before = time.monotonic()
    media_worker._poll(OnePollSession(media_worker, np))
    assert sent == [np]
    assert before <= np.read_at <= time.monotonic()


class ScriptedSession(OnePollSession):
    def __init__(self, media_worker, readings):
        super().__init__(media_worker, None)
        self.readings = list(readings)

    def now_playing(self, blocked, guard):
        reading = self.readings.pop(0)
        if not self.readings:
            self.media_worker._stop = True
        if isinstance(reading, Exception):
            raise reading
        return reading


def poll_readings(media_worker, monkeypatch, readings):
    monkeypatch.setattr(worker.time, "sleep", lambda s: None)
    monkeypatch.setattr(media_worker, "_fetch", lambda np: None)
    sent = []
    media_worker.track.connect(sent.append, Qt.ConnectionType.DirectConnection)
    media_worker._poll(ScriptedSession(media_worker, readings))
    return sent


def test_a_reading_dated_by_the_player_keeps_its_date(
    media_worker, monkeypatch
):
    np = types.SimpleNamespace(key=("titre", "groupe"), read_at=12.5)
    assert poll_readings(media_worker, monkeypatch, [np]) == [np]
    assert np.read_at == 12.5


def test_one_failed_reading_keeps_the_last_one(media_worker, monkeypatch):
    np = types.SimpleNamespace(key=("titre", "groupe"), read_at=None)
    sent = poll_readings(media_worker, monkeypatch, [np, OSError("bus")])
    assert sent == [np, np]


def test_an_old_reading_is_not_kept_after_a_failure(media_worker, monkeypatch):
    np = types.SimpleNamespace(
        key=("titre", "groupe"), read_at=time.monotonic() - 5
    )
    sent = poll_readings(media_worker, monkeypatch, [np, OSError("bus")])
    assert sent == [np, None]
