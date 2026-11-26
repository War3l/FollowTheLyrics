import threading

from followthelyrics.playback import track


class PlayerEvents:
    def __init__(self):
        self._ready = threading.Event()
        self._lock = threading.Lock()
        self._seeks: list[track.Seek] = []
        self._edges: list[track.Edge] = []
        self._readings: list[track.Reading] = []
        self._rate = 1.0

    def begin(self) -> None:
        self._ready.clear()

    def notify(self, seek: track.Seek | None = None) -> None:
        with self._lock:
            if seek is not None:
                self._seeks.append(seek)
        self._ready.set()

    def record_edge(self, edge: track.Edge) -> None:
        with self._lock:
            self._edges.append(edge)

    def record_reading(self, reading: track.Reading) -> None:
        with self._lock:
            self._readings.append(reading)

    def take_readings(self) -> tuple[track.Reading, ...]:
        with self._lock:
            readings, self._readings = self._readings, []
        return tuple(readings)

    def take_edges(self) -> tuple[track.Edge, ...]:
        with self._lock:
            edges, self._edges = self._edges, []
        return tuple(edges)

    def ready(self) -> bool:
        return self._ready.is_set()

    def wait(self, seconds: float) -> None:
        self._ready.wait(seconds)

    def take_seek(self) -> track.Seek | None:
        with self._lock:
            seeks, self._seeks = self._seeks, []
        return seeks[-1] if seeks else None

    def remember_rate(self, value) -> None:
        speed = track.positive_speed(value)
        if speed is None:
            return
        with self._lock:
            self._rate = speed

    def rate(self) -> float:
        with self._lock:
            return self._rate
