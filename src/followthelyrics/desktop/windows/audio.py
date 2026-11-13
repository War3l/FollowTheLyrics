import logging
import sys

import numpy as np
import pyaudiowpatch as pyaudio

from followthelyrics.desktop import ports

assert sys.platform == "win32"

logger = logging.getLogger(__name__)

FRAMES_PER_BUFFER = 1024


def _silence():
    return np.zeros(0, dtype=np.float32)


class WasapiCapture:
    def __init__(self, pa, device):
        self._channels = device.channels
        self._rate = device.rate
        self._stream = pa.open(
            format=pyaudio.paFloat32,
            channels=self._channels,
            rate=self._rate,
            input=True,
            input_device_index=device.index,
            frames_per_buffer=FRAMES_PER_BUFFER,
        )

    @property
    def rate(self):
        return self._rate

    def read(self):
        try:
            available = self._stream.get_read_available()
            if available <= 0:
                return _silence()
            samples = np.frombuffer(
                self._stream.read(available, exception_on_overflow=False),
                dtype=np.float32,
            )
        except Exception:
            logger.debug("read failed", exc_info=True)
            return _silence()
        if self._channels == 2:
            samples = (
                samples[: samples.size - samples.size % 2]
                .reshape(-1, 2)
                .mean(axis=1)
            )
        return samples

    def close(self):
        try:
            self._stream.stop_stream()
            self._stream.close()
        except Exception:
            logger.debug("close failed", exc_info=True)


class WasapiLoopback:
    def __init__(self):
        self._pa = pyaudio.PyAudio()

    def devices(self):
        return [
            ports.AudioDevice(
                index=info["index"],
                name=info["name"],
                channels=max(1, min(2, int(info["maxInputChannels"]))),
                rate=int(info["defaultSampleRate"]),
            )
            for info in self._pa.get_loopback_device_info_generator()
        ]

    def preferred(self, devices):
        wasapi = self._pa.get_host_api_info_by_type(pyaudio.paWASAPI)
        default_name = self._pa.get_device_info_by_index(
            wasapi["defaultOutputDevice"]
        )["name"]
        return next(
            (d for d in devices if d.name.startswith(default_name)),
            devices[0],
        )

    def capture(self, device):
        return WasapiCapture(self._pa, device)

    def close(self):
        try:
            self._pa.terminate()
        except Exception:
            logger.debug("close failed", exc_info=True)
