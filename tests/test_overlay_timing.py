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


def rewind(overlay, manual_clock, position):
    for step in (0.0, 0.5, 1.0):
        manual_clock.now += 0.5 if step else 0.0
        overlay.on_track(now_playing(position + step))


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
    rewind(overlay, manual_clock, 4.2)
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


@pytest.mark.parametrize("seed", [1, 3, 6])
def test_a_kept_place_never_covers_the_previous_line(
    overlay, manual_clock, seed
):
    overlay.rng = random.Random(seed)
    start_song(overlay)
    manual_clock.now = 0.5
    overlay.tick()
    overlay.on_track(now_playing(6.5))
    overlay.tick()
    kept = overlay._places[3]
    rewind(overlay, manual_clock, 4.5)
    overlay.tick()
    manual_clock.now = 2.5
    overlay.tick()
    assert overlay.cur["idx"] == 3
    assert overlay.prev["idx"] == 2
    assert kept.rect.intersects(overlay.prev["place"].rect)
    assert not overlay.cur["place"].rect.intersects(overlay.prev["place"].rect)


@pytest.mark.parametrize(
    "key", ["card", "mode", "position", "font", "translation", "stack"]
)
def test_a_display_setting_forgets_the_old_places(
    overlay, manual_clock, monkeypatch, key
):
    monkeypatch.setattr(settings, "save_config", lambda cfg: None)
    start_song(overlay)
    manual_clock.now = 4.2
    overlay.tick()
    assert overlay._places
    worker = types.SimpleNamespace(retranslate=lambda: None)
    fake_app = types.SimpleNamespace(
        cfg=overlay.cfg, overlay=overlay, worker=worker
    )
    app.App.set_cfg(fake_app, key, overlay.cfg[key])
    assert not overlay._places


def test_the_player_speed_drives_the_lyrics(overlay, manual_clock):
    overlay.on_track(now_playing(10.0, speed=2.0))
    manual_clock.now = 1.0
    assert overlay.raw_position() == pytest.approx(12.0)
    overlay.on_track(now_playing(12.0, speed=2.0))
    manual_clock.now = 2.0
    assert overlay.raw_position() == pytest.approx(14.0)


def test_a_track_played_again_starts_over_at_once(overlay, manual_clock):
    start_song(overlay)
    overlay.on_track(now_playing(198.8))
    manual_clock.now = 0.4
    overlay.on_track(now_playing(0.2))
    assert overlay.raw_position() == pytest.approx(0.2)


def seeking(position, at, playing=True):
    np = now_playing(position)
    np.playing = playing
    np.seek = track.Seek(position=100.0, at=at)
    return np


def test_a_seek_lands_the_lyrics_on_its_target_at_once(overlay, manual_clock):
    start_song(overlay)
    manual_clock.now = 5.0
    overlay.on_track(seeking(0.0, at=5.0))
    assert overlay.raw_position() == pytest.approx(100.0)


def test_a_seek_while_paused_holds_its_target(overlay, manual_clock):
    start_song(overlay)
    manual_clock.now = 5.0
    overlay.on_track(seeking(0.0, at=5.0, playing=False))
    manual_clock.now = 9.0
    assert overlay.raw_position() == pytest.approx(100.0)


def test_a_seek_is_projected_from_the_moment_it_was_received(
    overlay, manual_clock
):
    start_song(overlay)
    manual_clock.now = 5.5
    overlay.on_track(seeking(0.0, at=5.0))
    assert overlay.raw_position() == pytest.approx(100.5)


def test_a_seek_is_applied_when_the_duration_is_unknown(overlay, manual_clock):
    start_song(overlay)
    manual_clock.now = 5.0
    np = seeking_to(20.0, at=5.0)
    np.duration = 0.0
    overlay.on_track(np)
    assert overlay.raw_position() == pytest.approx(20.0)


def seeking_to(target, at, speed=1.0):
    np = now_playing(0.0, speed=speed)
    np.seek = track.Seek(position=target, at=at, speed=speed)
    return np


def test_a_seek_past_the_end_lands_on_the_end(overlay, manual_clock):
    start_song(overlay)
    manual_clock.now = 5.0
    overlay.on_track(seeking_to(250.0, at=5.0))
    assert overlay.raw_position() == pytest.approx(200.0)


def test_a_seek_keeps_the_speed_it_was_received_at(overlay, manual_clock):
    start_song(overlay)
    manual_clock.now = 5.5
    overlay.on_track(seeking_to(100.0, at=5.0, speed=2.0))
    assert overlay.raw_position() == pytest.approx(101.0)


def test_readings_of_a_paused_player_are_not_applied(overlay, manual_clock):
    start_song(overlay)
    manual_clock.now = 5.0
    np = now_playing(5.0, read_at=5.0)
    np.playing = False
    np.readings = (track.Reading(50.0, 5.0, np.key),)
    overlay.on_track(np)
    assert overlay.raw_position() == pytest.approx(5.0, abs=0.5)


def test_readings_of_a_paused_player_never_reach_the_clock_as_playing(
    overlay, manual_clock, monkeypatch
):
    start_song(overlay)
    received = []
    real_sync = overlay.playback.sync

    def spy(*args, **kwargs):
        received.append(args[1])
        return real_sync(*args, **kwargs)

    monkeypatch.setattr(overlay.playback, "sync", spy)
    manual_clock.now = 5.0
    np = now_playing(5.0, read_at=5.0)
    np.playing = False
    np.readings = (track.Reading(50.0, 5.0, np.key),)
    overlay.on_track(np)
    assert received == [False]


def test_repeated_readings_of_a_paused_player_never_move_the_lyrics(
    overlay, manual_clock
):
    start_song(overlay)
    for at in (5.0 + 0.4 * step for step in range(10)):
        manual_clock.now = at
        np = now_playing(5.0, read_at=at)
        np.playing = False
        np.readings = (track.Reading(50.0 + at - 5.0, at, np.key),)
        overlay.on_track(np)
    assert overlay.raw_position() == pytest.approx(5.0, abs=0.5)
