import logging
import math
import time
from typing import TYPE_CHECKING

from PyQt6.QtCore import QEasingCurve
from PyQt6.QtCore import QPointF
from PyQt6.QtCore import QRectF
from PyQt6.QtCore import QSize
from PyQt6.QtCore import Qt
from PyQt6.QtCore import QTimer
from PyQt6.QtCore import QVariantAnimation
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QBrush
from PyQt6.QtGui import QColor
from PyQt6.QtGui import QFont
from PyQt6.QtGui import QFontMetricsF
from PyQt6.QtGui import QIcon
from PyQt6.QtGui import QLinearGradient
from PyQt6.QtGui import QPainter
from PyQt6.QtGui import QPainterPath
from PyQt6.QtGui import QPen
from PyQt6.QtGui import QPixmap
from PyQt6.QtGui import QRadialGradient
from PyQt6.QtWidgets import QAbstractButton
from PyQt6.QtWidgets import QSizePolicy
from PyQt6.QtWidgets import QWidget

from followthelyrics.system import hotkeys

logger = logging.getLogger(__name__)

DEFAULT_ACCENT = QColor("#8B7CFF")
UI = {"accent": QColor(DEFAULT_ACCENT)}

BG = "#0b0c11"
CARD = "#0fffffff"
CARD_BORDER = "#26ffffff"
FIELD = "#16ffffff"
SOLID_CARD = "#14161e"
SOLID_BORDER = "#222533"
SOLID_FIELD = "#1b1e28"
BRAND = ("#5EE7FF", "#8B7CFF", "#FF6FB5")
TEXT = "#eceef4"
DIM = "#8b91a3"


def mix(a, b, t):
    a, b = QColor(a), QColor(b)
    t = max(0.0, min(1.0, t))
    return QColor(
        int(a.red() + (b.red() - a.red()) * t),
        int(a.green() + (b.green() - a.green()) * t),
        int(a.blue() + (b.blue() - a.blue()) * t),
        int(a.alpha() + (b.alpha() - a.alpha()) * t),
    )


def alpha(c, a):
    c = QColor(c)
    c.setAlpha(int(a))
    return c


def qss(c):
    c = QColor(c)
    return f"rgba({c.red()},{c.green()},{c.blue()},{c.alphaF():.3f})"


def ui_font(px, weight=QFont.Weight.Normal, family="Segoe UI Variable Text"):
    f = QFont(family)
    f.setPixelSize(px)
    f.setWeight(weight)
    return f


def fmt_time(t):
    t = max(0, int(t))
    return f"{t // 60}:{t % 60:02d}"


def make_anim(parent, setter, ms=180, curve=QEasingCurve.Type.OutCubic):
    a = QVariantAnimation(parent)
    a.setDuration(ms)
    a.setEasingCurve(curve)
    a.valueChanged.connect(lambda v: setter(float(v)))
    return a


def run_anim(a, start, end):
    a.stop()
    a.setStartValue(float(start))
    a.setEndValue(float(end))
    a.start()


def ease_out_back(t):
    t = max(0.0, min(1.0, t)) - 1.0
    return 1.0 + 2.70158 * t**3 + 1.70158 * t**2


if TYPE_CHECKING:
    _HoverBase = QWidget
else:
    _HoverBase = object


class Hover(_HoverBase):
    def init_hover(self):
        self._hover = 0.0
        self._hover_anim = make_anim(self, self._set_hover, 150)

    def _set_hover(self, v):
        self._hover = v
        self.update()

    def enterEvent(self, e):
        run_anim(self._hover_anim, self._hover, 1.0)
        super().enterEvent(e)

    def leaveEvent(self, e):
        run_anim(self._hover_anim, self._hover, 0.0)
        super().leaveEvent(e)


def logo_path():
    path = QPainterPath()
    for pts in (((16, 10), (16, 27), (48, 27)), ((16, 54), (16, 37), (48, 37))):
        path.moveTo(*pts[0])
        path.lineTo(*pts[1])
        path.lineTo(*pts[2])
        path.closeSubpath()
    return path


def draw_logo(p, rect, brush):
    p.save()
    p.translate(rect.left(), rect.top())
    p.scale(rect.width() / 64.0, rect.height() / 64.0)
    pen = QPen(brush, 4)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(brush)
    p.drawPath(logo_path())
    p.restore()


