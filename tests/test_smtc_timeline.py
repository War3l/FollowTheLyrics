from datetime import UTC
from datetime import datetime
from datetime import timedelta

import pytest

from followthelyrics.playback import timeline

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


class FakeSession:
    def __init__(self, app_id: str) -> None:
        self.source_app_user_model_id = app_id


def reading_at(position, seconds, rate=1.0, playing=True):
    return timeline.read(
        position, NOW + timedelta(seconds=seconds), rate, playing
    )


def test_a_timeline_is_dated_by_its_last_update_not_by_its_arrival():
    seek = timeline.seek_of_timeline(
        42.0, NOW - timedelta(seconds=2), NOW, 100.0, 1.0
    )
    assert seek is not None
    assert seek.position == 42.0
    assert seek.at == 98.0


def test_a_timeline_without_a_usable_position_is_no_seek():
    assert timeline.seek_of_timeline(None, NOW, NOW, 100.0, 1.0) is None
    assert timeline.seek_of_timeline(True, NOW, NOW, 100.0, 1.0) is None
    assert timeline.seek_of_timeline(-1.0, NOW, NOW, 100.0, 1.0) is None


def test_a_timeline_keeps_the_rate_it_was_reported_with():
    seek = timeline.seek_of_timeline(1.0, NOW, NOW, 0.0, 1.5)
    assert seek is not None
    assert seek.speed == 1.5


def test_a_timeline_without_a_valid_rate_keeps_normal_speed():
    seek = timeline.seek_of_timeline(1.0, NOW, NOW, 0.0, None)
    assert seek is not None
    assert seek.speed == 1.0


def test_a_timeline_without_an_update_time_is_dated_now():
    seek = timeline.seek_of_timeline(5.0, None, NOW, 100.0, 1.0)
    assert seek is not None
    assert seek.at == 100.0


def test_a_timeline_dated_in_the_future_or_hours_ago_is_dated_now():
    future = timeline.seek_of_timeline(
        5.0, NOW + timedelta(seconds=3), NOW, 100.0, 1.0
    )
    old = timeline.seek_of_timeline(
        5.0, NOW - timedelta(hours=2), NOW, 100.0, 1.0
    )
    assert future is not None and future.at == 100.0
    assert old is not None and old.at == 100.0


def test_a_read_without_a_usable_position_is_none():
    assert timeline.read(None, NOW, 1.0, True) is None
    assert timeline.read(-1.0, NOW, 1.0, True) is None


def test_the_first_reading_of_a_session_is_a_departure():
    assert timeline.departs(None, reading_at(10.0, 0)) is True


def test_a_playing_session_advancing_as_expected_is_not_a_departure():
    previous = reading_at(10.0, 0)
    assert timeline.departs(previous, reading_at(12.0, 2)) is False


def test_a_double_speed_session_advancing_as_expected_is_not_a_departure():
    previous = reading_at(10.0, 0, rate=2.0)
    assert timeline.departs(previous, reading_at(14.0, 2, rate=2.0)) is False


def test_a_paused_session_that_does_not_move_is_not_a_departure():
    previous = reading_at(10.0, 0, playing=False)
    assert (
        timeline.departs(previous, reading_at(10.0, 5, playing=False)) is False
    )


def test_a_drift_below_the_threshold_is_not_a_departure():
    previous = reading_at(10.0, 0)
    assert timeline.departs(previous, reading_at(12.2, 2)) is False


def test_a_small_seek_is_held_until_the_next_update_confirms_it():
    previous = reading_at(10.0, 0)
    seek = reading_at(12.8, 2)
    assert timeline.departs(previous, seek) is False
    pending = timeline.awaiting(previous, seek)
    assert pending == seek
    assert timeline.departs(seek, reading_at(14.9, 4), pending) is True


def test_a_repeated_update_of_the_held_reading_does_not_confirm_it():
    previous = reading_at(10.0, 0)
    seek = reading_at(12.8, 2)
    pending = timeline.awaiting(previous, seek)
    assert timeline.departs(seek, reading_at(12.8, 2), pending) is False


def test_a_confirmation_arriving_after_the_hold_does_not_confirm_it():
    previous = reading_at(10.0, 0)
    seek = reading_at(12.8, 2)
    pending = timeline.awaiting(previous, seek)
    late = timeline.HOLD_SECONDS + 1.0
    later = reading_at(12.8 + late, 2 + late)
    assert timeline.departs(seek, later, pending) is False


def test_a_confirmation_within_the_hold_confirms_it():
    previous = reading_at(10.0, 0)
    seek = reading_at(12.8, 2)
    pending = timeline.awaiting(previous, seek)
    within = timeline.HOLD_SECONDS
    confirmed = reading_at(12.8 + within, 2 + within)
    assert timeline.departs(seek, confirmed, pending) is True


@pytest.mark.parametrize("lag", [0.3, 0.4, 0.5])
def test_a_lagging_update_that_recovers_is_no_departure(lag):
    previous = reading_at(10.0, 0)
    lagged = reading_at(12.0 - lag, 2)
    pending = timeline.awaiting(previous, lagged)
    recovered = reading_at(14.0, 4)
    assert timeline.departs(lagged, recovered, pending) is False
    assert timeline.departs(previous, lagged) is False


