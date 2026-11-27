import itertools
import math
import random

import pytest

from followthelyrics.overlay import clock
from followthelyrics.playback import track

DEADBAND = 0.15
QUANTUM = 1.0
SLOWEST_REPORTABLE_RATIO = 1.0 / track.MAX_SPEED
FASTEST_REPORTABLE_RATIO = track.MAX_SPEED
RATIO_LOW = 0.25
RATIO_HIGH = 4.0
CONVERGED_BY = 20.0
HULL_MARGIN = 0.08
EXACT_AT_RATE = 1e-6
SMALL_LEAD = 0.3
LONG_HORIZON = 60.0
SHORT_HORIZON = CONVERGED_BY + 10.0
JITTER = 0.03
GOLDEN = 2.399963
SEEK_ORIGIN = 12.3
SEEK_PAUSE_DELAY = 0.79
SEEK_HORIZON = 16.0
LATE_SEEK_AT = 15.0
LATE_SEEK_TARGET = 30.0


MODES = ("exact", "trunc", "round")
SAMPLINGS = (0.1, 0.4, 0.8, 1.0)
CONVERGE_PAIRS = (
    (1.0, 0.25),
    (1.0, 0.5),
    (1.0, 0.75),
    (1.0, 0.97),
    (1.0, 1.0),
    (1.0, 1.03),
    (1.0, 1.25),
    (1.0, 1.5),
    (1.0, 2.0),
    (2.0, 1.0),
    (2.0, 1.94),
    (2.0, 2.0),
)
EXACT_RATE_PAIRS = (
    (0.5, 0.25),
    (1.0, 3.5),
    (2.0, 0.5),
    (2.0, 4.0),
)
SEEK_TRUTHS = (1.0, 1.94, 2.0)
ALTERNATIVE_OFFSET = {"trunc": 0.5, "round": 0.0}
PHASES = (0.0, 0.5)
MID_TRACK_OFFSET_SPAN = 1e4


def round_half_up(value):
    return math.floor(value + 0.5)


QUANTIZE = {"exact": float, "trunc": math.floor, "round": round_half_up}


def slow_unless(sampled, *values):
    return pytest.param(*values, marks=() if sampled else pytest.mark.slow)


def sample_times(sampling, horizon):
    times = []
    k = 0
    while True:
        k += 1
        t = round(k * sampling + JITTER * math.sin(GOLDEN * k), 6)
        if t > horizon:
            return times
        times.append(t)


def readings_of(mode, real, sampling, horizon):
    quantize = QUANTIZE[mode]
    return [(t, quantize(real * t)) for t in sample_times(sampling, horizon)]


def alternative_is_alive(mode, readings, origin, announced, now):
    if mode == "exact":
        return False
    offset = ALTERNATIVE_OFFSET[mode]
    low, high = -math.inf, math.inf
    for at, reading in readings:
        if at > now:
            break
        scale = announced * at
        low = max(low, (reading - offset - origin) / scale)
        high = min(high, (reading - offset + 1.0 - origin) / scale)
    return low < high


def alternative_death(mode, readings, origin, announced):
    for at, _ in readings:
        if not alternative_is_alive(mode, readings, origin, announced, at):
            return at
    return None


def feasible_ratios(readings, origin, announced, slack=0.0):
    low = dict.fromkeys(PHASES, -math.inf)
    high = dict.fromkeys(PHASES, math.inf)
    for at, reading in readings:
        scale = announced * at
        for phase in PHASES:
            low[phase] = max(
                low[phase], (reading - phase - origin - slack) / scale
            )
            high[phase] = min(
                high[phase], (reading - phase + 1.0 - origin + slack) / scale
            )
    return {
        phase: (low[phase], high[phase])
        for phase in PHASES
        if low[phase] < high[phase]
    }


def hull_half_width(readings, origin, announced, at, slack=0.0):
    ratios = feasible_ratios(readings, origin, announced, slack)
    ends = [
        announced * at * bound for bounds in ratios.values() for bound in bounds
    ]
    return (max(ends) - min(ends)) / 2


def announced_rate_fits(readings, origin, announced, slack=0.0):
    ratios = feasible_ratios(readings, origin, announced, slack)
    return any(low <= 1.0 <= high for low, high in ratios.values())


def hull_bound(readings, origin, announced, at):
    half = hull_half_width(readings, origin, announced, at)
    if announced_rate_fits(readings, origin, announced):
        return 2 * half
    return half + HULL_MARGIN


def oracle_width(readings, origin, announced, at, slack=0.0):
    half = hull_half_width(readings, origin, announced, at, slack)
    if announced_rate_fits(readings, origin, announced, slack):
        return 2 * half
    return half


def single_phase_bound(mode, readings, origin, announced, at, slack=0.0):
    if mode == "exact":
        return DEADBAND
    width = oracle_width(readings, origin, announced, at, slack)
    if width > DEADBAND:
        return width + HULL_MARGIN
    return DEADBAND


def converge_errors(mode, announced, real, sampling, horizon):
    quantize = QUANTIZE[mode]
    clk = clock.PlaybackClock(0.0)
    clk.reset(0.0, True, 0.0, announced, app="app", track_start=True)
    errors = []
    for t in sample_times(sampling, horizon):
        clk.sync(quantize(real * t), True, t, t, announced, 600.0, app="app")
        errors.append((t, abs(clk.position(t) - real * t)))
    return errors


def seek_readings(mode, truth, sampling):
    quantize = QUANTIZE[mode]
    return [
        (t, quantize(SEEK_ORIGIN + truth * t))
        for t in sample_times(sampling, SEEK_HORIZON)
    ]


def seek_pause(readings):
    return round(readings[-1][0] + SEEK_PAUSE_DELAY, 6)


def seek_error(mode, truth, sampling):
    readings = seek_readings(mode, truth, sampling)
    clk = clock.PlaybackClock(0.0)
    clk.reset(0.0, True, 0.0, 2.0, app="app", track_start=True)
    clk.seeked(SEEK_ORIGIN, 0.0, 0.0, True, 2.0, app="app")
    for t, reading in readings:
        clk.sync(reading, True, t, t, 2.0, 600.0, app="app")
    pause = seek_pause(readings)
    clk.status(False, pause, 2.0)
    return abs(clk.position(pause) - (SEEK_ORIGIN + truth * pause))


def ambiguous_at_converged(mode, announced, real, sampling):
    readings = readings_of(mode, real, sampling, LONG_HORIZON)
    return alternative_is_alive(mode, readings, 0.0, announced, CONVERGED_BY)


@pytest.mark.parametrize("sampling", SAMPLINGS)
@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("announced,real", CONVERGE_PAIRS)
def test_converging_clock_meets_the_announced_rate_contract(
    mode, announced, real, sampling
):
    assert_announced_rate_contract(mode, announced, real, sampling)


@pytest.mark.parametrize("sampling", SAMPLINGS)
@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("truth", SEEK_TRUTHS)
def test_seek_then_pause_holds_the_true_position(mode, truth, sampling):
    readings = seek_readings(mode, truth, sampling)
    pause = seek_pause(readings)
    error = seek_error(mode, truth, sampling)
    if truth == 2.0:
        assert error <= EXACT_AT_RATE
    elif alternative_is_alive(mode, readings, SEEK_ORIGIN, 2.0, pause):
        assert error <= hull_bound(readings, SEEK_ORIGIN, 2.0, pause)
    else:
        assert error <= DEADBAND


