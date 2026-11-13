import logging

import numpy as np
from PyQt6.QtCore import QRectF
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtGui import QImage

from followthelyrics import fonts
from followthelyrics.overlay import animation
from followthelyrics.overlay import colors

logger = logging.getLogger(__name__)

NEUTRAL_PALETTE = ["#FFFFFF", "#E8ECF4", "#CBD3E3"]

WHITE_PALETTE = ["#FFFFFF", "#F4F6FB", "#E6EAF3"]


def area(r: QRectF):
    return r.width() * r.height() if r.isValid() else 0.0


def mix(c1: QColor, c2: QColor, k):
    return QColor(
        int(animation.lerp(c1.red(), c2.red(), k)),
        int(animation.lerp(c1.green(), c2.green(), k)),
        int(animation.lerp(c1.blue(), c2.blue(), k)),
    )


def _box_blur(a, r, axis):
    if r < 1:
        return a
    pad = [(0, 0), (0, 0)]
    pad[axis] = (r + 1, r)
    c = np.cumsum(np.pad(a, pad), axis=axis)
    n = 2 * r + 1
    if axis == 1:
        return (c[:, n:] - c[:, :-n]) / n
    return (c[n:, :] - c[:-n, :]) / n


def gaussian_blur(a, sigma):
    r = max(1, round(sigma * 0.95))
    for _ in range(3):
        a = _box_blur(a, r, 1)
        a = _box_blur(a, r, 0)
    return a


_FAMILIES = None


def family_or_default(name):
    global _FAMILIES
    if _FAMILIES is None:
        _FAMILIES = fonts.families()
    if name in _FAMILIES:
        return name
    return "Segoe UI" if "Segoe UI" in _FAMILIES else fonts.BUNDLED


def image_rows(img: QImage) -> np.ndarray:
    bits = img.constBits()
    if bits is None:
        return np.zeros((0, 0), dtype=np.uint8)
    raw = np.frombuffer(bits.asstring(img.sizeInBytes()), dtype=np.uint8)
    return raw.reshape(img.height(), img.bytesPerLine())


def palette_from_cover(data):
    img = QImage.fromData(data) if not isinstance(data, QImage) else data
    if img.isNull():
        return None
    img = img.convertToFormat(QImage.Format.Format_RGBA8888).scaled(
        64,
        64,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    try:
        arr = (
            image_rows(img)[:, : img.width() * 4]
            .reshape(img.height(), img.width(), 4)[:, :, :3]
            .copy()
        )
        pal = colors.palette_rgb(arr)
    except Exception:
        logger.debug("palette_from_cover failed", exc_info=True)
        pal = None
    return [QColor(*c) for c in pal] if pal else None