@pytest.mark.parametrize("skew", [0.3, 0.4, 0.5])
def test_a_constant_skew_between_position_and_update_is_no_departure(skew):
    pending = None
    previous = reading_at(10.0 + skew, 0)
    for second in range(2, 12, 2):
        current = reading_at(10.0 + second + skew, second)
        assert timeline.departs(previous, current, pending) is False
        pending = timeline.awaiting(previous, current, pending)
        previous = current


def test_a_seek_beyond_one_second_is_a_departure_at_once():
    previous = reading_at(10.0, 0)
    assert timeline.departs(previous, reading_at(13.5, 2)) is True


def test_a_jump_beyond_the_threshold_is_a_departure():
    previous = reading_at(10.0, 0)
    assert timeline.departs(previous, reading_at(30.0, 2)) is True


def test_a_paused_session_that_moves_is_a_departure():
    previous = reading_at(10.0, 0, playing=False)
    assert (
        timeline.departs(previous, reading_at(40.0, 5, playing=False)) is True
    )


def test_a_reading_older_than_the_previous_one_is_a_departure():
    previous = reading_at(10.0, 5)
    assert timeline.departs(previous, reading_at(10.0, 1)) is True


def test_a_reading_without_an_update_time_is_a_departure():
    previous = reading_at(10.0, 0)
    current = timeline.read(10.5, None, 1.0, True)
    assert timeline.departs(previous, current) is True


def test_sessions_of_the_same_app_get_distinct_ordinals():
    assert timeline.session_keys(["firefox", "firefox", "vlc"]) == [
        ("firefox", 0),
        ("firefox", 1),
        ("vlc", 0),
    ]


def test_an_empty_app_id_is_keyed_like_any_other():
    assert timeline.session_keys(["", ""]) == [("", 0), ("", 1)]


def test_two_sessions_of_the_same_app_are_watched_apart():
    first, second = ("firefox", 0), ("firefox", 1)
    watched = [(first, "a", 1, 2), (second, "b", 3, 4)]
    kept, gone, fresh = timeline.partition_watched(
        watched,
        [(first, FakeSession("firefox")), (second, FakeSession("firefox"))],
    )
    assert kept == watched
    assert gone == []
    assert fresh == []


def test_a_session_replaced_by_a_new_object_under_the_same_key_is_kept():
    key = ("spotify", 0)
    entry = (key, "old", 1, 2)
    replacement = FakeSession("spotify")
    kept, gone, fresh = timeline.partition_watched(
        [entry], [(key, replacement)]
    )
    assert kept == [entry]
    assert gone == []
    assert fresh == []


def test_a_closed_session_is_dropped_and_an_open_one_watched():
    closed_key, opened_key = ("vlc", 0), ("mpv", 0)
    entry = (closed_key, "closed", 1, 2)
    opened = FakeSession("mpv")
    kept, gone, fresh = timeline.partition_watched(
        [entry], [(opened_key, opened)]
    )
    assert kept == []
    assert gone == [entry]
    assert fresh == [(opened_key, opened)]


def test_a_second_session_of_an_app_that_closes_resubscribes_the_first():
    first_key, second_key = ("firefox", 0), ("firefox", 1)
    first_entry = (first_key, "first", 1, 2)
    second_entry = (second_key, "second", 3, 4)
    survivor = FakeSession("firefox")
    kept, gone, fresh = timeline.partition_watched(
        [first_entry, second_entry],
        [(first_key, survivor)],
    )
    assert kept == []
    assert gone == [first_entry, second_entry]
    assert fresh == [(first_key, survivor)]


def test_a_session_opened_before_a_running_one_resubscribes_both():
    first_key, second_key = ("spotify", 0), ("spotify", 1)
    running = (first_key, "A", 1, 2)
    opened = FakeSession("spotify")
    existing = FakeSession("spotify")
    kept, gone, fresh = timeline.partition_watched(
        [running],
        [(first_key, opened), (second_key, existing)],
    )
    assert kept == []
    assert gone == [running]
    assert fresh == [(first_key, opened), (second_key, existing)]


def test_the_surviving_session_is_resubscribed_when_its_rank_changes():
    first_key, second_key = ("spotify", 0), ("spotify", 1)
    first_entry = (first_key, "A", 1, 2)
    second_entry = (second_key, "B", 3, 4)
    survivor = FakeSession("spotify")
    kept, gone, fresh = timeline.partition_watched(
        [first_entry, second_entry],
        [(first_key, survivor)],
    )
    assert kept == []
    assert gone == [first_entry, second_entry]
    assert fresh == [(first_key, survivor)]


def test_sessions_of_an_unchanged_app_are_kept_when_another_app_changes():
    spotify_key, vlc_key = ("spotify", 0), ("vlc", 0)
    spotify_entry = (spotify_key, "spotify", 1, 2)
    vlc_entry = (vlc_key, "vlc", 3, 4)
    spotify = FakeSession("spotify")
    kept, gone, fresh = timeline.partition_watched(
        [spotify_entry, vlc_entry],
        [(spotify_key, spotify)],
    )
    assert kept == [spotify_entry]
    assert gone == [vlc_entry]
    assert fresh == []
