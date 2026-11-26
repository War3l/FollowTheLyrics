from dataclasses import dataclass
from datetime import datetime

from followthelyrics.playback import track

MAX_AGE_SECONDS = 3600.0


def seek_of_timeline(
    position: object,
    last_updated: datetime | None,
    now: datetime,
    monotonic_now: float,
    rate: object,
) -> track.Seek | None:
    seconds = track.valid_position(position)
    if seconds is None:
        return None
    age = (
        (now - last_updated).total_seconds()
        if last_updated is not None
        else 0.0
    )
    if not 0.0 <= age <= MAX_AGE_SECONDS:
        age = 0.0
    return track.Seek(seconds, monotonic_now - age, track.playback_speed(rate))


SEEK_SECONDS = 0.3


@dataclass(frozen=True)
class Reading:
    position: float
    updated: datetime | None
    rate: float
    playing: bool


def read(
    position: object, updated: datetime | None, rate: object, playing: bool
) -> Reading | None:
    seconds = track.valid_position(position)
    if seconds is None:
        return None
    return Reading(seconds, updated, track.playback_speed(rate), playing)


LARGE_SEEK_SECONDS = 1.0
HOLD_SECONDS = 5.0


def _elapsed(base: Reading, current: Reading) -> float | None:
    if base.updated is None or current.updated is None:
        return None
    elapsed = (current.updated - base.updated).total_seconds()
    return elapsed if elapsed >= 0.0 else None


def _expected(base: Reading, elapsed: float) -> float:
    return base.position + (elapsed * base.rate if base.playing else 0.0)


def _continues(base: Reading, current: Reading) -> bool:
    elapsed = _elapsed(base, current)
    return (
        elapsed is not None
        and 0.0 < elapsed <= HOLD_SECONDS
        and abs(current.position - _expected(base, elapsed)) <= SEEK_SECONDS
    )


def departs(
    previous: Reading | None,
    current: Reading,
    pending: Reading | None = None,
) -> bool:
    elapsed = None if previous is None else _elapsed(previous, current)
    if previous is None or elapsed is None:
        return True
    offset = current.position - _expected(previous, elapsed)
    if abs(offset) > LARGE_SEEK_SECONDS:
        return True
    return pending is not None and _continues(pending, current)


def awaiting(
    previous: Reading | None,
    current: Reading,
    pending: Reading | None = None,
) -> Reading | None:
    if previous is None or departs(previous, current, pending):
        return None
    elapsed = _elapsed(previous, current)
    if elapsed is None:
        return None
    if abs(current.position - _expected(previous, elapsed)) > SEEK_SECONDS:
        return current
    return None


def session_keys(app_ids: list[str]) -> list[tuple[str, int]]:
    ordinals: dict[str, int] = {}
    keys = []
    for app_id in app_ids:
        ordinal = ordinals.get(app_id, 0)
        ordinals[app_id] = ordinal + 1
        keys.append((app_id, ordinal))
    return keys


def partition_watched(
    watched: list[tuple], current: list[tuple[tuple[str, int], object]]
) -> tuple[list, list, list]:
    apps = dict.fromkeys(
        [key[0] for key, _ in current] + [entry[0][0] for entry in watched]
    )
    kept: list = []
    gone: list = []
    fresh: list = []
    for app in apps:
        wanted = [(key, session) for key, session in current if key[0] == app]
        held = [entry for entry in watched if entry[0][0] == app]
        if sorted(key for key, _ in wanted) == sorted(
            entry[0] for entry in held
        ):
            kept.extend(held)
        else:
            gone.extend(held)
            fresh.extend(wanted)
    return kept, gone, fresh
