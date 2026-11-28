PROBE_SECONDS = 2.0
PROBE_TRANSITIONS = 2
SCAN_SECONDS = 0.05
REFINE_SECONDS = 0.0125
REFINE_STEPS = 4


class Probe:
    def __init__(self, period: float):
        self._period = period
        self._last: tuple[float, float] | None = None
        self._planned: list[float] = []
        self._transitions = 0
        self._deadline = 0.0

    @property
    def timed(self) -> bool:
        return self._transitions >= PROBE_TRANSITIONS

    def start(self, now: float) -> float | None:
        self._last = None
        self._planned = []
        self._transitions = 0
        self._deadline = now + PROBE_SECONDS
        return self.next_read(now)

    def record(self, at: float, whole: float) -> float | None:
        if self._last is not None and whole != self._last[1]:
            self._transitions += 1
            self._deadline = at + PROBE_SECONDS
            if self.timed:
                self._last = (at, whole)
                return None
            if self._transitions == 1:
                self._plan(self._last[0], at)
        self._last = (at, whole)
        return self.next_read(at)

    def _plan(self, before: float, after: float):
        centre = (before + after) / 2 + self._period
        self._planned = [
            centre + step * REFINE_SECONDS
            for step in range(-REFINE_STEPS, REFINE_STEPS + 1)
        ]

    def next_read(self, after: float) -> float | None:
        while self._planned and self._planned[0] <= after:
            self._planned.pop(0)
        if self._planned:
            upcoming = self._planned.pop(0)
        else:
            upcoming = after + SCAN_SECONDS
        if upcoming > self._deadline:
            return None
        return upcoming