@pytest.mark.parametrize("sampling", SAMPLINGS)
@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("real", (RATIO_LOW, RATIO_HIGH))
def test_ratio_extremes_converge(mode, real, sampling):
    assert not ambiguous_at_converged(mode, 1.0, real, sampling)
    late = [
        error
        for t, error in converge_errors(
            mode, 1.0, real, sampling, SHORT_HORIZON
        )
        if t >= CONVERGED_BY
    ]
    assert max(late) <= DEADBAND


@pytest.mark.parametrize("sampling", SAMPLINGS)
@pytest.mark.parametrize("announced,real", EXACT_RATE_PAIRS)
def test_exact_readings_converge_at_any_announced_rate(
    announced, real, sampling
):
    assert not ambiguous_at_converged("exact", announced, real, sampling)
    late = [
        error
        for t, error in converge_errors(
            "exact", announced, real, sampling, SHORT_HORIZON
        )
        if t >= CONVERGED_BY
    ]
    assert max(late) <= DEADBAND


def test_exact_readings_are_never_ambiguous_at_the_aliased_cell():
    assert not ambiguous_at_converged("exact", 1.0, 1.25, 0.8)
    errors = converge_errors("exact", 1.0, 1.25, 0.8, LONG_HORIZON)
    assert max(error for t, error in errors if t >= CONVERGED_BY) <= DEADBAND


def test_the_round_alias_cell_is_flagged_ambiguous_and_dies_later():
    assert ambiguous_at_converged("round", 1.0, 1.25, 0.8)
    readings = readings_of("round", 1.25, 0.8, LONG_HORIZON)
    death = alternative_death("round", readings, 0.0, 1.0)
    assert death is not None and death > CONVERGED_BY


def assert_announced_rate_contract(mode, announced, real, sampling):
    if real == announced:
        errors = converge_errors(mode, announced, real, sampling, LONG_HORIZON)
        assert max(error for _, error in errors) <= EXACT_AT_RATE
        return
    readings = readings_of(mode, real, sampling, LONG_HORIZON)
    if not ambiguous_at_converged(mode, announced, real, sampling):
        errors = converge_errors(mode, announced, real, sampling, SHORT_HORIZON)
        assert (
            max(
                beyond_the_single_phase_bound(
                    mode, readings, announced, errors, CONVERGED_BY
                )
            )
            <= 0.0
        )
        return
    death = alternative_death(mode, readings, 0.0, announced) or math.inf
    errors = converge_errors(mode, announced, real, sampling, LONG_HORIZON)
    beyond_the_bound = [
        error
        - hull_bound(
            [(at, reading) for at, reading in readings if at <= t],
            0.0,
            announced,
            t,
        )
        for t, error in errors
        if CONVERGED_BY <= t < death
    ]
    after_death = beyond_the_single_phase_bound(
        mode, readings, announced, [(t, e) for t, e in errors if t > death], 0.0
    )
    assert max(beyond_the_bound, default=0.0) <= 0.0
    assert max(after_death, default=0.0) <= 0.0


MID_TRACK_STARTS = tuple(round(0.05 + 1.37 * k, 2) for k in range(40))


def clip_offset_ratio_polygon(polygon, scale, low, high):
    def keep_side(polygon, signed):
        kept = []
        for corner, following in zip(
            polygon, polygon[1:] + polygon[:1], strict=True
        ):
            here, there = signed(corner), signed(following)
            if here >= 0:
                kept.append(corner)
            if (here >= 0) != (there >= 0):
                share = here / (here - there)
                kept.append(
                    (
                        corner[0] + share * (following[0] - corner[0]),
                        corner[1] + share * (following[1] - corner[1]),
                    )
                )
        return kept

    polygon = keep_side(polygon, lambda v: v[0] + v[1] * scale - low)
    if polygon:
        polygon = keep_side(polygon, lambda v: high - v[0] - v[1] * scale)
    return polygon


def offset_ratio_polygons(readings, announced):
    phases = phase_pairs(readings, None)
    polygons = []
    for phase, _ in phases:
        polygon = [
            (-MID_TRACK_OFFSET_SPAN, SLOWEST_REPORTABLE_RATIO),
            (MID_TRACK_OFFSET_SPAN, SLOWEST_REPORTABLE_RATIO),
            (MID_TRACK_OFFSET_SPAN, FASTEST_REPORTABLE_RATIO),
            (-MID_TRACK_OFFSET_SPAN, FASTEST_REPORTABLE_RATIO),
        ]
        for at, reading in readings:
            low, high = reading_interval(reading, phase)
            polygon = clip_offset_ratio_polygon(
                polygon, announced * at, low, high
            )
            if not polygon:
                break
        if polygon:
            polygons.append(polygon)
    return polygons


def mid_track_bound(readings, announced, at):
    polygons = offset_ratio_polygons(readings, announced)
    ends = [
        offset + ratio * announced * at
        for polygon in polygons
        for offset, ratio in polygon
    ]
    rate_fits = any(
        min(ratio for _, ratio in polygon)
        <= 1.0
        <= max(ratio for _, ratio in polygon)
        for polygon in polygons
    )
    half = (max(ends) - min(ends)) / 2
    return max(2 * half if rate_fits else half, DEADBAND) + HULL_MARGIN


def mid_track_excess(mode, announced, real, sampling, start):
    quantize = QUANTIZE[mode]
    first = quantize(start)
    c = clock.PlaybackClock(0.0)
    c.reset(first, True, 0.0, announced, app="app")
    readings = [(0.0, first)]
    excess = []
    for t in sample_times(sampling, SHORT_HORIZON):
        truth = start + real * t
        readings.append((t, quantize(truth)))
        c.sync(readings[-1][1], True, t, t, announced, 600.0, app="app")
        if t < CONVERGED_BY:
            continue
        known = [
            (at, reading)
            for at, reading in readings
            if at <= t - clock.SETTLE_SECONDS - sampling
        ]
        bound = mid_track_bound(known, announced, t)
        excess.append(abs(c.position(t) - truth) - bound)
    return max(excess)


@pytest.mark.parametrize("start", MID_TRACK_STARTS)
@pytest.mark.parametrize("mode", ["trunc", "round"])
def test_a_half_speed_player_joined_mid_track_holds_the_phase_it_proves(
    mode, start
):
    assert mid_track_excess(mode, 1.0, 0.5, 1.0, start) <= 0.0


def beyond_the_single_phase_bound(mode, readings, announced, errors, since):
    return [
        error
        - single_phase_bound(
            mode,
            [(at, reading) for at, reading in readings if at < t],
            0.0,
            announced,
            t,
        )
        for t, error in errors
        if t >= since
    ]


ANNOUNCED_HALF_AND_DOUBLE = (0.5, 2.0)
QUANTIZED_RATIOS = (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.5, 4.0)


@pytest.mark.parametrize("sampling", SAMPLINGS)
@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("ratio", QUANTIZED_RATIOS)
@pytest.mark.parametrize("announced", ANNOUNCED_HALF_AND_DOUBLE)
def test_players_at_announced_half_and_double_speed_converge(
    announced, ratio, mode, sampling
):
    assert_announced_rate_contract(mode, announced, announced * ratio, sampling)


