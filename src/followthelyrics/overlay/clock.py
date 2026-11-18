import math

DEADBAND = 0.15
JUMP = 1.0
MAX_SKEW = 0.05
SLEW_SECONDS = 2.0


class PlaybackClock:
    def __init__(self, now: float):
        self.playing = False
        self._anchor_pos = 0.0
        self._anchor_t = now
        self._rate = 1.0
        self._slew_until = now
        self._reading = (0.0, now)

    def position(self, now: float) -> float:
        if not self.playing:
            return self._anchor_pos
        slewing = min(now, self._slew_until) - self._anchor_t
        steady = max(0.0, now - self._slew_until)
        return self._anchor_pos + self._rate * max(0.0, slewing) + steady

    def reset(self, position: float, playing: bool, at: float):
        self.playing = playing
        self._anchor(position, at, 1.0, at)
        self._reading = (position, at)

    def sync(self, position: float, playing: bool, at: float, now: float):
        last_position, last_at = self._reading
        expected = last_position + (at - last_at if self.playing else 0.0)
        self._reading = (position, at)
        reported_now = position + (now - at if playing else 0.0)
        if abs(position - expected) >= JUMP:
            self.reset(reported_now, playing, now)
            return
        shown = self.position(now)
        if not playing:
            if self.playing or abs(position - last_position) <= DEADBAND:
                self.playing = False
                self._anchor(shown, now, 1.0, now)
            else:
                self.reset(position, False, now)
            return
        self.playing = True
        self._steer(shown, reported_now - shown, now)

    def _steer(self, shown: float, error: float, now: float):
        holding = math.isinf(self._slew_until) and self._rate == 0.0
        if error <= -JUMP or (holding and error < -DEADBAND):
            self._anchor(shown, now, 0.0, math.inf)
        elif error >= JUMP:
            self._anchor(shown + error, now, 1.0, now)
        elif abs(error) <= DEADBAND:
            self._anchor(shown, now, 1.0, now)
        else:
            skew = max(-MAX_SKEW, min(MAX_SKEW, error / SLEW_SECONDS))
            self._anchor(shown, now, 1.0 + skew, now + error / skew)

    def _anchor(self, position: float, at: float, rate: float, until: float):
        self._anchor_pos = position
        self._anchor_t = at
        self._rate = rate
        self._slew_until = until
