import itertools
import random

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
    for poll in range(3):
        c.sync(5.0 + 0.4 * poll, True, 3.0 + 0.4 * poll, 3.0 + 0.4 * poll)
        assert c.position(3.0 + 0.4 * poll) > 42.0
    c.sync(6.2, True, 4.2, 4.2)
    assert c.position(4.2) == pytest.approx(6.2)


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
    assert all(b > a for a, b in itertools.pairwise(samples))


def test_a_seek_while_paused_is_followed():
    c = clock.PlaybackClock(0.0)
    c.reset(30.0, False, 0.0)
    c.sync(29.5, False, 1.0, 1.0)
    assert c.position(2.0) == pytest.approx(29.5)


def test_a_stalled_player_holds_the_lyrics_instead_of_stepping_back():
    c = playing_clock()

    def truth(t):
        return 10.0 if t <= 1.5 else 10.0 + t - 1.5

    previous = c.position(0.0)
    for poll in range(1, 8):
        now = 0.4 * poll
        c.sync(truth(now), True, now, now)
        for step in range(4):
            current = c.position(now + step * 0.1)
            assert current >= previous - 1e-9
            previous = current
    assert c.position(3.0) == pytest.approx(truth(3.0), abs=clock.DEADBAND)


def follow(c, truth, polls, speed=1.0):
    previous = c.position(0.3)
    for poll in range(1, polls):
        now = 0.4 * poll
        c.sync(truth(now), True, now, now, speed)
        for step in range(4):
            current = c.position(now + step * 0.1)
            assert current >= previous - 1e-9
            previous = current


def test_a_player_at_its_reported_speed_is_followed_without_jumps():
    c = clock.PlaybackClock(0.0)
    c.reset(0.0, True, 0.0, 1.5)
    follow(c, lambda t: 1.5 * t, 60, speed=1.5)
    assert speeds(c, 23.6, 27.6) == pytest.approx([1.5] * 80)


def test_a_change_of_speed_is_followed():
    c = playing_clock()
    c.sync(11.0, True, 1.0, 1.0, 2.0)
    assert c.position(3.0) == pytest.approx(15.0)


def test_a_discontinuity_of_exactly_one_second_is_a_seek():
    c = playing_clock()
    c.sync(12.0, True, 1.0, 1.0)
    assert c.position(1.0) == pytest.approx(12.0)


@pytest.mark.parametrize("shift", [-0.7, -0.6, -0.5, -0.4])
def test_a_short_backward_seek_is_settled_by_holding(shift):
    c = playing_clock(position=0.0)

    def truth(t):
        return t if t < 4.0 else t + shift

    follow(c, truth, 20)
    assert c.position(7.6) == pytest.approx(truth(7.6), abs=0.01)


@pytest.mark.parametrize("shift", [0.4, 0.7])
def test_a_short_forward_seek_is_settled_within_two_seconds(shift):
    c = playing_clock(position=0.0)

    def truth(t):
        return t if t < 4.0 else t + shift

    follow(c, truth, 16)
    assert c.position(6.0) == pytest.approx(truth(6.0), abs=clock.DEADBAND)


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


def fast_clock():
    c = clock.PlaybackClock(0.0)
    c.reset(10.0, True, 0.0, 2.0)
    return c


def test_a_seek_is_measured_at_the_player_speed():
    c = fast_clock()
    for poll in range(4):
        at = 2.0 + 0.4 * poll
        c.sync(12.8 + 0.8 * poll, True, at, at, 2.0)
    assert c.position(3.2) == pytest.approx(15.2)


def test_the_reading_age_counts_at_the_player_speed():
    c = fast_clock()
    c.sync(11.2, True, 0.6, 1.2, 2.0)
    assert c.position(3.2) == pytest.approx(16.4)


def test_catching_up_scales_with_the_player_speed():
    c = fast_clock()
    c.sync(12.5, True, 1.0, 1.0, 2.0)
    assert c.position(6.0) == pytest.approx(22.5)
    assert c.position(11.0) == pytest.approx(32.5)


def assert_slewed_after(c, truth, polls, start):
    previous = c.position(0.3)
    for poll in range(1, polls):
        now = 0.4 * poll
        c.sync(truth(now), True, now, now)
        for step in range(4):
            current = c.position(now + step * 0.1)
            if now > start:
                assert 0.095 - 1e-9 <= current - previous <= 0.105 + 1e-9
            previous = current


def late_in_bursts(t):
    return t - 0.45 if int(t / 0.4 + 0.5) % 10 in (3, 4, 5, 6, 7) else t