CONVERGE_STARTS = (5.05, 12.7, 27.45)
OFFSET_CONVERGE_PAIRS = CONVERGE_PAIRS + tuple(
    (announced, announced * ratio)
    for announced in ANNOUNCED_HALF_AND_DOUBLE
    for ratio in QUANTIZED_RATIOS
)


def mid_track_cells():
    for pair_index, (announced, real) in enumerate(OFFSET_CONVERGE_PAIRS):
        for mode_index, mode in enumerate(MODES):
            turn = pair_index + mode_index
            for sampling in SAMPLINGS:
                for start in CONVERGE_STARTS:
                    sampled = (
                        sampling == SAMPLINGS[turn % len(SAMPLINGS)]
                        and start
                        == CONVERGE_STARTS[turn % len(CONVERGE_STARTS)]
                    )
                    yield slow_unless(
                        sampled, announced, real, mode, sampling, start
                    )


@pytest.mark.parametrize(
    "announced, real, mode, sampling, start", list(mid_track_cells())
)
def test_a_player_joined_mid_track_converges_within_what_its_readings_prove(
    announced, real, mode, sampling, start
):
    assert mid_track_excess(mode, announced, real, sampling, start) <= 0.0


def test_a_round_player_slightly_fast_polled_every_0_6_seconds_converges():
    assert_announced_rate_contract("round", 1.5, 1.5 * 1.0407, 0.6)


@pytest.mark.parametrize("ratio", [1.04, 1.0414])
def test_a_truncating_player_slightly_fast_at_half_speed_stays_in_the_hull(
    ratio,
):
    assert_announced_rate_contract("trunc", 0.5, 0.5 * ratio, 1.0)


@pytest.mark.parametrize("mode", ["trunc", "round"])
def test_a_small_lead_of_the_display_is_never_stepped_back(mode):
    quantize = QUANTIZE[mode]
    clk = clock.PlaybackClock(0.0)
    clk.reset(0.0, True, 0.0, 1.0, app="app", track_start=True)
    steps_back = []
    for t in sample_times(0.4, LONG_HORIZON):
        before = clk.position(t)
        clk.sync(quantize(1.03 * t), True, t, t, 1.0, 600.0, app="app")
        steps_back.append(before - clk.position(t))
    assert not [step for step in steps_back if 0.0 < step < SMALL_LEAD]


def test_a_round_player_polled_every_1_5_seconds_is_relearned_after_a_jump():
    errors = converge_errors("round", 0.5, 1.25, 1.5, 40.0)
    assert max(error for t, error in errors if t >= CONVERGED_BY) <= DEADBAND


def test_a_truncating_player_polled_every_second_keeps_its_first_readings():
    assert_announced_rate_contract("trunc", 1.0, 0.97, 1.0)


def test_an_exact_player_slower_than_announced_is_corrected_at_once():
    assert_announced_rate_contract("exact", 1.5, 1.125, 0.8)


@pytest.mark.parametrize(
    "mode,announced,ratio,sampling",
    [
        ("trunc", 0.5, 0.98, 0.8),
        ("trunc", 1.0, 0.99, 0.8),
        ("trunc", 0.5, 0.981234, 0.8),
        ("trunc", 2.0, 0.995923, 0.8),
        ("round", 1.5, 0.994767, 0.6),
        ("trunc", 1.0, 0.988286, 0.8),
        ("trunc", 2.0, 0.996838, 0.8),
        ("trunc", 1.0, 0.964554, 1.0),
        ("trunc", 2.0, 1.048561, 1.0),
        ("round", 1.5, 1.1, 0.6),
    ],
)
def test_a_single_phase_player_off_its_rate_stays_in_the_width_of_its_cell(
    mode, announced, ratio, sampling
):
    assert_announced_rate_contract(mode, announced, announced * ratio, sampling)


def late_seek_speeds(mode, real, sampling, lag):
    quantize = QUANTIZE[mode]
    c = clock.PlaybackClock(0.0)
    c.reset(0.0, True, 0.0, 1.0, app="app", track_start=True)
    readings, speeds, sought = [], [], None
    for t in sample_times(sampling, LATE_SEEK_AT + SEEK_HORIZON):
        if sought is None and t >= LATE_SEEK_AT:
            sought = t
            c.seeked(LATE_SEEK_TARGET, t, t, True, 1.0, app="app")
        if sought is not None and t >= sought + lag:
            truth = LATE_SEEK_TARGET + real * (t - sought - lag)
        else:
            truth = real * t
        reading = quantize(truth)
        c.sync(reading, True, t, t, 1.0, 600.0, app="app")
        if sought is None:
            readings.append((t, reading))
        elif t >= sought + lag + sampling:
            speeds.append(c.speed)
    return readings, speeds


@pytest.mark.parametrize(
    "mode, real, sampling, lag",
    [
        ("trunc", 1.1, 1.0, 0.2),
        ("trunc", 1.5, 0.5, 0.5),
        ("trunc", 1.25, 0.5, 0.2),
        ("trunc", 0.8, 1.0, 0.5),
    ],
)
def test_a_seek_the_player_applies_late_keeps_the_rate_proven_before_it(
    mode, real, sampling, lag
):
    readings, speeds = late_seek_speeds(mode, real, sampling, lag)
    ranges = feasible_ratios(readings, 0.0, 1.0).values()
    low = min(bounds[0] for bounds in ranges)
    high = max(bounds[1] for bounds in ranges)
    assert all(low <= speed <= high for speed in speeds)


GRID_MODES = ("exact", "trunc", "round")
GRID_SEEK_AT = 15.0
GRID_PAUSE = 3.0
GRID_END = 45.0
IGNORED_SEEK_SETTLE = 6.0
IGNORED_SEEK_RATES = (0.5, 0.8, 1.0, 1.1, 1.25, 1.5, 2.0, 3.0)
IGNORED_SEEK_POLLS = (0.25, 0.4, 0.5, 0.9, 1.0, 1.5, 2.0)
IGNORED_SEEK_TARGETS = (40.0, 5.0, 16.0, 30.0)
LATE_APPLY_RATES = (0.8, 1.1, 1.25, 1.5, 2.0)
LATE_APPLY_POLLS = (0.4, 0.5, 1.0)
LATE_APPLY_LAGS = (0.2, 0.5, 1.0)
LATE_APPLY_END = 30.0
RESUME_RATES = (1.0, 1.05, 1.1, 1.2, 0.9)
RESUME_PAUSES = (20.3, 20.7, 30.3, 40.7)
RESUME_POLLS = (0.4, 1.0)
RESUME_AFTER = 5.0
RESUME_SPAN = 10.0
REWIND_AT = 20.0
REWIND_BY = 15.0
REWIND_END = 40.0
REWIND_SETTLE = 5.0
REWIND_POLLS = (0.25, 0.4, 0.5, 0.9, 1.0)
DROPPED_SEEK_AT = 10.0
DROPPED_SEEK_EARLY = 0.05
DROPPED_SEEK_END = 30.0
DROPPED_SEEK_POLLS = (0.25, 0.4, 0.9, 1.0)
DROPPED_SEEK_TARGETS = (40.0, 40.4, 5.0)


def even_polls(step, end):
    times = []
    t = 0.0
    while t < end:
        t = round(t + step, 6)
        times.append(t)
    return times


