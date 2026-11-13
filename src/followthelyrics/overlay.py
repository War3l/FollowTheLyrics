import bisect
import contextlib
import ctypes
import logging
import math
import random
import time
from collections import OrderedDict
from ctypes import wintypes
from types import SimpleNamespace

import numpy as np
from PyQt6.QtCore import QPointF
from PyQt6.QtCore import QRectF
from PyQt6.QtCore import Qt
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QBrush
from PyQt6.QtGui import QColor
from PyQt6.QtGui import QFont
from PyQt6.QtGui import QFontDatabase
from PyQt6.QtGui import QFontMetricsF
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtGui import QImage
from PyQt6.QtGui import QLinearGradient
from PyQt6.QtGui import QPainter
from PyQt6.QtGui import QPainterPath
from PyQt6.QtGui import QPen
from PyQt6.QtGui import QRegion
from PyQt6.QtGui import QTransform
from PyQt6.QtWidgets import QWidget

from followthelyrics import analysis
from followthelyrics import animation
from followthelyrics import colors
from followthelyrics import easter
from followthelyrics import lyrics
from followthelyrics import settings

logger = logging.getLogger(__name__)

PREV_ALPHA = 0.42
HIDE_AFTER = 3.0
CARD_TIME = 4.5
UPPER = 0.5
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
        _FAMILIES = set(QFontDatabase.families())
    return name if name in _FAMILIES else "Segoe UI"


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
        ptr = img.constBits()
        ptr.setsize(img.sizeInBytes())
        arr = np.frombuffer(ptr, dtype=np.uint8).reshape(
            img.height(), img.bytesPerLine()
        )
        arr = (
            arr[:, : img.width() * 4]
            .reshape(img.height(), img.width(), 4)[:, :, :3]
            .copy()
        )
        pal = colors.palette_rgb(arr)
    except Exception:
        logger.debug("palette_from_cover failed", exc_info=True)
        pal = None
    return [QColor(*c) for c in pal] if pal else None