def icon_pixmap(size=64):
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = size / 64.0
    p.scale(s, s)
    g = QLinearGradient(QPointF(10, 8), QPointF(54, 56))
    g.setColorAt(0.0, QColor("#5EE7FF"))
    g.setColorAt(0.5, QColor("#8B7CFF"))
    g.setColorAt(1.0, QColor("#FF6FB5"))
    if size < 32:
        draw_logo(p, QRectF(-8.5, -9.6, 83.2, 83.2), QBrush(g))
    else:
        body = QRectF(2, 2, 60, 60)
        tile = QLinearGradient(QPointF(2, 2), QPointF(62, 62))
        tile.setColorAt(0.0, QColor("#1d1a33"))
        tile.setColorAt(1.0, QColor("#0b0a14"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(tile))
        p.drawRoundedRect(body, 15, 15)
        shine = QRadialGradient(QPointF(16, 6), 46)
        shine.setColorAt(0, QColor(255, 255, 255, 38))
        shine.setColorAt(1, QColor(255, 255, 255, 0))
        p.setBrush(QBrush(shine))
        p.drawRoundedRect(body, 15, 15)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 46), 1))
        p.drawRoundedRect(body.adjusted(0.5, 0.5, -0.5, -0.5), 14.5, 14.5)
        draw_logo(p, QRectF(11.5, 10, 44, 44), QBrush(g))
    p.end()
    return pm


def make_icon():
    ic = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(icon_pixmap(size))
    return ic


def draw_icon(p, name, rect, color, width=1.7):
    p.save()
    p.translate(rect.left(), rect.top())
    p.scale(rect.width() / 20.0, rect.height() / 20.0)
    pen = QPen(QColor(color), width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    fill = QBrush(QColor(color))
    if name == "home":
        path = QPainterPath(QPointF(2.5, 9.5))
        path.lineTo(10, 3)
        path.lineTo(17.5, 9.5)
        p.drawPath(path)
        path = QPainterPath(QPointF(4.5, 8.5))
        path.lineTo(4.5, 16.5)
        path.lineTo(15.5, 16.5)
        path.lineTo(15.5, 8.5)
        p.drawPath(path)
        p.drawLine(QPointF(10, 16.5), QPointF(10, 12.5))
    elif name == "screen":
        p.drawRoundedRect(QRectF(2, 3.5, 16, 11), 2.2, 2.2)
        p.drawLine(QPointF(7, 17.5), QPointF(13, 17.5))
        p.drawLine(QPointF(5, 7.5), QPointF(9, 7.5))
        p.drawLine(QPointF(5, 10.8), QPointF(12.5, 10.8))
    elif name == "style":

        def star(cx, cy, r):
            s = QPainterPath(QPointF(cx, cy - r))
            s.quadTo(QPointF(cx, cy), QPointF(cx + r, cy))
            s.quadTo(QPointF(cx, cy), QPointF(cx, cy + r))
            s.quadTo(QPointF(cx, cy), QPointF(cx - r, cy))
            s.quadTo(QPointF(cx, cy), QPointF(cx, cy - r))
            p.drawPath(s)

        star(8.2, 11, 6.2)
        star(15.2, 5, 3)
    elif name == "music":
        p.drawLine(QPointF(8, 14.5), QPointF(8, 4.8))
        p.drawLine(QPointF(8, 4.8), QPointF(16, 3.2))
        p.drawLine(QPointF(16, 3.2), QPointF(16, 12.8))
        p.setBrush(fill)
        p.drawEllipse(QPointF(5.9, 14.6), 2.1, 1.8)
        p.drawEllipse(QPointF(13.9, 12.9), 2.1, 1.8)
    elif name == "game":
        p.drawRoundedRect(QRectF(1.8, 5.5, 16.4, 9.6), 4.6, 4.6)
        p.drawLine(QPointF(5, 10.3), QPointF(8.2, 10.3))
        p.drawLine(QPointF(6.6, 8.7), QPointF(6.6, 11.9))
        p.setBrush(fill)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(12.6, 9.2), 1.05, 1.05)
        p.drawEllipse(QPointF(14.8, 11.4), 1.05, 1.05)
    elif name == "keys":
        p.drawRoundedRect(QRectF(1.8, 4.8, 16.4, 10.6), 2.6, 2.6)
        p.drawLine(QPointF(6.5, 12.3), QPointF(13.5, 12.3))
        p.setBrush(fill)
        p.setPen(Qt.PenStyle.NoPen)
        for x in (5.4, 8.5, 11.5, 14.6):
            p.drawEllipse(QPointF(x, 8.4), 0.95, 0.95)
    elif name == "sliders":
        for y, x in ((5, 7), (10, 13), (15, 8.5)):
            p.drawLine(QPointF(2.8, y), QPointF(x - 2.6, y))
            p.drawLine(QPointF(x + 2.6, y), QPointF(17.2, y))
            p.drawEllipse(QPointF(x, y), 2, 2)
    elif name == "chevron":
        path = QPainterPath(QPointF(7.5, 5))
        path.lineTo(12.5, 10)
        path.lineTo(7.5, 15)
        p.drawPath(path)
    p.restore()