def started_clock():
    c = clock.PlaybackClock(0.0)
    c.reset(0.0, True, 0.0, 1.0, app="app", track_start=True)
    return c


def ignored_seek_trace(mode, real, poll, paused, target):
    quantize = QUANTIZE[mode]
    c = started_clock()
    sought = resumed = None
    trace = []
    for t in even_polls(poll, GRID_END):
        if sought is None and t >= GRID_SEEK_AT:
            sought = t
            if paused:
                c.status(False, t, 1.0)
            c.seeked(target, t, t, not paused, 1.0, app="app")
        if (
            paused
            and resumed is None
            and sought is not None
            and (t >= sought + GRID_PAUSE)
        ):
            c.status(True, t, 1.0)
            resumed = t
        if not paused or sought is None:
            truth = real * t
        elif resumed is None:
            truth = real * sought
        else:
            truth = real * (sought + t - resumed)
        playing = not paused or sought is None or resumed is not None
        reading = quantize(truth)
        c.sync(reading, playing, t, t, 1.0, 600.0, app="app")
        trace.append((t, reading, c.position(t) - truth))
    return trace, sought, resumed


def ignored_seek_errors(mode, real, poll, paused, target):
    trace, _, _ = ignored_seek_trace(mode, real, poll, paused, target)
    return [
        abs(error)
        for t, _, error in trace
        if t > GRID_SEEK_AT + IGNORED_SEEK_SETTLE
    ]


@pytest.mark.parametrize("target", IGNORED_SEEK_TARGETS)
@pytest.mark.parametrize("paused", [False, True])
@pytest.mark.parametrize("poll", IGNORED_SEEK_POLLS)
@pytest.mark.parametrize("real", IGNORED_SEEK_RATES)
@pytest.mark.parametrize("mode", GRID_MODES)
def test_a_seek_the_player_ignores_is_given_up_within_a_quantum(
    mode, real, poll, paused, target
):
    errors = ignored_seek_errors(mode, real, poll, paused, target)
    assert max(errors) <= QUANTUM + clock.POSITION_RESOLUTION


def late_apply_rows(mode, real, poll, lag, end):
    quantize = QUANTIZE[mode]
    c = started_clock()
    sought = None
    rows = []
    for t in even_polls(poll, end):
        if sought is None and t >= LATE_SEEK_AT:
            sought = t
            c.seeked(LATE_SEEK_TARGET, t, t, True, 1.0, app="app")
        if sought is None or t < sought + lag:
            truth = real * t
        else:
            truth = LATE_SEEK_TARGET + real * (t - sought - lag)
        c.sync(quantize(truth), True, t, t, 1.0, 600.0, app="app")
        rows.append((t, truth, c.position(t), sought))
    return rows


def late_apply_errors(mode, real, poll, lag):
    return [
        abs(shown - truth)
        for t, truth, shown, sought in late_apply_rows(
            mode, real, poll, lag, LATE_APPLY_END
        )
        if sought is not None and t >= sought + lag + clock.SETTLE_SECONDS
    ]


@pytest.mark.parametrize("lag", LATE_APPLY_LAGS)
@pytest.mark.parametrize("poll", LATE_APPLY_POLLS)
@pytest.mark.parametrize("real", LATE_APPLY_RATES)
@pytest.mark.parametrize("mode", GRID_MODES)
def test_a_seek_applied_late_errs_by_no_more_than_its_delay_and_a_quantum(
    mode, real, poll, lag
):
    errors = late_apply_errors(mode, real, poll, lag)
    assert max(errors) <= real * lag + QUANTUM


def full_width_bound(readings, at):
    width = 2 * hull_half_width(
        readings, 0.0, 1.0, at, clock.POSITION_RESOLUTION
    )
    if width > DEADBAND:
        return width + HULL_MARGIN
    return DEADBAND


def resume_errors(mode, real, pause, poll):
    quantize = QUANTIZE[mode]
    c = started_clock()
    readings = []
    t = 0.0
    while t < pause - poll:
        t = round(t + poll, 6)
        readings.append((t, quantize(real * t)))
        c.sync(readings[-1][1], True, t, t, 1.0, 600.0, app="app")
    c.status(False, pause, 1.0)
    c.status(True, pause + RESUME_AFTER, 1.0)
    excess = []
    t = pause + RESUME_AFTER
    while t < pause + RESUME_AFTER + RESUME_SPAN:
        t = round(t + poll, 6)
        played = t - RESUME_AFTER
        bound = full_width_bound(readings, played)
        reading = quantize(real * played)
        c.sync(reading, True, t, t, 1.0, 600.0, app="app")
        excess.append(abs(c.position(t) - real * played) - bound)
        readings.append((played, reading))
    return excess


@pytest.mark.parametrize("poll", RESUME_POLLS)
@pytest.mark.parametrize("pause", RESUME_PAUSES)
@pytest.mark.parametrize("real", RESUME_RATES)
@pytest.mark.parametrize("mode", ("trunc", "round"))
def test_a_resume_stays_in_the_width_of_the_cells_proved_before_the_pause(
    mode, real, pause, poll
):
    assert max(resume_errors(mode, real, pause, poll)) <= 0.0


def rewind_errors(mode, poll):
    quantize = QUANTIZE[mode]
    c = started_clock()
    errors = []
    for t in even_polls(poll, REWIND_END):
        truth = t if t < REWIND_AT else t - REWIND_BY
        c.sync(quantize(truth), True, t, t, 1.0, 600.0, app="app")
        if t >= REWIND_AT + REWIND_SETTLE:
            errors.append(abs(c.position(t) - truth))
    return errors


@pytest.mark.parametrize("poll", REWIND_POLLS)
@pytest.mark.parametrize("mode", ("exact", "trunc"))
def test_an_unannounced_rewind_is_followed_within_half_a_quantum(mode, poll):
    assert max(rewind_errors(mode, poll)) <= QUANTUM / 2


def dropped_seek_errors(mode, poll, target):
    quantize = QUANTIZE[mode]
    c = started_clock()
    sent = None
    errors = []
    for t in even_polls(poll, DROPPED_SEEK_END):
        if sent is None and t >= DROPPED_SEEK_AT:
            sent = t - DROPPED_SEEK_EARLY
            c.seeked(target, sent, sent, True, 1.0, app="app")
        c.sync(quantize(t), True, t, t, 1.0, 600.0, app="app")
        if sent is not None:
            errors.append((t, abs(c.position(t) - t)))
    doubted = next(t for t, _ in errors if t > sent + clock.SETTLE_SECONDS)
    given_up = doubted + clock.CONFIRM_SECONDS
    return [(t - given_up, error) for t, error in errors if t >= given_up]


@pytest.mark.parametrize("target", DROPPED_SEEK_TARGETS)
@pytest.mark.parametrize("poll", DROPPED_SEEK_POLLS)
@pytest.mark.parametrize("mode", ("trunc", "round"))
def test_a_seek_the_player_drops_is_given_up_once_its_rewind_is_confirmed(
    mode, poll, target
):
    errors = dropped_seek_errors(mode, poll, target)
    assert max(error for _, error in errors) <= (
        QUANTUM + clock.POSITION_RESOLUTION
    )
    assert max(error for since, error in errors if since >= poll) <= DEADBAND