class Overlay(QWidget):
    def __init__(self, cfg, profiles, clock=time.monotonic, rng=None):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.NoDropShadowWindowHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self.cfg = cfg
        self.clock = clock
        self.rng = rng or random.Random()
        self.profile_key, self.profile = "bureau", profiles["bureau"]
        self.zones: list[QRectF] = []
        self.track = None
        self.track_key = None
        self.track_changed_at = -99.0
        self.card_since = -99.0
        self.cover_img: QImage | None = None
        self.lines: list[lyrics.Line] | None = None
        self.times: list[float] = []
        self.word_sync = False
        self.state = "idle"
        self.anchor_pos = 0.0
        self.anchor_t = clock()
        self.playing = False
        self.alpha = 0.0
        self.user_hidden = False
        self.toast_text = ""
        self.toast_until = -99.0
        self.zones_until = -99.0
        self.beat_t, self.beat_k = -99.0, 0.0
        self.last_tick = clock()
        self.cur = None
        self.prev = None
        self.exiting = []
        self.particles = []
        self.last_region = QRegion()
        self._layout_cache = {}
        self._band = None
        self._halo_cache = OrderedDict()
        self._hero_cache = {}
        self.word_lines = {}
        self.flash = None
        self.egg = None
        self.force_paint = True
        self.was_animating = False
        self.accent = [QColor(c) for c in NEUTRAL_PALETTE]
        self.apply_geometry()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(16)
        self.top_timer = QTimer(self)
        self.top_timer.timeout.connect(self.keep_on_top)
        self.top_timer.start(500)

    def apply_geometry(self):
        self.setGeometry(QGuiApplication.primaryScreen().geometry())
        self.update_zones()
        self.reset_layout()

    def reset_layout(self):
        self._layout_cache.clear()
        self._band = None
        self.cur = self.prev = None
        self.exiting = []
        self.flash = None
        self.force_paint = True
        self.update()

    def poke(self):
        self.force_paint = True

    def set_profile(self, key, profile):
        self.profile_key, self.profile = key, profile
        self.update_zones()
        self._band = None

    def update_zones(self):
        width, height = self.width(), self.height()
        self.zones = []
        for z in self.profile.get("zones_interdites", []):
            with contextlib.suppress(KeyError, TypeError, ValueError):
                self.zones.append(
                    QRectF(
                        z["x"] * width,
                        z["y"] * height,
                        z["l"] * width,
                        z["h"] * height,
                    )
                )

    def keep_on_top(self):
        if not self.isVisible():
            return
        try:
            u = ctypes.windll.user32
            u.SetWindowPos.argtypes = [
                wintypes.HWND,
                wintypes.HWND,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_uint,
            ]
            u.SetWindowPos.restype = wintypes.BOOL
            u.SetWindowPos(
                int(self.winId()),
                wintypes.HWND(-1),
                0,
                0,
                0,
                0,
                0x0001 | 0x0002 | 0x0010 | 0x0200,
            )
        except Exception:
            logger.debug("keep_on_top failed", exc_info=True)

    def install_foreground_hook(self):
        try:
            u = ctypes.windll.user32
            proto = ctypes.WINFUNCTYPE(
                None,
                wintypes.HANDLE,
                wintypes.DWORD,
                wintypes.HWND,
                wintypes.LONG,
                wintypes.LONG,
                wintypes.DWORD,
                wintypes.DWORD,
            )

            def on_foreground(*_):
                for delay in (0, 300, 1000, 2500):
                    QTimer.singleShot(delay, self.keep_on_top)

            self._fg_proc = proto(on_foreground)
            u.SetWinEventHook.restype = wintypes.HANDLE
            u.SetWinEventHook.argtypes = [
                wintypes.DWORD,
                wintypes.DWORD,
                wintypes.HANDLE,
                proto,
                wintypes.DWORD,
                wintypes.DWORD,
                wintypes.DWORD,
            ]
            self._fg_hook = u.SetWinEventHook(
                3, 3, None, self._fg_proc, 0, 0, 0
            )
        except Exception:
            logger.debug("install_foreground_hook failed", exc_info=True)
            self._fg_hook = None

    def harden_window(self):
        try:
            hwnd = int(self.winId())
            u = ctypes.windll.user32
            u.GetWindowLongPtrW.restype = ctypes.c_ssize_t
            u.SetWindowLongPtrW.argtypes = [
                wintypes.HWND,
                ctypes.c_int,
                ctypes.c_ssize_t,
            ]
            ex = u.GetWindowLongPtrW(hwnd, -20)
            u.SetWindowLongPtrW(hwnd, -20, ex | 0x20 | 0x80 | 0x08000000)
        except Exception:
            logger.debug("harden_window failed", exc_info=True)

    def raw_position(self):
        return self.anchor_pos + (
            (self.clock() - self.anchor_t) if self.playing else 0.0
        )

    def position(self):
        return self.raw_position() + self.cfg["offset"]

    def on_track(self, np):
        now = self.clock()
        if np is None:
            self.playing = False
            self.track = None
            return
        if np.key != self.track_key:
            self.track_key = np.key
            self.track_changed_at = self.card_since = now
            self.lines, self.times = None, []
            self.state = "loading"
            self.cur = self.prev = None
            self.exiting = []
            self.flash = None
            self.cover_img = None
            self.accent = [QColor(c) for c in NEUTRAL_PALETTE]
            self.anchor_pos, self.anchor_t = np.position, now
            self.egg = (
                easter.pick(np, self) if self.cfg.get("easter", True) else None
            )
            self.force_paint = True
        elif (
            np.playing != self.playing
            or abs(np.position - self.raw_position()) > 0.35
        ):
            self.anchor_pos, self.anchor_t = np.position, now
        self.playing = np.playing
        self.track = np

    def on_lyrics(self, key, lines):
        if key != self.track_key:
            return
        if lines:
            if lines[0].time > 0.5:
                lines = [lyrics.Line(0.0, ""), *list(lines)]
            analysis.compute_word_meta(lines)
            analysis.mark_chorus(lines)
            if self.track is not None:
                lyrics.mark_title_lines(
                    lines, self.track.title, self.track.artist
                )
            self._hero_cache = {}
            self.word_lines = analysis.count_word_lines(lines)
            self.cur = self.prev = None
            self.exiting = []
            self.lines = lines
            self.times = [line.time for line in lines]
            self.word_sync = any(line.chars for line in lines)
            self.state = "ok"
            if self.egg:
                self.egg.set_lines(lines)
        else:
            self.state = "missing"
        self.track_changed_at = self.clock()
        self.force_paint = True

    def on_translated(self, key):
        self._layout_cache.clear()
        self.force_paint = True

    def on_cover(self, key, data):
        if key != self.track_key:
            return
        img = QImage.fromData(data)
        if img.isNull():
            return
        self.cover_img = img
        pal = palette_from_cover(img)
        if pal:
            self.accent = pal
        self.force_paint = True

    def on_beat(self, strength):
        if self.cfg.get("beat", True):
            self.beat_t, self.beat_k = self.clock(), strength

    def beat_pulse(self):
        return self.beat_k * math.exp(-(self.clock() - self.beat_t) * 7.0)

    def toast(self, text):
        self.toast_text = text
        self.toast_until = self.clock() + 2.0

    def current_index(self, pos):
        return bisect.bisect_right(self.times, pos) - 1

    def current_text(self):
        if self.state == "ok" and self.cur and self.lines:
            return self.lines[self.cur["idx"]].text
        return ""

    def colors(self):
        if self.cfg.get("color") == "white":
            return [QColor(c) for c in WHITE_PALETTE]
        return self.accent

    def fill_brush(self, x0, roww, chorus):
        cols = self.colors()
        if self.cfg.get("color") == "white":
            return QBrush(cols[0])
        g = QLinearGradient(QPointF(x0, 0), QPointF(x0 + max(roww, 1), 0))
        white = QColor(255, 255, 255)
        key = tuple((c.red(), c.green(), c.blue()) for c in cols)
        for pos, rgb in colors.ramp(key):
            g.setColorAt(
                pos, mix(QColor(*rgb), white, 0.26 if chorus else 0.12)
            )
        return QBrush(g)

    def outline_pen(self):
        if self.cfg.get("color") == "white":
            pen = QPen(QColor(0, 0, 0, 105), 3.0)
        else:
            pen = QPen(QColor(0, 0, 0, 170), 4.5)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return pen

    def glow_pens(self, boost):
        if self.cfg.get("color") == "white":
            c, base = QColor(255, 255, 255), 55
        else:
            c, base = self.accent[1], 65
        pen = QPen(
            QColor(
                c.red(),
                c.green(),
                c.blue(),
                int(animation.clamp(base + 150 * boost, 0, 255)),
            ),
            10 + 8 * boost,
        )
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return [pen]

    def main_font(self):
        f = QFont(
            family_or_default(self.cfg.get("font", settings.DEFAULTS["font"])),
            1,
        )
        f.setPixelSize(int(34 * self.cfg["scale"]))
        f.setWeight(QFont.Weight.Black)
        return f

    def small_font(self, k=0.5, italic=True):
        f = QFont(self.main_font())
        f.setPixelSize(max(9, int(f.pixelSize() * k)))
        f.setWeight(QFont.Weight.DemiBold)
        f.setItalic(italic)
        return f

    def label_font(self):
        f = QFont("Segoe UI Variable Text", 1)
        f.setPixelSize(int(14 * self.cfg["scale"]))
        f.setWeight(QFont.Weight.Bold)
        return f

    def label_height(self):
        return QFontMetricsF(self.label_font()).height() * 1.05

    def show_translation(self, line):
        return self.cfg.get("translation", True) and bool(line.translation)

    def layout(self, text, font, maxw):
        key = (text, font.family(), font.pixelSize(), int(maxw))
        if key in self._layout_cache:
            return self._layout_cache[key]
        fm = QFontMetricsF(font)
        space = fm.horizontalAdvance(" ")
        rows, row, x, c = [], [], 0.0, 0
        for word in text.split():
            w = fm.horizontalAdvance(word)
            if row and x + w > maxw:
                rows.append((row, x - space))
                row, x = [], 0.0
            row.append((word, x, w, c))
            x += w + space
            c += len(word) + 1
        if row:
            rows.append((row, x - space))
        res = (rows, fm.height() * 1.05, fm.ascent())
        self._layout_cache[key] = res
        return res

    def block_size(self, line, maxw):
        font = self.main_font()
        rows, lh, _ = self.layout(line.text, font, maxw)
        w = max(rw for _, rw in rows)
        h = lh * len(rows) + (self.label_height() if line.singer else 0)
        if self.show_translation(line):
            tf = self.small_font(0.5)
            tw = QFontMetricsF(tf).horizontalAdvance(line.translation)
            w = max(w, min(tw, maxw * 1.2))
            h += QFontMetricsF(tf).height() * 1.1
        if line.adlib:
            w += (
                QFontMetricsF(self.small_font(0.6)).horizontalAdvance(
                    f"({line.adlib})"
                )
                + 12
            )
        return w, h

    def column_mode(self):
        return self.cfg.get("mode") in ("classic", "typewriter")

    def stacked(self):
        return self.cfg.get("mode") == "edit" and self.cfg.get("stack", True)

    def word_score(self, line, word, cstart, index):
        key = analysis.word_key(word)
        score = min(len(key), 12) * 0.04
        meta = (line.word_meta or {}).get(cstart)
        if meta:
            score += 3.0 * meta[2]
        span = line.title_span
        if span and span[0] <= index < span[0] + span[1]:
            score += 2.5
        if len(key) >= 4 and key not in analysis.COMMON_WORDS:
            score += 1.5 * animation.clamp(
                (self.word_lines.get(key, 1) - 1) / 5
            )
        return score

    def row_scales(self, line, rows):
        key = (line.time, line.text, len(rows))
        hero = self._hero_cache.get(key)
        if hero is None:
            best, index = -1.0, 0
            for r, (row, _w) in enumerate(rows):
                for word, _x, _ww, cstart in row:
                    sc = self.word_score(line, word, cstart, index)
                    if sc > best + 1e-9:
                        best, hero = sc, r
                    index += 1
            self._hero_cache[key] = hero
        return hero, [
            1.0 if r == hero else max(0.46, 0.64 - 0.12 * (abs(r - hero) - 1))
            for r in range(len(rows))
        ]

    def place_line(self, line, avoid):
        if self.column_mode():
            return self.column_place(line)
        width, height = self.width(), self.height()
        s = self.cfg["scale"]
        rng = self.rng
        margin = 26 * s
        top_limit = height * UPPER
        chorus = line.chorus
        best = None
        for attempt in range(200):
            if line.text:
                n = len(line.text)
                mul = rng.uniform(0.95, 1.1) * (
                    1.35 if n < 14 else 1.15 if n < 26 else 1.0
                )
                if chorus:
                    mul *= 1.22
                if attempt >= 100:
                    mul *= 0.78 if attempt < 150 else 0.62
                if self.stacked():
                    mul *= 1.45
                    maxw = rng.choice([0.11, 0.14, 0.18, 0.22]) * width / mul
                else:
                    maxw = rng.choice([0.18, 0.24, 0.30, 0.36]) * width / mul
                bw, bh = self.block_size(line, maxw)
                bw, bh = bw * mul, bh * mul
            else:
                mul, maxw, bw, bh = 1.0, 0, 90 * s, 34 * s
            room = top_limit - margin - bh
            if bw > width - 2 * margin or room < 0:
                continue
            y = margin + room * (rng.random() ** 1.6)
            r = QRectF(rng.uniform(margin, width - margin - bw), y, bw, bh)
            padded = r.adjusted(-20 * s, -14 * s, 20 * s, 14 * s)
            score = (
                sum(area(padded.intersected(z)) for z in self.zones)
                / (bw * bh)
                * 10
            )
            for a in avoid:
                score += (
                    area(
                        padded.adjusted(
                            -30 * s, -30 * s, 30 * s, 30 * s
                        ).intersected(a)
                    )
                    / (bw * bh)
                    * 5
                )
                if (
                    abs(r.center().x() - a.center().x()) < width * 0.18
                    and abs(r.center().y() - a.center().y()) < height * 0.15
                ):
                    score += 0.6
            card = self.card_rect()
            if self.card_visible() and card is not None:
                score += area(padded.intersected(card)) / (bw * bh) * 5
            if best is None or score < best[0]:
                best = (score, r, mul, maxw)
            if score == 0:
                break
        if best is None:
            r, mul, maxw = (
                QRectF(margin, margin, 300 * s, 60 * s),
                1.0,
                width * 0.3,
            )
        else:
            _, r, mul, maxw = best
        cx = r.center().x()
        align = (
            "left"
            if cx < width / 3
            else "right"
            if cx > 2 * width / 3
            else "center"
        )
        ax = {"left": r.left(), "right": r.right(), "center": cx}[align]
        if line.adlib and align == "right":
            ax -= (
                QFontMetricsF(self.small_font(0.6)).horizontalAdvance(
                    f"({line.adlib})"
                )
                * mul
                + 12
            )
        enter = (
            "pop" if chorus else rng.choice(["slide", "slide", "pop", "drop"])
        )
        direction = {"left": (-1, 0), "right": (1, 0)}.get(align, (0, -1))
        return SimpleNamespace(
            rect=r,
            ax=ax,
            cy=r.center().y(),
            align=align,
            mul=mul,
            maxw=maxw,
            rot=rng.choice([-4, -3, -2, -1, 0, 0, 1, 2, 3, 4]),
            enter=enter,
            dir=direction,
            chorus=chorus,
            tilt={"left": 1, "right": -1}.get(align, 0) * rng.uniform(26, 34),
        )

    def column_band(self):
        if self._band is not None:
            return self._band
        width, height = self.width(), self.height()
        s = self.cfg["scale"]
        m = 36 * s
        lh = QFontMetricsF(self.main_font()).height() * 1.05
        band_h = lh * 3.6
        mw = width * 0.36
        pos = self.cfg.get("position", "left")
        x = {"left": m, "right": width - m - mw}.get(pos, (width - mw) / 2)
        best = QRectF(x, m, mw, band_h)
        y = m
        while y + band_h <= height * UPPER + lh:
            r = QRectF(x, y, mw, band_h)
            if not any(r.intersects(z) for z in self.zones):
                best = r
                break
            y += 12 * s
        self._band = best
        return best

    def column_place(self, line):
        band = self.column_band()
        pos = self.cfg.get("position", "left")
        chorus = line.chorus
        mul = 1.12 if (chorus and self.cfg.get("mode") == "classic") else 1.0
        ax = {"left": band.left(), "right": band.right()}.get(
            pos, band.center().x()
        )
        return SimpleNamespace(
            rect=band,
            ax=ax,
            cy=band.center().y(),
            align=pos,
            mul=mul,
            maxw=band.width() / mul,
            rot=0,
            enter="column",
            dir=(0, 1),
            chorus=chorus,
        )

    def entry_height(self, e):
        line = self.lines[e["idx"]]
        if not line.text:
            return 30 * self.cfg["scale"]
        return self.block_size(line, e["place"].maxw)[1] * e["place"].mul

    def advance(self, idx, now):
        old = self.cur
        if self.prev:
            self.exiting.append((self.prev, now))
        self.prev = None
        if old:
            if self.lines[old["idx"]].text and idx > old["idx"]:
                self.prev = dict(old, prev_since=now)
            else:
                self.exiting.append((old, now))
        if idx < 0 or idx >= len(self.lines):
            self.cur = None
            return
        avoid = [self.prev["place"].rect] if self.prev else []
        self.cur = {
            "idx": idx,
            "place": self.place_line(self.lines[idx], avoid),
            "since": now,
        }
        self.maybe_flash(idx)

    def maybe_flash(self, idx):
        line = self.lines[idx]
        mode = self.cfg.get("title_drop", "always")
        if mode == "never" or self.egg or not line.title_drop:
            return
        in_game = self.profile_key != "bureau"
        if in_game and mode == "desktop":
            return
        i, n = line.title_span
        words = line.text.split()
        text = " ".join(words[i : i + n]).strip(",.!?;:…\"'()").upper()
        cstart = sum(len(w) + 1 for w in words[:i])
        start = (
            line.chars[cstart][0]
            if (line.chars and cstart < len(line.chars))
            else line.time
        )
        place = self.flash_place(text, in_game)
        if place is None:
            return
        font, rect = place
        self.flash = {
            "text": text,
            "font": font,
            "rect": rect,
            "start": start,
            "end": max(self.sung_end(idx) + 1.2, start + 2.2),
            "rot": self.rng.choice([-3, -2, -1, 1, 2, 3]),
        }

    def flash_place(self, text, in_game):
        width, height = self.width(), self.height()
        base = self.main_font()
        probe = QFont(base)
        probe.setPixelSize(100)
        fm = QFontMetricsF(probe)
        w100, h100 = max(1.0, fm.horizontalAdvance(text)), fm.height()

        def font_for(px):
            f = QFont(base)
            f.setPixelSize(int(px))
            return f

        if not in_game:
            px = min(height * 0.26, 100 * width * 0.84 / w100)
            w, h = w100 * px / 100, h100 * px / 100
            return font_for(px), QRectF(
                (width - w) / 2, height * 0.58 - h / 2, w, h
            )
        m = 24 * self.cfg["scale"]
        busy = [e["place"].rect for e in (self.cur, self.prev) if e]
        for frac in (0.62, 0.5, 0.42, 0.34, 0.27, 0.21):
            px = min(height * 0.15, 100 * width * frac / w100)
            if px < base.pixelSize() * 1.5:
                break
            w, h = w100 * px / 100, h100 * px / 100
            xs = sorted(
                (m + k * (width - 2 * m - w) / 12 for k in range(13)),
                key=lambda x: abs(x + w / 2 - width / 2),
            )
            y = m
            while y + h <= height * UPPER:
                for x in xs:
                    r = QRectF(x, y, w, h)
                    pad = r.adjusted(-12, -8, 12, 8)
                    if not any(
                        pad.intersects(z) for z in self.zones
                    ) and not any(pad.intersects(b) for b in busy):
                        return font_for(px), r
                y += height * 0.03
        return None

    def draw_flash(self, p, pos):
        f = self.flash
        if not f or pos < f["start"]:
            return
        k = animation.clamp((pos - f["start"]) / 0.38)
        out = animation.clamp((f["end"] - pos) / 0.6)
        a = animation.ease_out(animation.clamp(k * 1.6)) * out
        if a <= 0.003:
            return
        sc = (
            animation.lerp(1.4, 1.0, animation.ease_out_back(k))
            * (1 + 0.05 * self.beat_pulse())
            * (1 + 0.05 * (1 - out))
        )
        font = f["font"]
        fm = QFontMetricsF(font)
        tw = fm.horizontalAdvance(f["text"])
        c = f["rect"].center()
        p.save()
        p.setOpacity(animation.clamp(self.alpha * a * 0.95))
        p.translate(c)
        p.rotate(f["rot"])
        p.scale(sc, sc)
        x, y = -tw / 2, fm.ascent() - fm.height() / 2
        self.draw_text_fx(
            p, f["text"], font, x, y, self.fill_brush(x, tw, True), glow=1.5
        )
        p.restore()

    def is_animating(self, now, pos):
        if self.exiting or self.particles or self.flash:
            return True
        if self.egg and self.egg.busy(now, pos):
            return True
        if (
            now < self.toast_until
            or now < self.zones_until
            or self.card_visible()
        ):
            return True
        if self.beat_pulse() > 0.01:
            return True
        if self.state != "ok" or not self.lines:
            return False
        typewriter = self.cfg.get("mode") == "typewriter"
        for e in (self.cur, self.prev):
            if not e:
                continue
            if now - e["since"] < 0.8 or now - e.get("prev_since", -99) < 0.8:
                return True
            line = self.lines[e["idx"]]
            if not line.text:
                if e is self.cur:
                    return True
                continue
            fade = self.done_fade(e["idx"], pos)
            if 0 < fade < 1:
                return True
            if e is self.cur and fade > 0:
                if typewriter:
                    return True
                if (
                    pos
                    < max(
                        self.sung_end(e["idx"]),
                        line.time + len(line.text.split()) * 0.06,
                    )
                    + 0.8
                ):
                    return True
        return False

    def tick(self, dt=None):
        now = self.clock()
        if dt is None:
            dt = min(0.1, now - self.last_tick)
        self.last_tick = now

        if self.state == "ok" and self.lines:
            idx = self.current_index(self.position())
            if self.cur is None or idx != self.cur["idx"]:
                self.advance(idx, now)
        self.exiting = [(e, t) for e, t in self.exiting if now - t < 0.45]
        pos_now = self.position()
        if self.flash and (
            pos_now > self.flash["end"] or pos_now < self.flash["start"] - 6
        ):
            self.flash = None

        alive = []
        for pt in self.particles:
            pt["life"] -= dt
            if pt["life"] > 0:
                pt["x"] += pt["vx"] * dt
                pt["y"] += pt["vy"] * dt
                pt["vy"] -= 20 * dt
                pt["vx"] *= 0.97
                alive.append(pt)
        self.particles = alive
        if self.egg:
            self.egg.tick(now, dt, pos_now)

        toast_on = now < self.toast_until or now < self.zones_until
        since = now - self.track_changed_at
        show = (
            not self.user_hidden
            and self.track is not None
            and self.playing
            and (self.state == "ok" or since < 4.0)
        ) or toast_on
        target = 1.0 if show else 0.0
        self.alpha += (target - self.alpha) * (
            1 - math.exp(-dt * (8 if show else 4))
        )

        region = QRegion()
        if self.alpha > 0.003:
            pad = int(120 * self.cfg["scale"])
            if self.column_mode():
                b = self.column_band()
                region = QRegion(
                    b.toAlignedRect().adjusted(
                        -pad, -int(b.height()), pad, int(b.height())
                    )
                )
            else:
                for e in self.visible_entries():
                    region = region.united(
                        QRegion(
                            e["place"]
                            .rect.toAlignedRect()
                            .adjusted(-pad, -pad, pad, pad)
                        )
                    )
            card = self.card_rect()
            if card is not None and (self.card_visible() or toast_on):
                region = region.united(
                    QRegion(card.toAlignedRect().adjusted(-40, -10, 40, 70))
                )
            for pt in self.particles:
                region = region.united(
                    QRegion(int(pt["x"]) - 8, int(pt["y"]) - 8, 16, 16)
                )
            if self.flash:
                g = int(self.flash["font"].pixelSize() * 0.9) + 40
                region = region.united(
                    QRegion(
                        self.flash["rect"]
                        .toAlignedRect()
                        .adjusted(-g, -g, g, g)
                    )
                )
            if now < self.zones_until or (
                self.egg and self.egg.busy(now, pos_now)
            ):
                region = QRegion(self.rect())
        dirty = region.united(self.last_region)
        animating = abs(target - self.alpha) > 0.002 or self.is_animating(
            now, pos_now
        )
        if not dirty.isEmpty() and (
            animating
            or self.was_animating
            or self.force_paint
            or region != self.last_region
        ):
            self.update(dirty)
        self.was_animating = animating
        self.force_paint = False
        self.last_region = region

    def visible_entries(self):
        out = [e for e, _ in self.exiting]
        if self.prev:
            out.append(self.prev)
        if self.cur:
            out.append(self.cur)
        return out

    def paintEvent(self, ev):
        if self.alpha < 0.003:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        now = self.clock()
        pos = self.position()

        if now < self.zones_until:
            self.draw_zones(p)

        if self.state == "ok" and self.lines:
            if self.column_mode():
                self.draw_column(p, now, pos)
            else:
                for e, t in self.exiting:
                    k = animation.clamp((now - t) / 0.4)
                    a = PREV_ALPHA * self.done_fade(e["idx"], pos) * (1 - k)
                    self.draw_entry(
                        p, e, a, 0.88 - 0.06 * k, 0, -14 * k, "prev", pos
                    )
                if self.prev:
                    k = animation.ease_out(
                        animation.clamp((now - self.prev["prev_since"]) / 0.3)
                    )
                    a = animation.lerp(1.0, PREV_ALPHA, k) * self.done_fade(
                        self.prev["idx"], pos
                    )
                    self.draw_entry(
                        p,
                        self.prev,
                        a,
                        animation.lerp(1.0, 0.88, k),
                        0,
                        0,
                        "prev",
                        pos,
                    )
                if self.cur:
                    self.draw_current(p, self.cur, now, pos)

            self.draw_flash(p, pos)

        self.draw_particles(p)
        self.draw_card(p)
        if self.egg:
            self.egg.draw(p, now, pos)
        p.end()

    def sung_end(self, idx):
        line = self.lines[idx]
        if line.end:
            return line.end
        nxt = (
            self.times[idx + 1]
            if idx + 1 < len(self.times)
            else line.time + 6.0
        )
        return min(nxt, line.time + max(2.0, len(line.text) * 0.09))

    def done_fade(self, idx, pos):
        if not self.lines[idx].text:
            return 1.0
        return animation.clamp(
            1 - (pos - self.sung_end(idx) - HIDE_AFTER) / 0.5
        )

    def beat_scale(self, chorus):
        return 1 + (0.09 if chorus else 0.05) * self.beat_pulse()

    def draw_current(self, p, e, now, pos):
        pl = e["place"]
        k = animation.clamp((now - e["since"]) / (0.55 if pl.chorus else 0.45))
        a, sc, ox, oy = (
            animation.ease_out(k) * self.done_fade(e["idx"], pos),
            1.0,
            0.0,
            0.0,
        )
        d = 90 * self.cfg["scale"]
        if pl.enter == "slide":
            ox, oy = (
                pl.dir[0] * d * (1 - animation.ease_out(k)),
                pl.dir[1] * d * (1 - animation.ease_out(k)),
            )
        elif pl.enter == "pop":
            sc = animation.lerp(
                1.7 if pl.chorus else 1.4, 1.0, animation.ease_out_back(k)
            )
        else:
            oy = -60 * self.cfg["scale"] * (1 - animation.ease_out_back(k))
        sc *= self.beat_scale(pl.chorus)
        self.draw_entry(p, e, a, sc, ox, oy, "current", pos)

    def draw_column(self, p, now, pos):
        band = self.column_band()
        s = self.cfg["scale"]
        gap = 8 * s
        cur_y = band.top() + band.height() * 0.64
        hc = self.entry_height(self.cur) if self.cur else 0
        for e, t in self.exiting:
            k = animation.clamp((now - t) / 0.4)
            y = band.top() + band.height() * 0.18 - 30 * s * k
            a = PREV_ALPHA * self.done_fade(e["idx"], pos) * (1 - k)
            self.draw_entry(
                p, e, a, 0.72, 0, 0, "prev", pos, at=(e["place"].ax, y)
            )
        if self.prev:
            k = animation.ease_out(
                animation.clamp((now - self.prev["prev_since"]) / 0.4)
            )
            hp = self.entry_height(self.prev)
            target = cur_y - hc / 2 - hp * 0.72 / 2 - gap
            y = animation.lerp(cur_y, target, k)
            a = animation.lerp(1.0, PREV_ALPHA, k) * self.done_fade(
                self.prev["idx"], pos
            )
            self.draw_entry(
                p,
                self.prev,
                a,
                animation.lerp(1.0, 0.72, k),
                0,
                0,
                "prev",
                pos,
                at=(self.prev["place"].ax, y),
            )
        if self.cur:
            pl = self.cur["place"]
            k = animation.ease_out(
                animation.clamp((now - self.cur["since"]) / 0.4)
            )
            typewriter = self.cfg.get("mode") == "typewriter"
            y = cur_y + (0 if typewriter else (1 - k) * 28 * s)
            a = (1.0 if typewriter else k) * self.done_fade(
                self.cur["idx"], pos
            )
            self.draw_entry(
                p,
                self.cur,
                a,
                self.beat_scale(pl.chorus),
                0,
                0,
                "current",
                pos,
                at=(pl.ax, y),
            )

    def draw_entry(self, p, e, alpha, scale_k, ox, oy, mode, pos, at=None):
        if alpha <= 0.003:
            return
        line = self.lines[e["idx"]]
        if self.egg:
            alpha *= self.egg.line_alpha(e["idx"], pos, e["place"].rect)
            if alpha <= 0.003:
                return
        pl = e["place"]
        x, y = at if at else (pl.ax, pl.cy)
        p.save()
        p.setOpacity(animation.clamp(self.alpha * alpha))
        p.translate(x + ox, y + oy)
        tilt = getattr(pl, "tilt", 0) if self.cfg.get("tilt", True) else 0
        if tilt and line.text:
            ang = math.radians(abs(tilt))
            depth = max(120.0, pl.rect.width()) * 2.1
            k = math.copysign(math.sin(ang) / depth, tilt)
            p.setTransform(
                QTransform(math.cos(ang), 0, k, 0, 1, 0, 0, 0, 1), True
            )
        p.rotate(pl.rot)
        p.scale(pl.mul * scale_k, pl.mul * scale_k)
        if not line.text:
            if mode == "current":
                self.draw_dots(p, pl.align)
        else:
            self.draw_block(p, line, pl, mode, pos)
        p.restore()

    def draw_dots(self, p, align):
        s = self.cfg["scale"]
        t = self.clock()
        r, step = 6 * s, 22 * s
        total = step * 2
        x0 = {"left": r, "right": -total - r}.get(align, -total / 2)
        p.setPen(Qt.PenStyle.NoPen)
        beat = self.beat_pulse()
        cols = self.colors()
        for k in range(3):
            pulse = 0.5 + 0.5 * math.sin(t * 4 - k * 0.9)
            c = QColor(cols[k])
            c.setAlphaF(animation.clamp(0.35 + 0.65 * pulse))
            p.setBrush(c)
            rr = r * (0.8 + 0.35 * pulse + 0.3 * beat)
            p.drawEllipse(QPointF(x0 + k * step, -4 * s * pulse), rr, rr)

    def typed_times(self, line, idx):
        n = len(line.text)
        if line.chars and len(line.chars) == n:
            return [c[0] for c in line.chars]
        nxt = (
            self.times[idx + 1]
            if idx + 1 < len(self.times)
            else line.time + 4.0
        )
        d = min((nxt - line.time) * 0.9, 0.35 + 0.045 * n)
        return [line.time + d * i / max(1, n) for i in range(n)]

    def glow_color(self):
        if self.cfg.get("color") == "white":
            return QColor(236, 244, 255)
        c = self.accent[0]
        h, s = c.hsvHueF(), c.hsvSaturationF()
        if s < 0.10:
            return QColor(236, 244, 255)
        return QColor.fromHsvF(max(h, 0), min(1.0, s * 1.25 + 0.1), 1.0)

    def base_glow(self):
        return 0.85 if self.cfg.get("color") == "white" else 1.0

    def halo(self, text, font, color, radius, strength):
        key = (
            text,
            font.family(),
            font.pixelSize(),
            str(font.weight()),
            font.italic(),
            color.rgb(),
            int(radius * 10),
            int(strength * 10),
        )
        hit = self._halo_cache.get(key)
        if hit is not None:
            self._halo_cache.move_to_end(key)
            return hit
        k = 0.5
        f2 = QFont(font)
        f2.setPixelSize(max(4, round(font.pixelSize() * k)))
        r2 = max(0.8, radius * k)
        fm = QFontMetricsF(f2)
        pad = int(r2 * 3) + 2
        width = int(fm.horizontalAdvance(text)) + 2 * pad + 4
        height = int(fm.height()) + 2 * pad + 2
        img = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        qp = QPainter(img)
        qp.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addText(QPointF(pad, pad + fm.ascent()), f2, text)
        qp.fillPath(path, QColor(255, 255, 255))
        qp.end()
        raw = np.frombuffer(
            img.constBits().asstring(img.sizeInBytes()), dtype=np.uint8
        )
        a = (
            raw.reshape(height, img.bytesPerLine())[:, : width * 4]
            .reshape(height, width, 4)[:, :, 3]
            .astype(np.float32)
        )
        a = np.clip(gaussian_blur(a, r2) * strength, 0, 255)
        out = np.empty((height, width, 4), dtype=np.uint8)
        out[..., 0] = a * (color.blue() / 255)
        out[..., 1] = a * (color.green() / 255)
        out[..., 2] = a * (color.red() / 255)
        out[..., 3] = a
        q = QImage(
            out.tobytes(),
            width,
            height,
            width * 4,
            QImage.Format.Format_ARGB32_Premultiplied,
        ).copy()
        entry = (q, pad / k, fm.ascent() / k, width / k, height / k)
        self._halo_cache[key] = entry
        if len(self._halo_cache) > 700:
            self._halo_cache.popitem(last=False)
        return entry

    def blit_halo(
        self, p, text, font, x, base_y, color, radius, strength, alpha, dy=0.0
    ):
        if alpha <= 0.01 or not text.strip():
            return
        img, pad, asc, w, h = self.halo(text, font, color, radius, strength)
        p.save()
        p.setOpacity(p.opacity() * animation.clamp(alpha))
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.drawImage(QRectF(x - pad, base_y - asc - pad + dy, w, h), img)
        p.restore()

    def draw_text_fx(
        self, p, text, font, x, base_y, brush, glow=1.0, shadow=1.0, path=None
    ):
        px = min(font.pixelSize(), 110)
        white = self.cfg.get("color") == "white"
        if shadow > 0:
            self.blit_halo(
                p,
                text,
                font,
                x,
                base_y,
                QColor(0, 0, 0),
                px * 0.32,
                1.2,
                0.32 * shadow,
                px * 0.04,
            )
            self.blit_halo(
                p,
                text,
                font,
                x,
                base_y,
                QColor(0, 0, 0),
                px * 0.09,
                2.0,
                0.7 * shadow,
                px * 0.05,
            )
        if glow > 0:
            gc = self.glow_color()
            self.blit_halo(
                p, text, font, x, base_y, gc, px * 0.5, 1.7, 0.55 * glow
            )
            self.blit_halo(
                p,
                text,
                font,
                x,
                base_y,
                gc,
                px * 0.14,
                1.8,
                min(1.0, (0.65 if white else 0.5) * glow),
            )
        if path is None:
            path = QPainterPath()
            path.addText(QPointF(x, base_y), font, text)
        p.fillPath(path, brush)

    def draw_block(self, p, line, pl, mode, pos):
        font = self.main_font()
        rows, lh, ascent = self.layout(line.text, font, pl.maxw)
        label_h = self.label_height() if line.singer else 0
        tf = self.small_font(0.5)
        trans_h = (
            QFontMetricsF(tf).height() * 1.1
            if self.show_translation(line)
            else 0
        )
        stack = self.stacked() and len(rows) > 1
        hero, scales = (
            self.row_scales(line, rows) if stack else (-1, [1.0] * len(rows))
        )
        rows_h = lh * sum(scales)
        h = rows_h + label_h + trans_h
        style = self.cfg["style"]
        align = pl.align
        current = mode == "current"
        cols = self.colors()
        base_glow = self.base_glow()
        p.translate(0, -h / 2)
        if line.singer:
            lf = self.label_font()
            fm = QFontMetricsF(lf)
            label = line.singer.upper()
            lw = fm.horizontalAdvance(label)
            lx = {"left": 0, "right": -lw}.get(align, -lw / 2)
            self.draw_text_fx(
                p,
                label,
                lf,
                lx,
                fm.ascent(),
                QBrush(cols[0]),
                glow=0.35 if current else 0,
            )
            p.translate(0, label_h)

        last_row_end = (0.0, 0.0)
        if current and self.cfg.get("mode") == "typewriter":
            last_row_end = self.draw_typed(
                p, line, rows, lh, ascent, font, align, pos, pl.chorus
            )
        else:
            timed = current and bool(line.chars)
            meta = line.word_meta or {}
            chorus = pl.chorus
            word_i = 0
            lit = []
            white = self.cfg.get("color") == "white"
            row_top = 0.0
            for r, (row, roww) in enumerate(rows):
                x0 = {"left": 0, "right": -roww}.get(align, -roww / 2)
                rs = scales[r]
                p.save()
                p.translate(0, row_top)
                p.scale(rs, rs)
                base_y = ascent
                plain = stack and r != hero
                brush = (
                    QBrush(QColor(255, 255, 255, 215 if white else 245))
                    if plain
                    else self.fill_brush(x0, roww, chorus or stack)
                )
                for word, wx, ww, cstart in row:
                    x = x0 + wx
                    if not current:
                        self.draw_text_fx(
                            p,
                            word,
                            font,
                            x,
                            base_y,
                            QBrush(QColor(255, 255, 255, 235)),
                            glow=0.12,
                        )
                        word_i += 1
                        continue
                    sc, dx, dy, glow_k, sx = (
                        animation.held_fx(meta.get(cstart), pos)
                        if timed
                        else (1, 0, 0, 0, 1)
                    )
                    glow = base_glow * (1 + 1.4 * glow_k) + (
                        0.25 if chorus else 0
                    )
                    if plain:
                        glow *= 0.4
                    elif stack:
                        glow *= 1.25
                    cxw, cyw = x + ww / 2, base_y - ascent * 0.35
                    p.save()
                    if sc != 1 or dx or dy or sx != 1:
                        p.translate(cxw + dx, cyw + dy)
                        p.scale(sc * sx, sc)
                        p.translate(-cxw, -cyw)
                    if (
                        self.cfg.get("particles", True)
                        and glow_k > 0.15
                        and pos <= meta.get(cstart, (0, 0, 0))[1]
                    ):
                        self.spawn_particles(
                            p, x, base_y - ascent, ww, ascent, glow_k
                        )
                    if style == "kinetic":
                        start = (
                            line.chars[cstart][0]
                            if (timed and cstart < len(line.chars))
                            else line.time + word_i * 0.06
                        )
                        k = animation.clamp((pos - start) / 0.3)
                        if k <= 0:
                            p.restore()
                            word_i += 1
                            continue
                        e = animation.ease_out_back(k)
                        rot0 = ((cstart * 37) % 25) - 12
                        p.translate(cxw, cyw)
                        p.rotate(rot0 * (1 - e))
                        p.scale(
                            animation.lerp(1.45, 1.0, e),
                            animation.lerp(1.45, 1.0, e),
                        )
                        p.translate(-cxw, -cyw + 22 * (1 - e))
                        p.setOpacity(
                            p.opacity()
                            * animation.ease_out(animation.clamp(k * 1.7))
                        )
                        self.draw_text_fx(p, word, font, x, base_y, brush, glow)
                    elif style == "simple" or not timed:
                        self.draw_text_fx(p, word, font, x, base_y, brush, glow)
                    else:
                        wf = self.word_fill(line, cstart, len(word), pos)
                        self.draw_text_fx(
                            p,
                            word,
                            font,
                            x,
                            base_y,
                            QBrush(QColor(255, 255, 255, 105)),
                            glow=0,
                        )
                        if wf > 0:
                            lit.append(
                                (
                                    word,
                                    x,
                                    ww,
                                    wf,
                                    sc,
                                    dx,
                                    dy,
                                    sx,
                                    glow,
                                    cxw,
                                    cyw,
                                )
                            )
                    p.restore()
                    word_i += 1
                if style == "karaoke" and timed and lit:
                    m = font.pixelSize()
                    _, lx, lw_, lwf = lit[-1][:4]
                    fill_x = lx + lw_ * lwf
                    left, top = x0 - 2 * m, base_y - ascent - 2 * m
                    lw_img, lh_img = fill_x - left + m, lh + 4 * m
                    layer = QImage(
                        int(lw_img) + 2,
                        int(lh_img) + 2,
                        QImage.Format.Format_ARGB32_Premultiplied,
                    )
                    layer.fill(Qt.GlobalColor.transparent)
                    lp = QPainter(layer)
                    lp.setRenderHint(QPainter.RenderHint.Antialiasing)
                    lp.translate(-left, -top)
                    for (
                        word,
                        x,
                        _ww,
                        _wf,
                        sc,
                        dx,
                        dy,
                        sx,
                        glow,
                        cxw,
                        cyw,
                    ) in lit:
                        lp.save()
                        if sc != 1 or dx or dy or sx != 1:
                            lp.translate(cxw + dx, cyw + dy)
                            lp.scale(sc * sx, sc)
                            lp.translate(-cxw, -cyw)
                        self.draw_text_fx(
                            lp, word, font, x, base_y, brush, glow, shadow=0
                        )
                        lp.restore()
                    lp.setCompositionMode(
                        QPainter.CompositionMode.CompositionMode_DestinationIn
                    )
                    fade = QLinearGradient(
                        QPointF(fill_x - m * 0.08, 0),
                        QPointF(fill_x + m * 0.22, 0),
                    )
                    fade.setColorAt(0, QColor(0, 0, 0, 255))
                    fade.setColorAt(1, QColor(0, 0, 0, 0))
                    lp.fillRect(
                        QRectF(left, top, lw_img + 2, lh_img + 2), QBrush(fade)
                    )
                    lp.end()
                    p.drawImage(QPointF(left, top), layer)
                lit = []
                p.restore()
                last_row_end = ((x0 + roww) * rs, row_top + ascent * rs)
                row_top += lh * rs

        if line.adlib and current:
            ad_t = line.adlib_time if line.adlib_time is not None else line.time
            if self.cfg.get("mode") == "typewriter":
                ad_t = max(ad_t, self.typed_times(line, self.cur["idx"])[-1])
            k = (
                animation.clamp((pos - ad_t) / 0.3)
                if (line.chars or self.cfg.get("mode") == "typewriter")
                else 1.0
            )
            if k > 0:
                af = self.small_font(0.6)
                ex, ey = last_row_end
                ox, oy = ex + 12, ey - lh * 0.45
                p.save()
                p.setOpacity(p.opacity() * 0.92 * animation.ease_out(k))
                p.translate(ox, oy)
                p.rotate(-6)
                p.translate(-ox, -oy - 8 * (1 - animation.ease_out(k)))
                self.draw_text_fx(
                    p,
                    f"({line.adlib})",
                    af,
                    ox,
                    oy,
                    QBrush(mix(cols[2], QColor(255, 255, 255), 0.45)),
                    glow=0.5,
                )
                p.restore()

        if current and self.show_translation(line):
            fm = QFontMetricsF(tf)
            text = fm.elidedText(
                line.translation, Qt.TextElideMode.ElideRight, pl.maxw * 1.2
            )
            tw = fm.horizontalAdvance(text)
            tx = {"left": 0, "right": -tw}.get(align, -tw / 2)
            ty = rows_h + fm.ascent() + 2
            self.draw_text_fx(
                p, text, tf, tx, ty, QBrush(QColor(255, 255, 255, 205)), glow=0
            )

    def draw_typed(self, p, line, rows, lh, ascent, font, align, pos, chorus):
        times = self.typed_times(line, self.cur["idx"])
        fm = QFontMetricsF(font)
        glow = self.base_glow() + (0.25 if chorus else 0)
        cursor = None
        last_row_end = (0.0, 0.0)
        for r, (row, roww) in enumerate(rows):
            x0 = {"left": 0, "right": -roww}.get(align, -roww / 2)
            base_y = r * lh + ascent
            if cursor is None:
                cursor = (x0, base_y)
            brush = self.fill_brush(x0, roww, chorus)
            for word, wx, _ww, cstart in row:
                vis = sum(
                    1
                    for i in range(cstart, min(cstart + len(word), len(times)))
                    if times[i] <= pos
                )
                if vis == 0:
                    continue
                sub = word[:vis]
                self.draw_text_fx(p, sub, font, x0 + wx, base_y, brush, glow)
                cursor = (x0 + wx + fm.horizontalAdvance(sub), base_y)
            last_row_end = (x0 + roww, base_y)
        typing = bool(times) and pos < times[-1] + 0.15
        if cursor and (typing or int(self.clock() * 2.4) % 2 == 0):
            cx, cy = cursor
            s = self.cfg["scale"]
            rect = QRectF(cx + 4 * s, cy - ascent * 0.8, 4 * s, ascent * 0.95)
            gc = self.glow_color()
            for grow, al in ((7 * s, 40), (3 * s, 90)):
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(gc.red(), gc.green(), gc.blue(), al))
                p.drawRoundedRect(
                    rect.adjusted(-grow, -grow * 0.5, grow, grow * 0.5),
                    grow,
                    grow,
                )
            p.setBrush(self.colors()[0])
            p.drawRoundedRect(rect, 1.5, 1.5)
        return last_row_end

    @staticmethod
    def word_fill(line, cstart, wlen, pos):
        seg = line.chars[cstart : cstart + wlen] if line.chars else None
        if not seg:
            return 1.0
        done = 0.0
        for a, b in seg:
            if pos >= b:
                done += 1
            elif pos > a:
                done += (pos - a) / (b - a)
        return done / len(seg)

    def spawn_particles(self, p, x, y, w, h, k):
        if len(self.particles) > 160 or self.rng.random() > 0.35 + 0.5 * k:
            return
        tr = p.transform()
        cols = self.colors()
        for _ in range(1 + int(k * 2)):
            pt = tr.map(
                QPointF(x + self.rng.random() * w, y + self.rng.random() * h)
            )
            self.particles.append(
                {
                    "x": pt.x(),
                    "y": pt.y(),
                    "vx": self.rng.uniform(-40, 40),
                    "vy": self.rng.uniform(-70, -20),
                    "life": self.rng.uniform(0.5, 1.0),
                    "max": 1.0,
                    "col": QColor(cols[self.rng.randrange(3)]),
                    "size": self.rng.uniform(1.5, 3.5) * self.cfg["scale"],
                }
            )

    def draw_particles(self, p):
        if not self.particles:
            return
        p.save()
        p.setPen(Qt.PenStyle.NoPen)
        for pt in self.particles:
            c = QColor(pt["col"])
            c.setAlphaF(animation.clamp(pt["life"] / pt["max"]) * self.alpha)
            p.setBrush(c)
            p.drawEllipse(QPointF(pt["x"], pt["y"]), pt["size"], pt["size"])
        p.restore()

    def card_visible(self):
        return (
            self.cfg.get("card", True)
            and self.track is not None
            and self.clock() - self.card_since < CARD_TIME
        )

    def card_fonts(self):
        s = self.cfg["scale"]
        title = QFont("Segoe UI Variable Display", 1)
        title.setPixelSize(int(16 * s))
        title.setWeight(QFont.Weight.Bold)
        artist = QFont("Segoe UI Variable Text", 1)
        artist.setPixelSize(int(13 * s))
        badge = QFont("Segoe UI Variable Text", 1)
        badge.setPixelSize(max(8, int(10 * s)))
        badge.setWeight(QFont.Weight.Bold)
        return title, artist, badge

    def card_badge(self):
        if self.state == "ok":
            return "MOT À MOT" if self.word_sync else "LIGNE"
        return {"loading": "RECHERCHE...", "missing": "PAS DE PAROLES"}.get(
            self.state, ""
        )

    def card_rect(self):
        s = self.cfg["scale"]
        tf, af, bf = self.card_fonts()
        t = self.track
        title = t.title if t else "FollowTheLyrics"
        artist = t.artist if t else ""
        tw = min(QFontMetricsF(tf).horizontalAdvance(title), 260 * s)
        aw = min(QFontMetricsF(af).horizontalAdvance(artist), 260 * s)
        bw = QFontMetricsF(bf).horizontalAdvance(self.card_badge()) + 12 * s
        w = 12 * s + 64 * s + 14 * s + max(tw, aw, bw) + 18 * s
        h = 88 * s
        width = self.width()
        m = 18 * s
        spots = [(m, m), (width - m - w, m), ((width - w) / 2, m)]
        band = None
        if self.column_mode():
            band = self.column_band()
            if self.cfg.get("position") == "left":
                spots = [(width - m - w, m), ((width - w) / 2, m), (m, m)]
        for x, y in spots:
            r = QRectF(x, y, w, h)
            if any(r.intersects(z) for z in self.zones):
                continue
            if band is not None and r.intersects(band):
                continue
            return r
        return QRectF(*spots[0], w, h)

    def draw_card(self, p):
        now = self.clock()
        toast = now < self.toast_until
        if not (self.card_visible() or toast):
            return
        s = self.cfg["scale"]
        rect = self.card_rect()
        tf, af, bf = self.card_fonts()
        p.save()
        if self.card_visible():
            t = now - self.card_since
            a = animation.ease_out(animation.clamp(t / 0.35)) * animation.clamp(
                (CARD_TIME - t) / 0.5
            )
            slide = (
                (1 - animation.ease_out(animation.clamp(t / 0.35)))
                * 30
                * s
                * (-1 if rect.center().x() < self.width() / 2 else 1)
            )
            p.setOpacity(self.alpha * a)
            r = rect.translated(slide, 0)
            g = QLinearGradient(r.topLeft(), r.bottomRight())
            g.setColorAt(0, mix(QColor(14, 14, 20), self.accent[0], 0.22))
            g.setColorAt(1, QColor(12, 12, 18))
            p.setPen(
                QPen(
                    QColor(
                        self.accent[0].red(),
                        self.accent[0].green(),
                        self.accent[0].blue(),
                        110,
                    ),
                    1.2,
                )
            )
            p.setBrush(QBrush(g))
            p.drawRoundedRect(r, 14 * s, 14 * s)
            cov = QRectF(r.left() + 12 * s, r.top() + 12 * s, 64 * s, 64 * s)
            if self.cover_img is not None:
                path = QPainterPath()
                path.addRoundedRect(cov, 9 * s, 9 * s)
                p.save()
                p.setClipPath(path)
                p.drawImage(cov, self.cover_img)
                p.restore()
            else:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(255, 255, 255, 25))
                p.drawRoundedRect(cov, 9 * s, 9 * s)
                p.setPen(QColor(255, 255, 255, 150))
                p.setFont(tf)
                p.drawText(cov, Qt.AlignmentFlag.AlignCenter, "♪")
            tx = cov.right() + 14 * s
            tr = self.track
            p.setFont(tf)
            p.setPen(QColor(255, 255, 255, 240))
            fm = QFontMetricsF(tf)
            p.drawText(
                QPointF(tx, r.top() + 14 * s + fm.ascent()),
                fm.elidedText(
                    tr.title if tr else "", Qt.TextElideMode.ElideRight, 260 * s
                ),
            )
            p.setFont(af)
            p.setPen(QColor(255, 255, 255, 170))
            afm = QFontMetricsF(af)
            p.drawText(
                QPointF(tx, r.top() + 14 * s + fm.height() + afm.ascent()),
                afm.elidedText(
                    tr.artist if tr else "",
                    Qt.TextElideMode.ElideRight,
                    260 * s,
                ),
            )
            badge = self.card_badge()
            if badge:
                bfm = QFontMetricsF(bf)
                br = QRectF(
                    tx,
                    r.bottom() - 12 * s - bfm.height() - 4 * s,
                    bfm.horizontalAdvance(badge) + 12 * s,
                    bfm.height() + 4 * s,
                )
                col = (
                    QColor(self.accent[0])
                    if (self.state == "ok" and self.word_sync)
                    else QColor(180, 180, 190)
                )
                p.setPen(QPen(col, 1))
                p.setBrush(QColor(col.red(), col.green(), col.blue(), 40))
                p.drawRoundedRect(br, br.height() / 2, br.height() / 2)
                p.setFont(bf)
                p.setPen(col)
                p.drawText(br, Qt.AlignmentFlag.AlignCenter, badge)
        if toast:
            p.setOpacity(1.0)
            fm = QFontMetricsF(af)
            tw = fm.horizontalAdvance(self.toast_text)
            r = QRectF(
                rect.left(),
                rect.bottom() + 8 * s,
                tw + 24 * s,
                fm.height() + 12 * s,
            )
            if rect.left() > self.width() / 2:
                r.moveRight(rect.right())
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(12, 12, 18, 215))
            p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
            p.setFont(af)
            p.setPen(QColor(255, 255, 255, 235))
            p.drawText(
                QPointF(r.left() + 12 * s, r.top() + 6 * s + fm.ascent()),
                self.toast_text,
            )
        p.restore()

    def draw_zones(self, p):
        p.save()
        p.setOpacity(1.0)
        _, af, _ = self.card_fonts()
        p.setFont(af)
        for z, info in zip(
            self.zones, self.profile.get("zones_interdites", []), strict=False
        ):
            p.setPen(QPen(QColor(255, 70, 70, 220), 2))
            p.setBrush(QColor(255, 40, 40, 55))
            p.drawRect(z)
            p.setPen(QColor(255, 255, 255, 230))
            p.drawText(
                z.adjusted(8, 6, -8, -6),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                info.get("nom", ""),
            )
        p.setPen(QPen(QColor(120, 200, 255, 160), 1.5, Qt.PenStyle.DashLine))
        y = self.height() * UPPER
        p.drawLine(QPointF(0, y), QPointF(self.width(), y))
        p.restore()