def draw_keycaps(p, names, x, cy, dim=False):
    font = ui_font(12, QFont.Weight.Bold)
    fm = QFontMetricsF(font)
    p.setFont(font)
    for i, name in enumerate(names):
        if i:
            p.setPen(QColor(DIM))
            p.drawText(
                QRectF(x, cy - 12, 14, 24), Qt.AlignmentFlag.AlignCenter, "+"
            )
            x += 14
        w = max(26.0, fm.horizontalAdvance(name) + 16)
        r = QRectF(x, cy - 12, w, 24)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#0c0d12"))
        p.drawRoundedRect(r.translated(0, 2), 6, 6)
        p.setBrush(QColor("#2a2e3c"))
        p.setPen(QPen(QColor("#3a3f51"), 1))
        p.drawRoundedRect(r, 6, 6)
        p.setPen(QColor(DIM) if dim else QColor(TEXT))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, name)
        x += w
    return x


class Toggle(QAbstractButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(46, 26)
        self._pos = 0.0
        self._anim = make_anim(self, self._set_pos, 170)
        self.toggled.connect(self._go)

    def _set_pos(self, v):
        self._pos = v
        self.update()

    def _go(self, on):
        if self.isVisible():
            run_anim(self._anim, self._pos, 1.0 if on else 0.0)
        else:
            self._anim.stop()
            self._set_pos(1.0 if on else 0.0)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = self._pos
        p.setPen(Qt.PenStyle.NoPen)
        track = mix("#30ffffff", UI["accent"], t)
        if not self.isEnabled():
            track = mix(track, BG, 0.6)
        p.setBrush(track)
        p.drawRoundedRect(QRectF(0, 0, 46, 26), 13, 13)
        p.setBrush(mix("#cfd3de", "#ffffff", t))
        p.drawEllipse(QRectF(3 + 20 * t, 3, 20, 20))


class Segmented(QWidget):
    changed = pyqtSignal(str)
    H, PAD = 38, 3

    def __init__(self, options: dict, parent=None):
        super().__init__(parent)
        self.keys = list(options)
        self.labels = [options[k] for k in self.keys]
        self.font_ = ui_font(13, QFont.Weight.DemiBold)
        fm = QFontMetricsF(self.font_)
        self.widths = [fm.horizontalAdvance(t) + 30 for t in self.labels]
        self.index = 0
        self._x = 0.0
        self._hover_i = -1
        self._anim = make_anim(self, self._set_x, 220)
        self.setFixedSize(int(sum(self.widths) + 2 * self.PAD), self.H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)

    def _set_x(self, v):
        self._x = v
        self.update()

    def seg_rect(self, i):
        return QRectF(
            self.PAD + sum(self.widths[:i]),
            self.PAD,
            self.widths[i],
            self.H - 2 * self.PAD,
        )

    def set_value(self, key):
        if key not in self.keys:
            return
        i = self.keys.index(key)
        if i == self.index and self._x == i:
            return
        self.index = i
        if self.isVisible():
            run_anim(self._anim, self._x, i)
        else:
            self._anim.stop()
            self._set_x(float(i))

    def _at(self, x):
        for i in range(len(self.keys)):
            if self.seg_rect(i).left() <= x <= self.seg_rect(i).right():
                return i
        return -1

    def mouseMoveEvent(self, e):
        i = self._at(e.position().x())
        if i != self._hover_i:
            self._hover_i = i
            self.update()

    def leaveEvent(self, e):
        self._hover_i = -1
        self.update()

    def mousePressEvent(self, e):
        i = self._at(e.position().x())
        if i >= 0 and i != self.index and self.isEnabled():
            self.set_value(self.keys[i])
            self.changed.emit(self.keys[i])

    def changeEvent(self, e):
        super().changeEvent(e)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        on = self.isEnabled()
        acc = UI["accent"]
        p.setPen(QPen(QColor(CARD_BORDER), 1))
        p.setBrush(QColor(FIELD))
        p.drawRoundedRect(
            QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 11, 11
        )
        lo = max(0, min(len(self.keys) - 1, math.floor(self._x)))
        hi = min(len(self.keys) - 1, lo + 1)
        f = self._x - lo
        a, b = self.seg_rect(lo), self.seg_rect(hi)
        pill = QRectF(
            a.left() + (b.left() - a.left()) * f,
            a.top(),
            a.width() + (b.width() - a.width()) * f,
            a.height(),
        )
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(acc if on else mix(FIELD, acc, 0.28))
        p.drawRoundedRect(pill, 8, 8)
        p.setFont(self.font_)
        for i, label in enumerate(self.labels):
            near = max(0.0, 1.0 - abs(self._x - i))
            if on:
                col = mix(
                    "#c2c6d2" if i != self._hover_i else "#ffffff", BG, near
                )
            else:
                col = QColor("#565b6b")
            p.setPen(col)
            p.drawText(self.seg_rect(i), Qt.AlignmentFlag.AlignCenter, label)


class SideNav(QWidget):
    changed = pyqtSignal(str)
    ITEM_H, GAP = 44, 4

    def __init__(self, items, parent=None):
        super().__init__(parent)
        self.items = list(items)
        self.index = 0
        self._y = 0.0
        self._hover_i = -1
        self.badges = set()
        self._anim = make_anim(self, self._set_y, 240)
        self.setFixedHeight(len(self.items) * (self.ITEM_H + self.GAP))
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _set_y(self, v):
        self._y = v
        self.update()

    def key(self):
        return self.items[self.index][0]

    def select(self, key, emit=True):
        for i, (k, _t, _ic) in enumerate(self.items):
            if k == key:
                if i != self.index:
                    self.index = i
                    if self.isVisible():
                        run_anim(self._anim, self._y, i)
                    else:
                        self._set_y(float(i))
                    if emit:
                        self.changed.emit(k)
                return

    def set_badge(self, key, on):
        (self.badges.add if on else self.badges.discard)(key)
        self.update()

    def _at(self, y):
        i = int(y // (self.ITEM_H + self.GAP))
        return i if 0 <= i < len(self.items) else -1

    def mouseMoveEvent(self, e):
        i = self._at(e.position().y())
        if i != self._hover_i:
            self._hover_i = i
            self.update()

    def leaveEvent(self, e):
        self._hover_i = -1
        self.update()

    def mousePressEvent(self, e):
        i = self._at(e.position().y())
        if i >= 0:
            self.select(self.items[i][0])

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        acc = UI["accent"]
        step = self.ITEM_H + self.GAP
        w = self.width()
        if 0 <= self._hover_i != self.index:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 12))
            p.drawRoundedRect(
                QRectF(0, self._hover_i * step, w, self.ITEM_H), 11, 11
            )
        pill = QRectF(0, self._y * step, w, self.ITEM_H)
        p.setPen(QPen(alpha(acc, 90), 1))
        p.setBrush(alpha(acc, 38))
        p.drawRoundedRect(pill.adjusted(0.5, 0.5, -0.5, -0.5), 11, 11)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(acc)
        p.drawRoundedRect(
            QRectF(0, pill.top() + 11, 3.5, self.ITEM_H - 22), 1.75, 1.75
        )
        for i, (key, text, icon) in enumerate(self.items):
            near = max(0.0, 1.0 - abs(self._y - i))
            base = (
                QColor("#d7dae3") if i == self._hover_i else QColor("#9aa0b1")
            )
            col = mix(base, "#ffffff", near)
            y = i * step
            draw_icon(p, icon, QRectF(15, y + 12, 20, 20), mix(base, acc, near))
            p.setPen(col)
            p.setFont(
                ui_font(
                    14,
                    QFont.Weight.Bold
                    if i == self.index
                    else QFont.Weight.DemiBold,
                )
            )
            p.drawText(
                QRectF(48, y, w - 60, self.ITEM_H),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                text,
            )
            if key in self.badges:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(acc)
                p.drawEllipse(QPointF(w - 16, y + self.ITEM_H / 2), 4, 4)


