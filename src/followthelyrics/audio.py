import threading
import time
from collections import deque

import numpy as np

try:
    import pyaudiowpatch as pyaudio
except Exception:
    pyaudio = None

BLOCK = 1024


class BeatDetector:

    def __init__(self, rate):
        self.rate = rate
        freqs = np.fft.rfftfreq(BLOCK, 1 / rate)
        self.band = (freqs >= 40) & (freqs <= 150)
        self.window = np.hanning(BLOCK).astype(np.float32)
        self.prev = 0.0
        self.flux_hist = deque(maxlen=int(1.5 * rate / BLOCK))
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


class _Capture:

    def __init__(self, pa, dev):
        self.dev = dev
        self.ch = max(1, min(2, int(dev["maxInputChannels"])))
        self.rate = int(dev["defaultSampleRate"])
        self.stream = pa.open(format=pyaudio.paFloat32, channels=self.ch, rate=self.rate, input=True,
                              input_device_index=dev["index"], frames_per_buffer=BLOCK)

    def read(self):
        try:
            avail = self.stream.get_read_available()
            if avail <= 0:
                return np.zeros(0, dtype=np.float32)
            a = np.frombuffer(self.stream.read(avail, exception_on_overflow=False), dtype=np.float32)
        except Exception:
            return np.zeros(0, dtype=np.float32)
        if self.ch == 2:
            a = a[: a.size - a.size % 2].reshape(-1, 2).mean(axis=1)
        return a

    def close(self):
        try:
            self.stream.stop_stream()
            self.stream.close()
        except Exception:
            pass


class AudioBeats:

    def __init__(self, on_beat):
        self.on_beat = on_beat
        self.enabled = pyaudio is not None
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

    def _measure(self, pa, dev, seconds=0.3):
        try:
            cap = _Capture(pa, dev)
        except Exception:
            return 0.0
        total, n = 0.0, 0
        end = time.monotonic() + seconds
        while time.monotonic() < end and not self._stop.is_set():
            a = cap.read()
            total += float(np.abs(a).sum())
            n += a.size
            time.sleep(0.02)
        cap.close()
        return total / n if n else 0.0

    def _run(self):
        try:
            pa = pyaudio.PyAudio()
            wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
            default_name = pa.get_device_info_by_index(wasapi["defaultOutputDevice"])["name"]
            devices = list(pa.get_loopback_device_info_generator())
        except Exception:
            self.enabled = False
            return
        if not devices:
            self.enabled = False
            return
        current = next((d for d in devices if d["name"].startswith(default_name)), devices[0])
        cap = None
        try:
            cap = _Capture(pa, current)
            det = BeatDetector(cap.rate)
            self.device_name = current["name"]
            buf = np.zeros(0, dtype=np.float32)
            last_sound = time.monotonic()
            last_check = last_scan = 0.0
            scan_wait = 8.0
            while not self._stop.is_set():
                a = cap.read()
                now = time.monotonic()
                if a.size:
                    if float(np.abs(a).mean()) > 0.002:
                        last_sound = now
                        scan_wait = 8.0
                    buf = np.concatenate([buf, a])
                    while buf.size >= BLOCK:
                        block, buf = buf[:BLOCK], buf[BLOCK:]
                        k = det.feed(block, now)
                        if k > 0:
                            try:
                                self.on_beat(k)
                            except Exception:
                                pass
                else:
                    time.sleep(0.01)
                if now - last_check < 0.5:
                    continue
                last_check = now
                if now - last_sound > 3.0 and self.music_playing and now - last_scan > scan_wait:
                    last_scan = now
                    cap.close()
                    best, best_lvl = current, 0.0
                    for d in devices:
                        if self._stop.is_set():
                            break
                        lvl = self._measure(pa, d)
                        if lvl > best_lvl:
                            best, best_lvl = d, lvl
                    if best_lvl > 0.002:
                        current = best
                        scan_wait = 8.0
                    else:
                        scan_wait = min(120.0, scan_wait * 2)
                    cap = _Capture(pa, current)
                    det = BeatDetector(cap.rate)
                    self.device_name = current["name"]
                    buf = np.zeros(0, dtype=np.float32)
                    last_sound = time.monotonic()
        except Exception:
            self.enabled = False
        finally:
            if cap:
                cap.close()
            try:
                pa.terminate()
            except Exception:
                pass
