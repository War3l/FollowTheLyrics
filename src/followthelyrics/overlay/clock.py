import collections
import enum
import math

from followthelyrics.playback import track

DEADBAND = 0.15
SETTLE = 0.3
SETTLE_SECONDS = 2.0
STALL_SECONDS = 1.0
QUICK_STALL_SECONDS = 0.5
UPDATE_MARGIN = 1.25
MOVES_BEFORE_TRUST = 5
RECENT_GAPS = 8
LOOP_MARGIN = 2.0
CONFIRM_SECONDS = 1.0
STILL = 0.01
JUMP = 1.0
MAX_SKEW = 0.05
QUANTIZED_TOLERANCE = 0.001
QUANTIZED_READS = 3
SLEW_SECONDS = 2.0
LEARN_SECONDS = 5.0
LEARN_RESIDUAL = 0.1
GAIN_MAX = track.MAX_SPEED
GAIN_MIN = 1.0 / track.MAX_SPEED
QUANTUM = 1.0
PHASES = (0.0, 0.5)
POSITION_RESOLUTION = 1e-6
PIN_WIDTH = 0.05
ERR_PIN = 0.2
HOLD_LEAD = 0.3
SEEK_RATIO_LOW = 0.25
SEEK_RATIO_HIGH = 4.0
MISMATCH_READS = 3


class Rewind(enum.Enum):
    NONE = enum.auto()
    DOUBTED = enum.auto()
    CONFIRMED = enum.auto()


def _whole(seconds: float) -> bool:
    return seconds == math.floor(seconds)


def _box(lower: float, upper: float) -> list[tuple[float, float]]:
    return [
        (lower, GAIN_MIN),
        (upper, GAIN_MIN),
        (upper, GAIN_MAX),
        (lower, GAIN_MAX),
    ]


def _shear(
    cell: list[tuple[float, float]], elapsed: float, speed: float
) -> list[tuple[float, float]]:
    dt = max(0.0, elapsed) * speed
    return [(position + ratio * dt, ratio) for position, ratio in cell]


def _cut(
    cell: list[tuple[float, float]], bound: float, keep_above: bool
) -> list[tuple[float, float]]:
    kept = []
    count = len(cell)
    for i in range(count):
        x1, r1 = cell[i]
        x2, r2 = cell[(i + 1) % count]
        inside1 = x1 >= bound if keep_above else x1 <= bound
        inside2 = x2 >= bound if keep_above else x2 <= bound
        if inside1:
            kept.append((x1, r1))
        if inside1 != inside2:
            t = (bound - x1) / (x2 - x1)
            kept.append((bound, r1 + t * (r2 - r1)))
    return kept


def _clip(
    cell: list[tuple[float, float]], lower: float, upper: float
) -> list[tuple[float, float]]:
    return _cut(_cut(cell, lower, True), upper, False)


def _admitting(
    cells: dict[float, list[tuple[float, float]]],
    elapsed: float,
    position: float,
    speed: float,
) -> dict[float, list[tuple[float, float]]]:
    candidates = {
        phase: _clip(
            _shear(cell, elapsed, speed),
            position - phase - POSITION_RESOLUTION,
            position + QUANTUM - phase + POSITION_RESOLUTION,
        )
        for phase, cell in cells.items()
    }
    return {phase: cell for phase, cell in candidates.items() if cell}


def _xbounds(cell: list[tuple[float, float]]) -> tuple[float, float]:
    positions = [position for position, _ in cell]
    return min(positions), max(positions)


def _slice(
    cell: list[tuple[float, float]], ratio: float
) -> tuple[float, float] | None:
    positions = []
    count = len(cell)
    for i in range(count):
        x1, r1 = cell[i]
        x2, r2 = cell[(i + 1) % count]
        if r1 == ratio:
            positions.append(x1)
        if (r1 - ratio) * (r2 - ratio) < 0:
            positions.append(x1 + (ratio - r1) * (x2 - x1) / (r2 - r1))
    if not positions:
        return None
    return min(positions), max(positions)