class CoverView(QWidget):
    def __init__(self, size, radius=18, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.radius = radius
        self.img = None
        self.old = None
        self._fade = 1.0
        self._anim = make_anim(self, self._set_fade, 420)

    def _set_fade(self, v):
        self._fade = v
        self.update()

    def set_image(self, img):
        self.old = self.img
        self.img = img
        if self.isVisible():
            run_anim(self._anim, 0.0, 1.0)
        else:
            self._set_fade(1.0)

    def _draw(self, p, r, img):
        if img is not None and not img.isNull():
            p.drawImage(r, img)
            return
        acc = UI["accent"]
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, alpha(acc, 130))
        g.setColorAt(1, alpha(acc, 10))
        p.fillRect(r, QColor("#161822"))
        p.fillRect(r, QBrush(g))
        p.setPen(QColor(255, 255, 255, 170))
        p.setFont(
            ui_font(int(r.width() * 0.32), QFont.Weight.Bold, "Segoe UI Symbol")
        )
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, "♪")

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = QRectF(self.rect())
        path = QPainterPath()
        path.addRoundedRect(r, self.radius, self.radius)
        p.setClipPath(path)
        if self._fade < 1.0:
            self._draw(p, r, self.old)
            p.setOpacity(self._fade)
        self._draw(p, r, self.img)


