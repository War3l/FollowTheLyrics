import random

import pytest
from PyQt6.QtWidgets import QApplication

from followthelyrics import desktop
from followthelyrics.config import games
from followthelyrics.config import settings
from followthelyrics.lyrics import model
from followthelyrics.overlay import window
from followthelyrics.playback import track


class ManualClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


@pytest.fixture
def manual_clock():
    return ManualClock()


@pytest.fixture
def overlay(manual_clock):
    app = QApplication.instance() or QApplication([])
    o = window.Overlay(
        dict(settings.DEFAULTS, card=False, mode="edit", offset=0.0),
        games.DEFAULT_PROFILES,
        desktop.current().windowing,
        clock=manual_clock,
        rng=random.Random(3),
    )
    o.timer.stop()
    o.top_timer.stop()
    o.setGeometry(0, 0, 960, 720)
    yield o
    o.close()
    app.processEvents()


def now_playing(position, read_at=None):
    return track.NowPlaying(
        title="Titre",
        artist="Groupe",
        album="",
        duration=200.0,
        position=position,
        playing=True,
        app="test",
        read_at=read_at,
    )


def start_song(overlay):
    overlay.on_track(now_playing(0.0))
    overlay.on_lyrics(
        overlay.track_key,
        [model.Line(float(t), f"ligne {t}") for t in range(0, 20, 2)],
    )


def test_a_short_rewind_keeps_the_current_line(overlay, manual_clock):
    start_song(overlay)
    manual_clock.now = 4.2
    overlay.tick()
    assert overlay.cur["idx"] == 2
    assert overlay.line_to_show(3.8) == 2


def test_a_real_rewind_goes_back_to_the_earlier_line(overlay, manual_clock):
    start_song(overlay)
    manual_clock.now = 4.2
    overlay.tick()
    assert overlay.line_to_show(2.5) == 1


def test_a_line_keeps_its_place_when_shown_again(overlay, manual_clock):
    start_song(overlay)
    manual_clock.now = 4.2
    overlay.tick()
    first = overlay.cur["place"]
    manual_clock.now = 6.2
    overlay.tick()
    overlay.on_track(now_playing(4.2))
    overlay.tick()
    assert overlay.cur["idx"] == 2
    assert overlay.cur["place"] is first


def test_a_late_reading_does_not_pull_the_line_back(overlay, manual_clock):
    start_song(overlay)
    manual_clock.now = 6.1
    overlay.tick()
    assert overlay.cur["idx"] == 3
    overlay.on_track(now_playing(5.7))
    overlay.tick()
    assert overlay.cur["idx"] == 3
    assert overlay.raw_position() >= 6.1


def test_new_lyrics_forget_the_old_places(overlay, manual_clock):
    start_song(overlay)
    manual_clock.now = 4.2
    overlay.tick()
    assert overlay._places
    start_song(overlay)
    assert not overlay._places