def test_bursts_of_late_readings_never_hold_or_jump():
    assert_slewed_after(playing_clock(position=0.0), late_in_bursts, 150, 0.0)


def test_a_speed_reported_one_reading_late_does_not_jump():
    c = playing_clock(position=0.0)
    c.sync(0.4, True, 0.4, 0.4)
    c.sync(1.2, True, 0.8, 0.8)
    previous = c.position(0.8)
    for poll in range(3, 15):
        now = 0.4 * poll
        c.sync(1.2 + 2 * (now - 0.8), True, now, now, 2.0)
        current = c.position(now)
        assert current - previous <= 0.4 * 2.1 + 1e-9
        previous = current


def test_a_resume_catches_up_at_once():
    c = playing_clock(position=0.0)
    c.sync(1.2, True, 0.4, 0.4)
    c.sync(1.6, False, 0.8, 0.8)
    c.sync(1.6, True, 1.0, 1.0)
    assert c.position(1.0) == pytest.approx(1.6)


def test_two_steps_forward_are_settled_from_the_first_one():
    c = playing_clock(position=0.0)

    def truth(t):
        return t + (0.8 if t >= 4.4 else 0.4 if t >= 4.0 else 0.0)

    follow(c, truth, 16)
    assert c.position(6.0) == pytest.approx(truth(6.0), abs=clock.DEADBAND)


def test_a_steady_small_lag_is_caught_up_without_stopping():
    c = playing_clock(position=0.0)
    assert_slewed_after(c, lambda t: t if t < 4.0 else t - 0.25, 40, 0.0)


def test_a_new_track_forgets_a_pending_shift():
    c = playing_clock(position=0.0)
    c.sync(0.0, True, 0.4, 0.4)
    c.reset(50.0, True, 3.0)
    c.sync(49.9, True, 3.4, 3.4)
    assert c.position(3.8) > c.position(3.4)


def test_the_same_reading_twice_is_not_a_stall():
    c = playing_clock()
    c.sync(10.9, True, 1.0, 1.0)
    c.sync(10.9, True, 1.0, 1.4)
    assert c.position(1.8) - c.position(1.4) > 0.3


def test_a_step_back_then_forward_is_settled_forward():
    c = playing_clock(position=0.0)

    def truth(t):
        return t + (0.4 if t >= 4.4 else -0.4 if t >= 4.0 else 0.0)

    follow(c, truth, 17)
    assert c.position(6.4) == pytest.approx(truth(6.4), abs=clock.DEADBAND)


def offset_steps(*steps):
    def truth(t):
        index = round(t / 0.4) - 10
        return t + (steps[min(index, len(steps) - 1)] if index >= 0 else 0.0)

    return truth


def test_a_shift_that_drifts_back_is_slewed_back():
    c = playing_clock(position=0.0)
    assert_slewed_after(c, offset_steps(0.4, 0.2, 0.0, -0.2, -0.4), 20, 4.0)


def test_a_shift_that_mostly_closes_is_not_settled():
    c = playing_clock(position=0.0)
    assert_slewed_after(c, offset_steps(0.4, 0.3, 0.2), 20, 4.0)


def test_a_shift_is_settled_only_once():
    c = playing_clock(position=0.0)
    truth = offset_steps(*([0.4] * 6), 0.5, 0.6, 0.7, 0.8)
    assert_slewed_after(c, truth, 26, 6.2)


@pytest.mark.parametrize("real_speed", [0.9, 1.1])
def test_a_player_off_its_reported_speed_stays_within_a_second(real_speed):
    c = playing_clock(position=0.0)
    follow(c, lambda t: real_speed * t, 80)
    assert c.position(31.6) == pytest.approx(real_speed * 31.6, abs=clock.JUMP)


def test_one_reading_more_than_a_second_late_is_ignored():
    c = playing_clock(position=0.0)
    assert_slewed_after(
        c, lambda t: t - 1.2 if round(t / 0.4) == 15 else t, 30, 0.0
    )


def test_a_backward_seek_is_applied_once_confirmed():
    c = playing_clock(position=0.0)
    seek_at = 0.4 * 15
    follow(c, lambda t: t, 15)
    for poll in range(4):
        at = seek_at + 0.4 * poll
        c.sync(at - 3.0, True, at, at)
    assert c.position(seek_at + 1.2) == pytest.approx(seek_at - 1.8)


def test_a_position_rounded_to_the_second_is_not_a_stall():
    c = playing_clock(position=0.0)
    previous = c.position(0.3)
    for poll in range(1, 60):
        now = 0.4 * poll
        c.sync(float(int(now)), True, now, now)
        for step in range(4):
            current = c.position(now + step * 0.1)
            assert current - previous >= 0.095 - 1e-9
            previous = current


