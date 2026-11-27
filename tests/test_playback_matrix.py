import math

import pytest

from followthelyrics.overlay import clock

DEADBAND = clock.DEADBAND
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


def feasible_ratios(readings, origin, announced):
    low = dict.fromkeys(PHASES, -math.inf)
    high = dict.fromkeys(PHASES, math.inf)
    for at, reading in readings:
        scale = announced * at
        for phase in PHASES:
            low[phase] = max(low[phase], (reading - phase - origin) / scale)
            high[phase] = min(
                high[phase], (reading - phase + 1.0 - origin) / scale
            )
    return {
        phase: (low[phase], high[phase])
        for phase in PHASES
        if low[phase] < high[phase]
    }


def hull_half_width(readings, origin, announced, at):
    ends = [
        announced * at * bound
        for bounds in feasible_ratios(readings, origin, announced).values()
        for bound in bounds
    ]
    return (max(ends) - min(ends)) / 2


def announced_rate_fits(readings, origin, announced):
    return any(
        low <= 1.0 <= high
        for low, high in feasible_ratios(readings, origin, announced).values()
    )


def hull_bound(readings, origin, announced, at):
    half = hull_half_width(readings, origin, announced, at)
    if announced_rate_fits(readings, origin, announced):
        return 2 * half
    return half + HULL_MARGIN


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
    if not ambiguous_at_converged(mode, announced, real, sampling):
        late = [
            error
            for t, error in converge_errors(
                mode, announced, real, sampling, SHORT_HORIZON
            )
            if t >= CONVERGED_BY
        ]
        assert max(late) <= DEADBAND
        return
    readings = readings_of(mode, real, sampling, LONG_HORIZON)
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
    after_death = [error for t, error in errors if t > death]
    assert max(beyond_the_bound) <= 0.0
    assert max(after_death, default=0.0) <= DEADBAND


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