@pytest.mark.parametrize(
    "mode, real, poll, lag",
    [
        ("trunc", 1.25, 1.0, 0.5),
        ("round", 1.25, 1.0, 1.0),
        ("trunc", 0.8, 1.0, 1.0),
    ],
)
def test_a_seek_applied_late_is_re_anchored_within_half_a_quantum(
    mode, real, poll, lag
):
    assert max(late_apply_errors(mode, real, poll, lag)) <= QUANTUM / 2


def ignored_seek_excess(mode, real, poll, target):
    quantize = QUANTIZE[mode]
    c = started_clock()
    readings, excess = [], []
    sought = False
    for t in even_polls(poll, GRID_END):
        if not sought and t >= GRID_SEEK_AT:
            sought = True
            c.seeked(target, t, t, True, 1.0, app="app")
        reading = quantize(real * t)
        bound = single_phase_bound(mode, readings, 0.0, 1.0, t)
        c.sync(reading, True, t, t, 1.0, 600.0, app="app")
        readings.append((t, reading))
        if t > GRID_SEEK_AT + IGNORED_SEEK_SETTLE:
            excess.append(abs(c.position(t) - real * t) - bound)
    return excess


def test_cells_killed_by_an_ignored_seek_restart_at_the_hull_middle():
    assert max(ignored_seek_excess("round", 0.5, 1.0, 5.0)) <= 0.0


def resumed_errors_after_an_ignored_seek(mode, poll, paused_at):
    quantize = QUANTIZE[mode]
    c = started_clock()
    t = 0.0
    while t < GRID_SEEK_AT:
        t = round(t + poll, 6)
        c.sync(quantize(t), True, t, t, 1.0, 600.0, app="app")
    c.seeked(IGNORED_SEEK_TARGETS[0], t, t, True, 1.0, app="app")
    while t + poll < paused_at:
        t = round(t + poll, 6)
        c.sync(quantize(t), True, t, t, 1.0, 600.0, app="app")
    c.status(False, paused_at, 1.0)
    resumed = paused_at + RESUME_AFTER
    c.status(True, resumed, 1.0)
    errors = []
    for t in even_polls(poll, RESUME_SPAN):
        truth = paused_at + t
        c.sync(
            quantize(truth),
            True,
            resumed + t,
            resumed + t,
            1.0,
            600.0,
            app="app",
        )
        if t > GRID_PAUSE:
            errors.append(abs(c.position(resumed + t) - truth))
    return errors


@pytest.mark.parametrize(
    "mode, poll, paused_at",
    [("trunc", 0.5, 16.2), ("round", 1.0, 16.5), ("trunc", 1.0, 15.9)],
)
def test_cells_from_before_an_ignored_seek_stop_moving_during_a_pause(
    mode, poll, paused_at
):
    errors = resumed_errors_after_an_ignored_seek(mode, poll, paused_at)
    assert max(errors) <= EXACT_AT_RATE


def paused_ignored_seek_excess(mode, real, poll, target):
    quantize = QUANTIZE[mode]
    c = started_clock()
    sought = resumed = None
    readings, excess = [], []
    for t in even_polls(poll, GRID_END):
        if sought is None and t >= GRID_SEEK_AT:
            sought = t
            c.status(False, t, 1.0)
            c.seeked(target, t, t, False, 1.0, app="app")
        if resumed is None and sought is not None and t >= sought + GRID_PAUSE:
            c.status(True, t, 1.0)
            resumed = t
        if sought is not None and resumed is None:
            c.sync(quantize(real * sought), False, t, t, 1.0, 600.0, app="app")
            continue
        played = t if sought is None else sought + t - resumed
        reading = quantize(real * played)
        c.sync(reading, True, t, t, 1.0, 600.0, app="app")
        if t > GRID_SEEK_AT + IGNORED_SEEK_SETTLE:
            bound = single_phase_bound(
                mode, readings, 0.0, 1.0, played, clock.POSITION_RESOLUTION
            )
            excess.append(abs(c.position(t) - real * played) - bound)
        readings.append((played, reading))
    return excess


def test_a_paused_ignored_seek_resumes_within_the_width_of_a_single_phase():
    assert max(paused_ignored_seek_excess("trunc", 0.5, 1.5, 16.0)) <= 0.0


def forward_seek_errors(mode, poll, paused, ahead, applied):
    quantize = QUANTIZE[mode]
    c = started_clock()
    sought = resumed = None
    errors = []
    for t in even_polls(poll, GRID_END):
        if sought is None and t >= GRID_SEEK_AT:
            sought = t
            if paused:
                c.status(False, t, 1.0)
            c.seeked(t + ahead, t, t, not paused, 1.0, app="app")
        if (
            paused
            and resumed is None
            and sought is not None
            and t >= sought + GRID_PAUSE
        ):
            c.status(True, t, 1.0)
            resumed = t
        if sought is None:
            played = t
        elif paused:
            played = sought if resumed is None else sought + t - resumed
        else:
            played = t
        playing = not paused or sought is None or resumed is not None
        truth = played
        if applied and sought is not None and played >= sought + ahead:
            target, applied_at = sought + ahead, sought + ahead
            truth = target + (played - applied_at)
        c.sync(quantize(truth), playing, t, t, 1.0, 600.0, app="app")
        if t > GRID_SEEK_AT + IGNORED_SEEK_SETTLE:
            errors.append(abs(c.position(t) - truth))
    return errors


@pytest.mark.parametrize("ahead", [0.7, 1.0])
@pytest.mark.parametrize("paused", [False, True])
@pytest.mark.parametrize("poll", [0.9, 1.0])
@pytest.mark.parametrize("mode", ["trunc", "round"])
def test_a_forward_seek_applied_as_late_as_its_length_reads_as_an_ignored_one(
    mode, poll, paused, ahead
):
    ignored = forward_seek_errors(mode, poll, paused, ahead, False)
    late = forward_seek_errors(mode, poll, paused, ahead, True)
    assert ignored == late
    assert max(late) <= QUANTUM + clock.POSITION_RESOLUTION


MODE_SWITCH_TWIN_RATE = 0.534


def mode_switch_twin(poll_end):
    c = started_clock()
    resumed = GRID_SEEK_AT + GRID_PAUSE
    rows = []
    for t in even_polls(1.0, poll_end):
        if t == GRID_SEEK_AT:
            c.status(False, t, 1.0)
            c.seeked(IGNORED_SEEK_TARGETS[1], t, t, False, 1.0, app="app")
        if t == resumed:
            c.status(True, t, 1.0)
        played = t if t < GRID_SEEK_AT else GRID_SEEK_AT + max(0.0, t - resumed)
        rounded = 0.5 * played
        switched = MODE_SWITCH_TWIN_RATE * played
        reading = QUANTIZE["round"](rounded)
        twin = QUANTIZE["round" if t < resumed else "trunc"](switched)
        c.sync(
            reading,
            t < GRID_SEEK_AT or t >= resumed,
            t,
            t,
            1.0,
            600.0,
            app="app",
        )
        rows.append((t, reading, twin, rounded, switched, c.position(t)))
    return rows