def test_random_jitter_is_absorbed_without_steps():
    rng = random.Random(1)
    c = playing_clock(position=0.0)
    assert_slewed_after(c, lambda t: t - rng.uniform(0.0, 0.5), 400, 0.0)


def test_a_hold_is_shortened_when_the_player_speeds_up():
    c = playing_clock(position=0.0)

    def truth(t):
        if t < 4.0:
            return t
        if t < 6.4:
            return t - 0.7
        return 5.7 + 2.0 * (t - 6.4)

    previous = c.position(0.3)
    for poll in range(1, 19):
        now = 0.4 * poll
        c.sync(truth(now), True, now, now, 2.0 if now >= 6.4 else 1.0)
        assert c.position(now) >= previous - 1e-9
        previous = c.position(now)
    assert c.position(7.2) == pytest.approx(truth(7.2), abs=clock.DEADBAND)


def test_a_new_track_starts_its_own_stall_watch():
    c = playing_clock(position=0.0)
    c.reset(50.0, True, 3.0)
    c.sync(50.0, True, 3.4, 3.4)
    assert c.position(3.8) > c.position(3.4)


def test_a_new_track_forgets_a_doubted_reading():
    c = playing_clock(position=0.0)
    c.sync(0.4, True, 0.4, 0.4)
    c.sync(-1.0, True, 0.8, 0.8)
    c.reset(50.0, True, 1.0)
    c.sync(48.0, True, 1.4, 1.4)
    assert c.position(1.4) > 50.0


def test_readings_getting_later_are_not_held_at_once():
    c = playing_clock(position=0.0)
    c.sync(0.4 - 0.45, True, 0.4, 0.4)
    c.sync(0.8 - 1.05, True, 0.8, 0.8)
    assert c.position(1.2) > c.position(0.8)


@pytest.mark.parametrize("late", [1.05, 1.2, 1.5])
def test_late_readings_in_a_row_are_ignored(late):
    c = playing_clock(position=0.0)

    def truth(t):
        return t - late if round(t / 0.4) % 10 in (5, 6, 7) else t

    assert_slewed_after(c, truth, 60, 0.0)


def test_late_readings_that_disagree_restart_the_doubt():
    c = playing_clock(position=0.0)
    c.sync(0.4, True, 0.4, 0.4)
    c.sync(-2.0, True, 0.8, 0.8)
    c.sync(-1.0, True, 1.2, 1.2)
    c.sync(-0.6, True, 1.6, 1.6)
    c.sync(-0.2, True, 2.0, 2.0)
    assert c.position(2.0) > 1.5
    c.sync(0.2, True, 2.4, 2.4)
    assert c.position(2.4) == pytest.approx(0.2)


def test_a_frozen_player_ahead_of_the_lyrics_is_joined():
    c = clock.PlaybackClock(0.0)
    c.reset(0.0, True, 0.0, 0.1)
    for poll in range(1, 7):
        now = 0.4 * poll
        c.sync(0.29, True, now, now, 0.1)
        assert c.position(now) < 0.29
    assert c.position(2.8) > c.position(2.4)


def test_a_rewind_while_paused_is_applied_at_once():
    c = playing_clock(position=50.0)
    c.sync(50.4, False, 0.4, 0.4)
    c.sync(10.0, False, 0.8, 0.8)
    assert c.position(0.8) == pytest.approx(10.0)


def test_a_pause_right_after_a_rewind_stops_at_the_rewound_place():
    c = playing_clock(position=10.0)
    c.sync(10.4, True, 0.4, 0.4)
    c.sync(9.3, True, 0.8, 0.8)
    assert c.position(0.8) > 10.5
    c.sync(9.5, False, 1.2, 1.2)
    assert c.position(1.2) == pytest.approx(9.5)
    assert c.position(4.0) == pytest.approx(9.5)


def test_a_rewind_at_a_speed_change_is_applied_once_confirmed():
    c = playing_clock(position=4.8, at=4.8)
    for poll, position in enumerate([3.9, 4.7, 5.5, 6.3], start=1):
        at = 4.8 + 0.4 * poll
        c.sync(position, True, at, at, 2.0)
    assert c.position(6.4) == pytest.approx(6.3)


def test_a_new_track_does_not_confirm_an_old_doubt():
    c = playing_clock(position=50.0)
    c.sync(10.0, True, 1.0, 1.0)
    c.reset(100.0, True, 1.4)
    c.sync(11.2, True, 2.2, 2.2)
    assert c.position(2.2) > 99.0
