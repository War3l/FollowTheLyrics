import enum
import math

DEADBAND = 0.15
SETTLE = 0.3
SETTLE_SECONDS = 2.0
STALL_SECONDS = 1.0
PRECISE_STALL_SECONDS = 0.5
LOOP_MARGIN = 2.0
CONFIRM_SECONDS = 1.0
STILL = 0.001
JUMP = 1.0
MAX_SKEW = 0.05
SLEW_SECONDS = 2.0


class Rewind(enum.Enum):
    NONE = enum.auto()
    DOUBTED = enum.auto()
    CONFIRMED = enum.auto()


class PlaybackClock:
    def __init__(self, now: float):
        self.playing = False
        self.speed = 1.0
        self._anchor_pos = 0.0
        self._anchor_t = now
        self._rate = 1.0
        self._slew_until = now
        self._reading = (0.0, now)
        self._shift: tuple[float, float] | None = None
        self._doubt: tuple[float, float] | None = None
        self._still_since = now
        self._precise = False

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
        self, position: float, playing: bool, at: float, speed: float = 1.0
    ):
        self.playing = playing
        self.speed = speed
        self._anchor(position, at, speed, at)
        self._reading = (position, at)
        self._shift = None
        self._doubt = None
        self._still_since = at
        self._precise = False

    def sync(
        self,
        position: float,
        playing: bool,
        at: float,
        now: float,
        speed: float = 1.0,
        duration: float | None = None,
    ):
        last_position, last_at = self._reading
        elapsed = (at - last_at) * self.speed if self.playing else 0.0
        jump = position - (last_position + elapsed)
        reported_now = position + ((now - at) * speed if playing else 0.0)
        if self._looped(last_position, position, duration):
            self.reset(reported_now, playing, now, speed)
            return
        rewind = self._doubts(jump, position, at, speed if playing else None)
        if rewind is Rewind.DOUBTED:
            return
        if rewind is Rewind.CONFIRMED or abs(jump) >= JUMP:
            self.reset(reported_now, playing, now, speed)
            return
        self._reading = (position, at)
        shown = self.position(now)
        if not playing:
            if self.playing or abs(position - last_position) <= DEADBAND:
                self.playing = False
                self._shift = None
                self._anchor(shown, now, speed, now)
            else:
                self.reset(position, False, now, speed)
            return
        if not self.playing or abs(position - last_position) >= STILL:
            self._still_since = at
        self._precise = self._precise or abs(position - round(position)) > STILL
        patience = PRECISE_STALL_SECONDS if self._precise else STALL_SECONDS
        stalled = at - self._still_since >= patience
        self._track_shift(jump, speed, at)
        resumed = not self.playing
        self.playing = True
        self.speed = speed
        error = reported_now - shown
        settled = self._settled(error, at, abs(jump) <= SETTLE)
        resumed_off = resumed and abs(error) > DEADBAND
        self._steer(shown, error, now, stalled, settled or resumed_off)

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
        self, jump: float, position: float, at: float, speed: float | None
    ) -> Rewind:
        if speed is None:
            self._doubt = None
            return Rewind.NONE
        if self._doubt is not None:
            first_position, first_at = self._doubt
            drift = position - (first_position + (at - first_at) * speed)
            if abs(drift) <= SETTLE:
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
    ):
        holding = self._rate == 0.0 and now < self._slew_until
        if stalled and error < 0.0:
            self._anchor(shown, now, 0.0, math.inf)
        elif (holding or settled) and error < 0.0:
            self._anchor(shown, now, 0.0, now - error / self.speed)
        elif settled:
            self._anchor(shown + error, now, self.speed, now)
        elif abs(error) <= DEADBAND:
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
