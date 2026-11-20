import math

from PyQt6.QtCore import QPointF
from PyQt6.QtCore import QRectF
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtGui import QPainter
from PyQt6.QtGui import QPainterPath
from PyQt6.QtGui import QPen
from PyQt6.QtGui import QPolygonF

W, H = 20.0, 14.0
EDGE = QColor(128, 128, 134, 150)


def _bands(p, r, colors, vertical=False, weights=None):
    weights = weights or [1] * len(colors)
    total, pos = sum(weights), 0.0
    for color, w in zip(colors, weights, strict=True):
        if vertical:
            span = r.width() * w / total
            band = QRectF(r.left() + pos, r.top(), span, r.height())
        else:
            span = r.height() * w / total
            band = QRectF(r.left(), r.top() + pos, r.width(), span)
        p.fillRect(band.adjusted(0, 0, 0.5, 0.5), QColor(color))
        pos += span


def _star(p, c, radius, color):
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rad = radius if i % 2 == 0 else radius * 0.4
        pts.append(c + QPointF(rad * math.cos(a), rad * math.sin(a)))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color))
    p.drawPolygon(QPolygonF(pts))


def _uk(p, r):
    p.fillRect(r, QColor("#012169"))
    h = r.height()
    diag = (
        (r.topLeft(), r.bottomRight()),
        (r.bottomLeft(), r.topRight()),
    )
    for color, width in (("#ffffff", h * 0.2), ("#C8102E", h * 0.07)):
        p.setPen(QPen(QColor(color), width, cap=Qt.PenCapStyle.FlatCap))
        for a, b in diag:
            p.drawLine(a, b)
    c = r.center()
    for color, width in (("#ffffff", h / 3), ("#C8102E", h / 5)):
        p.fillRect(
            QRectF(r.left(), c.y() - width / 2, r.width(), width), QColor(color)
        )
        p.fillRect(
            QRectF(c.x() - width / 2, r.top(), width, r.height()), QColor(color)
        )


def _china(p, r):
    p.fillRect(r, QColor("#DE2910"))
    u = r.height() / 20
    o = r.topLeft()
    _star(p, QPointF(o.x() + 5 * u, o.y() + 5 * u), 3.4 * u, "#FFDE00")
    for x, y in ((10, 2), (12, 4), (12, 7), (10, 9)):
        _star(p, QPointF(o.x() + x * u, o.y() + y * u), 1.3 * u, "#FFDE00")


def _japan(p, r):
    p.fillRect(r, QColor("#ffffff"))
    d = r.height() * 0.6
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#BC002D"))
    p.drawEllipse(QRectF(r.center().x() - d / 2, r.center().y() - d / 2, d, d))


def _france(p, r):
    _bands(p, r, ("#0055A4", "#ffffff", "#EF4135"), vertical=True)


def _spain(p, r):
    _bands(p, r, ("#AA151B", "#F1BF00", "#AA151B"), weights=(1, 2, 1))


def _russia(p, r):
    _bands(p, r, ("#ffffff", "#0039A6", "#D52B1E"))


PAINTERS = {
    "en": _uk,
    "fr": _france,
    "es": _spain,
    "zh": _china,
    "ru": _russia,
    "ja": _japan,
}


def paint(p: QPainter, lang: str, r: QRectF, opacity: float = 1.0) -> None:
    painter = PAINTERS.get(lang)
    if painter is None:
        return
    p.save()
    p.setOpacity(opacity)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    clip = QPainterPath()
    clip.addRoundedRect(r, 2.5, 2.5)
    p.setClipPath(clip)
    painter(p, r)
    p.setClipping(False)
    p.setPen(QPen(EDGE, 1))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), 2.5, 2.5)
    p.restore()