class Equalizer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(20, 16)
        self.playing = False

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(UI["accent"] if self.playing else QColor(DIM))
        t = time.monotonic()
        for i in range(4):
            h = 4.0
            if self.playing:
                h = (
                    4
                    + 11
                    * (0.5 + 0.5 * math.sin(t * (5.2 + i * 1.7) + i * 1.9))
                    ** 1.4
                )
            p.drawRoundedRect(QRectF(i * 5.2, 16 - h, 3.2, h), 1.6, 1.6)


class ProgressView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(34)
        self.elapsed, self.duration = 0.0, 0.0

    def set_values(self, pos, dur):
        self.elapsed, self.duration = pos, dur
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#28ffffff"))
        p.drawRoundedRect(QRectF(0, 6, w, 5), 2.5, 2.5)
        if self.duration > 0:
            frac = max(0.0, min(1.0, self.elapsed / self.duration))
            p.setBrush(UI["accent"])
            p.drawRoundedRect(QRectF(0, 6, w * frac, 5), 2.5, 2.5)
            p.setBrush(QColor("white"))
            p.drawEllipse(QPointF(max(5.0, min(w - 5.0, w * frac)), 8.5), 5, 5)
        p.setPen(QColor(DIM))
        p.setFont(ui_font(11))
        p.drawText(
            QRectF(0, 16, w / 2, 18),
            Qt.AlignmentFlag.AlignLeft,
            fmt_time(self.elapsed) if self.duration else "",
        )
        p.drawText(
            QRectF(w / 2, 16, w / 2, 18),
            Qt.AlignmentFlag.AlignRight,
            fmt_time(self.duration) if self.duration else "",
        )


class MiniPlayer(Hover, QAbstractButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_hover()
        self.setFixedHeight(60)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.img = None
        self.title, self.artist = "", ""

    def set_track(self, title, artist, img):
        if (title, artist) != (self.title, self.artist) or img is not self.img:
            self.title, self.artist, self.img = title, artist, img
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(mix(CARD_BORDER, UI["accent"], self._hover * 0.6), 1))
        p.setBrush(mix(CARD, FIELD, self._hover))
        p.drawRoundedRect(r, 13, 13)
        cov = QRectF(8, 8, 44, 44)
        path = QPainterPath()
        path.addRoundedRect(cov, 9, 9)
        p.save()
        p.setClipPath(path)
        if self.img is not None and not self.img.isNull():
            p.drawImage(cov, self.img)
        else:
            p.fillRect(cov, alpha(UI["accent"], 70))
            p.setPen(QColor(255, 255, 255, 190))
            p.setFont(ui_font(18, QFont.Weight.Bold, "Segoe UI Symbol"))
            p.drawText(cov, Qt.AlignmentFlag.AlignCenter, "♪")
        p.restore()
        tw = self.width() - 72
        f1 = ui_font(13, QFont.Weight.Bold)
        p.setFont(f1)
        p.setPen(QColor(TEXT))
        p.drawText(
            QRectF(62, 11, tw, 18),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            QFontMetricsF(f1).elidedText(
                self.title, Qt.TextElideMode.ElideRight, tw
            ),
        )
        f2 = ui_font(12)
        p.setFont(f2)
        p.setPen(QColor(DIM))
        p.drawText(
            QRectF(62, 31, tw, 18),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            QFontMetricsF(f2).elidedText(
                self.artist, Qt.TextElideMode.ElideRight, tw
            ),
        )