def test_a_mode_switch_at_a_resume_reads_alike_until_the_rates_part():
    rows = mode_switch_twin(32.0)
    assert all(reading == twin for _, reading, twin, *_ in rows)
    assert all(
        min(a, b) - HULL_MARGIN <= shown <= max(a, b) + HULL_MARGIN
        for t, _, _, a, b, shown in rows
        if t >= GRID_SEEK_AT + GRID_PAUSE
    )


@pytest.mark.parametrize("lag", LATE_APPLY_LAGS)
@pytest.mark.parametrize("poll", LATE_APPLY_POLLS)
@pytest.mark.parametrize("real", LATE_APPLY_RATES)
@pytest.mark.parametrize("mode", GRID_MODES)
def test_until_a_late_seek_lands_the_display_follows_the_refuting_readings(
    mode, real, poll, lag
):
    rows = late_apply_rows(mode, real, poll, lag, LATE_APPLY_END)
    sought = rows[-1][3]
    refuted = [
        (shown, truth)
        for t, truth, shown, _ in rows
        if sought < t < sought + lag
        and abs(truth - LATE_SEEK_TARGET - real * (t - sought)) >= clock.JUMP
    ]
    resolution = DEADBAND if mode == "exact" else QUANTUM
    assert all(abs(shown - truth) <= resolution for shown, truth in refuted)


REFUTED_SEEK_AT = 10.0
REFUTED_SEEK_START = 23.4
REFUTED_SEEK_RATE = 0.8


def refuted_seek_errors(mode, lead, poll):
    quantize = QUANTIZE[mode]
    c = clock.PlaybackClock(0.0)
    c.reset(
        quantize(REFUTED_SEEK_START),
        True,
        0.0,
        REFUTED_SEEK_RATE,
        app="app",
        track_start=True,
    )
    errors = []
    for t in even_polls(poll, REFUTED_SEEK_AT + 5.0):
        truth = REFUTED_SEEK_START + REFUTED_SEEK_RATE * t
        if t == REFUTED_SEEK_AT:
            c.seeked(truth + lead, t, t, True, 1.0, app="app")
        c.sync(quantize(truth), True, t, t, REFUTED_SEEK_RATE, 600.0, app="app")
        if t > REFUTED_SEEK_AT:
            errors.append(c.position(t) - truth)
    return errors


@pytest.mark.parametrize("poll", (0.25, 1.0))
@pytest.mark.parametrize("lead", (2.0, -2.0))
@pytest.mark.parametrize("mode", GRID_MODES)
def test_an_ignored_seek_is_given_up_at_the_first_reading_refuting_it(
    mode, lead, poll
):
    resolution = DEADBAND if mode == "exact" else QUANTUM
    errors = refuted_seek_errors(mode, lead, poll)
    assert max(abs(error) for error in errors) <= resolution


HIDDEN_REWIND_RATE = LATE_SEEK_TARGET / LATE_SEEK_AT
RATE_BAND_CLOSES = 2 * LATE_SEEK_AT
RATE_BAND_END = LATE_SEEK_AT + RATE_BAND_CLOSES + 15.0


@pytest.mark.parametrize("lag", LATE_APPLY_LAGS)
@pytest.mark.parametrize("poll", LATE_APPLY_POLLS)
@pytest.mark.parametrize("mode", GRID_MODES)
def test_a_rewind_hidden_by_a_late_seek_is_absorbed_once_the_rate_band_closes(
    mode, poll, lag
):
    rows = late_apply_rows(mode, HIDDEN_REWIND_RATE, poll, lag, RATE_BAND_END)
    sought = rows[-1][3]
    assert all(
        abs(shown - truth) <= QUANTUM / 2 + DEADBAND
        for t, truth, shown, _ in rows
        if t >= sought + RATE_BAND_CLOSES
    )


TRUNCATED_TWIN_LEAD = QUANTUM - 1e-3


@pytest.mark.parametrize("poll", [0.5, 1.0])
@pytest.mark.parametrize("lag", [0.5, 1.0])
def test_an_exact_player_behind_a_hidden_rewind_reads_like_a_truncating_twin(
    lag, poll
):
    rows = late_apply_rows(
        "exact", HIDDEN_REWIND_RATE, poll, lag, RATE_BAND_END
    )
    sought = rows[-1][3]
    applied = sought + lag
    twin_applied = applied - TRUNCATED_TWIN_LEAD / HIDDEN_REWIND_RATE
    twins = []
    for t, truth, shown, _ in rows:
        if t < twin_applied:
            twin = HIDDEN_REWIND_RATE * t
        else:
            twin = LATE_SEEK_TARGET + HIDDEN_REWIND_RATE * (t - twin_applied)
        twins.append((t, truth, twin, shown))
    assert all(math.floor(twin) == truth for _, truth, twin, _ in twins)
    settled = [
        (t, truth, twin, shown)
        for t, truth, twin, shown in twins
        if t >= applied + clock.SETTLE_SECONDS
    ]
    leads = [shown - truth for _, truth, _, shown in settled]
    assert all(
        truth - clock.POSITION_RESOLUTION
        <= shown
        <= twin + clock.POSITION_RESOLUTION
        for _, truth, twin, shown in settled
    )
    assert all(
        later <= earlier + clock.POSITION_RESOLUTION
        for earlier, later in itertools.pairwise(leads)
    )
    assert all(
        shown - truth <= (twin - truth) / 2 + DEADBAND
        for t, truth, twin, shown in settled
        if t >= sought + RATE_BAND_CLOSES
    )


def phase_pairs(readings, switch):
    if any(reading != math.floor(reading) for _, reading in readings):
        return [(None, None)]
    return [
        (before, after)
        for before in PHASES
        for after in PHASES
        if switch is not None or before == after
    ]


def reading_interval(reading, phase):
    if phase is None:
        low, high = reading, reading
    else:
        low, high = reading - phase, reading + QUANTUM - phase
    return low - clock.POSITION_RESOLUTION, high + clock.POSITION_RESOLUTION


def hypothesis_ratios(readings, hypothesis, phases):
    offset, played, switch = hypothesis
    low, high = SLOWEST_REPORTABLE_RATIO, FASTEST_REPORTABLE_RATIO
    for at, reading in readings:
        phase = phases[0] if switch is None or at < switch else phases[1]
        lowest, highest = reading_interval(reading, phase)
        start, span = offset(at), played(at)
        if span <= 0:
            if not lowest <= start <= highest:
                return None
            continue
        low = max(low, (lowest - start) / span)
        high = min(high, (highest - start) / span)
        if low > high:
            return None
    return low, high


def hypotheses_bound(readings, hypotheses, at):
    ends = []
    rate_fits = False
    for hypothesis in hypotheses:
        offset, played, switch = hypothesis
        for phases in phase_pairs(readings, switch):
            ratios = hypothesis_ratios(readings, hypothesis, phases)
            if ratios is None:
                continue
            ends += [offset(at) + ratio * played(at) for ratio in ratios]
            rate_fits = rate_fits or ratios[0] <= 1.0 <= ratios[1]
    if not ends:
        return None
    half = (max(ends) - min(ends)) / 2
    return max(2 * half if rate_fits else half, DEADBAND) + HULL_MARGIN


