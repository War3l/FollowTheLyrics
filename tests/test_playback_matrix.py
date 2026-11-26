import math

import pytest

from followthelyrics.overlay import clock

DEADBAND = clock.DEADBAND
RATIO_LOW = 0.25
RATIO_HIGH = 4.0
CONVERGED_BY = 20.0
AMBIGUOUS_BOUND = 0.3
LONG_HORIZON = 60.0
SHORT_HORIZON = CONVERGED_BY + 10.0
JITTER = 0.03
GOLDEN = 2.399963
SEEK_ORIGIN = 12.3
SEEK_PAUSE_DELAY = 0.79

MODES = ("exact", "trunc", "round")
SAMPLINGS = (0.1, 0.4, 0.8)
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


def converge_errors(mode, announced, real, sampling, horizon):
    quantize = QUANTIZE[mode]
    clk = clock.PlaybackClock(0.0)
    clk.reset(0.0, True, 0.0, announced, app="app", track_start=True)
    errors = []
    for t in sample_times(sampling, horizon):
        clk.sync(quantize(real * t), True, t, t, announced, 600.0, app="app")
        errors.append((t, abs(clk.position(t) - real * t)))
    return errors


def seek_error(mode, truth, sampling):
    quantize = QUANTIZE[mode]
    clk = clock.PlaybackClock(0.0)
    clk.reset(0.0, True, 0.0, 2.0, app="app", track_start=True)
    clk.seeked(SEEK_ORIGIN, 0.0, 0.0, True, 2.0, app="app")
    last = 0.0
    for t in sample_times(sampling, 16.0):
        clk.sync(
            quantize(SEEK_ORIGIN + truth * t), True, t, t, 2.0, 600.0, app="app"
        )
        last = t
    pause = round(last + SEEK_PAUSE_DELAY, 6)
    clk.status(False, pause, 2.0)
    return abs(clk.position(pause) - (SEEK_ORIGIN + truth * pause))


def ambiguous_at_converged(mode, announced, real, sampling):
    readings = readings_of(mode, real, sampling, LONG_HORIZON)
    return alternative_is_alive(mode, readings, 0.0, announced, CONVERGED_BY)


@pytest.mark.parametrize("sampling", SAMPLINGS)
@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("announced,real", CONVERGE_PAIRS)
def test_converged_estimate_stays_within_the_deadband(
    mode, announced, real, sampling
):
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
    death = alternative_death(mode, readings, 0.0, announced)
    assert death is not None
    errors = converge_errors(mode, announced, real, sampling, LONG_HORIZON)
    while_ambiguous = [
        error for t, error in errors if CONVERGED_BY <= t < death
    ]
    after_death = [error for t, error in errors if t > death]
    assert max(while_ambiguous) < AMBIGUOUS_BOUND
    assert after_death
    assert max(after_death) <= DEADBAND


@pytest.mark.parametrize("sampling", SAMPLINGS)
@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("truth", SEEK_TRUTHS)
def test_seek_then_pause_holds_the_true_position(mode, truth, sampling):
    assert seek_error(mode, truth, sampling) <= DEADBAND


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


ANNOUNCED_HALF_AND_DOUBLE = (0.5, 2.0)
QUANTIZED_RATIOS = (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.5, 4.0)


@pytest.mark.parametrize("sampling", SAMPLINGS)
@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("ratio", QUANTIZED_RATIOS)
@pytest.mark.parametrize("announced", ANNOUNCED_HALF_AND_DOUBLE)
def test_players_at_announced_half_and_double_speed_converge(
    announced, ratio, mode, sampling
):
    real = announced * ratio
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
    death = alternative_death(mode, readings, 0.0, announced)
    assert death is not None
    errors = converge_errors(mode, announced, real, sampling, LONG_HORIZON)
    while_ambiguous = [
        error for t, error in errors if CONVERGED_BY <= t < death
    ]
    after_death = [error for t, error in errors if t > death]
    assert max(while_ambiguous) < AMBIGUOUS_BOUND
    assert after_death
    assert max(after_death) <= DEADBAND


def test_a_round_player_polled_every_1_5_seconds_is_relearned_after_a_jump():
    errors = converge_errors("round", 0.5, 1.25, 1.5, 40.0)
    assert max(error for t, error in errors if t >= CONVERGED_BY) <= DEADBAND
