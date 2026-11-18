import itertools

import pytest

from followthelyrics.overlay import clock


def playing_clock(position=10.0, at=0.0):
    c = clock.PlaybackClock(at)
    c.reset(position, True, at)
    return c


def speeds(c, start, end, step=0.05):
    times = [start + i * step for i in range(round((end - start) / step))]
    return [(c.position(t + step) - c.position(t)) / step for t in times]


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
    assert c.position(3.0) == pytest.approx(13.0)


def test_a_late_reading_never_moves_the_lyrics_backward():
    c = playing_clock()
    c.sync(10.5, True, 1.0, 1.0)
    samples = [c.position(1.0 + step / 10) for step in range(101)]
    assert all(b >= a for a, b in itertools.pairwise(samples))
    assert c.position(11.0) == pytest.approx(20.5)


def test_an_early_reading_is_caught_up_smoothly():
    c = playing_clock()
    c.sync(11.6, True, 1.0, 1.0)
    assert c.position(1.1) - c.position(1.0) < 0.2
    assert c.position(13.0) == pytest.approx(23.6)


def test_catching_up_changes_the_speed_by_five_percent_at_most():
    for error in (-0.9, -0.4, 0.3, 0.9):
        c = playing_clock()
        c.sync(11.0 + error, True, 1.0, 1.0)
        assert all(0.95 - 1e-6 <= s <= 1.05 + 1e-6 for s in speeds(c, 1, 30))


def test_an_error_just_under_a_second_is_caught_up():
    c = playing_clock()
    c.sync(11.9, True, 1.0, 1.0)
    assert c.position(1.0) == pytest.approx(11.0)


def test_a_seek_is_applied_at_once():
    c = playing_clock()
    c.sync(12.1, True, 1.0, 1.0)
    assert c.position(1.0) == pytest.approx(12.1)
    c.sync(42.0, True, 2.0, 2.0)
    assert c.position(2.0) == pytest.approx(42.0)
    c.sync(5.0, True, 3.0, 3.0)
    assert c.position(3.0) == pytest.approx(5.0)


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


def test_a_pause_while_ahead_does_not_step_back():
    c = playing_clock()
    c.sync(10.5, True, 1.0, 1.0)
    shown = c.position(1.4)
    c.sync(10.9, False, 1.4, 1.4)
    assert c.position(1.4) == pytest.approx(shown)
    c.sync(10.9, True, 3.0, 3.0)
    samples = [c.position(3.0 + step / 10) for step in range(50)]
    assert samples[0] == pytest.approx(shown)
    assert all(b >= a for a, b in itertools.pairwise(samples))


def test_a_seek_while_paused_is_followed():
    c = clock.PlaybackClock(0.0)
    c.reset(30.0, False, 0.0)
    c.sync(29.5, False, 1.0, 1.0)
    assert c.position(2.0) == pytest.approx(29.5)


def test_a_stalled_player_holds_the_lyrics_instead_of_stepping_back():
    c = playing_clock()

    def truth(t):
        return 10.0 if t <= 1.6 else 10.0 + t - 1.6

    previous = c.position(0.0)
    for poll in range(1, 16):
        now = 0.4 * poll
        c.sync(truth(now), True, now, now)
        for step in range(4):
            current = c.position(now + step * 0.1)
            assert current >= previous - 1e-9
            previous = current
    assert c.position(6.0) == pytest.approx(truth(6.0), abs=clock.DEADBAND)


def test_a_faster_player_is_never_left_a_second_behind():
    c = playing_clock(position=0.0)
    for poll in range(1, 60):
        now = 0.4 * poll
        c.sync(1.5 * now, True, now, now)
        assert abs(c.position(now) - 1.5 * now) < clock.JUMP


def test_jittery_player_never_steps_back_inside_a_track():
    c = playing_clock(position=0.0)
    lags = [0.0, 0.5, 0.1, 0.6, 0.0, 0.3, 0.55, 0.05]
    previous = c.position(0.3)
    now = 0.0
    for poll in range(80):
        now = 0.4 * (poll + 1)
        c.sync(now - lags[poll % len(lags)], True, now, now)
        for step in range(4):
            current = c.position(now + step * 0.1)
            assert current >= previous - 1e-9
            assert 0.0 <= current - previous <= 0.1 * 1.05 + 1e-9
            previous = current
