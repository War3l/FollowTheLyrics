import logging
import threading
import time
from collections import deque

import numpy as np

logger = logging.getLogger(__name__)

BLOCK = 1024


class BeatDetector:
    def __init__(self, rate):
        self.rate = rate
        freqs = np.fft.rfftfreq(BLOCK, 1 / rate)
        self.band = (freqs >= 40) & (freqs <= 150)
        self.window = np.hanning(BLOCK).astype(np.float32)
        self.prev = 0.0
        self.flux_hist: deque[float] = deque(maxlen=int(1.5 * rate / BLOCK))
        self.last_beat = 0.0

    def feed(self, mono, now):
        mag = np.abs(np.fft.rfft(mono * self.window))
        e = float(np.sqrt(np.sum(mag[self.band] ** 2)))
        flux = max(0.0, e - self.prev)
        self.prev = e
        hist = self.flux_hist
        strength = 0.0
        if len(hist) >= 10 and e > 0.05:
            arr = np.fromiter(hist, dtype=np.float32)
            thr = float(arr.mean() + 1.4 * arr.std()) + 0.02
            if flux > thr and now - self.last_beat > 0.22:
                self.last_beat = now
                strength = min(1.0, 0.45 + 0.55 * (flux - thr) / (thr + 1e-6))
        hist.append(flux)
        return strength


SILENCE_LEVEL = 0.002
QUIET_BEFORE_SCAN = 3.0
FIRST_SCAN_WAIT = 8.0
MAX_SCAN_WAIT = 120.0


def _silence():
    return np.zeros(0, dtype=np.float32)


class AudioBeats:
    def __init__(self, backend, on_beat):
        self.backend = backend
        self.on_beat = on_beat
        self.enabled = backend is not None
        self.music_playing = False
        self.device_name = ""
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        if self.enabled:
            self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=1.5)

    def _measure(self, loopback, device, seconds=0.3):
        try:
            capture = loopback.capture(device)
        except Exception:
            logger.debug("_measure failed", exc_info=True)
            return 0.0
        total, count = 0.0, 0
        end = time.monotonic() + seconds
        while time.monotonic() < end and not self._stop.is_set():
            samples = capture.read()
            total += float(np.abs(samples).sum())
            count += samples.size
            time.sleep(0.02)
        capture.close()
        return total / count if count else 0.0

    def _loudest(self, loopback, devices, current):
        best, best_level = current, 0.0
        for device in devices:
            if self._stop.is_set():
                break
            level = self._measure(loopback, device)
            if level > best_level:
                best, best_level = device, level
        return best, best_level

    def _run(self):
        try:
            loopback = self.backend.open()
        except Exception:
            logger.warning("_run failed", exc_info=True)
            self.enabled = False
            return
        try:
            self._listen(loopback)
        except Exception:
            logger.warning("_run failed", exc_info=True)
            self.enabled = False
        finally:
            loopback.close()

    def _listen(self, loopback):
        devices = loopback.devices()
        if not devices:
            self.enabled = False
            return
        current = loopback.preferred(devices)
        capture = None
        try:
            capture = loopback.capture(current)
            detector = BeatDetector(capture.rate)
            self.device_name = current.name
            buf = _silence()
            last_sound = time.monotonic()
            last_check = last_scan = 0.0
            scan_wait = FIRST_SCAN_WAIT
            while not self._stop.is_set():
                samples = capture.read()
                now = time.monotonic()
                if samples.size:
                    if float(np.abs(samples).mean()) > SILENCE_LEVEL:
                        last_sound = now
                        scan_wait = FIRST_SCAN_WAIT
                    buf = np.concatenate([buf, samples])
                    while buf.size >= BLOCK:
                        block, buf = buf[:BLOCK], buf[BLOCK:]
                        strength = detector.feed(block, now)
                        if strength > 0:
                            try:
                                self.on_beat(strength)
                            except Exception:
                                logger.debug("_listen failed", exc_info=True)
                else:
                    time.sleep(0.01)
                if now - last_check < 0.5:
                    continue
                last_check = now
                if (
                    now - last_sound > QUIET_BEFORE_SCAN
                    and self.music_playing
                    and now - last_scan > scan_wait
                ):
                    last_scan = now
                    capture.close()
                    capture = None
                    best, level = self._loudest(loopback, devices, current)
                    if level > SILENCE_LEVEL:
                        current = best
                        scan_wait = FIRST_SCAN_WAIT
                    else:
                        scan_wait = min(MAX_SCAN_WAIT, scan_wait * 2)
                    capture = loopback.capture(current)
                    detector = BeatDetector(capture.rate)
                    self.device_name = current.name
                    buf = _silence()
                    last_sound = time.monotonic()
        finally:
            if capture is not None:
                capture.close()