class ModeCard(Hover, QAbstractButton):
    def __init__(self, key, title, desc, parent=None):
        super().__init__(parent)
        self.init_hover()
        self.key, self.title, self.desc = key, title, desc
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(170, 196)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._sel = 0.0
        self._sel_anim = make_anim(self, self._set_sel, 200)
        self.toggled.connect(
            lambda on: (
                run_anim(self._sel_anim, self._sel, 1.0 if on else 0.0)
                if self.isVisible()
                else self._set_sel(1.0 if on else 0.0)
            )
        )

    def _set_sel(self, v):
        self._sel = v
        self.update()

    def alive(self):
        return self.isChecked() or self.underMouse()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        acc = UI["accent"]
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(
            QPen(
                mix(mix(CARD_BORDER, "#58ffffff", self._hover), acc, self._sel),
                1 + self._sel,
            )
        )
        p.setBrush(
            mix(mix(FIELD, "#24ffffff", self._hover), acc, 0.16 * self._sel)
        )
        p.drawRoundedRect(r, 15, 15)

        scr = QRectF(r.left() + 12, r.top() + 12, r.width() - 24, 96)
        p.setPen(QPen(QColor("#2b2f3c"), 1))
        p.setBrush(QColor("#090a0e"))
        p.drawRoundedRect(scr, 9, 9)
        p.setPen(Qt.PenStyle.NoPen)
        dim = QColor(255, 255, 255, 62)
        w = scr.width()
        now = time.monotonic() if self.alive() else 1.95
        p.save()
        p.setClipRect(scr.adjusted(2, 2, -2, -2))

        def bar(x, y, length, col, h=6.0, rot=0.0):
            if length <= 0:
                return
            p.save()
            p.translate(scr.left() + x, scr.top() + y)
            p.rotate(rot)
            p.setBrush(col)
            p.drawRoundedRect(QRectF(0, -h / 2, length, h), h / 2, h / 2)
            p.restore()

        if self.key == "classic":
            t = (now % 3.0) / 3.0
            slide = max(0.0, (t - 0.86) / 0.14) * 15
            bar(12, 18 - slide, w * 0.32, alpha(dim, 62 * (1 - slide / 15)), 5)
            bar(12, 33 - slide, w * 0.52, dim, 7)
            bar(12, 33 - slide, w * 0.52 * min(1.0, t / 0.8), acc, 7)
            bar(12, 48 - slide, w * 0.40, alpha(dim, 34), 5)
            bar(12, 63 - slide, w * 0.30, alpha(dim, 34 * slide / 15), 5)
        elif self.key == "edit":
            slots = (
                (12, 22, 0.36, -5),
                (w * 0.52, 34, 0.38, 4),
                (w * 0.2, 66, 0.44, -2),
                (w * 0.44, 78, 0.34, 3),
            )
            k = int(now / 1.05) % len(slots)
            local = (now % 1.05) / 1.05
            x, y, length, rot = slots[k]
            grow = ease_out_back(local * 3.5)
            fade = 1.0 if local < 0.82 else max(0.0, (1 - local) / 0.18)
            bar(x, y, w * length * grow, alpha(dim, 62 * fade), 8, rot)
            bar(
                x,
                y,
                w * length * grow * min(1.0, local / 0.7),
                alpha(acc, 255 * fade),
                8,
                rot,
            )
        else:
            t = (now % 2.8) / 2.8
            steps = 11
            shown = min(steps, int(t * 1.3 * steps))
            length = w * 0.5 * shown / steps
            bar(w * 0.22, 26, w * 0.34, alpha(dim, 40), 5)
            bar(w * 0.22, 46, length, acc, 7)
            if int(now * 2.6) % 2 == 0 or shown < steps:
                p.setBrush(QColor("white"))
                p.drawRoundedRect(
                    QRectF(
                        scr.left() + w * 0.22 + length + 3,
                        scr.top() + 39,
                        2.5,
                        14,
                    ),
                    1,
                    1,
                )
        p.restore()

        p.setPen(QColor(TEXT))
        p.setFont(ui_font(15, QFont.Weight.Bold, "Segoe UI Variable Display"))
        p.drawText(
            QRectF(r.left() + 14, scr.bottom() + 10, r.width() - 50, 22),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self.title,
        )
        c = QPointF(r.right() - 22, scr.bottom() + 21)
        p.setPen(QPen(mix("#3b4052", acc, self._sel), 1.6))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(c, 8, 8)
        if self._sel > 0.01:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(acc)
            p.drawEllipse(c, 4.6 * self._sel, 4.6 * self._sel)
        p.setPen(QColor(DIM))
        p.setFont(ui_font(12))
        p.drawText(
            QRectF(r.left() + 14, scr.bottom() + 36, r.width() - 28, 40),
            Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignTop
            | Qt.TextFlag.TextWordWrap,
            self.desc,
        )


