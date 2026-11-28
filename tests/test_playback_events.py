import math
import threading
import time

import pytest

from followthelyrics.playback import events
from followthelyrics.playback import track


def test_a_notice_sent_before_the_wait_ends_it_at_once():
    hub = events.PlayerEvents()
    hub.notify()
    started = time.monotonic()
    hub.wait(5.0)
    assert time.monotonic() - started < 1.0


def test_a_wait_without_notice_lasts_the_full_timeout():
    hub = events.PlayerEvents()
    started = time.monotonic()
    hub.wait(0.2)
    assert time.monotonic() - started >= 0.19


def test_a_notice_from_another_thread_ends_the_wait():
    hub = events.PlayerEvents()
    timer = threading.Timer(0.05, hub.notify)
    timer.start()
    started = time.monotonic()
    hub.wait(5.0)
    timer.join()
    assert time.monotonic() - started < 1.0


def test_begin_forgets_a_notice_that_came_before_the_read():
    hub = events.PlayerEvents()
    hub.notify()
    hub.begin()
    assert not hub.ready()


def test_a_notice_after_begin_is_kept_for_the_wait():
    hub = events.PlayerEvents()
    hub.begin()
    hub.notify()
    assert hub.ready()


def test_only_the_latest_seek_is_taken_once():
    hub = events.PlayerEvents()
    first = track.Seek(10.0, 1.0)
    last = track.Seek(20.0, 2.0)
    hub.notify(first)
    hub.notify(last)
    assert hub.take_seek() == last
    assert hub.take_seek() is None


def test_a_plain_notice_carries_no_seek():
    hub = events.PlayerEvents()
    hub.notify()
    assert hub.take_seek() is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0, 0.0), (12.5, 12.5), (86_400, 86_400.0)],
)
def test_a_valid_position_is_kept(value, expected):
    assert track.valid_position(value) == expected


@pytest.mark.parametrize(
    "value",
    [-1, -0.5, 86_400.5, math.nan, math.inf, -math.inf, None, "12", True],
)
def test_an_invalid_position_is_dropped(value):
    assert track.valid_position(value) is None


@pytest.mark.parametrize("value", [0.0, -1.0, "fast", 40.0, float("nan")])
def test_an_invalid_rate_does_not_replace_the_last_played_one(value):
    player_events = events.PlayerEvents()
    player_events.remember_rate(2.0)
    player_events.remember_rate(value)
    assert player_events.rate() == 2.0


def test_the_last_played_rate_is_kept_for_a_seek():
    player_events = events.PlayerEvents()
    player_events.remember_rate(1.5)
    assert player_events.rate() == 1.5


def test_a_seek_position_is_kept_without_a_known_duration():
    assert track.bounded_position(105.0, 0.0) == 105.0
    assert track.bounded_position(5.0, -1.0) == 5.0


def test_a_seek_position_is_bounded_by_a_known_duration():
    assert track.bounded_position(5.0, 3.0) == 3.0
