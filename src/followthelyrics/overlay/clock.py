import math

DEADBAND = 0.15
SETTLE = 0.3
SETTLE_SECONDS = 2.0
STILL = 0.001
JUMP = 1.0
MAX_SKEW = 0.05
SLEW_SECONDS = 2.0


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

    def sync(
        self,
        position: float,
        playing: bool,
        at: float,
        now: float,
        speed: float = 1.0,
    ):
        last_position, last_at = self._reading
        elapsed = (at - last_at) * self.speed if self.playing else 0.0
        jump = position - (last_position + elapsed)
        self._reading = (position, at)
        reported_now = position + ((now - at) * speed if playing else 0.0)
        if abs(jump) >= JUMP:
            self.reset(reported_now, playing, now, speed)
            return
        shown = self.position(now)
        if not playing:
            if self.playing or abs(position - last_position) <= DEADBAND:
                self.playing = False
                self._shift = None
                self._anchor(shown, now, speed, now)
            else:
                self.reset(position, False, now, speed)
            return
        stalled = at > last_at and abs(position - last_position) < STILL
        self._track_shift(jump, speed, at)
        self.playing = True
        self.speed = speed
        self._steer(shown, reported_now - shown, now, at, stalled)

    def _track_shift(self, jump: float, speed: float, at: float):
        if speed != self.speed:
            self._shift = None
        elif abs(jump) > SETTLE:
            direction = math.copysign(1.0, jump)
            if self._shift is None or self._shift[1] != direction:
                self._shift = (at, direction)

    def _settled(self, error: float, at: float) -> bool:
        if self._shift is None or at - self._shift[0] < SETTLE_SECONDS:
            return False
        direction = self._shift[1]
        self._shift = None
        return abs(error) > DEADBAND and math.copysign(1.0, error) == direction

    def _steer(
        self, shown: float, error: float, now: float, at: float, stalled: bool
    ):
        holding = math.isinf(self._slew_until) and self._rate == 0.0
        settled = self._settled(error, at) or abs(error) >= JUMP
        if (stalled and error < 0.0) or (holding and error < -DEADBAND):
            self._anchor(shown, now, 0.0, math.inf)
        elif settled and error < 0.0:
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