class ColorCard(Hover, QAbstractButton):
    def __init__(self, key, title, desc, colors_fn, parent=None):
        super().__init__(parent)
        self.init_hover()
        self.key, self.title, self.desc = key, title, desc
        self.colors_fn = colors_fn
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(116)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._sel = 0.0
        self._sel_anim = make_anim(self, self._set_sel, 200)
        self.toggled.connect(
            lambda on: (
                run_anim(self._sel_anim, self._sel, 1.0 if on else 0.0)
                if self.isVisible()
                else self._set_sel(1.0 if on else 0.0)
            )
        )

    def _set_sel(self, v):
        self._sel = v
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        acc = UI["accent"]
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(
            QPen(
                mix(mix(CARD_BORDER, "#58ffffff", self._hover), acc, self._sel),
                1 + self._sel,
            )
        )
        p.setBrush(
            mix(mix(FIELD, "#24ffffff", self._hover), acc, 0.16 * self._sel)
        )
        p.drawRoundedRect(r, 15, 15)
        cols = [QColor(c) for c in self.colors_fn()] or [QColor("white")]
        font = ui_font(27, QFont.Weight.Black, "Segoe UI Variable Display")
        path = QPainterPath()
        path.addText(QPointF(r.left() + 18, r.top() + 44), font, "Paroles")
        br = path.boundingRect()
        g = QLinearGradient(br.topLeft(), br.topRight())
        for i, c in enumerate(cols):
            g.setColorAt(i / max(1, len(cols) - 1) if len(cols) > 1 else 0.0, c)
        for width, a in ((12, 22), (7, 34), (3, 50)):
            pen = QPen(alpha(cols[0], a), width)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.strokePath(path, pen)
        p.fillPath(path, QBrush(g))
        x = br.right() + 18
        for c in cols[:3]:
            p.setPen(QPen(QColor(0, 0, 0, 90), 1))
            p.setBrush(c)
            p.drawEllipse(QPointF(x + 7, br.center().y() + 2), 7, 7)
            x += 20
        radio = QPointF(r.right() - 22, r.top() + 24)
        p.setPen(QPen(mix("#3b4052", acc, self._sel), 1.6))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(radio, 8, 8)
        if self._sel > 0.01:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(acc)
            p.drawEllipse(radio, 4.6 * self._sel, 4.6 * self._sel)
        p.setPen(QColor(TEXT))
        p.setFont(ui_font(14, QFont.Weight.Bold))
        p.drawText(
            QRectF(r.left() + 18, r.top() + 62, r.width() - 36, 20),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self.title,
        )
        p.setPen(QColor(DIM))
        p.setFont(ui_font(12))
        p.drawText(
            QRectF(r.left() + 18, r.top() + 83, r.width() - 36, 18),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self.desc,
        )


class NavTile(Hover, QAbstractButton):
    def __init__(self, icon, caption, parent=None):
        super().__init__(parent)
        self.init_hover()
        self.glyph, self.caption, self.value = icon, caption, ""
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(84)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )

    def set_value(self, text):
        if text != self.value:
            self.value = text
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        acc = UI["accent"]
        h = self._hover
        r = (
            QRectF(self.rect())
            .adjusted(0.5, 0.5, -0.5, -0.5 - 2 * (1 - h))
            .translated(0, 2 * (1 - h))
        )
        p.setPen(QPen(mix(CARD_BORDER, acc, h * 0.8), 1))
        p.setBrush(mix(CARD, mix(CARD, acc, 0.12), h))
        p.drawRoundedRect(r, 16, 16)
        box = QRectF(r.left() + 14, r.center().y() - 21, 42, 42)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(alpha(acc, 36 + 30 * h))
        p.drawRoundedRect(box, 12, 12)
        draw_icon(p, self.glyph, box.adjusted(11, 11, -11, -11), acc)
        tw = r.width() - 104
        p.setPen(QColor(DIM))
        p.setFont(ui_font(12, QFont.Weight.DemiBold))
        p.drawText(
            QRectF(box.right() + 12, r.center().y() - 21, tw, 18),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self.caption,
        )
        f = ui_font(15, QFont.Weight.Bold)
        p.setFont(f)
        p.setPen(QColor(TEXT))
        p.drawText(
            QRectF(box.right() + 12, r.center().y() - 1, tw, 22),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            QFontMetricsF(f).elidedText(
                self.value, Qt.TextElideMode.ElideRight, tw
            ),
        )
        draw_icon(
            p,
            "chevron",
            QRectF(r.right() - 30 + 3 * h, r.center().y() - 9, 18, 18),
            mix(DIM, acc, h),
        )


