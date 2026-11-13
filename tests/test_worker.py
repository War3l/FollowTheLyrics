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