def ignored_seek_hypotheses(paused, target, sought, resumed):
    if not paused:
        return [
            (lambda at: 0.0, lambda at: at, None),
            (
                lambda at: 0.0 if at < sought else target,
                lambda at: at if at < sought else at - sought,
                sought,
            ),
        ]
    resumed_at = math.inf if resumed is None else resumed
    return [
        (
            lambda at: 0.0,
            lambda at: min(at, sought) + max(0.0, at - resumed_at),
            resumed_at,
        ),
        (
            lambda at: 0.0 if at < sought else target,
            lambda at: at if at < sought else max(0.0, at - resumed_at),
            sought,
        ),
    ]


def ignored_seek_oracle_excess(mode, real, poll, paused, target):
    trace, sought, resumed = ignored_seek_trace(
        mode, real, poll, paused, target
    )
    hypotheses = ignored_seek_hypotheses(paused, target, sought, resumed)
    reaction = clock.SETTLE_SECONDS + poll
    readings = [(t, reading) for t, reading, _ in trace]
    excess = []
    for t, _, error in trace:
        if t <= GRID_SEEK_AT + IGNORED_SEEK_SETTLE:
            continue
        known = [
            (at, reading)
            for at, reading in readings
            if at <= t - reaction + clock.POSITION_RESOLUTION
        ]
        bound = hypotheses_bound(known, hypotheses, t)
        if bound is not None:
            excess.append(abs(error) - bound)
    return max(excess)