class HotkeyButton(Hover, QWidget):
    captured = pyqtSignal(str)
    started = pyqtSignal()
    ended = pyqtSignal()

    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.init_hover()
        self.manager = manager
        self.combo = ""
        self.error = False
        self.listening = False
        self.live = []
        self.note = ""
        self.setFixedSize(250, 42)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.pulse = QTimer(self)
        self.pulse.setInterval(33)
        self.pulse.timeout.connect(self.update)

    def set_combo(self, combo, error=False):
        self.combo, self.error = combo, error
        self.update()

    def start(self):
        if self.listening:
            return
        self.listening, self.live, self.note = True, [], ""
        self.started.emit()
        self.setFocus()
        self.grabKeyboard()
        self.pulse.start()
        self.update()

    def finish(self, combo=None):
        if not self.listening:
            return
        self.listening = False
        self.pulse.stop()
        self.releaseKeyboard()
        self.ended.emit()
        if combo is not None:
            self.captured.emit(combo)
        self.update()

    def mousePressEvent(self, e):
        if self.listening:
            self.finish()
        else:
            self.start()

    def focusOutEvent(self, e):
        self.finish()
        super().focusOutEvent(e)

    def hideEvent(self, e):
        self.finish()
        super().hideEvent(e)

    @staticmethod
    def _mods(e):
        m, out = e.modifiers(), 0
        if m & Qt.KeyboardModifier.ControlModifier:
            out |= hotkeys.MOD_CTRL
        if m & Qt.KeyboardModifier.AltModifier:
            out |= hotkeys.MOD_ALT
        if m & Qt.KeyboardModifier.ShiftModifier:
            out |= hotkeys.MOD_SHIFT
        return out

    def keyPressEvent(self, e):
        if not self.listening:
            return super().keyPressEvent(e)
        if e.isAutoRepeat():
            return None
        vk = self.manager.keyboard.virtual_key(
            int(e.nativeVirtualKey()), e.key()
        )
        mods = self._mods(e)
        if vk == 0x1B:
            return self.finish()
        if vk in (0x08, 0x2E) and not mods:
            return self.finish("")
        held = [
            hotkeys.PRETTY.get(n, n) for n, flag in hotkeys.MODS if mods & flag
        ]
        if not vk or vk in hotkeys.MODIFIER_VKS:
            self.live, self.note = held, ""
        elif not hotkeys.allowed(mods, vk):
            self.live, self.note = [], "Ajoute Ctrl ou Alt"
        else:
            return self.finish(hotkeys.make(mods, vk))
        self.update()
        return None

    def keyReleaseEvent(self, e):
        if self.listening and not e.isAutoRepeat():
            mods = self._mods(e)
            self.live = [
                hotkeys.PRETTY.get(n, n)
                for n, flag in hotkeys.MODS
                if mods & flag
            ]
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        acc = UI["accent"]
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        if self.listening:
            beat = 0.5 + 0.5 * math.sin(time.monotonic() * 6.0)
            p.setPen(QPen(alpha(acc, 150 + 105 * beat), 2))
            p.setBrush(mix(FIELD, acc, 0.10 + 0.10 * beat))
        elif self.error:
            p.setPen(QPen(QColor(255, 170, 60, 200), 1.4))
            p.setBrush(QColor(FIELD))
        else:
            p.setPen(QPen(mix(CARD_BORDER, acc, self._hover * 0.85), 1))
            p.setBrush(mix(FIELD, "#26ffffff", self._hover))
        p.drawRoundedRect(r, 11, 11)
        cy = r.center().y()
        if self.listening:
            if self.live:
                x = draw_keycaps(p, self.live, r.left() + 12, cy)
                p.setPen(acc)
                p.setFont(ui_font(13, QFont.Weight.DemiBold))
                p.drawText(
                    QRectF(x + 8, r.top(), 60, r.height()),
                    Qt.AlignmentFlag.AlignVCenter,
                    "+ …",
                )
            else:
                p.setPen(QColor(255, 190, 110) if self.note else acc)
                p.setFont(ui_font(13, QFont.Weight.DemiBold))
                p.drawText(
                    r.adjusted(14, 0, -10, 0),
                    Qt.AlignmentFlag.AlignVCenter,
                    self.note or "Appuie sur les touches…",
                )
        elif self.combo:
            draw_keycaps(
                p, self.manager.key_names(self.combo), r.left() + 12, cy
            )
        else:
            p.setPen(QColor(DIM))
            p.setFont(ui_font(13))
            p.drawText(
                r.adjusted(14, 0, -10, 0),
                Qt.AlignmentFlag.AlignVCenter,
                "Aucun · clique pour choisir",
            )
        if not self.listening and self._hover > 0.05 and self.combo:
            p.setPen(alpha(acc, 255 * self._hover))
            p.setFont(ui_font(12, QFont.Weight.DemiBold))
            p.drawText(
                r.adjusted(0, 0, -12, 0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                "Modifier",
            )

    def sizeHint(self):
        return QSize(250, 42)
