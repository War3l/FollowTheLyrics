import math

DEADBAND = 0.15
SETTLE = 0.3
SETTLE_READINGS = 3
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
        self._drift = 0

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
        self._drift = 0

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
        self._reading = (position, at)
        reported_now = position + ((now - at) * speed if playing else 0.0)
        if abs(position - (last_position + elapsed)) >= JUMP:
            self.reset(reported_now, playing, now, speed)
            return
        shown = self.position(now)
        if not playing:
            if self.playing or abs(position - last_position) <= DEADBAND:
                self.playing = False
                self._drift = 0
                self._anchor(shown, now, speed, now)
            else:
                self.reset(position, False, now, speed)
            return
        self.playing = True
        self.speed = speed
        self._steer(shown, reported_now - shown, now)

    def _steer(self, shown: float, error: float, now: float):
        holding = math.isinf(self._slew_until) and self._rate == 0.0
        self._drift = self._drift_after(error)
        if self._drift <= -SETTLE_READINGS or (holding and error < -DEADBAND):
            self._anchor(shown, now, 0.0, math.inf)
        elif self._drift >= SETTLE_READINGS:
            self._drift = 0
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

    def _drift_after(self, error: float) -> int:
        if error > SETTLE:
            return max(self._drift, 0) + 1
        if error < -SETTLE:
            return min(self._drift, 0) - 1
        return 0

    def _anchor(self, position: float, at: float, rate: float, until: float):
        self._anchor_pos = position
        self._anchor_t = at
        self._rate = rate
        self._slew_until = until
