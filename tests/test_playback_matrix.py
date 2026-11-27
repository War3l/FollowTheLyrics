import itertools
import math

import pytest

from followthelyrics.overlay import clock

DEADBAND = clock.DEADBAND
QUANTUM = clock.QUANTUM
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


def round_half_up(value):
    return math.floor(value + 0.5)


QUANTIZE = {"exact": float, "trunc": math.floor, "round": round_half_up}


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
DROPPED_SEEK_POLLS = (0.4, 0.9, 1.0)
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
    return [error for t, error in errors if t >= given_up]


@pytest.mark.parametrize("target", DROPPED_SEEK_TARGETS)
@pytest.mark.parametrize("poll", DROPPED_SEEK_POLLS)
@pytest.mark.parametrize("mode", ("trunc", "round"))
def test_a_seek_the_player_drops_is_given_up_once_its_rewind_is_confirmed(
    mode, poll, target
):
    assert max(dropped_seek_errors(mode, poll, target)) <= DEADBAND


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
def test_until_a_late_seek_is_applied_the_display_trusts_the_sought_target(
    mode, real, poll, lag
):
    rows = late_apply_rows(mode, real, poll, lag, LATE_APPLY_END)
    sought = rows[-1][3]
    trusted = [
        (shown, LATE_SEEK_TARGET + real * (t - sought))
        for t, truth, shown, _ in rows
        if sought < t < sought + lag
        and abs(truth - LATE_SEEK_TARGET - real * (t - sought)) >= clock.JUMP
    ]
    assert all(abs(shown - target) <= DEADBAND for shown, target in trusted)


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
    low, high = clock.GAIN_MIN, clock.GAIN_MAX
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


STALE_GAIN_SHORTFALLS = (
    *(("trunc", 1.5, 1.5, False, target) for target in IGNORED_SEEK_TARGETS),
    *(("trunc", 0.8, 2.0, False, target) for target in IGNORED_SEEK_TARGETS),
    *(("round", 1.25, 2.0, True, target) for target in IGNORED_SEEK_TARGETS),
    *(("round", 0.5, 1.5, False, target) for target in (16.0, 30.0, 40.0)),
    *(("round", 0.5, 1.0, False, target) for target in (16.0, 30.0, 40.0)),
    *(("trunc", 1.1, 2.0, False, target) for target in (30.0, 40.0)),
)
NEAR_TARGET_SHORTFALLS = (
    *(("trunc", 1.1, poll, False, 16.0) for poll in (0.25, 0.5, 1.0, 1.5)),
    *(("trunc", 1.1, poll, True, 16.0) for poll in (0.25, 0.5, 0.9, 1.0, 1.5)),
    *(("exact", 1.1, poll, False, 16.0) for poll in (0.25, 0.4, 0.5, 0.9, 1.5)),
    *(("exact", 1.0, poll, False, 16.0) for poll in (0.4, 0.9)),
    ("exact", 0.8, 2.0, False, 16.0),
)
EXACT_RESUME_SHORTFALLS = tuple(
    ("exact", real, 0.4, True, target)
    for real in (1.0, 1.1, 1.25, 1.5, 2.0)
    for target in IGNORED_SEEK_TARGETS
)
ORACLE_SHORTFALLS = {
    **dict.fromkeys(STALE_GAIN_SHORTFALLS, "a stale proven gain is kept"),
    **dict.fromkeys(
        NEAR_TARGET_SHORTFALLS, "a single hypothesis is kept near the target"
    ),
    **dict.fromkeys(
        EXACT_RESUME_SHORTFALLS, "an exact resume outruns the reaction delay"
    ),
}


def ignored_seek_oracle_cells():
    for mode in GRID_MODES:
        for real in IGNORED_SEEK_RATES:
            for poll in IGNORED_SEEK_POLLS:
                for paused in (False, True):
                    for target in IGNORED_SEEK_TARGETS:
                        cell = (mode, real, poll, paused, target)
                        marks = ()
                        if cell in ORACLE_SHORTFALLS:
                            marks = pytest.mark.xfail(
                                strict=True, reason=ORACLE_SHORTFALLS[cell]
                            )
                        yield pytest.param(*cell, marks=marks)


@pytest.mark.parametrize(
    "mode, real, poll, paused, target", list(ignored_seek_oracle_cells())
)
def test_an_ignored_seek_errs_within_the_bound_of_what_the_readings_allow(
    mode, real, poll, paused, target
):
    assert ignored_seek_oracle_excess(mode, real, poll, paused, target) <= 0.0
