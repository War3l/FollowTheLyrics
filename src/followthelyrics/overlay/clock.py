DEADBAND = 0.15
JUMP = 1.0
SLEW_SECONDS = 2.0


class PlaybackClock:
    def __init__(self, now: float):
        self.playing = False
        self._anchor_pos = 0.0
        self._anchor_t = now
        self._rate = 1.0
        self._slew_until = now

    def position(self, now: float) -> float:
        if not self.playing:
            return self._anchor_pos
        slewing = min(now, self._slew_until) - self._anchor_t
        steady = max(0.0, now - self._slew_until)
        return self._anchor_pos + self._rate * max(0.0, slewing) + steady

    def reset(self, position: float, playing: bool, at: float):
        self.playing = playing
        self._anchor_pos = position
        self._anchor_t = at
        self._rate = 1.0
        self._slew_until = at

    def sync(self, position: float, playing: bool, at: float, now: float):
        reported_now = position + (now - at if playing else 0.0)
        if playing != self.playing or not playing:
            self.reset(reported_now, playing, now)
            return
        error = reported_now - self.position(now)
        if abs(error) >= JUMP:
            self.reset(reported_now, playing, now)
        elif abs(error) > DEADBAND:
            self._anchor_pos = self.position(now)
            self._anchor_t = now
            self._rate = 1.0 + error / SLEW_SECONDS
            self._slew_until = now + SLEW_SECONDS
