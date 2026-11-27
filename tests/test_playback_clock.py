import itertools
import math
import random

import pytest

from followthelyrics.overlay import clock
from followthelyrics.playback import probe

STEP = 0.0125
SYNC_EVERY_STEPS = 32


def playing_clock(position=10.0, at=0.0):
    c = clock.PlaybackClock(at)
    c.reset(position, True, at)
    return c


def speeds(c, start, end, step=0.05):
    times = [start + i * step for i in range(round((end - start) / step))]
    return [(c.position(t + step) - c.position(t)) / step for t in times]


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
    c.sync(11.4, True, 3.0, 3.0)
    assert c.position(3.0) == pytest.approx(11.4)
    assert c.position(4.0) == pytest.approx(12.4)


def test_a_pause_while_ahead_waits_for_the_player_without_stepping_back():
    c = playing_clock()
    c.sync(10.5, True, 1.0, 1.0)
    shown = c.position(1.4)
    c.sync(10.9, False, 1.4, 1.4)
    assert c.position(1.4) == pytest.approx(shown)
    c.sync(10.9, True, 3.0, 3.0)
    samples = [c.position(3.0 + step / 10) for step in range(50)]
    assert samples[0] == pytest.approx(shown)
    assert all(b >= a for a, b in itertools.pairwise(samples))
    assert c.position(4.0) == pytest.approx(11.9)


def test_a_track_played_again_restarts_at_once():
    c = playing_clock(position=198.4)
    c.sync(198.8, True, 0.4, 0.4, duration=200.0)
    c.sync(0.2, True, 0.8, 0.8, duration=200.0)
    assert c.position(0.8) == pytest.approx(0.2)


def test_a_late_reading_near_the_start_is_not_a_restart():
    c = playing_clock(position=2.0)
    c.sync(2.4, True, 0.4, 0.4, duration=200.0)
    c.sync(0.6, True, 0.8, 0.8, duration=200.0)
    assert c.position(0.8) > 2.5


def player_moving_at_every_reading():
    c = playing_clock(position=10.2)
    for poll in range(1, 7):
        now = 0.4 * poll
        c.sync(10.2 + now, True, now, now)
    return c


def test_a_player_updating_at_every_reading_is_held_sooner():
    c = player_moving_at_every_reading()
    c.sync(12.6, True, 2.8, 2.8)
    c.sync(12.6, True, 3.2, 3.2)
    assert c.position(3.6) == pytest.approx(c.position(3.2))


def test_a_single_unchanged_reading_is_not_a_stall():
    c = player_moving_at_every_reading()
    c.sync(12.6, True, 2.8, 2.8)
    assert c.position(3.0) > c.position(2.8)


def test_a_new_track_forgets_how_often_the_player_updates():
    c = player_moving_at_every_reading()
    c.reset(0.0, True, 3.0)
    shown = [c.position(3.0)]
    for poll in range(1, 8):
        now = 3.0 + 0.4 * poll
        c.sync(float(math.floor(now - 3.0)), True, now, now)
        shown.append(c.position(now))
    assert all(b > a for a, b in itertools.pairwise(shown))


def test_a_precise_player_updating_every_second_is_never_frozen():
    def reported(t):
        return 10.3 + math.floor(t + 0.3)

    c = clock.PlaybackClock(0.0)
    c.reset(reported(0.0), True, 0.0)
    shown = [c.position(0.0)]
    for poll in range(1, 76):
        now = 0.4 * poll
        shown += [c.position(now - 0.4 + 0.1 * step) for step in (1, 2, 3)]
        c.sync(reported(now), True, now, now)
        shown.append(c.position(now))
    assert all(b > a for a, b in itertools.pairwise(shown))


def test_a_stall_right_after_the_start_waits_a_full_second():
    c = playing_clock(position=0.0)
    c.sync(0.4, True, 0.4, 0.4)
    c.sync(0.8, True, 0.8, 0.8)
    c.sync(0.8, True, 1.2, 1.2)
    c.sync(0.8, True, 1.6, 1.6)
    assert c.position(1.8) > c.position(1.6)


def test_two_whole_readings_do_not_declare_a_quantized_player():
    c = playing_clock(position=12.0)
    c.sync(12.0, True, 0.4, 0.4)
    c.sync(12.0, True, 0.8, 0.8)
    assert c._truth == {}


def test_three_whole_readings_at_distinct_times_declare_a_quantized_player():
    c = playing_clock(position=12.0)
    for at in (0.4, 0.8, 1.2):
        c.sync(12.0, True, at, at)
    assert c._truth != {}


def test_whole_readings_at_one_instant_count_once():
    c = playing_clock(position=12.0)
    for _ in range(3):
        c.sync(12.0, True, 0.4, 0.4)
    assert c._truth == {}


def test_a_whole_second_player_is_held_after_a_second():
    c = playing_clock(position=0.0)
    for poll in range(1, 11):
        now = 0.4 * poll
        c.sync(float(math.floor(now)), True, now, now)
    for poll in range(11, 14):
        now = 0.4 * poll
        c.sync(4.0, True, now, now)
    assert c.position(5.6) == pytest.approx(c.position(5.2))


def test_readings_closer_together_still_wait_half_a_second():
    c = playing_clock(position=10.0)
    for poll in range(1, 8):
        now = 0.2 * poll
        c.sync(10.0 + now, True, now, now)
    c.sync(11.4, True, 1.8, 1.8)
    assert c.position(1.9) > c.position(1.8)


