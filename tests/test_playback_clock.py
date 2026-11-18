import itertools

import pytest

from followthelyrics.overlay import clock


def playing_clock(position=10.0, at=0.0):
    c = clock.PlaybackClock(at)
    c.reset(position, True, at)
    return c


def test_position_advances_with_time_while_playing():
    c = playing_clock()
    assert c.position(2.5) == pytest.approx(12.5)


def test_position_is_frozen_while_paused():
    c = clock.PlaybackClock(0.0)
    c.reset(30.0, False, 0.0)
    assert c.position(5.0) == 30.0


def test_small_errors_are_ignored():
    c = playing_clock()
    c.sync(11.1, True, 1.0, 1.0)
    assert c.position(1.0) == pytest.approx(11.0)


def test_a_late_reading_never_moves_the_lyrics_backward():
    c = playing_clock()
    c.sync(10.5, True, 1.0, 1.0)
    samples = [c.position(1.0 + step / 10) for step in range(31)]
    assert all(b >= a for a, b in itertools.pairwise(samples))
    assert c.position(4.0) == pytest.approx(13.5)


def test_an_early_reading_is_caught_up_smoothly():
    c = playing_clock()
    c.sync(11.6, True, 1.0, 1.0)
    assert c.position(1.1) - c.position(1.0) < 0.2
    assert c.position(4.0) == pytest.approx(14.6)


def test_a_seek_is_applied_at_once():
    c = playing_clock()
    c.sync(42.0, True, 1.0, 1.0)
    assert c.position(1.0) == pytest.approx(42.0)
    c.sync(5.0, True, 2.0, 2.0)
    assert c.position(2.0) == pytest.approx(5.0)


def test_reading_time_counts_instead_of_receipt_time():
    c = playing_clock()
    c.sync(10.6, True, 0.6, 1.2)
    assert c.position(4.0) == pytest.approx(14.0)


def test_pause_and_resume_are_applied_at_once():
    c = playing_clock()
    c.sync(11.0, False, 1.0, 1.0)
    assert c.position(3.0) == pytest.approx(11.0)
    c.sync(11.0, True, 3.0, 3.0)
    assert c.position(4.0) == pytest.approx(12.0)


def test_jittery_player_never_steps_back_inside_a_track():
    c = playing_clock(position=0.0)
    lags = [0.0, 0.5, 0.1, 0.6, 0.0, 0.3, 0.55, 0.05]
    previous = c.position(0.0)
    now = 0.0
    for poll in range(80):
        now = 0.4 * (poll + 1)
        c.sync(now - lags[poll % len(lags)], True, now, now)
        for step in range(4):
            current = c.position(now + step * 0.1)
            assert current >= previous - 1e-9
            previous = current