def ignored_seek_oracle_cells():
    players = itertools.product(
        GRID_MODES, IGNORED_SEEK_RATES, IGNORED_SEEK_POLLS
    )
    for turn, (mode, real, poll) in enumerate(players):
        sampled_target = IGNORED_SEEK_TARGETS[turn % len(IGNORED_SEEK_TARGETS)]
        sampled_paused = (turn // len(IGNORED_SEEK_TARGETS)) % 2 == 1
        for paused in (False, True):
            for target in IGNORED_SEEK_TARGETS:
                sampled = paused == sampled_paused and target == sampled_target
                yield slow_unless(sampled, mode, real, poll, paused, target)


@pytest.mark.parametrize(
    "mode, real, poll, paused, target", list(ignored_seek_oracle_cells())
)
def test_an_ignored_seek_errs_within_the_bound_of_what_the_readings_allow(
    mode, real, poll, paused, target
):
    assert ignored_seek_oracle_excess(mode, real, poll, paused, target) <= 0.0


STEP_SEEK_AT = 10.0
STEP_END = 30.0
STEP_SAMPLE = 0.05
STEP_TOLERANCE = 1e-5
VISIBLE_STEP = 0.05
LEAD_RATES = (1.0, 1.25, 0.8)
LEAD_POLLS = (0.25, 1.0)
LEADS = (0.2, 0.5, 1.0, 2.0)
LEAD_SEEDS = tuple(range(6))
LEAD_FAMILIES = {
    "ignored": (False, True),
    "applied": (True, True),
    "ignored joined at the seek": (False, False),
    "applied joined at the seek": (True, False),
}
FUZZ_SEEDS = tuple(range(150))
FUZZ_MODES = ("trunc", "round", "exact")
FUZZ_RATES = (0.5, 0.8, 1.0, 1.1, 1.25, 1.5, 2.0, 3.0)
FUZZ_POLLS = (0.1, 0.25, 0.4, 0.5, 1.0)
FUZZ_SEEK_SPREAD = (0.2, 1.5)
FUZZ_REPORTED_SEEDS = (16, 52, 64, 65, 73)
FUZZ_SAMPLE_EVERY = 15
UNBOUNDED_START = 1e6


def random_start(seed):
    return random.Random(seed).uniform(0.0, 60.0)


def step_hypotheses(target):
    held = (lambda at: 1.0, lambda at: 0.0, lambda at: at, None)
    if target is None:
        return [held]
    sought = (
        lambda at: 1.0 if at < STEP_SEEK_AT else 0.0,
        lambda at: 0.0 if at < STEP_SEEK_AT else target,
        lambda at: at if at < STEP_SEEK_AT else at - STEP_SEEK_AT,
        STEP_SEEK_AT,
    )
    return [held, sought]


def keep_below(polygon, along_start, along_ratio, bound):
    kept = []
    for i, first in enumerate(polygon):
        second = polygon[(i + 1) % len(polygon)]
        first_slack = bound - along_start * first[0] - along_ratio * first[1]
        second_slack = bound - along_start * second[0] - along_ratio * second[1]
        if first_slack >= 0:
            kept.append(first)
        if (first_slack >= 0) != (second_slack >= 0):
            share = first_slack / (first_slack - second_slack)
            kept.append(
                (
                    first[0] + share * (second[0] - first[0]),
                    first[1] + share * (second[1] - first[1]),
                )
            )
    return kept


def start_and_ratio_cell(readings, hypothesis, phases):
    weight, offset, played, switch = hypothesis
    span = UNBOUNDED_START
    low, high = SLOWEST_REPORTABLE_RATIO, FASTEST_REPORTABLE_RATIO
    cell = [(-span, low), (span, low), (span, high), (-span, high)]
    for at, reading in readings:
        phase = phases[0] if switch is None or at < switch else phases[1]
        lowest, highest = reading_interval(reading, phase)
        along_start, along_ratio = weight(at), played(at)
        cell = keep_below(cell, along_start, along_ratio, highest - offset(at))
        cell = keep_below(cell, -along_start, -along_ratio, offset(at) - lowest)
        if not cell:
            return None
    return cell


def proven_upper(readings, hypotheses, at):
    ends = []
    for hypothesis in hypotheses:
        weight, offset, played, switch = hypothesis
        for phases in phase_pairs(readings, switch):
            cell = start_and_ratio_cell(readings, hypothesis, phases)
            if cell is not None:
                ends += [
                    weight(at) * start + offset(at) + ratio * played(at)
                    for start, ratio in cell
                ]
    return max(ends)


def unproven_share(before, after, upper):
    if before <= upper + STEP_TOLERANCE:
        return before - after
    return max(0.0, upper - after)


def display_steps_back(scenario):
    mode, real, poll, announced, start, target, applied, warm = scenario
    quantize = QUANTIZE[mode]
    c = clock.PlaybackClock(0.0)
    reported_start = quantize(start)
    c.reset(reported_start, True, 0.0, announced, app="app", track_start=True)
    hypotheses = step_hypotheses(target)
    reported_speed = 1.0 if warm else real
    readings = [(0.0, reported_start)]
    steps = []
    shown = c.position(0.0)
    previous = 0.0
    sought = target is None
    for t in even_polls(poll, STEP_END):
        if not sought and t >= STEP_SEEK_AT:
            sought = True
            c.seeked(target, t, t, True, 1.0, app="app")
            shown = c.position(t)
            previous = t
        for sample in even_polls(STEP_SAMPLE, round(t - previous, 6)):
            at = previous + sample
            drawn = c.position(at)
            if shown - drawn > STEP_TOLERANCE:
                steps.append((at, shown - drawn, shown - drawn))
            shown = drawn
        previous = t
        if applied and target is not None and t >= STEP_SEEK_AT:
            truth = target + real * (t - STEP_SEEK_AT)
        else:
            truth = start + real * t
        if not warm and t < STEP_SEEK_AT:
            continue
        readings.append((t, quantize(truth)))
        c.sync(readings[-1][1], True, t, t, reported_speed, 600.0, app="app")
        after = c.position(t)
        if shown - after > STEP_TOLERANCE:
            upper = proven_upper(readings, hypotheses, t)
            steps.append(
                (t, shown - after, unproven_share(shown, after, upper))
            )
        shown = after
    return steps


def unproven_steps_back(scenario):
    return [
        (round(at, 2), round(unproven, 3))
        for at, _, unproven in display_steps_back(scenario)
        if unproven > STEP_TOLERANCE
    ]


def lead_scenario(family, mode, real, poll, lead, seed):
    applied, warm = LEAD_FAMILIES[family]
    start = random_start(seed)
    target = start + real * STEP_SEEK_AT + lead
    return mode, real, poll, real, start, target, applied, warm


def fuzz_scenario(seed, seeking):
    draw = random.Random(seed)
    mode = draw.choice(FUZZ_MODES)
    real = draw.choice(FUZZ_RATES)
    poll = draw.choice(FUZZ_POLLS)
    announced = draw.choice([1.0, real])
    start = draw.uniform(0.0, 60.0)
    target = (
        start
        + real * STEP_SEEK_AT
        + draw.choice([-1, 1]) * draw.uniform(*FUZZ_SEEK_SPREAD)
    )
    return (
        mode,
        real,
        poll,
        announced,
        start,
        target if seeking else None,
        True,
        True,
    )


def lead_cells():
    cells = itertools.product(
        LEAD_FAMILIES, GRID_MODES, LEAD_RATES, LEAD_POLLS, LEADS, LEAD_SEEDS
    )
    for index, cell in enumerate(cells):
        yield slow_unless(index % len(LEAD_SEEDS) == 0, *cell)


def fuzz_cells():
    for seed in FUZZ_SEEDS:
        sampled = seed in FUZZ_REPORTED_SEEDS or seed % FUZZ_SAMPLE_EVERY == 0
        for seeking in (False, True):
            yield slow_unless(sampled, seed, seeking)


@pytest.mark.parametrize(
    "family, mode, real, poll, lead, seed", list(lead_cells())
)
def test_a_lead_after_a_seek_is_stepped_back_only_as_far_as_the_readings_prove(
    family, mode, real, poll, lead, seed
):
    scenario = lead_scenario(family, mode, real, poll, lead, seed)
    assert unproven_steps_back(scenario) == []


@pytest.mark.parametrize("seed, seeking", list(fuzz_cells()))
def test_a_random_player_is_stepped_back_only_as_far_as_the_readings_prove(
    seed, seeking
):
    assert unproven_steps_back(fuzz_scenario(seed, seeking)) == []


@pytest.mark.parametrize("seed", (15, 18))
def test_a_half_speed_player_is_stepped_back_only_as_far_as_proven(
    seed,
):
    scenario = lead_scenario(
        "ignored joined at the seek", "trunc", 0.5, 0.25, 1.0, seed
    )
    assert unproven_steps_back(scenario) == []


def test_a_small_lead_after_an_ignored_seek_shows_no_visible_step_back():
    scenario = lead_scenario(
        "ignored joined at the seek", "round", 1.0, 0.25, 0.2, 2
    )
    steps = display_steps_back(scenario)
    assert max((step for _, step, _ in steps), default=0.0) <= VISIBLE_STEP


@pytest.mark.parametrize("seed", (11, 76, 131))
def test_a_fast_player_from_its_track_start_shows_no_visible_step_back(
    seed,
):
    steps = display_steps_back(fuzz_scenario(seed, False))
    assert max((step for _, step, _ in steps), default=0.0) <= VISIBLE_STEP


TWIN_RATE = 2.0
TWIN_BASES = (10.0, 23.0, 41.0)
TWIN_OFFSETS = {
    "trunc": (0.0, 0.25, 0.5, 0.75, 0.999),
    "round": (-0.5, -0.25, 0.0, 0.25, 0.499),
}
TWIN_END = 40.0
TWIN_START_HALF_WIDTH = (QUANTUM + QUANTUM / 2) / 2


def twin_starts(base):
    return [
        (mode, base + offset)
        for mode, offsets in TWIN_OFFSETS.items()
        for offset in offsets
    ]


def twin_readings(mode, start):
    quantize = QUANTIZE[mode]
    return [
        (t, quantize(start + TWIN_RATE * t)) for t in even_polls(1.0, TWIN_END)
    ]


@pytest.mark.parametrize("base", TWIN_BASES)
def test_a_double_speed_player_polled_each_second_errs_within_its_twins(
    base,
):
    twins = twin_starts(base)
    readings = twin_readings(*twins[0])
    reported_start = QUANTIZE[twins[0][0]](twins[0][1])
    assert all(twin_readings(*twin) == readings for twin in twins)
    assert all(QUANTIZE[mode](start) == reported_start for mode, start in twins)
    c = clock.PlaybackClock(0.0)
    c.reset(reported_start, True, 0.0, 1.0, app="app", track_start=True)
    worst = 0.0
    for t, reading in readings:
        c.sync(reading, True, t, t, 1.0, 600.0, app="app")
        if t >= CONVERGED_BY:
            shown = c.position(t)
            worst = max(
                worst,
                *(abs(shown - (start + TWIN_RATE * t)) for _, start in twins),
            )
    assert TWIN_START_HALF_WIDTH > DEADBAND
    assert worst <= TWIN_START_HALF_WIDTH + clock.POSITION_RESOLUTION


TWIN_SEEK_AT = 10.0
TWIN_SEEK_STARTS = (5.0, 12.7, 27.45)
TWIN_SEEK_ANNOUNCED = (TWIN_RATE, 1.0)


def ignored_twin_seek_errors(mode, poll, announced, lead, start):
    quantize = QUANTIZE[mode]
    c = clock.PlaybackClock(0.0)
    c.reset(quantize(start), True, 0.0, announced, app="app", track_start=True)
    given_up = TWIN_SEEK_AT + clock.SETTLE_SECONDS + poll
    errors = []
    for t in even_polls(poll, TWIN_END):
        if t == TWIN_SEEK_AT:
            target = start + TWIN_RATE * t + lead
            c.seeked(target, t, t, True, announced, app="app")
        truth = start + TWIN_RATE * t
        c.sync(quantize(truth), True, t, t, announced, 600.0, app="app")
        if t >= given_up:
            errors.append(abs(c.position(t) - truth))
    return errors


@pytest.mark.parametrize("start", TWIN_SEEK_STARTS)
@pytest.mark.parametrize("lead", LEADS)
@pytest.mark.parametrize("announced", TWIN_SEEK_ANNOUNCED)
@pytest.mark.parametrize("poll", LEAD_POLLS)
@pytest.mark.parametrize("mode", ("trunc", "round"))
def test_a_double_speed_player_ignoring_a_seek_errs_within_its_twins(
    mode, poll, announced, lead, start
):
    errors = ignored_twin_seek_errors(mode, poll, announced, lead, start)
    assert max(errors) <= TWIN_START_HALF_WIDTH + clock.POSITION_RESOLUTION


def test_the_oracle_shares_the_clock_deadband_quantum_and_ratio_range():
    assert (
        DEADBAND,
        QUANTUM,
        SLOWEST_REPORTABLE_RATIO,
        FASTEST_REPORTABLE_RATIO,
    ) == (
        clock.DEADBAND,
        clock.QUANTUM,
        clock.GAIN_MIN,
        clock.GAIN_MAX,
    )
