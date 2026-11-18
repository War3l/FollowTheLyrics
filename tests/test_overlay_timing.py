import random
import types

import pytest
from PyQt6.QtWidgets import QApplication

from followthelyrics import app
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


def now_playing(position, read_at=None, speed=1.0):
    return track.NowPlaying(
        title="Titre",
        artist="Groupe",
        album="",
        duration=200.0,
        position=position,
        playing=True,
        app="test",
        read_at=read_at,
        speed=speed,
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


def test_a_small_offset_change_keeps_the_current_line(overlay, manual_clock):
    start_song(overlay)
    manual_clock.now = 4.2
    overlay.tick()
    overlay.cfg["offset"] = -0.3
    overlay.tick()
    assert overlay.cur["idx"] == 2


@pytest.mark.parametrize(
    "change",
    [
        lambda o: o.reset_layout(),
        lambda o: o.update_zones(),
        lambda o: o.set_profile("bureau", o.profile),
        lambda o: o.on_translated(o.track_key),
    ],
)
def test_layout_changes_forget_the_old_places(overlay, manual_clock, change):
    start_song(overlay)
    manual_clock.now = 4.2
    overlay.tick()
    assert overlay._places
    change(overlay)
    assert not overlay._places


def test_a_lost_player_freezes_the_lyrics_where_they_are(overlay, manual_clock):
    start_song(overlay)
    manual_clock.now = 4.2
    overlay.on_track(None)
    manual_clock.now = 6.2
    assert overlay.raw_position() == pytest.approx(4.2)


def test_the_reading_is_dated_when_it_was_taken(overlay, manual_clock):
    start_song(overlay)
    manual_clock.now = 6.1
    overlay.on_track(now_playing(5.7, read_at=5.7))
    manual_clock.now = 8.1
    assert overlay.raw_position() == pytest.approx(8.1)


@pytest.mark.parametrize("seed", range(20))
def test_a_kept_place_never_covers_the_previous_line(
    overlay, manual_clock, seed
):
    overlay.rng = random.Random(seed)
    start_song(overlay)
    manual_clock.now = 0.5
    overlay.tick()
    overlay.on_track(now_playing(6.5))
    overlay.tick()
    overlay.on_track(now_playing(4.5))
    overlay.tick()
    manual_clock.now = 2.5
    overlay.tick()
    assert overlay.cur["idx"] == 3
    assert overlay.prev["idx"] == 2
    assert not overlay.cur["place"].rect.intersects(overlay.prev["place"].rect)


def test_turning_the_card_on_or_off_forgets_the_old_places(monkeypatch):
    calls = []
    overlay = types.SimpleNamespace(
        reset_layout=lambda: calls.append("reset_layout"),
        apply_geometry=lambda: calls.append("apply_geometry"),
        poke=lambda: None,
    )
    fake_app = types.SimpleNamespace(cfg={}, overlay=overlay)
    monkeypatch.setattr(settings, "save_config", lambda cfg: None)
    app.App.set_cfg(fake_app, "card", False)
    assert calls == ["reset_layout"]


def test_the_player_speed_drives_the_lyrics(overlay, manual_clock):
    overlay.on_track(now_playing(10.0, speed=2.0))
    manual_clock.now = 1.0
    assert overlay.raw_position() == pytest.approx(12.0)
    overlay.on_track(now_playing(12.0, speed=2.0))
    manual_clock.now = 2.0
    assert overlay.raw_position() == pytest.approx(14.0)
