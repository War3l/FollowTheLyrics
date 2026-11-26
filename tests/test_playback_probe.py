import pytest

from followthelyrics.playback import probe


def test_scan_reads_follow_each_other_every_scan_interval_until_a_change():
    schedule = probe.Probe(1.0)
    first = schedule.start(0.0)
    assert first == pytest.approx(probe.SCAN_SECONDS)
    second = schedule.record(first, 12)
    assert second == pytest.approx(2 * probe.SCAN_SECONDS)
    third = schedule.record(second, 12)
    assert third == pytest.approx(3 * probe.SCAN_SECONDS)
    assert not schedule.timed


def test_a_change_plans_nine_reads_one_period_after_the_bracket_midpoint():
    schedule = probe.Probe(1.0)
    schedule.start(0.0)
    schedule.record(0.05, 12)
    first = schedule.record(0.10, 13)
    times = [first]
    for _ in range(8):
        times.append(schedule.record(times[-1], 13))
    centre = (0.05 + 0.10) / 2 + 1.0
    expected = [
        centre + step * probe.REFINE_SECONDS
        for step in range(-probe.REFINE_STEPS, probe.REFINE_STEPS + 1)
    ]
    assert times == pytest.approx(expected)


def test_a_second_change_on_a_planned_read_stops_the_probe():
    schedule = probe.Probe(1.0)
    schedule.start(0.0)
    schedule.record(0.05, 12)
    first = schedule.record(0.10, 13)
    assert schedule.record(first, 14) is None
    assert schedule.timed


def test_a_probe_without_changes_stops_at_its_deadline():
    schedule = probe.Probe(1.0)
    moment = schedule.start(0.0)
    last = None
    while moment is not None:
        last = moment
        moment = schedule.record(moment, 12)
    assert (
        probe.PROBE_SECONDS - probe.SCAN_SECONDS
        <= last
        <= probe.PROBE_SECONDS + 1e-6
    )
    assert not schedule.timed


def test_each_change_restarts_the_deadline():
    schedule = probe.Probe(1.0)
    moment = schedule.start(0.0)
    while moment < 1.95:
        moment = schedule.record(moment, 12)
    upcoming = schedule.record(moment, 13)
    assert upcoming is not None
    assert upcoming > probe.PROBE_SECONDS
