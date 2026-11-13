import logging

import numpy as np
import soundcard

from followthelyrics.desktop import ports

logger = logging.getLogger(__name__)

SAMPLE_RATE = 48_000
BLOCK_FRAMES = 1024


def _silence():
    return np.zeros(0, dtype=np.float32)


class MonitorCapture:
    def __init__(self, microphone):
        self._recorder = microphone.recorder(
            samplerate=SAMPLE_RATE, blocksize=BLOCK_FRAMES
        )
        self._recorder.__enter__()

    @property
    def rate(self):
        return SAMPLE_RATE

    def read(self):
        try:
            frames = self._recorder.record(numframes=None)
        except Exception:
            logger.debug("read failed", exc_info=True)
            return _silence()
        samples = np.asarray(frames, dtype=np.float32)
        if samples.ndim == 2:
            samples = samples.mean(axis=1)
        return samples.astype(np.float32, copy=False)

    def close(self):
        try:
            self._recorder.__exit__(None, None, None)
        except Exception:
            logger.debug("close failed", exc_info=True)


class PulseLoopback:
    def __init__(self):
        self._monitors = [
            m
            for m in soundcard.all_microphones(include_loopback=True)
            if m.isloopback
        ]

    def devices(self):
        return [
            ports.AudioDevice(
                index=index,
                name=monitor.name,
                channels=max(1, min(2, int(monitor.channels))),
                rate=SAMPLE_RATE,
            )
            for index, monitor in enumerate(self._monitors)
        ]

    def preferred(self, devices):
        try:
            speaker = soundcard.default_speaker().name
        except Exception:
            logger.debug("preferred failed", exc_info=True)
            return devices[0]
        return next((d for d in devices if speaker in d.name), devices[0])

    def capture(self, device):
        return MonitorCapture(self._monitors[device.index])

    def close(self):
        pass