class PlaybackClock:
    def __init__(self, now: float):
        self.playing = False
        self.speed = 1.0
        self._app = ""
        self._phases: dict[str, float] = {}
        self._phase_before_anchor: float | None = None
        self._cells_before_anchor: (
            tuple[dict[float, list[tuple[float, float]]], float, bool] | None
        ) = None
        self._truth: dict[float, list[tuple[float, float]]] = {}
        self._truth_t = now
        self._truth_playing = False
        self._anchored = False
        self._anchor_pos = 0.0
        self._anchor_t = now
        self._rate = 1.0
        self._gain = 1.0
        self._gain_proven = False
        self._gain_before_chance: tuple[float, bool] | None = None
        self._window: tuple[float, list[tuple[float, float]]] | None = None
        self._hold: tuple[float, float, float, float | None] | None = None
        self._slew_until = now
        self._reading = (0.0, now)
        self._shift: tuple[float, float] | None = None
        self._doubt: tuple[float, float] | None = None
        self._still_since = now
        self._still_position = 0.0
        self._whole_run = 0
        self._whole_at = -math.inf
        self._mismatch: tuple[float, int] | None = None
        self._gaps: collections.deque[float] = collections.deque(
            maxlen=RECENT_GAPS
        )

    def position(self, now: float) -> float:
        if not self.playing:
            return self._anchor_pos
        slewing = min(now, self._slew_until) - self._anchor_t
        steady = max(0.0, now - self._slew_until)
        return (
            self._anchor_pos
            + self._rate * max(0.0, slewing)
            + self.speed * steady
        )

    def reset(
        self,
        position: float,
        playing: bool,
        at: float,
        speed: float = 1.0,
        app: str = "",
        track_start: bool = False,
    ):
        self.playing = playing
        self.speed = speed * self._gain
        self._app = app
        self._anchor(position, at, self.speed, at)
        self._reading = (position, at)
        self._shift = None
        self._doubt = None
        self._still_since = at
        self._still_position = position
        self._gaps.clear()
        self._window = None
        self._hold = None
        self._truth = {}
        self._anchored = False
        self._cells_before_anchor = None
        if track_start and playing and position < QUANTUM:
            self._exact(0.0, at, True)

    def seeked(
        self,
        position: float,
        at: float,
        now: float,
        playing: bool,
        speed: float = 1.0,
        app: str = "",
    ):
        elapsed = max(0.0, now - min(at, now)) if playing else 0.0
        target = position + elapsed * speed * self._gain
        stale = self._reading[0]
        anchored_cells = (
            (self._truth, self._truth_t, self._truth_playing)
            if self._anchored and self._truth
            else None
        )
        self.reset(target, playing, now, speed, app)
        self._exact(target, now, playing)
        self._cells_before_anchor = anchored_cells
        if playing:
            self._hold = (target, now, now + SETTLE_SECONDS, None)
        else:
            self._hold = (target, now, math.inf, stale)

    def sync(
        self,
        position: float,
        playing: bool,
        at: float,
        now: float,
        speed: float = 1.0,
        duration: float | None = None,
        app: str = "",
    ):
        self._app = app
        self._count_whole(position, playing, at)
        quantized = self._whole_run >= QUANTIZED_READS
        if quantized:
            self._gain_before_chance = None
        elif self._gain_before_chance is not None and not _whole(position):
            self._drop_chance_gain(position, playing, at, now, speed)
            return
        if not playing:
            self._freeze(at)
        if self._holds(position, playing, at, now):
            if (
                playing
                and self._anchored
                and self._plausible_after_hold(position, at)
                and _whole(position)
            ):
                gain = self._gain
                proven = self._gain_proven
                self._relearn_rate(position, at, now, speed)
                if (
                    not quantized
                    and self._gain != gain
                    and self._gain_before_chance is None
                ):
                    self._gain_before_chance = (gain, proven)
            if playing and self._follows_base(position, at):
                self._reading = (position, at)
            return
        if not playing and quantized and self._reads_frozen(position):
            self._hold_frozen(position, at, now, speed)
            return
        last_position, last_at = self._reading
        elapsed = (at - last_at) * self.speed if self.playing else 0.0
        jump = position - (last_position + elapsed)
        effective = speed * self._gain
        lower = position + ((now - at) * effective if playing else 0.0)
        reported_now = lower + (QUANTUM / 2 if quantized else 0.0)
        if self._looped(last_position, position, duration):
            self.reset(reported_now, playing, now, speed)
            return
        if (
            not quantized
            and playing
            and self._learn_exact_rate(
                position, last_position, last_at, at, jump
            )
        ):
            self.reset(
                position + (now - at) * speed * self._gain,
                playing,
                now,
                speed,
            )
            return
        rewind = self._doubts(
            jump,
            position,
            at,
            effective if playing else None,
            quantized,
        )
        explained = (
            playing
            and (self._anchored or quantized)
            and _whole(position)
            and self._explained(position, at, speed)
        )
        if rewind is Rewind.DOUBTED:
            if explained:
                self._narrow(position, at, speed)
            if (
                quantized
                and playing
                and _whole(position)
                and position > last_position
            ):
                self._relearn_rate(position, at, now, speed)
            return
        if (rewind is Rewind.CONFIRMED or abs(jump) >= JUMP) and not explained:
            if not (playing and self._revive(position, at, now, speed)):
                self.reset(reported_now, playing, now, speed)
            return
        learned = self._learn(position, at, speed, playing)
        effective = speed * self._gain
        self._reading = (position, at)
        shown = self.position(now)
        if not playing:
            if self.playing or abs(position - last_position) <= DEADBAND:
                self.playing = False
                self._shift = None
                self._anchor(shown, now, effective, now)
            else:
                self.reset(position, False, now, speed)
            return
        moved = abs(position - self._still_position) >= STILL
        if self.playing and moved:
            self._gaps.append(at - self._still_since)
        if not self.playing or moved:
            self._still_since = at
            self._still_position = position
        stalled = at - self._still_since >= self._stall_patience(
            quantized, effective
        )
        self._track_shift(jump, effective, at)
        resumed = not self.playing
        self.playing = True
        self.speed = effective
        whole = _whole(position)
        narrowing = whole and (quantized or self._anchored)
        if narrowing:
            hypotheses_before = len(self._truth)
            self._narrow(position, at, speed)
            corrected = len(self._truth) < hypotheses_before or (
                explained and abs(jump) >= JUMP
            )
            if quantized:
                gain_before = self._gain
                self._learn_rate()
                corrected = corrected or (
                    self._gain != gain_before and len(self._truth) == 1
                )
                effective = speed * self._gain
                self.speed = effective
        else:
            self._truth = {}
            self._anchored = False
            corrected = False
        error = self._error(position, at, now, shown, effective, narrowing)
        outside = False
        if narrowing and self._anchored:
            lower, upper = self._hull(now - at, speed)
            outside = error > SETTLE or not lower <= shown <= upper
        settled = self._settled(error, at, abs(jump) <= SETTLE)
        resumed_off = resumed and abs(error) > DEADBAND
        tolerance = QUANTIZED_TOLERANCE if narrowing else DEADBAND
        relearned = learned
        if corrected and error < -HOLD_LEAD:
            self._anchor(shown + error, now, self.speed, now)
            return
        self._steer(
            shown,
            error,
            now,
            stalled,
            settled or resumed_off or relearned or corrected or outside,
            tolerance,
        )

    def _learn_exact_rate(
        self,
        position: float,
        last_position: float,
        last_at: float,
        at: float,
        jump: float,
    ) -> bool:
        elapsed = (at - last_at) * self.speed
        if abs(jump) <= SETTLE or elapsed <= 0.0:
            self._mismatch = None
            return False
        ratio = (position - last_position) / elapsed
        if not SEEK_RATIO_LOW <= ratio <= SEEK_RATIO_HIGH:
            self._mismatch = None
            return False
        if self._mismatch is not None and abs(ratio - self._mismatch[0]) <= (
            MAX_SKEW * ratio
        ):
            self._mismatch = (ratio, self._mismatch[1] + 1)
        else:
            self._mismatch = (ratio, 1)
        if self._mismatch[1] < MISMATCH_READS:
            return False
        self._gain = min(GAIN_MAX, max(GAIN_MIN, self._gain * ratio))
        self._mismatch = None
        return True

    def _relearn_rate(
        self, position: float, at: float, now: float, speed: float
    ):
        gain = self._gain
        self._narrow(position, at, speed)
        self._learn_rate()
        if self._gain != gain:
            self.speed = speed * self._gain
            lower, upper = self._truth_bounds()
            estimate = (lower + upper) / 2 + (now - at) * self.speed
            self._anchor(estimate, now, self.speed, now)

    def _drop_chance_gain(
        self,
        position: float,
        playing: bool,
        at: float,
        now: float,
        speed: float,
    ):
        if self._gain_before_chance is not None:
            self._gain, self._gain_proven = self._gain_before_chance
        self._gain_before_chance = None
        reported = position + ((now - at) * speed if playing else 0.0)
        self.reset(reported, playing, now, speed)

    def _plausible_after_hold(self, position: float, at: float) -> bool:
        if self._hold is None:
            return False
        held_position, held_at, _, _ = self._hold
        elapsed = at - held_at
        advance = position - held_position
        return (
            SEEK_RATIO_LOW * elapsed - QUANTUM
            <= advance
            <= SEEK_RATIO_HIGH * elapsed + QUANTUM
        )

    def _follows_base(self, position: float, at: float) -> bool:
        base_position, base_at = self._reading
        elapsed = at - base_at
        return elapsed > 0.0 and (
            SEEK_RATIO_LOW * elapsed
            <= position - base_position
            <= SEEK_RATIO_HIGH * elapsed
        )

    def _count_whole(self, position: float, playing: bool, at: float):
        if not _whole(position):
            self._whole_run = 0
        elif playing and at > self._whole_at:
            self._whole_run += 1
            self._whole_at = at

    def status(self, playing: bool, at: float, speed: float = 1.0):
        if playing == self.playing:
            return
        if playing:
            self._play(at, speed)
        else:
            self._pause(at)

    def _pause(self, at: float):
        self._freeze(at)
        frozen = self._pinned_position()
        shown = self.position(at)
        self.playing = False
        self._anchor(shown if frozen is None else frozen, at, self.speed, at)

    def _play(self, at: float, speed: float):
        frozen = None if self._truth_playing else self._pinned_position()
        self.playing = True
        self.speed = speed * self._gain
        if frozen is None:
            self._truth_t = at
            self._truth_playing = True
            self._anchor(self._anchor_pos, at, self.speed, at)
        else:
            self._exact(frozen, at, True)
            self._anchor(frozen, at, self.speed, at)
        if self._cells_before_anchor is not None:
            cells, _, _ = self._cells_before_anchor
            self._cells_before_anchor = (cells, at, True)

    def _freeze(self, at: float):
        if self._cells_before_anchor is not None:
            cells, since, playing = self._cells_before_anchor
            if playing:
                speed = self.speed / self._gain
                self._cells_before_anchor = (
                    {
                        phase: _shear(cell, at - since, speed)
                        for phase, cell in cells.items()
                    },
                    at,
                    False,
                )
        if self._truth and self._truth_playing:
            elapsed = at - self._truth_t
            speed = self.speed / self._gain
            self._truth = {
                phase: _shear(cell, elapsed, speed)
                for phase, cell in self._truth.items()
            }
        self._truth_t = at
        self._truth_playing = False

    def _pinned_position(self) -> float | None:
        if not self._truth:
            return None
        lower, upper = self._truth_bounds()
        if upper - lower > PIN_WIDTH:
            return None
        return (lower + upper) / 2

    def _exact(self, truth: float, at: float, playing: bool):
        self._phase_before_anchor = self._phases.get(self._app)
        self._truth = {
            phase: _box(
                truth - POSITION_RESOLUTION, truth + POSITION_RESOLUTION
            )
            for phase in PHASES
        }
        self._truth_t = at
        self._truth_playing = playing
        self._anchored = True

    def _revived_cells(
        self, position: float, at: float, speed: float
    ) -> dict[float, list[tuple[float, float]]]:
        return self._cells_revived_by(
            position, at, speed
        ) or self._reading_cells(position)

    def _cells_revived_by(
        self, position: float, at: float, speed: float
    ) -> dict[float, list[tuple[float, float]]]:
        if self._cells_before_anchor is None:
            return {}
        cells, since, playing = self._cells_before_anchor
        self._cells_before_anchor = None
        elapsed = at - since if playing else 0.0
        return _admitting(cells, elapsed, position, speed)

    def _revive(
        self, position: float, at: float, now: float, speed: float
    ) -> bool:
        revived = self._cells_revived_by(position, at, speed)
        if not revived:
            return False
        self._restore_phase()
        self._truth = revived
        self._truth_t = at
        self._truth_playing = True
        self._anchored = True
        self._doubt = None
        self._hold = None
        self._shift = None
        self._learn_rate()
        self.speed = speed * self._gain
        self.playing = True
        self._reading = (position, at)
        lower, upper = self._truth_bounds()
        estimate = (lower + upper) / 2 + (now - at) * self.speed
        self._anchor(estimate, now, self.speed, now)
        return True

    def _restore_phase(self):
        if self._phase_before_anchor is None:
            self._phases.pop(self._app, None)
        else:
            self._phases[self._app] = self._phase_before_anchor

    def _phase_candidates(self) -> tuple[float, ...]:
        if self._app in self._phases:
            return (self._phases[self._app],)
        return PHASES

    def _narrow(self, position: float, at: float, speed: float):
        if self._truth:
            elapsed = at - self._truth_t if self._truth_playing else 0.0
            survivors = _admitting(self._truth, elapsed, position, speed)
        else:
            survivors = self._reading_cells(position)
        if not survivors:
            self._gain_proven = False
            self._restore_phase()
            survivors = self._revived_cells(position, at, speed)
        elif self._anchored and len(survivors) == 1:
            (phase,) = survivors
            self._phases[self._app] = phase
        self._truth = survivors
        self._truth_t = at
        self._truth_playing = True

    def _explained(self, position: float, at: float, speed: float) -> bool:
        elapsed = at - self._truth_t if self._truth_playing else 0.0
        return bool(_admitting(self._truth, elapsed, position, speed))

    def _hold_frozen(
        self, position: float, at: float, now: float, speed: float
    ):
        shown = self.position(now)
        self._reading = (position, at)
        self.playing = False
        self._shift = None
        self._anchor(shown, now, speed * self._gain, now)

    def _reads_frozen(self, position: float) -> bool:
        return any(
            lower < position + QUANTUM - phase and upper >= position - phase
            for phase, (lower, upper) in self._phase_bounds().items()
        )

    def _reading_cells(
        self, position: float
    ) -> dict[float, list[tuple[float, float]]]:
        return {
            phase: _box(position - phase, position + QUANTUM - phase)
            for phase in self._phase_candidates()
        }

    def _phase_bounds(self) -> dict[float, tuple[float, float]]:
        slices = {
            phase: _slice(cell, self._gain)
            for phase, cell in self._truth.items()
        }
        consistent = {
            phase: bounds for phase, bounds in slices.items() if bounds
        }
        if consistent:
            return consistent
        return {phase: _xbounds(cell) for phase, cell in self._truth.items()}

    def _truth_bounds(self) -> tuple[float, float]:
        bounds = self._phase_bounds().values()
        return (
            min(lower for lower, _ in bounds),
            max(upper for _, upper in bounds),
        )

    def _hull(self, elapsed: float, speed: float) -> tuple[float, float]:
        bounds = [
            _xbounds(_shear(cell, elapsed, speed))
            for cell in self._truth.values()
        ]
        return (
            min(lower for lower, _ in bounds),
            max(upper for _, upper in bounds),
        )

    def _ratio_spread(self) -> float:
        ratios = [ratio for cell in self._truth.values() for _, ratio in cell]
        return max(ratios) - min(ratios)

    def _announced_fits(self) -> bool:
        return any(
            _slice(cell, 1.0) is not None for cell in self._truth.values()
        )

    def _fits_all(self, gain: float) -> bool:
        return all(
            _slice(cell, gain) is not None for cell in self._truth.values()
        )

    def _learn_rate(self):
        if self._gain_proven and self._fits_all(self._gain):
            return
        if self._announced_fits():
            self._gain = 1.0
            self._gain_proven = False
            return
        self._gain_proven = True
        if self._fits_all(self._gain):
            return
        ratios = [ratio for cell in self._truth.values() for _, ratio in cell]
        self._gain = min(
            GAIN_MAX, max(GAIN_MIN, (max(ratios) + min(ratios)) / 2)
        )

    def _error(
        self,
        position: float,
        at: float,
        now: float,
        shown: float,
        effective: float,
        quantized: bool,
    ) -> float:
        if not quantized:
            return position + (now - at) * effective - shown
        if (
            len(self._truth) == 1
            and self._ratio_spread() <= ERR_PIN
            and not self._announced_fits()
        ):
            lower, upper = self._hull(now - at, effective / self._gain)
            return (lower + upper) / 2 - shown
        lower, upper = self._truth_bounds()
        return (lower + upper) / 2 + (now - at) * effective - shown

    def _holds(
        self, position: float, playing: bool, at: float, now: float
    ) -> bool:
        if self._hold is None:
            return False
        held_position, held_at, until, stale = self._hold
        if stale is not None:
            if not playing and (
                abs(position - held_position) <= DEADBAND
                or abs(position - stale) <= DEADBAND
            ):
                return True
            self._hold = None
            return False
        if now >= until:
            self._hold = None
            return False
        expected = held_position
        if playing:
            expected += (at - held_at) * self.speed
        if abs(position - expected) <= DEADBAND:
            self._hold = None
            return False
        return True

    def _learn(
        self,
        position: float,
        at: float,
        speed: float,
        playing: bool,
    ) -> bool:
        if not playing or speed <= 0.0:
            self._window = None
            return False
        if self._window is None or self._window[0] != speed:
            self._window = (speed, [(position, at)])
            return False
        readings = self._window[1]
        readings.append((position, at))
        first_position, first_at = readings[0]
        if at - first_at < LEARN_SECONDS:
            return False
        offsets = [(t - first_at, p - first_position) for p, t in readings]
        slope = sum(dt * dp for dt, dp in offsets) / sum(
            dt * dt for dt, _ in offsets
        )
        residual = max(abs(dp - slope * dt) for dt, dp in offsets)
        self._window = (speed, [(position, at)])
        if residual <= LEARN_RESIDUAL:
            gain = min(GAIN_MAX, max(GAIN_MIN, slope / speed))
            changed = abs(gain - self._gain) > MAX_SKEW * self._gain
            self._gain = gain
            return changed
        return False

    def _stall_patience(self, quantized: bool, effective: float) -> float:
        if len(self._gaps) < MOVES_BEFORE_TRUST:
            patience = STALL_SECONDS
        else:
            expected = max(self._gaps) * UPDATE_MARGIN
            patience = min(STALL_SECONDS, max(QUICK_STALL_SECONDS, expected))
        if quantized:
            patience = max(patience, QUANTUM / effective)
        return patience

    @staticmethod
    def _looped(
        last_position: float, position: float, duration: float | None
    ) -> bool:
        return bool(
            duration
            and last_position >= duration - LOOP_MARGIN
            and position < LOOP_MARGIN
        )

    def _doubts(
        self,
        jump: float,
        position: float,
        at: float,
        speed: float | None,
        quantized: bool,
    ) -> Rewind:
        if speed is None:
            self._doubt = None
            return Rewind.NONE
        if self._doubt is not None:
            first_position, first_at = self._doubt
            drift = position - (first_position + (at - first_at) * speed)
            limit = QUANTUM if quantized else SETTLE
            if abs(drift) < limit:
                if at - first_at < CONFIRM_SECONDS:
                    return Rewind.DOUBTED
                self._doubt = None
                return Rewind.CONFIRMED
        if jump > -JUMP:
            self._doubt = None
            return Rewind.NONE
        self._doubt = (position, at)
        return Rewind.DOUBTED

    def _track_shift(self, jump: float, speed: float, at: float):
        if speed != self.speed:
            self._shift = None
        elif abs(jump) > SETTLE:
            direction = math.copysign(1.0, jump)
            if self._shift is None or self._shift[1] != direction:
                self._shift = (at, direction)

    def _settled(self, error: float, at: float, gradual: bool) -> bool:
        if gradual and abs(error) >= JUMP:
            return True
        if self._shift is None or at - self._shift[0] < SETTLE_SECONDS:
            return False
        direction = self._shift[1]
        self._shift = None
        return abs(error) > SETTLE and math.copysign(1.0, error) == direction

    def _steer(
        self,
        shown: float,
        error: float,
        now: float,
        stalled: bool,
        settled: bool,
        tolerance: float,
    ):
        holding = self._rate == 0.0 and now < self._slew_until
        if stalled and error < 0.0:
            self._anchor(shown, now, 0.0, math.inf)
        elif (holding or settled) and error < 0.0:
            self._anchor(shown, now, 0.0, now - error / self.speed)
        elif settled:
            self._anchor(shown + error, now, self.speed, now)
        elif abs(error) <= tolerance:
            self._anchor(shown, now, self.speed, now)
        else:
            skew = max(-MAX_SKEW, min(MAX_SKEW, error / SLEW_SECONDS))
            self._anchor(
                shown,
                now,
                self.speed * (1.0 + skew),
                now + error / (skew * self.speed),
            )

    def _anchor(self, position: float, at: float, rate: float, until: float):
        self._anchor_pos = position
        self._anchor_t = at
        self._rate = rate
        self._slew_until = until