def test_one_late_update_after_a_quick_one_is_not_a_stall():
    c = playing_clock(position=10.0)
    readings = [10.0] + [10.8 + 0.8 * (poll // 2) for poll in range(11)]
    readings += [15.2, 15.2, 15.2]
    for poll, position in enumerate(readings, start=1):
        now = 0.4 * poll
        c.sync(position, True, now, now)
    assert c.position(6.1) > c.position(6.0)


def test_an_update_a_little_late_on_its_usual_gap_is_not_a_stall():
    c = playing_clock(position=10.0)
    readings = [10.0 + 0.5 * (poll // 2) for poll in range(2, 16)]
    readings.append(readings[-1])
    for poll, position in enumerate(readings, start=1):
        now = 0.25 * poll
        c.sync(position, True, now, now)
    last = 0.25 * len(readings)
    assert c.position(last + 0.1) > c.position(last)


def test_a_long_past_stall_does_not_delay_the_next_one():
    c = playing_clock(position=0.0)
    readings = [0.4, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8, 1.2]
    readings += [1.2 + 0.4 * step for step in range(1, 7)]
    readings += [3.6, 3.6, 3.6, 3.6]
    for poll, position in enumerate(readings, start=1):
        now = 0.4 * poll
        c.sync(position, True, now, now)
    last = 0.4 * len(readings)
    assert c.position(last + 0.4) == pytest.approx(c.position(last))


def test_a_frozen_player_with_a_jittery_position_is_held():
    c = player_moving_at_every_reading()
    noise = itertools.cycle([0.002, -0.002, 0.003, -0.001])
    for poll in range(7, 16):
        now = 0.4 * poll
        c.sync(12.6 + next(noise), True, now, now)
    assert c.position(6.0) < 13.45


def test_a_very_slow_player_is_not_mistaken_for_a_frozen_one():
    c = playing_clock(position=10.0)
    shown = []
    for poll in range(1, 20):
        now = 0.4 * poll
        c.sync(10.0 + 0.02 * now, True, now, now, speed=0.02)
        shown.append(c.position(now))
    assert all(b > a for a, b in itertools.pairwise(shown))


def test_an_old_slow_update_is_forgotten_after_a_while():
    c = playing_clock(position=0.0)
    readings = [0.4, 0.8, 0.8, 0.8, 1.2]
    readings += [1.2 + 0.4 * step for step in range(1, 10)]
    readings += [4.8] * 6
    for poll, position in enumerate(readings, start=1):
        now = 0.4 * poll
        c.sync(position, True, now, now)
    assert c.position(0.4 * len(readings)) < 5.7


def test_a_pause_does_not_count_as_a_slow_update():
    c = player_moving_at_every_reading()
    c.sync(12.6, False, 2.8, 2.8)
    c.sync(12.7, True, 5.0, 5.0)
    c.sync(13.1, True, 5.4, 5.4)
    c.sync(13.1, True, 5.8, 5.8)
    c.sync(13.1, True, 6.2, 6.2)
    assert c.position(6.6) == pytest.approx(c.position(6.2))


def test_a_rewind_near_the_end_is_not_a_restart():
    c = playing_clock(position=198.4)
    c.sync(198.8, True, 0.4, 0.4, duration=200.0)
    c.sync(150.0, True, 0.8, 0.8, duration=200.0)
    assert c.position(0.8) > 198.0


def test_a_resume_close_to_the_lyrics_does_not_jump():
    c = playing_clock()
    c.sync(10.4, False, 0.4, 0.4)
    c.sync(10.5, True, 2.0, 2.0)
    assert c.position(2.0) == pytest.approx(10.4)


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


@pytest.mark.parametrize("shift", [-0.7, -0.4])
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


@pytest.mark.parametrize("late", [1.05, 1.5])
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


def test_a_pause_forgets_a_doubted_rewind():
    c = playing_clock(position=10.0)
    c.sync(10.4, True, 0.4, 0.4)
    c.sync(9.0, True, 0.8, 0.8)
    c.sync(11.0, False, 1.2, 1.2)
    c.sync(10.2, True, 2.0, 2.0)
    assert c.position(2.0) > 10.5


def test_a_seek_while_playing_lands_on_the_target_plus_the_time_since_it():
    c = playing_clock(position=10.0, at=0.0)
    c.seeked(50.0, at=1.0, now=1.2, playing=True)
    assert c.position(1.2) == pytest.approx(50.2)
    assert c.position(2.2) == pytest.approx(51.2)


def test_a_seek_while_paused_holds_the_target():
    c = playing_clock(position=10.0, at=0.0)
    c.seeked(50.0, at=1.0, now=1.2, playing=False)
    assert c.position(1.2) == pytest.approx(50.0)
    assert c.position(9.0) == pytest.approx(50.0)
    assert not c.playing


def test_a_seek_is_projected_at_the_playback_speed():
    c = playing_clock(position=10.0, at=0.0)
    c.seeked(50.0, at=1.0, now=1.5, playing=True, speed=2.0)
    assert c.position(1.5) == pytest.approx(51.0)
    assert c.position(2.5) == pytest.approx(53.0)


def test_a_seek_received_after_the_reading_is_not_projected_in_the_future():
    c = playing_clock(position=10.0, at=0.0)
    c.seeked(50.0, at=2.0, now=1.0, playing=True)
    assert c.position(1.0) == pytest.approx(50.0)


def test_a_seek_is_followed_by_a_consistent_reading_without_a_shift():
    c = playing_clock(position=10.0, at=0.0)
    c.seeked(50.0, at=1.0, now=1.0, playing=True)
    c.sync(50.1, True, 1.1, 1.1)
    assert c.position(1.1) == pytest.approx(50.1)
    assert c.position(3.1) == pytest.approx(52.1)


def test_a_seek_backward_replaces_a_doubted_rewind():
    c = playing_clock(position=50.0, at=0.0)
    c.sync(30.0, True, 0.4, 0.4)
    c.seeked(5.0, at=0.5, now=0.5, playing=True)
    assert c.position(0.5) == pytest.approx(5.0)
    c.sync(5.1, True, 0.6, 0.6)
    assert c.position(0.6) == pytest.approx(5.1)


def test_a_resume_seek_to_the_shown_position_does_not_move_the_lyrics():
    c = playing_clock(position=10.0, at=0.0)
    shown = c.position(5.0)
    c.seeked(shown, 5.0, 5.0, True, 1.0)
    assert c.position(5.0) == pytest.approx(shown)
    assert c.position(5.4) == pytest.approx(shown + 0.4, abs=1e-6)


@pytest.mark.parametrize("real_speed", [0.9, 1.1])
def test_a_player_off_its_announced_speed_is_followed_once_learned(real_speed):
    c = playing_clock(position=10.0, at=0.0)
    worst = 0.0
    for poll in range(1, 151):
        now = 0.4 * poll
        c.sync(10.0 + real_speed * now, True, now, now)
        if now >= 20.0:
            worst = max(worst, abs(c.position(now) - (10.0 + real_speed * now)))
    assert worst <= clock.DEADBAND + 0.03


def test_a_shift_of_the_player_teaches_no_speed():
    c = playing_clock(position=10.0, at=0.0)
    for poll in range(1, 101):
        now = 0.4 * poll
        truth = now - 0.25 if now >= 10.0 else now
        c.sync(10.0 + truth, True, now, now)
    assert c.speed == pytest.approx(1.0, abs=0.01)


def steady_player(
    rate, position=10.0, polls=0.4, count=40, lag=0.0, jitter=None
):
    c = clock.PlaybackClock(0.0)
    c.reset(position, True, 0.0, 1.0)
    rng = random.Random(7)
    for k in range(1, count + 1):
        t = round(polls * k, 3)
        truth = position + rate * t
        noisy = (
            truth if jitter is None else truth + rng.uniform(-jitter, jitter)
        )
        c.sync(noisy, True, t, t + lag, 1.0, 600.0)
    return c


def test_a_seek_does_not_leave_a_learned_gain_behind():
    c = steady_player(1.0, position=100.0, count=5)
    c.seeked(20.0, 2.0, 2.0, True, 1.0)
    worst = 0.0
    for k in range(1, 16):
        t = 2.0 + 0.4 * k
        c.sync(20.0 + 0.4 * k, True, t, t, 1.0, 600.0)
        worst = max(worst, abs(c.position(t + 0.2) - (20.0 + 0.4 * k + 0.2)))
    assert worst < 0.05
    assert clock.GAIN_MIN <= c._gain <= clock.GAIN_MAX


def test_a_new_track_does_not_learn_a_negative_speed():
    c = steady_player(1.0, position=100.0, count=5)
    c.reset(0.5, True, 2.4, 1.0)
    for k in range(1, 16):
        t = 2.4 + 0.4 * k
        c.sync(0.5 + 0.4 * k, True, t, t, 1.0, 180.0)
        assert c.speed > 0.0
        assert c.position(t + 0.2) == pytest.approx(
            0.5 + 0.4 * k + 0.2, abs=0.05
        )


def test_the_learned_gain_follows_a_quarter_speed_player():
    c = steady_player(0.25, count=40)
    assert c.speed == pytest.approx(0.25, abs=0.02)


def test_the_learned_gain_follows_a_triple_speed_player():
    c = steady_player(3.0, count=40)
    assert c.speed == pytest.approx(3.0, abs=0.05)


@pytest.mark.parametrize("rate", [0.8, 1.25])
def test_a_large_steady_deviation_is_learned(rate):
    c = steady_player(rate, count=60)
    assert c.speed == pytest.approx(rate, abs=0.02)


@pytest.mark.parametrize("rate", [0.8, 1.25])
def test_a_large_deviation_is_learned_despite_jitter_and_late_readings(rate):
    c = steady_player(rate, count=60, lag=0.3, jitter=0.05)
    assert c.speed == pytest.approx(rate, abs=0.03)


def test_a_paused_seek_is_not_undone_by_the_next_reading():
    c = clock.PlaybackClock(0.0)
    c.reset(12.0, False, 0.0, 1.0)
    c.seeked(12.5, 1.0, 1.0, False, 1.0)
    c.sync(12.0, False, 1.2, 1.2, 1.0, 60.0)
    assert c.position(1.2) == pytest.approx(12.5)
    c.sync(12.0, False, 1.6, 1.6, 1.0, 60.0)
    assert c.position(1.6) == pytest.approx(12.5)


def test_a_paused_seek_holds_while_the_stale_value_repeats_for_ten_seconds():
    c = clock.PlaybackClock(0.0)
    c.reset(12.0, False, 0.0, 1.0)
    c.seeked(12.5, 1.0, 1.0, False, 1.0)
    for k in range(1, 21):
        t = 1.0 + 0.5 * k
        c.sync(12.0, False, t, t, 1.0, 60.0)
        assert c.position(t) == pytest.approx(12.5)


def test_a_seek_held_through_a_long_pause_keeps_the_target_after_resume():
    c = clock.PlaybackClock(0.0)
    c.reset(12.0, False, 0.0, 1.0)
    c.seeked(12.5, 1.0, 1.0, False, 1.0)
    t = 1.0
    for _ in range(10):
        t = round(t + 0.5, 6)
        c.sync(12.0, False, t, t, 1.0, 60.0)
    resume = round(t + 0.1, 6)
    c.status(True, resume, 1.0)
    for k in range(1, 8):
        t = round(resume + 0.5 * k, 6)
        c.sync(12.0, True, t, t, 1.0, 60.0)
        assert c.position(t) == pytest.approx(
            12.5 + (t - resume), abs=clock.DEADBAND
        )


def test_a_paused_seek_on_truncated_readings_resumes_within_the_deadband():
    c = clock.PlaybackClock(0.0)
    c.reset(12.0, False, 0.0, 1.0)
    c.seeked(12.5, 1.0, 1.0, False, 1.0)
    t = 1.0
    for _ in range(25):
        t += 0.4
        c.sync(12.0, False, t, t, 1.0, 600.0)
    start = t
    c.status(True, start)
    for _ in range(25):
        t += 0.4
        truth = 12.5 + (t - start)
        c.sync(math.floor(truth), True, t, t, 1.0, 600.0)
        assert abs(c.position(t) - truth) <= clock.DEADBAND + 0.01


def test_a_paused_seek_is_kept_while_the_position_repeats_for_a_minute():
    c = clock.PlaybackClock(0.0)
    c.reset(12.0, False, 0.0, 1.0)
    c.seeked(12.5, 1.0, 1.0, False, 1.0)
    for k in range(1, 151):
        t = 1.0 + 0.4 * k
        c.sync(12.0, False, t, t, 1.0, 600.0)
    assert c.position(61.0) == pytest.approx(12.5)


def test_a_paused_seek_is_released_by_a_different_position():
    c = clock.PlaybackClock(0.0)
    c.reset(12.0, False, 0.0, 1.0)
    c.seeked(12.5, 1.0, 1.0, False, 1.0)
    c.sync(12.0, False, 6.0, 6.0, 1.0, 60.0)
    c.sync(20.0, False, 6.5, 6.5, 1.0, 60.0)
    assert c.position(6.5) == pytest.approx(20.5, abs=0.5)


def test_a_paused_seek_is_released_by_a_track_change():
    c = clock.PlaybackClock(0.0)
    c.reset(12.0, False, 0.0, 1.0)
    c.seeked(12.5, 1.0, 1.0, False, 1.0)
    c.reset(12.0, False, 5.0, 1.0)
    c.sync(12.0, False, 5.5, 5.5, 1.0, 60.0)
    assert c.position(5.5) == pytest.approx(12.0)


def test_a_paused_seek_is_released_by_resume_and_the_readings_after_it_decide():
    c = clock.PlaybackClock(0.0)
    c.reset(12.0, False, 0.0, 1.0)
    c.seeked(12.5, 1.0, 1.0, False, 1.0)
    c.sync(12.0, False, 10.0, 10.0, 1.0, 60.0)
    c.sync(12.0, True, 10.5, 10.5, 1.0, 60.0)
    for k in range(10):
        t = 10.5 + 0.5 * k
        c.sync(12.0 + (t - 10.5), True, t, t, 1.0, 60.0)
    assert c.position(15.0) == pytest.approx(16.5, abs=0.3)


def test_a_playing_seek_hold_expires_when_readings_keep_disagreeing():
    c = clock.PlaybackClock(0.0)
    c.reset(12.0, True, 0.0, 1.0)
    c.seeked(12.5, 1.0, 1.0, True, 1.0)
    for k in range(6):
        t = 1.5 + 0.5 * k
        c.sync(20.3, True, t, t, 1.0, 60.0)
    assert c.position(4.0) == pytest.approx(20.8, abs=0.6)


def test_a_paused_seek_released_on_resume_lets_stale_readings_move_the_clock():
    c = clock.PlaybackClock(0.0)
    c.reset(12.0, False, 0.0, 1.0)
    c.seeked(12.5, 1.0, 1.0, False, 1.0)
    c.sync(12.0, False, 10.0, 10.0, 1.0, 60.0)
    for t in (10.5, 11.0, 11.5, 12.0):
        c.sync(12.0, True, t, t, 1.0, 60.0)
    assert c.position(12.25) > 12.8


def test_a_confirmed_paused_seek_is_kept_and_later_readings_apply():
    c = clock.PlaybackClock(0.0)
    c.reset(12.0, False, 0.0, 1.0)
    c.seeked(12.5, 1.0, 1.0, False, 1.0)
    c.sync(12.5, False, 1.2, 1.2, 1.0, 60.0)
    c.sync(30.0, False, 1.6, 1.6, 1.0, 60.0)
    assert c.position(1.6) == pytest.approx(30.0)


def test_a_playing_seek_ignores_a_stale_reading_until_settled():
    c = playing_clock()
    c.seeked(40.0, 1.0, 1.0, True, 1.0)
    c.sync(11.5, True, 1.5, 1.5, 1.0, 600.0)
    assert c.position(1.5) == pytest.approx(40.5)
    c.sync(40.6, True, 1.6, 1.6, 1.0, 600.0)
    assert c.position(1.6) == pytest.approx(40.6, abs=0.05)


def test_a_reset_forgets_the_readings_before_it():
    c = clock.PlaybackClock(0.0)
    c.reset(9.59, True, 0.0, 1.0)
    c.sync(9.99, True, 0.4, 0.4, 1.0, 600.0)
    c.reset(10.0, True, 0.5, 1.0)
    for k in range(1, 25):
        t = 0.5 + 0.4 * k
        c.sync(t + 9.5, True, t, t, 1.0, 600.0)
    assert c.speed == pytest.approx(1.0, abs=1e-6)


def worst_error_of(events):
    c = clock.PlaybackClock(0.0)
    c.reset(100.0, True, 0.0, 1.0)
    worst = 0.0
    for kind, t, position in events:
        if kind == "seek":
            c.seeked(position, t, t, True, 1.0)
            continue
        c.sync(position, True, t, t, 1.0, 600.0)
        worst = max(worst, abs(c.position(t + 0.2) - position - 0.2))
    return worst


def test_a_steady_player_is_followed_closely_once_its_pace_is_learned():
    before = [("sync", round(0.4 * k, 2), 100.0 + 0.4 * k) for k in range(1, 6)]
    after = [
        ("sync", round(2.0 + 0.4 * k, 2), 102.0 + 0.4 * k) for k in range(1, 16)
    ]
    assert worst_error_of(before + after) < 0.05


def test_a_seek_in_the_middle_does_not_teach_a_wrong_pace():
    before = [("sync", round(0.4 * k, 2), 100.0 + 0.4 * k) for k in range(1, 6)]
    after = [
        ("sync", round(2.0 + 0.4 * k, 2), 20.0 + 0.4 * k) for k in range(1, 16)
    ]
    assert worst_error_of([*before, ("seek", 2.0, 20.0), *after]) < 0.05


def test_a_paused_seek_holds_its_target_against_the_stale_poll_after_it():
    c = clock.PlaybackClock(0.0)
    c.reset(12.0, False, 0.0, 1.0)
    c.seeked(12.5, 1.0, 1.0, False, 1.0)
    assert c.position(1.0) == pytest.approx(12.5)
    c.sync(12.0, False, 1.2, 1.2, 1.0, 60.0)
    assert c.position(1.2) == pytest.approx(12.5)
    c.sync(12.0, False, 1.6, 1.6, 1.0, 60.0)
    assert c.position(1.6) == pytest.approx(12.5)


def test_a_new_track_is_followed_at_its_own_pace_after_a_learned_one():
    c = clock.PlaybackClock(0.0)
    c.reset(100.0, True, 0.0, 1.0)
    for k in range(1, 6):
        c.sync(100.0 + 0.4 * k, True, 0.4 * k, 0.4 * k, 1.0, 300.0)
    c.reset(0.5, True, 2.4, 1.0)
    for k in range(1, 16):
        t = 2.4 + 0.4 * k
        c.sync(0.5 + 0.4 * k, True, t, t, 1.0, 180.0)
        assert c.position(t + 0.2) == pytest.approx(
            0.5 + 0.4 * k + 0.2, abs=0.05
        )
    assert c._gain == pytest.approx(1.0)


def test_a_learned_gain_is_not_slower_than_the_smallest_allowed():
    c = steady_player(0.02, count=40)
    assert c.speed == pytest.approx(clock.GAIN_MIN, abs=0.005)


def resume_error(speed, phase, poll=0.4):
    c = clock.PlaybackClock(0.0)
    c.reset(12.0, False, 0.0, speed)
    c.seeked(12.5, 1.0, 1.0, False, speed)
    t = 1.0
    for _ in range(25):
        t += poll
        c.sync(12.0, False, t, t, speed, 600.0)
    start = t
    c.status(True, start, speed)
    worst = 0.0
    for _ in range(25):
        t += poll
        truth = 12.5 + (t - start) * speed
        c.sync(math.floor(truth + phase), True, t, t, speed, 600.0)
        worst = max(worst, abs(c.position(t) - truth))
    return worst


@pytest.mark.parametrize("speed", [1.0, 2.0])
@pytest.mark.parametrize("phase", [0.0, 0.5])
def test_a_paused_exact_position_resumes_exactly_at_one_and_two_times(
    speed, phase
):
    assert resume_error(speed, phase) <= clock.DEADBAND + 0.01


def test_a_pause_freezes_the_position_at_the_edge_time():
    c = clock.PlaybackClock(0.0)
    c.reset(20.0, True, 0.0, 1.0, track_start=False)
    c.seeked(20.0, 0.0, 0.0, True, 1.0)
    c.status(False, 3.0)
    assert c.position(3.0) == pytest.approx(23.0)
    assert c.position(12.0) == pytest.approx(23.0)
    c.sync(23, False, 13.0, 13.0, 1.0, 600.0)
    assert c.position(13.0) == pytest.approx(23.0)


def test_an_unpinned_resume_is_dated_at_the_edge_not_at_the_poll():
    c = playing_clock(10.0, 0.0)
    c.sync(10.0, True, 1.0, 1.0)
    c.status(False, 5.0)
    held = c.position(5.0)
    c.status(True, 9.0)
    assert c.position(9.0) == pytest.approx(held)
    assert c.position(10.0) == pytest.approx(held + 1.0)


def test_a_repeated_status_changes_nothing():
    c = playing_clock(10.0, 0.0)
    before = c.position(2.0)
    c.status(True, 1.0)
    assert c.position(2.0) == pytest.approx(before)


def test_a_pause_without_a_pin_holds_the_position_shown_at_the_edge():
    c = clock.PlaybackClock(0.0)
    c.reset(0.0, True, 0.0, 1.0, app="app")
    c.status(True, 0.0)
    for t in (0.4, 0.8, 1.2, 1.6, 2.0):
        c.sync(math.floor(t), True, t, t, 1.0, 600.0)
    shown = c.position(2.0)
    c.status(False, 2.0)
    assert c.position(9.0) == pytest.approx(shown)


def probed_track(c, origin, speed, phase, start, app, anchor, total=8.0):
    def truth(t):
        return origin + speed * t

    if anchor:
        c.reset(origin, True, start, speed, app=app, track_start=True)
    else:
        c.reset(math.floor(truth(start) + phase), True, start, speed, app=app)
    c.status(True, start, speed)
    t = start
    worst = 0.0
    while t < start + total:
        step = 0.05 if t - start < 2.0 else 0.4
        t = round(t + step, 6)
        c.sync(math.floor(truth(t) + phase), True, t, t, speed, 600.0)
        if t >= start + 3.0:
            worst = max(worst, abs(c.position(t) - truth(t)))
    return worst


@pytest.mark.parametrize("speed", [1.0, 2.0])
@pytest.mark.parametrize("phase", [0.0, 0.5])
def test_a_track_start_is_exact_at_one_and_two_times(speed, phase):
    c = clock.PlaybackClock(0.0)
    assert probed_track(c, 0.0, speed, phase, 0.0, "app", True) <= (
        clock.DEADBAND + 0.01
    )


@pytest.mark.parametrize("speed", [1.0, 2.0])
@pytest.mark.parametrize("phase", [0.0, 0.5])
def test_a_new_track_of_a_learned_app_is_within_the_deadband(speed, phase):
    c = clock.PlaybackClock(0.0)
    probed_track(c, 0.0, speed, phase, 0.0, "app", True)
    error = probed_track(c, 12.3, speed, phase, 20.0, "app", False)
    assert error <= clock.DEADBAND + 0.01


@pytest.mark.parametrize("speed", [1.0, 2.0])
@pytest.mark.parametrize("phase", [0.0, 0.5])
@pytest.mark.parametrize("origin", [12.3, 12.8])
def test_a_track_without_any_anchor_stays_within_the_pre_anchor_bound(
    speed, phase, origin
):
    c = clock.PlaybackClock(0.0)
    assert (
        probed_track(c, origin, speed, phase, 0.0, "app", False) <= 0.3 + 1e-6
    )


def test_on_the_poll_grid_two_pre_anchor_truths_apart_read_the_same():
    rounded_origin, truncated_origin = 12.3, 12.99
    floor = (truncated_origin - rounded_origin) / 2
    times = [round(0.4 * k, 6) for k in range(1, 151)]
    rounded = [math.floor(rounded_origin + t + 0.5) for t in times]
    truncated = [math.floor(truncated_origin + t) for t in times]
    assert rounded == truncated
    c = clock.PlaybackClock(0.0)
    c.reset(rounded[0], True, times[0], 1.0, app="app")
    worst = 0.0
    for t, reading in zip(times, rounded, strict=True):
        c.sync(reading, True, t, t, 1.0, 600.0, app="app")
        if t >= 20.0:
            shown = c.position(t)
            worst = max(
                worst,
                abs(shown - rounded_origin - t),
                abs(shown - truncated_origin - t),
            )
    assert floor <= worst <= floor + 0.01


def test_a_rate_learned_too_high_is_relearned_from_readings_left_behind():
    real = 2.1
    c = clock.PlaybackClock(0.0)
    c.reset(0.0, True, 0.0, 1.5, app="app", track_start=True)
    times = [0.1, 0.2, 0.3] + [round(1.4 + 0.4 * k, 6) for k in range(97)]
    worst = 0.0
    for t in times:
        c.sync(math.floor(real * t + 0.5), True, t, t, 1.5, 600.0, app="app")
        if t >= 20.0:
            worst = max(worst, abs(c.position(t) - real * t))
    assert worst <= clock.DEADBAND


def test_a_correction_far_behind_the_display_steps_back_at_the_reading():
    real = 1.04
    c = clock.PlaybackClock(0.0)
    c.reset(0.0, True, 0.0, 1.0, app="app", track_start=True)
    at_reading, half_a_poll_later = [], []
    for k in range(1, 61):
        t = float(k)
        c.sync(math.floor(real * t + 0.5), True, t, t, 1.0, 600.0, app="app")
        at_reading.append(abs(c.position(t) - real * t))
        half_a_poll_later.append(abs(c.position(t + 0.5) - real * (t + 0.5)))
    last_off = max(
        i for i, e in enumerate(half_a_poll_later) if e > clock.DEADBAND
    )
    assert at_reading[last_off] > clock.HOLD_LEAD
    assert at_reading[last_off + 1] <= clock.DEADBAND


HELD_TARGET, HELD_AT = 198.4, 10.2


def held_seek_times():
    return [round(11.1 + 0.9 * k, 6) for k in range(40)]


HELD_HULL_MARGIN = 0.08


def held_seek_readings(real, quantize):
    return [
        (t, quantize(HELD_TARGET + real * (t - HELD_AT)))
        for t in held_seek_times()
    ]


def held_seek_errors(real, quantize=math.floor):
    c = clock.PlaybackClock(0.0)
    c.reset(0.0, True, 0.0, 1.0, app="app", track_start=True)
    c.seeked(HELD_TARGET, HELD_AT, HELD_AT, True, 1.0, app="app")
    errors = []
    for t, reading in held_seek_readings(real, quantize):
        c.sync(reading, True, t, t, 1.0, 600.0, app="app")
        truth = HELD_TARGET + real * (t - HELD_AT)
        errors.append((t - HELD_AT, c.position(t) - truth))
    return errors


def held_seek_hull(readings):
    low = dict.fromkeys(clock.PHASES, -math.inf)
    high = dict.fromkeys(clock.PHASES, math.inf)
    hulls = []
    for t, reading in readings:
        elapsed = t - HELD_AT
        for phase in clock.PHASES:
            low[phase] = max(
                low[phase], (reading - phase - HELD_TARGET) / elapsed
            )
            high[phase] = min(
                high[phase], (reading - phase + 1.0 - HELD_TARGET) / elapsed
            )
        alive = [phase for phase in clock.PHASES if low[phase] < high[phase]]
        ends = [
            HELD_TARGET + elapsed * bound
            for phase in alive
            for bound in (low[phase], high[phase])
        ]
        width = max(ends) - min(ends)
        if any(low[phase] <= 1.0 <= high[phase] for phase in alive):
            bound = width
        else:
            bound = width / 2 + HELD_HULL_MARGIN
        hulls.append((len(alive), bound))
    return hulls


def test_a_truncating_player_fast_and_a_rounding_one_at_rate_read_alike():
    fast = held_seek_readings(1.2, math.floor)
    at_rate = held_seek_readings(1.0, round_half_up)
    assert fast[:7] == at_rate[:7]
    assert fast[6][0] - HELD_AT == pytest.approx(6.3)
    assert fast[7] != at_rate[7]


def test_a_rounding_player_at_its_announced_rate_stays_exact_after_a_seek():
    errors = held_seek_errors(1.0, round_half_up)
    assert max(abs(error) for _, error in errors) <= 1e-6


@pytest.mark.parametrize(
    "offset",
    [
        0.0,
        1e-9,
        -1e-9,
        clock.POSITION_RESOLUTION / 2,
        -clock.POSITION_RESOLUTION / 2,
    ],
)
@pytest.mark.parametrize("shift", [0.0, 3e-7, -3e-7])
@pytest.mark.parametrize("fraction", [0.0, 0.1, 0.4, 0.5, 0.6])
@pytest.mark.parametrize("poll", [0.4, 0.5, 0.9, 1.0])
@pytest.mark.parametrize("mode", ["exact", "trunc", "round"])
def test_a_seek_at_rate_is_exact_on_and_beside_the_reading_boundaries(
    mode, poll, fraction, shift, offset
):
    quantize = {"exact": float, "trunc": math.floor, "round": round_half_up}[
        mode
    ]
    target = 198.0 + fraction
    c = clock.PlaybackClock(0.0)
    c.reset(0.0, True, 0.0, 1.0, app="app", track_start=True)
    c.seeked(target, HELD_AT, HELD_AT, True, 1.0, app="app")
    worst = 0.0
    for k in range(1, int(40 / poll) + 1):
        t = round(HELD_AT + poll * k, 9) + shift
        truth = target + (t - HELD_AT) + offset
        c.sync(quantize(truth), True, t, t, 1.0, 600.0, app="app")
        worst = max(worst, abs(c.position(t) - truth))
    assert worst <= clock.POSITION_RESOLUTION


@pytest.mark.parametrize("real", [1.05, 1.1, 1.15, 1.2, 1.25, 1.3, 1.4, 1.5])
def test_a_held_seek_off_its_announced_rate_stays_in_the_hull(real):
    errors = held_seek_errors(real)
    hulls = held_seek_hull(held_seek_readings(real, math.floor))
    for (_, error), (alive, bound) in zip(errors, hulls, strict=True):
        if alive == len(clock.PHASES):
            assert abs(error) <= bound
        else:
            assert abs(error) <= clock.DEADBAND


@pytest.mark.parametrize("mode", ["trunc", "round"])
def test_a_learned_rate_that_fits_every_cell_is_kept_as_they_narrow(mode):
    quantize = math.floor if mode == "trunc" else round_half_up
    c = clock.PlaybackClock(0.0)
    c.reset(0.0, True, 0.0, 1.0, app="app", track_start=True)
    late = []
    for t in range(1, 61):
        truth = 2.0 * t
        c.sync(quantize(truth), True, t, t, 1.0, 600.0, app="app")
        if t >= 20:
            late.append(abs(c.position(t) - truth))
    assert max(late) <= clock.DEADBAND


@pytest.mark.parametrize("real", [1.2, 1.4])
def test_a_held_seek_on_a_player_faster_than_announced_converges(real):
    late = [abs(e) for elapsed, e in held_seek_errors(real) if elapsed >= 20.0]
    assert max(late) <= clock.DEADBAND


def test_readings_during_a_held_seek_at_1_4x_keep_the_display_within_a_jump():
    released = [
        abs(e) for elapsed, e in held_seek_errors(1.4) if 2.0 < elapsed < 6.0
    ]
    assert max(released) < clock.JUMP


def test_a_rate_learned_from_an_ignored_seek_dies_with_it():
    lag = 0.01
    c = clock.PlaybackClock(0.0)
    c.reset(12.0, False, 0.0, 1.0)
    c.seeked(12.5, 0.0, 0.0, False, 1.0)
    t = 0.0
    while t < 10.0:
        t = round(t + 0.4, 6)
        c.sync(12, False, t, t, 1.0, 600.0)
    start = t
    errors = []
    while t < start + 60.0:
        t = round(t + 0.4, 6)
        truth = 12.0 + (t - start - lag)
        c.sync(math.floor(truth), True, t, t, 1.0, 600.0)
        if t >= start + 3.0:
            errors.append(abs(c.position(t) - truth))
    assert max(errors) <= errors[-1] + 0.01


@pytest.mark.parametrize("skip", [2.0, 3.0])
def test_a_skip_after_an_ignored_seek_is_read_from_the_readings_alone(skip):
    c = clock.PlaybackClock(0.0)
    c.reset(12.0, True, 0.0, 1.0, app="app")
    t = 0.0
    while t < 6.0:
        t = round(t + 1.0, 6)
        c.sync(math.floor(12.0 + t), True, t, t, 1.0, 600.0, app="app")
    c.seeked(40.0, t, t, True, 1.0, app="app")
    start = t
    errors = []
    while t < start + 20.0:
        t = round(t + 1.0, 6)
        skipped = t - start >= 2.4
        truth = 12.0 + t + (skip if skipped else 0.0)
        c.sync(math.floor(truth), True, t, t, 1.0, 600.0, app="app")
        if skipped:
            errors.append(abs(c.position(t) - truth))
    assert max(errors[1:]) <= clock.QUANTUM / 2


@pytest.mark.parametrize("mode", ["trunc", "round"])
def test_a_gain_fitted_to_an_ignored_seek_is_dropped_with_its_cells(mode):
    quantize = math.floor if mode == "trunc" else round_half_up
    c = clock.PlaybackClock(0.0)
    c.reset(0.0, True, 0.0, 1.0, app="app", track_start=True)
    late = []
    for t in range(1, 46):
        if t == 15:
            c.seeked(40.0, t, t, True, 1.0, app="app")
        truth = 1.5 * t
        c.sync(quantize(truth), True, t, t, 1.0, 600.0, app="app")
        if t > 21:
            late.append(abs(c.position(t) - truth))
    assert max(late) <= clock.QUANTUM


def test_a_mode_learned_for_one_app_is_not_applied_to_another():
    learned = clock.PlaybackClock(0.0)
    probed_track(learned, 0.0, 1.0, 0.5, 0.0, "first", True)
    fresh = clock.PlaybackClock(0.0)
    error = probed_track(fresh, 12.3, 1.0, 0.0, 20.0, "second", False)
    assert error <= 0.3 + 1e-6


def paused_quantized_clock(mode, pause, speed):
    quantize = math.floor if mode == "trunc" else round_half_up

    def truth(t):
        return 12.3 + speed * (t - 3.0)

    c = clock.PlaybackClock(0.0)
    c.reset(quantize(0.0), True, 0.0, speed, app="app", track_start=True)
    t = 0.0
    while t < 3.0 - 1e-9:
        t = round(t + 0.4, 6)
        c.sync(quantize(speed * t), True, t, t, speed, 600.0, app="app")
    c.seeked(12.3, 3.0, 3.0, True, speed, app="app")
    tick = 3.0
    while tick < 5.0 - 1e-9:
        tick = round(tick + 0.05, 6)
        now = round(math.ceil(tick / 0.2 - 1e-9) * 0.2, 6)
        c.sync(quantize(truth(tick)), True, tick, now, speed, 600.0, app="app")
    t = tick
    while t < pause - 0.25:
        t = round(t + 0.4, 6)
        c.sync(quantize(truth(t)), True, t, t, speed, 600.0, app="app")
    c.status(False, pause, speed)
    return c, quantize, truth, t


@pytest.mark.parametrize("speed", [1.0, 2.0])
@pytest.mark.parametrize("pause", [20.3, 20.7])
@pytest.mark.parametrize(
    "before,after", [("trunc", "round"), ("round", "trunc")]
)
def test_a_pinned_resume_revises_the_reading_mode(before, after, pause, speed):
    modes = {"trunc": math.floor, "round": round_half_up}
    c = clock.PlaybackClock(0.0)
    c.reset(0.0, True, 0.0, speed, app="app", track_start=True)
    t = 0.0
    while t < pause - 0.4:
        t = round(t + 0.4, 6)
        c.sync(modes[before](speed * t), True, t, t, speed, 600.0, app="app")
    c.status(False, pause, speed)
    resume = pause + 5.0
    c.status(True, resume, speed)
    t = resume
    worst = 0.0
    while t < resume + 20.0:
        t = round(t + 0.4, 6)
        truth = speed * (pause + t - resume)
        c.sync(modes[after](truth), True, t, t, speed, 600.0, app="app")
        worst = max(worst, abs(c.position(t) - truth))
    assert worst <= clock.POSITION_RESOLUTION


@pytest.mark.parametrize("speed", [1.0, 2.0])
@pytest.mark.parametrize(
    "pause,width", [(20.3, 0.0), (20.7, 0.0), (20.95, clock.PIN_WIDTH)]
)
@pytest.mark.parametrize("mode", ["trunc", "round"])
def test_the_paused_edge_shows_the_pinned_position(mode, pause, width, speed):
    c, _, truth, _ = paused_quantized_clock(mode, pause, speed)
    assert c.position(pause) == pytest.approx(
        truth(pause), abs=width * speed + 1e-6
    )


@pytest.mark.parametrize("speed", [1.0, 2.0])
@pytest.mark.parametrize(
    "pause,width", [(20.3, 0.0), (20.7, 0.0), (20.95, clock.PIN_WIDTH)]
)
@pytest.mark.parametrize("mode", ["trunc", "round"])
def test_a_paused_quantized_reading_keeps_the_frozen_position(
    mode, pause, width, speed
):
    c, quantize, truth, t = paused_quantized_clock(mode, pause, speed)
    worst = 0.0
    for _ in range(10):
        t = round(t + 0.4, 6)
        c.sync(quantize(truth(pause)), False, t, t, speed, 600.0, app="app")
        worst = max(worst, abs(c.position(t) - truth(pause)))
    assert worst <= width * speed + 1e-6


@pytest.mark.parametrize("speed", [1.0, 2.0])
@pytest.mark.parametrize(
    "pause,width", [(20.3, 0.0), (20.7, 0.0), (20.95, clock.PIN_WIDTH)]
)
@pytest.mark.parametrize("mode", ["trunc", "round"])
def test_a_resumed_quantized_player_continues_from_its_exact_pause(
    mode, pause, width, speed
):
    c, _, truth, _ = paused_quantized_clock(mode, pause, speed)
    resume = round(pause + 2.0, 6)
    c.status(True, resume, speed)
    assert c.position(resume) == pytest.approx(
        truth(pause), abs=width * speed + 1e-6
    )


@pytest.mark.parametrize("mode", ["trunc", "round"])
def test_a_pause_during_a_slew_after_an_exact_seek_freezes_the_pinned_position(
    mode,
):
    quantize = math.floor if mode == "trunc" else round_half_up
    c = clock.PlaybackClock(0.0)
    c.reset(0.0, True, 0.0, 2.0, app="app", track_start=True)
    c.seeked(12.3, 0.0, 0.0, True, 2.0, app="app")
    t = 0.0
    while t < 2.25 - 1e-9:
        t = round(t + 0.05, 6)
        c.sync(quantize(12.3 + 1.94 * t), True, t, t, 2.0, 600.0, app="app")
    c.status(False, 2.25, 2.0)
    assert c.position(2.25) == pytest.approx(
        12.3 + 1.94 * 2.25, abs=clock.PIN_WIDTH
    )


@pytest.mark.parametrize("sampling", [0.1, 0.4, 0.8])
@pytest.mark.parametrize("truth", [1.94, 2.0])
@pytest.mark.parametrize("mode", ["trunc", "round"])
def test_a_seek_then_pause_stays_within_the_deadband(mode, truth, sampling):
    quantize = math.floor if mode == "trunc" else round_half_up
    c = clock.PlaybackClock(0.0)
    c.reset(0.0, True, 0.0, 2.0, app="app", track_start=True)
    c.seeked(12.3, 0.0, 0.0, True, 2.0, app="app")
    t = 0.0
    while t < 16.0 - 1e-9:
        t = round(t + sampling, 6)
        c.sync(quantize(12.3 + truth * t), True, t, t, 2.0, 600.0, app="app")
    pause = round(t + 0.79, 6)
    c.status(False, pause, 2.0)
    assert c.position(pause) == pytest.approx(
        12.3 + truth * pause, abs=clock.DEADBAND
    )


@pytest.mark.parametrize("mode", ["trunc", "round"])
def test_a_slew_pause_before_an_exact_anchor_is_within_the_pre_anchor_bound(
    mode,
):
    quantize = math.floor if mode == "trunc" else round_half_up
    c = clock.PlaybackClock(0.0)
    c.reset(quantize(12.3), True, 0.0, 2.0, app="app", track_start=True)
    t = 0.0
    while t < 2.25 - 1e-9:
        t = round(t + 0.05, 6)
        c.sync(quantize(12.3 + 1.94 * t), True, t, t, 2.0, 600.0, app="app")
    c.status(False, 2.25, 2.0)
    pinned = c.position(2.25)
    assert abs(pinned - (12.3 + 1.94 * 2.25)) < 0.3
    assert c.position(3.0) == pinned


@pytest.mark.parametrize("sampling", [0.1, 0.4, 0.8])
@pytest.mark.parametrize("speed", [0.97, 1.0, 1.03])
@pytest.mark.parametrize("mode", ["trunc", "round"])
def test_an_anchored_quantized_player_converges_within_the_deadband(
    mode, speed, sampling
):
    quantize = math.floor if mode == "trunc" else round_half_up
    c = clock.PlaybackClock(0.0)
    c.reset(0.0, True, 0.0, 1.0, app="app", track_start=True)
    worst = 0.0
    t = 0.0
    while t < 30.0 - 1e-9:
        t = round(t + sampling, 6)
        c.sync(quantize(speed * t), True, t, t, 1.0, 600.0, app="app")
        if t >= 20.0:
            worst = max(worst, abs(c.position(t) - speed * t))
    assert worst <= clock.DEADBAND


@pytest.mark.parametrize("mode", ["trunc", "round"])
def test_a_quantized_player_running_fast_is_steered_within_the_deadband(mode):
    quantize = math.floor if mode == "trunc" else round_half_up
    c = clock.PlaybackClock(0.0)
    c.reset(0.0, True, 0.0, 1.0, app="app", track_start=True)
    worst = 0.0
    t = 0.0
    while t < 30.0 - 1e-9:
        t = round(t + 0.1, 6)
        c.sync(quantize(1.15 * t), True, t, t, 1.0, 600.0, app="app")
        if t >= 20.0:
            worst = max(worst, abs(c.position(t) - 1.15 * t))
    assert worst <= clock.DEADBAND


def playing_quantized(c, origin, start, end, speed, app, quantize):
    t = start
    while t < end - 1e-9:
        t = round(t + 0.4, 6)
        c.sync(
            quantize(origin + speed * (t - start)),
            True,
            t,
            t,
            speed,
            600.0,
            app=app,
        )
    return t


def worst_after_settling(c, origin, start, speed, app, quantize):
    worst = 0.0
    t = start
    while t < start + 8.0 - 1e-9:
        t = round(t + 0.4, 6)
        c.sync(
            quantize(origin + speed * (t - start)),
            True,
            t,
            t,
            speed,
            600.0,
            app=app,
        )
        if t >= start + 3.0:
            worst = max(
                worst, abs(c.position(t) - (origin + speed * (t - start)))
            )
    return worst


def round_half_up(x):
    return math.floor(x + 0.5)


@pytest.mark.parametrize("speed", [1.0, 2.0])
@pytest.mark.parametrize("anchor", ["seek", "track"])
@pytest.mark.parametrize(
    "modes",
    [(math.floor, round_half_up), (round_half_up, math.floor)],
    ids=["trunc_then_round", "round_then_trunc"],
)
def test_a_mode_switch_revealed_by_an_exact_anchor_is_within_the_deadband(
    speed, anchor, modes
):
    first, second = modes
    c = clock.PlaybackClock(0.0)
    c.reset(0.0, True, 0.0, speed, app="app", track_start=True)
    playing_quantized(c, 0.0, 0.0, 20.0, speed, "app", first)
    if anchor == "seek":
        origin = speed * 20.0
        c.seeked(origin, 20.0, 20.0, True, speed, app="app")
    else:
        origin = 0.0
        c.reset(origin, True, 20.0, speed, app="app", track_start=True)
    error = worst_after_settling(c, origin, 20.0, speed, "app", second)
    assert error <= clock.DEADBAND + 0.01


@pytest.mark.parametrize("speed", [1.0, 2.0])
@pytest.mark.parametrize(
    "modes",
    [(math.floor, round_half_up), (round_half_up, math.floor)],
    ids=["trunc_then_round", "round_then_trunc"],
)
def test_a_revised_mode_is_used_by_the_next_unanchored_track(speed, modes):
    first, second = modes
    c = clock.PlaybackClock(0.0)
    c.reset(0.0, True, 0.0, speed, app="app", track_start=True)
    playing_quantized(c, 0.0, 0.0, 20.0, speed, "app", first)
    c.seeked(speed * 20.0, 20.0, 20.0, True, speed, app="app")
    worst_after_settling(c, speed * 20.0, 20.0, speed, "app", second)
    c.reset(second(speed * 28.0), True, 28.0, speed, app="app")
    error = worst_after_settling(c, speed * 28.0, 28.0, speed, "app", second)
    assert error <= clock.DEADBAND + 0.01


def probed_worst_error(
    mode, speed, offset, rate_error=1.0, settle=20.0, horizon=40.0
):
    quantize = math.floor if mode == "trunc" else round_half_up

    def truth(t):
        return 12.0 + offset + speed * t

    def new_probe():
        return probe.Probe(1.0 / (speed * rate_error))

    c = clock.PlaybackClock(0.0)
    c.reset(quantize(truth(0.0)), True, 0.0, speed, app="app")
    schedule = new_probe()
    next_read = schedule.start(0.0)
    queued = []
    worst = 0.0
    for k in range(1, round(horizon / STEP) + 1):
        t = round(k * STEP, 6)
        while next_read is not None and next_read <= t:
            reading = quantize(truth(next_read))
            queued.append((reading, next_read))
            next_read = schedule.record(next_read, reading)
        if k % SYNC_EVERY_STEPS:
            continue
        for reading, at in queued:
            c.sync(reading, True, at, t, speed, 600.0, app="app")
        queued = []
        c.sync(quantize(truth(t)), True, t, t, speed, 600.0, app="app")
        if t >= settle:
            worst = max(worst, abs(c.position(t) - truth(t)))
        if next_read is None and not schedule.timed:
            schedule = new_probe()
            next_read = schedule.start(t)
    return worst


@pytest.mark.parametrize("rate_error", [1.0, 1.03, 0.97])
@pytest.mark.parametrize("speed", [1.0, 2.0])
@pytest.mark.parametrize("mode", ["trunc", "round"])
def test_a_probed_quantized_player_settles_within_its_pre_anchor_bound(
    mode, speed, rate_error
):
    worst = max(
        probed_worst_error(mode, speed, offset * 0.05, rate_error)
        for offset in range(20)
    )
    assert worst <= 0.28


def test_a_quick_quantized_player_is_followed_from_the_start():
    c = clock.PlaybackClock(0.0)
    c.reset(0.0, True, 0.0, 1.0, app="app", track_start=True)
    for k in range(1, 51):
        t = round(0.4 * k, 6)
        c.sync(math.floor(4.0 * t + 0.5), True, t, t, 1.0, 600.0, app="app")
    assert c.position(20.0) == pytest.approx(80.0, abs=clock.DEADBAND)


def test_a_half_speed_quantized_player_is_not_frozen_between_steps():
    c = clock.PlaybackClock(0.0)
    c.reset(0.0, True, 0.0, 1.0, app="app", track_start=True)
    late = []
    for k in range(1, 51):
        t = round(0.8 * k, 6)
        c.sync(math.floor(0.5 * t + 0.5), True, t, t, 1.0, 600.0, app="app")
        if t >= 25.0:
            late.append(abs(c.position(t) - 0.5 * t))
    assert max(late) <= clock.DEADBAND


def test_a_pinned_quantized_slope_stays_within_the_deadband_after_a_minute():
    c = clock.PlaybackClock(0.0)
    c.reset(0.0, True, 0.0, 1.0, app="app", track_start=True)
    late = []
    for k in range(1, 76):
        t = round(k * 0.8, 6)
        c.sync(math.floor(2.0 * t), True, t, t, 1.0, 600.0, app="app")
        if t >= 40.0:
            late.append(abs(c.position(t) - 2.0 * t))
    assert max(late) <= clock.DEADBAND


def test_a_forward_jump_the_quantum_explains_is_followed_without_a_reset():
    c = clock.PlaybackClock(0.0)
    c.reset(0.0, True, 0.0, 1.0, app="app", track_start=True)
    late = []
    for k in range(1, 151):
        t = round(k * 0.4, 6)
        offset = 1.5 if t >= 10.0 else 0.0
        c.sync(math.floor(t + offset), True, t, t, 1.0, 600.0, app="app")
        if t >= 16.0:
            late.append(abs(c.position(t) - (t + offset)))
    assert max(late) <= clock.DEADBAND


def test_a_lagged_double_rate_quantized_reading_is_followed_in_the_deadband():
    c = clock.PlaybackClock(0.0)
    c.reset(0.0, True, 0.0, 1.0, app="app", track_start=True)
    late = []
    for k in range(1, 151):
        t = round(k * 0.4, 6)
        seen = t - 0.5
        c.sync(math.floor(2.0 * seen), True, seen, t, 1.0, 600.0, app="app")
        if t >= 40.0:
            late.append(abs(c.position(t) - 2.0 * t))
    assert max(late) <= clock.DEADBAND


def test_a_small_explained_jump_is_followed_at_once_from_the_track_start():
    c = clock.PlaybackClock(0.0)
    c.reset(0.0, True, 0.0, 1.0, app="app", track_start=True)
    worst = 0.0
    for k in range(1, 7):
        t = round(k * 0.8, 6)
        offset = 1.2 if t >= 1.6 else 0.0
        c.sync(math.floor(1.25 * t + offset), True, t, t, 1.0, 600.0, app="app")
        if 0.5 <= t <= 3.0:
            worst = max(worst, abs(c.position(t) - (1.25 * t + offset)))
    assert worst <= 0.3


def test_a_rejected_paused_seek_resumed_rounded_is_followed():
    c = clock.PlaybackClock(0.0)
    c.reset(12.0, False, 0.0, 1.0)
    c.seeked(12.5, 0.0, 0.0, False, 1.0)
    t = 0.0
    while t < 10.0:
        t += 0.4
        c.sync(12, False, t, t, 1.0, 600.0)
    start = t
    worst = 0.0
    while t < start + 20.0:
        t += 0.4
        truth = 12.0 + (t - start)
        c.sync(math.floor(truth + 0.5), True, t, t, 1.0, 600.0)
        if t >= start + 3.0:
            worst = max(worst, abs(c.position(t) - truth))
    assert worst <= 0.32


def test_a_truncated_player_from_a_whole_second_is_followed():
    c = clock.PlaybackClock(0.0)
    c.reset(12.0, True, 0.0, 1.0)
    worst = 0.0
    t = 0.0
    while t < 20.0:
        t += 0.4
        truth = 12.0 + t
        c.sync(math.floor(truth), True, t, t, 1.0, 600.0)
        if t >= 3.0:
            worst = max(worst, abs(c.position(t) - truth))
    assert worst <= 0.18


def test_an_exact_player_that_changes_rate_is_relearned_from_its_gain():
    c = clock.PlaybackClock(0.0)
    c.reset(0.0, True, 0.0, 1.0, app="app", track_start=True)
    switch_at, switch_position = 30.0, 30.0 * 3.5
    worst = 0.0
    for poll in range(1, 250):
        t = 0.4 * poll
        if t <= switch_at:
            truth = 3.5 * t
        else:
            truth = switch_position + (t - switch_at)
        c.sync(truth, True, t, t, 1.0, 600.0, app="app")
        if t >= switch_at + 3.0:
            worst = max(worst, abs(c.position(t) - truth))
    assert worst <= clock.DEADBAND


@pytest.mark.parametrize("poll", [0.4, 0.5])
@pytest.mark.parametrize("real", [0.8, 1.1, 1.25, 1.5])
@pytest.mark.parametrize("mode", ["trunc", "round"])
def test_a_seek_read_one_poll_late_keeps_its_target_then_follows(
    mode, real, poll
):
    quantize = math.floor if mode == "trunc" else round_half_up
    c = clock.PlaybackClock(0.0)
    c.reset(0.0, True, 0.0, 1.0, app="app", track_start=True)
    late = []
    t = 0.0
    while t < 30.0:
        t = round(t + poll, 6)
        if t == 15.0:
            c.seeked(30.0, t, t, True, 1.0, app="app")
        truth = real * t if t <= 15.0 else 30.0 + real * (t - 15.0)
        c.sync(quantize(truth), True, t, t, 1.0, 600.0, app="app")
        if t == 15.0:
            assert c.position(t) == pytest.approx(30.0, abs=1e-9)
        if t >= 20.0:
            late.append(abs(c.position(t) - truth))
    assert max(late) <= clock.QUANTUM


@pytest.mark.parametrize("poll", [0.25, 0.4, 0.5])
@pytest.mark.parametrize("mode", ["trunc", "round"])
def test_a_quantized_rewind_polled_quickly_is_confirmed(mode, poll):
    quantize = math.floor if mode == "trunc" else round_half_up
    c = clock.PlaybackClock(0.0)
    c.reset(0.0, True, 0.0, 1.0, app="app", track_start=True)
    late = []
    t = 0.0
    while t < 40.0:
        t = round(t + poll, 6)
        truth = t if t < 20.0 else t - 15.0
        c.sync(quantize(truth), True, t, t, 1.0, 600.0, app="app")
        if t >= 25.0:
            late.append(abs(c.position(t) - truth))
    assert max(late) <= clock.QUANTUM


@pytest.mark.parametrize("poll", [0.5, 1.0])
def test_a_precise_player_ignoring_a_seek_is_not_given_the_rate_to_reach_it(
    poll,
):
    c = clock.PlaybackClock(0.0)
    c.reset(0.0, True, 0.0, 1.0, app="app", track_start=True)
    late = []
    t = 0.0
    while t < 45.0:
        t = round(t + poll, 6)
        if t == 15.0:
            c.seeked(5.0, t, t, True, 1.0, app="app")
        truth = 1.25 * t
        c.sync(truth, True, t, t, 1.0, 600.0, app="app")
        if t > 21.0:
            late.append(abs(c.position(t) - truth))
    assert max(late) <= clock.DEADBAND


@pytest.mark.parametrize("mode", ["trunc", "round"])
@pytest.mark.parametrize("real", [1.5, 2.0, 3.0])
@pytest.mark.parametrize("poll", [0.5, 1.0, 1.5, 2.0])
@pytest.mark.parametrize("target", [5.0, 16.0])
def test_a_player_faster_than_announced_relearns_its_rate_after_an_ignored_seek(
    mode, real, poll, target
):
    quantize = math.floor if mode == "trunc" else round_half_up
    c = clock.PlaybackClock(0.0)
    c.reset(0.0, True, 0.0, 1.0, app="app", track_start=True)
    t = 0.0
    seeked = False
    while t < 60.0:
        t = round(t + poll, 6)
        if not seeked and t >= 15.0:
            seeked = True
            c.seeked(target, t, t, True, 1.0, app="app")
        c.sync(quantize(real * t), True, t, t, 1.0, 600.0, app="app")
    assert c.speed == pytest.approx(real, abs=0.01)


@pytest.mark.parametrize("real", [0.5, 0.8, 1.25, 1.5])
@pytest.mark.parametrize("poll", [0.25, 0.4, 0.5, 1.0])
@pytest.mark.parametrize("target", [5.0, 16.0])
def test_an_exact_player_ignoring_a_seek_never_learns_from_a_whole_reading(
    real, poll, target
):
    c = clock.PlaybackClock(0.0)
    c.reset(0.0, True, 0.0, 1.0, app="app", track_start=True)
    t = 0.0
    ignored = None
    errors = []
    while t < 45.0:
        t = round(t + poll, 6)
        truth = real * t
        if ignored is None and t >= 15.0:
            ignored = abs(target - truth)
            c.seeked(target, t, t, True, 1.0, app="app")
        c.sync(truth, True, t, t, 1.0, 600.0, app="app")
        if ignored is not None:
            errors.append((t, abs(c.position(t) - truth)))
    assert max(error for _, error in errors) <= ignored + clock.DEADBAND
    assert max(error for at, error in errors if at > 21.0) <= clock.DEADBAND


@pytest.mark.parametrize("quantize", [math.floor, round_half_up])
@pytest.mark.parametrize("poll", [0.25, 0.4, 0.5, 0.9, 1.0, 1.5, 2.0])
@pytest.mark.parametrize("target", [5.0, 30.0, 40.0])
def test_a_quantized_player_at_its_announced_rate_ignoring_a_seek_ends_exact(
    quantize, poll, target
):
    c = clock.PlaybackClock(0.0)
    c.reset(0.0, True, 0.0, 1.0, app="app", track_start=True)
    t = 0.0
    seeked = False
    errors = []
    while t < 45.0:
        t = round(t + poll, 6)
        if not seeked and t >= 15.0:
            seeked = True
            c.seeked(target, t, t, True, 1.0, app="app")
        c.sync(quantize(t), True, t, t, 1.0, 600.0, app="app")
        if t > 21.0:
            errors.append(abs(c.position(t) - t))
    assert max(errors) <= 1e-6


@pytest.mark.parametrize("quantize", [math.floor, round_half_up])
@pytest.mark.parametrize("real", [0.8, 1.25, 1.5])
@pytest.mark.parametrize("poll", [0.25, 0.4, 0.5])
@pytest.mark.parametrize("target", [5.0, 40.0])
def test_a_rate_learned_before_an_ignored_paused_seek_survives_the_resume(
    quantize, real, poll, target
):
    c = clock.PlaybackClock(0.0)
    c.reset(0.0, True, 0.0, 1.0, app="app", track_start=True)
    t = 0.0
    while t < 15.0:
        t = round(t + poll, 6)
        c.sync(quantize(real * t), True, t, t, 1.0, 600.0, app="app")
    paused_at = t
    c.status(False, t, 1.0)
    c.seeked(target, t, t, False, 1.0, app="app")
    while t < paused_at + 3.0:
        t = round(t + poll, 6)
        c.sync(quantize(real * paused_at), False, t, t, 1.0, 600.0, app="app")
    c.status(True, t, 1.0)
    resumed_at = t
    speeds = []
    while t < resumed_at + 20.0:
        t = round(t + poll, 6)
        truth = real * (paused_at + t - resumed_at)
        c.sync(quantize(truth), True, t, t, 1.0, 600.0, app="app")
        if t > resumed_at + 10.0:
            speeds.append(c.speed)
    assert all(abs(speed - real) <= clock.MAX_SKEW * real for speed in speeds)


@pytest.mark.parametrize("real", [0.8, 1.5, 2.0, 3.0])
@pytest.mark.parametrize("poll", [0.4, 0.9, 1.0])
def test_a_paused_ignored_seek_keeps_the_rate_the_cells_proved(real, poll):
    assert_paused_ignored_seek_error(
        math.floor, real, poll, 5.0, clock.QUANTUM / 2 + clock.DEADBAND
    )


@pytest.mark.parametrize("poll", [0.25, 0.4, 0.5])
def test_a_paused_seek_one_second_ahead_the_player_ignores_keeps_its_cells(
    poll,
):
    assert_paused_ignored_seek_error(
        math.floor, 1.0, poll, 16.0, clock.QUANTUM / 2 + clock.DEADBAND
    )


def test_a_cell_narrowed_to_a_point_on_whole_seconds_survives_rounding():
    assert_paused_ignored_seek_error(
        math.floor, 1.25, 0.9, 5.0, 2 * clock.DEADBAND
    )


@pytest.mark.parametrize("target", [5.0, 16.0, 30.0, 40.0])
def test_a_rounded_reading_on_the_upper_edge_of_a_cell_keeps_it(target):
    assert_paused_ignored_seek_error(
        round_half_up, 1.25, 0.25, target, clock.DEADBAND
    )


@pytest.mark.parametrize(
    ("real", "poll"), [(0.8, 0.25), (0.8, 0.5), (0.8, 1.0), (2.0, 0.25)]
)
def test_an_exact_player_paused_on_a_whole_second_resumes_at_its_rate(
    real, poll
):
    assert_paused_ignored_seek_error(float, real, poll, 16.0, 1e-6)


def assert_paused_ignored_seek_error(quantize, real, poll, target, bound):
    c = clock.PlaybackClock(0.0)
    c.reset(0.0, True, 0.0, 1.0, app="app", track_start=True)
    t = 0.0
    paused_at = None
    resumed_at = None
    errors = []
    while t < 45.0:
        t = round(t + poll, 6)
        if paused_at is None and t >= 15.0:
            paused_at = t
            c.status(False, t, 1.0)
            c.seeked(target, t, t, False, 1.0, app="app")
        if (
            resumed_at is None
            and paused_at is not None
            and t >= paused_at + 3.0
        ):
            resumed_at = t
            c.status(True, t, 1.0)
        if paused_at is None:
            truth = real * t
        elif resumed_at is None:
            truth = real * paused_at
        else:
            truth = real * (paused_at + t - resumed_at)
        c.sync(
            quantize(truth),
            resumed_at is not None or paused_at is None,
            t,
            t,
            1.0,
            600.0,
            app="app",
        )
        if t > 21.0:
            errors.append(abs(c.position(t) - truth))
    assert max(errors) <= bound


@pytest.mark.parametrize(("real", "target"), [(1.1, 16.0), (2.0, 30.0)])
def test_a_playing_seek_the_player_ignores_keeps_the_speed_its_cells_proved(
    real, target
):
    c = clock.PlaybackClock(0.0)
    c.reset(0.0, True, 0.0, 1.0, app="app", track_start=True)
    t = 0.0
    before = None
    speeds_after = []
    while t < 25.0:
        t = round(t + 0.9, 6)
        if before is None and t >= 15.0:
            before = c.speed
            c.seeked(target, t, t, True, 1.0, app="app")
        c.sync(round_half_up(real * t), True, t, t, 1.0, 600.0, app="app")
        if before is not None:
            speeds_after.append(c.speed)
    assert max(abs(speed - before) for speed in speeds_after) <= 1e-9


@pytest.mark.parametrize("poll", [0.25, 0.4, 0.5, 1.0])
def test_a_dropped_chance_rate_does_not_prove_the_rate_it_replaced(poll):
    c = clock.PlaybackClock(0.0)
    c.reset(0.0, True, 0.0, 1.0, app="app", track_start=True)
    t = 0.0
    seeked = False
    errors = []
    while t < 60.0:
        t = round(t + poll, 6)
        if not seeked and t >= 15.0:
            seeked = True
            c.seeked(16.0, t, t, True, 1.0, app="app")
        if t < 30.0:
            truth = round(1.25 * t, 6)
            c.sync(truth, True, t, t, 1.0, 600.0, app="app")
        else:
            truth = 1.25 * 30.0 + (t - 30.0)
            c.sync(math.floor(truth), True, t, t, 1.0, 600.0, app="app")
        if t > 20.0:
            errors.append(abs(c.position(t) - truth))
    assert max(errors) <= clock.QUANTUM / 2
