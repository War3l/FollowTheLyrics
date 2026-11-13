import bisect
import math
import re

from PyQt6.QtCore import QPointF
from PyQt6.QtCore import QRectF
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush
from PyQt6.QtGui import QColor
from PyQt6.QtGui import QFont
from PyQt6.QtGui import QFontMetricsF
from PyQt6.QtGui import QLinearGradient
from PyQt6.QtGui import QPainterPath
from PyQt6.QtGui import QPen
from PyQt6.QtGui import QPolygonF
from PyQt6.QtGui import QRadialGradient

BADGE_TIME = 7.0
WORD_TIME = 2.4
MAX_SPARKS = 1300
LEVELS = 6

HUES = [45, 28, 355, 325, 275, 190, 130]


def clamp(x, lo=0.0, hi=1.0):
    return lo if x < lo else hi if x > hi else x


def ease_out(x):
    return 1 - (1 - x) ** 3


def ease_out_back(x):
    c = 1.70158
    return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2


def _squash(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def pick(track, overlay):
    title, artist = (
        _squash(getattr(track, "title", "")),
        _squash(getattr(track, "artist", "")),
    )
    for show in SHOWS:
        if show.title_key in title and show.artist_key in title + artist:
            return show(overlay)
    return None


class FireworkShow:
    name = "Firework"
    title_key = "firework"
    artist_key = "katyperry"
    pattern = r"firework"
    WORD = "FIREWORK"

    def __init__(self, overlay):
        self.o = overlay
        self.rng = overlay.rng
        self.born = overlay.clock()
        self.hits = []
        self.line_hit = {}
        self.last_pos = None
        self.queue = []
        self.rockets = []
        self.sparks = []
        self.flashes = []
        self.colors = [QColor.fromHsv(h, 215, 255) for h in HUES] + [
            QColor(255, 250, 235)
        ]
        self._pens = {}
        self._font = None
        s = self.unit()
        width = overlay.width()
        for dx in (-0.16, 0.16):
            self.queue.append(
                (self.born + 0.55, width * (0.5 + dx), 70 * s, 0.0, False)
            )

    def unit(self):
        return self.o.height() / 1080.0

    def set_lines(self, lines):
        o = self.o
        self.hits, self.line_hit = [], {}
        for idx, line in enumerate(lines):
            for m in re.finditer(self.pattern, line.text.lower()):
                c = m.start()
                if line.chars and c < len(line.chars):
                    t = line.chars[c][0]
                else:
                    t = line.time + (o.sung_end(idx) - line.time) * c / max(
                        1, len(line.text)
                    )
                self.hits.append(t)
                self.line_hit.setdefault(idx, t)
        self.hits.sort()
        self.last_pos = None

    def line_alpha(self, idx, pos, rect=None):
        t = self.line_hit.get(idx)
        if t is not None:
            return clamp((t - pos) / 0.15)
        st = self.word_state(pos)
        if st and rect is not None and rect.intersects(self.word_rect()):
            return 1 - clamp(st[1] / 0.15) * clamp((st[2] - pos) / 0.4)
        return 1.0

    def word_rect(self):
        width, height = self.o.width(), self.o.height()
        h = self.word_font().pixelSize() * 1.5
        return QRectF(width * 0.06, height * 0.44 - h / 2, width * 0.88, h)

    def word_state(self, pos):
        i = bisect.bisect_right(self.hits, pos) - 1
        if i < 0:
            return None
        t = self.hits[i]
        end = t + WORD_TIME
        if pos >= end:
            return None
        return i, pos - t, end

    def busy(self, now, pos):
        return bool(
            now - self.born < BADGE_TIME
            or self.word_state(pos)
            or self.active(now)
        )

    def active(self, now):
        return bool(self.sparks or self.rockets or self.queue or self.flashes)

    def word_colors(self, i):
        return self.colors[i % len(HUES)], [
            self.colors[(i + j * 2) % len(HUES)].lighter(125) for j in range(5)
        ]

    def tick(self, now, dt, pos):
        if self.last_pos is not None and 0 < pos - self.last_pos < 1.0:
            for i, t in enumerate(self.hits):
                if self.last_pos < t <= pos:
                    self.fire(i, now)
        self.last_pos = pos
        self.update(now, dt)

    def update(self, now, dt):
        if self.queue:
            later = []
            for q in self.queue:
                if q[0] > now:
                    later.append(q)
                elif q[4]:
                    self.launch(q[1], q[2], q[3], now)
                else:
                    self.burst(q[1], q[2], q[3], now)
            self.queue = later

        flying = []
        for r in self.rockets:
            if now >= r["t1"]:
                self.burst(r["x1"], r["y1"], r["k"], now)
            else:
                flying.append(r)
        self.rockets = flying

        g, alive = 150 * self.unit(), []
        for sp in self.sparks:
            sp[4] -= dt
            if sp[4] <= 0:
                continue
            drag = math.exp(-sp[8] * dt)
            sp[2] *= drag
            sp[3] = sp[3] * drag + g * sp[9] * dt
            sp[0] += sp[2] * dt
            sp[1] += sp[3] * dt
            alive.append(sp)
        self.sparks = alive
        self.flashes = [f for f in self.flashes if now - f[2] < 0.22]

    def fire(self, i, now):
        n = len(self.hits)
        k = (i + 1) / n
        width, height = self.o.width(), self.o.height()
        rnd = self.rng
        for side in (0.22, 0.78):
            self.burst(
                width * (side + rnd.uniform(-0.06, 0.06)),
                height * rnd.uniform(0.16, 0.34),
                k,
                now,
            )
        count = 2 + round(20 * k**1.5)
        span = 0.5 + 1.9 * k
        for _ in range(count):
            self.queue.append(
                (
                    now + rnd.uniform(0.0, span),
                    width * rnd.uniform(0.06, 0.94),
                    height * rnd.uniform(0.10, 0.58),
                    k,
                    True,
                )
            )
        if i == n - 1:
            for j in range(75):
                self.queue.append(
                    (
                        now + 0.6 + j * 0.11 + rnd.uniform(0, 0.1),
                        width * rnd.uniform(0.05, 0.95),
                        height * rnd.uniform(0.08, 0.62),
                        1.0,
                        j % 3 != 0,
                    )
                )

    def launch(self, x, y, k, now):
        height = self.o.height()
        dur = self.rng.uniform(0.45, 0.75)
        self.rockets.append(
            {
                "x0": x + self.rng.uniform(-90, 90) * self.unit(),
                "x1": x,
                "y1": y,
                "y0": height + 10,
                "t0": now,
                "t1": now + dur,
                "k": k,
                "col": self.rng.randrange(len(HUES)),
            }
        )

    def burst(self, x, y, k, now):
        rnd = self.rng
        s = self.unit()
        room = MAX_SPARKS - len(self.sparks)
        n = min(int(36 + 44 * k), room)
        if n < 8:
            return
        col = rnd.randrange(len(HUES))
        second = rnd.randrange(len(HUES)) if rnd.random() < 0.35 else col
        white = len(self.colors) - 1
        kind = rnd.choice(("ball", "ball", "ring", "willow"))
        speed = rnd.uniform(300, 430) * s * (0.6 if k <= 0 else 0.85 + 0.45 * k)
        for j in range(n):
            a = math.tau * (j + rnd.random()) / n
            if kind == "ring":
                v, life, drag, grav = (
                    speed * rnd.uniform(0.95, 1.05),
                    rnd.uniform(0.9, 1.3),
                    1.9,
                    0.7,
                )
            elif kind == "willow":
                v, life, drag, grav = (
                    speed * rnd.uniform(0.3, 1.0),
                    rnd.uniform(1.6, 2.3),
                    2.3,
                    1.1,
                )
            else:
                v, life, drag, grav = (
                    speed * math.sqrt(rnd.random()) * 1.1,
                    rnd.uniform(0.8, 1.5),
                    1.7,
                    0.9,
                )
            c = (
                0
                if kind == "willow"
                else (
                    white if rnd.random() < 0.12 else (col if j % 2 else second)
                )
            )
            self.sparks.append(
                [
                    x,
                    y,
                    math.cos(a) * v,
                    math.sin(a) * v,
                    life,
                    life,
                    c,
                    rnd.choice((1, 1, 2)),
                    drag,
                    grav,
                    rnd.uniform(0, 6.28),
                ]
            )
        self.flashes.append((x, y, now, col, (90 + 70 * max(k, 0)) * s))

    def pen(self, col, level, size):
        key = (col, level, size)
        pen = self._pens.get(key)
        if pen is None:
            c = QColor(self.colors[col])
            c.setAlphaF(level / LEVELS)
            pen = QPen(c, (2.2 + 1.5 * size) * self.unit())
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            self._pens[key] = pen
        return pen

    def draw(self, p, now, pos):
        if self.o.alpha < 0.003:
            return
        p.save()
        p.setOpacity(self.o.alpha)
        self.draw_fx(p, now)
        p.restore()
        self.draw_word(p, pos)
        self.draw_badge(p, now)

    def draw_fx(self, p, now):
        p.setPen(Qt.PenStyle.NoPen)
        for x, y, t0, col, radius in self.flashes:
            k = clamp((now - t0) / 0.22)
            grad = QRadialGradient(QPointF(x, y), radius * (0.5 + k))
            c0, c1 = (
                QColor(255, 255, 255, int(230 * (1 - k))),
                QColor(self.colors[col]),
            )
            c1.setAlpha(0)
            grad.setColorAt(0, c0)
            grad.setColorAt(1, c1)
            p.setBrush(QBrush(grad))
            p.drawEllipse(QPointF(x, y), radius * (0.5 + k), radius * (0.5 + k))
        for r in self.rockets:
            u = clamp((now - r["t0"]) / (r["t1"] - r["t0"]))
            e, e0 = ease_out(u), ease_out(max(0.0, u - 0.12))
            x, y = (
                r["x0"] + (r["x1"] - r["x0"]) * e,
                r["y0"] + (r["y1"] - r["y0"]) * e,
            )
            x0, y0 = (
                r["x0"] + (r["x1"] - r["x0"]) * e0,
                r["y0"] + (r["y1"] - r["y0"]) * e0,
            )
            p.setPen(self.pen(0, 3, 1))
            p.drawLine(QPointF(x0, y0), QPointF(x, y))
            p.setPen(self.pen(len(self.colors) - 1, LEVELS, 2))
            p.drawPoint(QPointF(x, y))
        for sp in self.sparks:
            f = sp[4] / sp[5]
            if f < 0.45 and math.sin(sp[4] * 38 + sp[10]) < -0.2:
                continue
            level = max(1, min(LEVELS, int(f * 1.6 * LEVELS) + 1))
            p.setPen(self.pen(sp[6], level, sp[7]))
            p.drawLine(
                QPointF(sp[0] - sp[2] * 0.045, sp[1] - sp[3] * 0.045),
                QPointF(sp[0], sp[1]),
            )

    def word_font(self):
        base = self.o.main_font()
        key = (base.family(), self.o.width(), self.o.height())
        if self._font is None or self._font[0] != key:
            width, height = self.o.width(), self.o.height()
            probe = QFont(base)
            probe.setPixelSize(100)
            probe.setBold(True)
            w100 = max(1.0, QFontMetricsF(probe).horizontalAdvance(self.WORD))
            font = QFont(probe)
            font.setPixelSize(
                int(min(height * 0.30, 100 * width * 0.78 / w100))
            )
            self._font = (key, font)
        return self._font[1]

    def draw_word(self, p, pos):
        st = self.word_state(pos)
        if not st:
            return
        i, u, end = st
        o = self.o
        k = clamp(u / 0.32)
        out = clamp((end - pos) / 0.5)
        a = ease_out(clamp(k * 1.8)) * out
        if a <= 0.003:
            return
        font = self.word_font()
        fm = QFontMetricsF(font)
        tw = fm.horizontalAdvance(self.WORD)
        width, height = o.width(), o.height()
        shake = 9 * self.unit() * math.exp(-u * 5)
        sc = (
            (0.3 + 0.7 * ease_out_back(k))
            * (1 + 0.035 * u)
            * (1 + 0.06 * o.beat_pulse())
        )
        p.save()
        p.setOpacity(clamp(o.alpha * a))
        p.translate(
            width / 2 + shake * math.sin(u * 70),
            height * 0.44 + shake * math.cos(u * 57),
        )
        p.rotate((-2.5, 2.0, -1.5, 2.5)[i % 4])
        p.scale(sc, sc)
        x, y = -tw / 2, fm.ascent() - fm.height() / 2
        px = min(font.pixelSize(), 110)
        o.blit_halo(
            p,
            self.WORD,
            font,
            x,
            y,
            QColor(0, 0, 0),
            px * 0.09,
            2.0,
            0.7,
            px * 0.05,
        )
        glow, cols = self.word_colors(i)
        o.blit_halo(p, self.WORD, font, x, y, glow, px * 0.5, 1.7, 0.9)
        grad = QLinearGradient(x, 0, x + tw, 0)
        for j, c in enumerate(cols):
            grad.setColorAt(j / (len(cols) - 1), c)
        path = QPainterPath()
        path.addText(QPointF(x, y), font, self.WORD)
        p.fillPath(path, QBrush(grad))
        p.setPen(QPen(QColor(255, 255, 255, 200), max(1.5, px * 0.02)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.restore()

    def draw_badge(self, p, now):
        age = now - self.born
        if age >= BADGE_TIME:
            return
        o = self.o
        s = o.cfg["scale"] * self.unit()
        a = ease_out(clamp(age / 0.5)) * clamp((BADGE_TIME - age) / 0.7)
        big = QFont(o.main_font())
        big.setPixelSize(int(30 * s))
        big.setBold(True)
        big.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 118)
        small = QFont(o.main_font())
        small.setPixelSize(int(15 * s))
        title, sub = "EASTER EGG", f"{self.name} · attends le refrain…"
        fb, fs = QFontMetricsF(big), QFontMetricsF(small)
        star = 26 * s
        w = (
            max(
                fb.horizontalAdvance(title) + 2 * star + 16 * s,
                fs.horizontalAdvance(sub),
            )
            + 44 * s
        )
        h = fb.height() + fs.height() + 20 * s
        rect = QRectF((o.width() - w) / 2, 18 * s, w, h)
        card = o.card_rect() if o.card_visible() else None
        if card is not None and card.adjusted(-10, -10, 10, 10).intersects(
            rect
        ):
            rect.moveTop(card.bottom() + 12 * s)
        p.save()
        p.setOpacity(clamp(o.alpha * a))
        p.translate(0, -30 * s * (1 - ease_out_back(clamp(age / 0.5))))
        shine = 0.5 + 0.5 * math.sin(age * 5)
        gold = QColor.fromHsv(45, int(150 + 60 * shine), 255)
        p.setPen(QPen(gold, 2 * s))
        p.setBrush(QColor(14, 12, 24, 215))
        p.drawRoundedRect(rect, h / 2, h / 2)
        grad = QLinearGradient(rect.left(), 0, rect.right(), 0)
        shift = (age * 0.35) % 1.0
        for j in range(6):
            grad.setColorAt(
                j / 5, QColor.fromHsvF((shift + j / 5 * 0.6) % 1.0, 0.55, 1.0)
            )
        tw = fb.horizontalAdvance(title)
        base = rect.top() + 9 * s + fb.ascent()
        path = QPainterPath()
        path.addText(QPointF(rect.center().x() - tw / 2, base), big, title)
        p.setPen(Qt.PenStyle.NoPen)
        p.fillPath(path, QBrush(grad))
        for side in (-1, 1):
            cx = rect.center().x() + side * (tw / 2 + star * 0.75)
            cy = base - fb.ascent() * 0.38
            r = star * 0.36 * (0.85 + 0.25 * math.sin(age * 6 + side))
            sp = QPainterPath()
            for j in range(8):
                ang = age * 1.5 * side + j * math.pi / 4
                rr = r if j % 2 == 0 else r * 0.38
                pt = QPointF(cx + rr * math.cos(ang), cy + rr * math.sin(ang))
                if j:
                    sp.lineTo(pt)
                else:
                    sp.moveTo(pt)
            sp.closeSubpath()
            p.fillPath(sp, gold)
        p.setFont(small)
        p.setPen(QColor(235, 235, 245, 220))
        p.drawText(
            QRectF(
                rect.left(),
                base + fb.descent() + 1 * s,
                rect.width(),
                fs.height(),
            ),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            sub,
        )
        p.restore()


class ThunderShow(FireworkShow):
    name, title_key, artist_key = "Thunderstruck", "thunderstruck", "acdc"
    pattern, WORD = r"thunder", "THUNDER"

    def __init__(self, overlay):
        super().__init__(overlay)
        self.queue = [(self.born + 0.6, 0.0)]
        self.bolts = []
        self.flash_t, self.flash_k = -99.0, 0.0

    def active(self, now):
        return bool(self.bolts or self.queue or now - self.flash_t < 0.35)

    def word_colors(self, i):
        return QColor(110, 165, 255), [
            QColor(215, 232, 255),
            QColor(255, 255, 255),
            QColor(150, 195, 255),
            QColor(255, 255, 255),
            QColor(200, 222, 255),
        ]

    def fire(self, i, now):
        rnd = self.rng
        k = (i + 1) / len(self.hits)
        for j in range(1 + int(2.6 * k)):
            self.queue.append((now + j * rnd.uniform(0.06, 0.2), k))
        if i == len(self.hits) - 1:
            t = now + 0.4
            for _ in range(34):
                t += rnd.uniform(0.06, 0.3)
                self.queue.append((t, 1.0))

    def update(self, now, dt):
        if self.queue:
            later = []
            for t, k in self.queue:
                if t > now:
                    later.append((t, k))
                else:
                    self.strike(now, k)
            self.queue = later
        self.bolts = [b for b in self.bolts if now - b[0] < b[1]]

    def strike(self, now, k):
        rnd = self.rng
        width, height = self.o.width(), self.o.height()
        s = self.unit()
        depth = height * (
            rnd.uniform(0.14, 0.22) if k <= 0 else rnd.uniform(0.42, 0.9)
        )
        steps = 9 if k <= 0 else rnd.randint(13, 19)
        x, y = (
            width
            * (rnd.choice((0.32, 0.68)) if k <= 0 else rnd.uniform(0.05, 0.95)),
            -8.0,
        )
        drift = rnd.uniform(-0.35, 0.35) * depth / steps
        pts = [QPointF(x, y)]
        for _ in range(steps):
            x += drift + rnd.uniform(-46, 46) * s
            y += depth / steps * rnd.uniform(0.7, 1.3)
            pts.append(QPointF(x, y))
        lines = [(QPolygonF(pts), 1.0)]
        for _ in range(0 if k <= 0 else rnd.randint(1, 3)):
            j = rnd.randrange(2, len(pts) - 2)
            bx, by = pts[j].x(), pts[j].y()
            side = rnd.choice((-1, 1))
            branch = [QPointF(bx, by)]
            for _ in range(rnd.randint(3, 6)):
                bx += side * rnd.uniform(18, 60) * s
                by += rnd.uniform(14, 52) * s
                branch.append(QPointF(bx, by))
            lines.append((QPolygonF(branch), 0.55))
        self.bolts.append(
            (now, rnd.uniform(0.3, 0.5), lines, rnd.uniform(0, 6.28))
        )
        if k > 0:
            self.flash_t, self.flash_k = now, 0.05 + 0.07 * k

    def draw_fx(self, p, now):
        s = self.unit()
        age = now - self.flash_t
        if age < 0.35:
            a = self.flash_k * math.exp(-age * 9)
            p.fillRect(self.o.rect(), QColor(190, 215, 255, int(255 * a)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        for t0, life, lines, phase in self.bolts:
            u = (now - t0) / life
            a = (1 - u) * (0.65 + 0.35 * math.sin(u * 34 + phase))
            for poly, w in lines:
                for width, col in (
                    (16 * s * w, QColor(90, 140, 255, int(60 * a))),
                    (6 * s * w, QColor(170, 205, 255, int(170 * a))),
                    (2.2 * s * w, QColor(255, 255, 255, int(255 * a))),
                ):
                    pen = QPen(col, width)
                    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                    p.setPen(pen)
                    p.drawPolyline(poly)


class LightsShow(FireworkShow):
    name, title_key, artist_key = "Blinding Lights", "blindinglights", "weeknd"
    pattern, WORD = r"lights?", "LIGHTS"
    NEONS = (
        QColor(255, 45, 85),
        QColor(255, 50, 190),
        QColor(255, 125, 40),
        QColor(165, 70, 255),
    )

    def __init__(self, overlay):
        super().__init__(overlay)
        self.queue = [
            (self.born + 0.5, "beam", 0.3),
            (self.born + 0.8, "beam", 0.3),
        ]
        self.beams = []
        self.glares = []

    def active(self, now):
        return bool(self.beams or self.glares or self.queue)

    def word_colors(self, i):
        n = self.NEONS
        return n[i % 2], [
            n[2].lighter(125),
            n[0].lighter(120),
            n[1].lighter(125),
            n[3].lighter(135),
            n[1].lighter(125),
        ]

    def fire(self, i, now):
        rnd = self.rng
        k = (i + 1) / len(self.hits)
        self.queue.append((now, "glare", k))
        for _ in range(2 + int(5 * k)):
            self.queue.append((now + rnd.uniform(0, 0.5 + k), "beam", k))
        if i == len(self.hits) - 1:
            for j in range(40):
                self.queue.append(
                    (now + 0.5 + j * 0.16 + rnd.uniform(0, 0.1), "beam", 1.0)
                )
            for j in range(5):
                self.queue.append((now + 1.2 + j * 1.2, "glare", 1.0))

    def update(self, now, dt):
        if self.queue:
            rnd = self.rng
            width, height = self.o.width(), self.o.height()
            later = []
            for q in self.queue:
                if q[0] > now:
                    later.append(q)
                    continue
                k = q[2]
                if q[1] == "beam":
                    top = rnd.random() < 0.5
                    mid = math.pi / 2 if top else -math.pi / 2
                    a0 = mid + rnd.uniform(-0.75, 0.75)
                    a1 = a0 + rnd.choice((-1, 1)) * rnd.uniform(0.35, 0.9)
                    self.beams.append(
                        (
                            now,
                            rnd.uniform(1.1, 1.8),
                            width * rnd.uniform(0.05, 0.95),
                            top,
                            a0,
                            a1,
                            rnd.randrange(len(self.NEONS)),
                            rnd.uniform(0.035, 0.07),
                        )
                    )
                else:
                    self.glares.append(
                        (
                            now,
                            0.9,
                            width * rnd.choice((0.14, 0.86))
                            + rnd.uniform(-60, 60),
                            height * rnd.uniform(0.18, 0.4),
                            height * (0.28 + 0.2 * k),
                            rnd.randrange(len(self.NEONS)),
                        )
                    )
            self.queue = later
        self.beams = [b for b in self.beams if now - b[0] < b[1]]
        self.glares = [g for g in self.glares if now - g[0] < g[1]]

    def draw_fx(self, p, now):
        height = self.o.height()
        length = height * 1.35
        p.setPen(Qt.PenStyle.NoPen)
        for t0, life, x, top, a0, a1, col, half in self.beams:
            u = (now - t0) / life
            ang = a0 + (a1 - a0) * u * u * (3 - 2 * u)
            a = math.sin(math.pi * u)
            o = QPointF(x, -20.0 if top else height + 20.0)
            c0, c1 = QColor(self.NEONS[col]), QColor(self.NEONS[col])
            c0.setAlpha(int(165 * a))
            c1.setAlpha(0)
            grad = QLinearGradient(
                o,
                QPointF(
                    o.x() + length * math.cos(ang),
                    o.y() + length * math.sin(ang),
                ),
            )
            grad.setColorAt(0, c0)
            grad.setColorAt(1, c1)
            p.setBrush(QBrush(grad))
            p.drawPolygon(
                QPolygonF(
                    [
                        o,
                        QPointF(
                            o.x() + length * math.cos(ang - half),
                            o.y() + length * math.sin(ang - half),
                        ),
                        QPointF(
                            o.x() + length * math.cos(ang + half),
                            o.y() + length * math.sin(ang + half),
                        ),
                    ]
                )
            )
        for t0, life, x, y, radius, col in self.glares:
            u = (now - t0) / life
            a = (1 - u) ** 2
            r = radius * (0.55 + 0.7 * u)
            c1, c2 = QColor(self.NEONS[col]), QColor(self.NEONS[col])
            c1.setAlpha(int(120 * a))
            c2.setAlpha(0)
            grad = QRadialGradient(QPointF(x, y), r)
            grad.setColorAt(0, QColor(255, 255, 255, int(150 * a)))
            grad.setColorAt(0.25, c1)
            grad.setColorAt(1, c2)
            p.setBrush(QBrush(grad))
            p.drawEllipse(QPointF(x, y), r, r)
            streak = QLinearGradient(
                QPointF(x - r * 2.4, y), QPointF(x + r * 2.4, y)
            )
            streak.setColorAt(0, QColor(255, 255, 255, 0))
            streak.setColorAt(0.5, QColor(255, 255, 255, int(200 * a)))
            streak.setColorAt(1, QColor(255, 255, 255, 0))
            p.setBrush(QBrush(streak))
            p.drawEllipse(QPointF(x, y), r * 2.4, max(1.5, r * 0.025))


def _gem_path():
    path = QPainterPath()
    path.addPolygon(
        QPolygonF(
            [
                QPointF(-0.5, -0.15),
                QPointF(-0.28, -0.42),
                QPointF(0.28, -0.42),
                QPointF(0.5, -0.15),
                QPointF(0.0, 0.5),
            ]
        )
    )
    path.closeSubpath()
    return path


def _star_path():
    path = QPainterPath()
    for j in range(8):
        r = 1.0 if j % 2 == 0 else 0.16
        pt = QPointF(
            r * math.cos(j * math.pi / 4), r * math.sin(j * math.pi / 4)
        )
        if j:
            path.lineTo(pt)
        else:
            path.moveTo(pt)
    path.closeSubpath()
    return path


class DiamondShow(FireworkShow):
    name, title_key, artist_key = "Diamonds", "diamonds", "rihanna"
    pattern, WORD = r"diamonds?", "DIAMONDS"
    MAX_GEMS = 170
    FACETS = (
        (-0.5, -0.15, 0.5, -0.15),
        (-0.18, -0.15, 0.0, 0.5),
        (0.18, -0.15, 0.0, 0.5),
        (-0.28, -0.42, -0.18, -0.15),
        (0.28, -0.42, 0.18, -0.15),
        (0.0, -0.42, -0.18, -0.15),
        (0.0, -0.42, 0.18, -0.15),
    )

    def __init__(self, overlay):
        super().__init__(overlay)
        self.queue = []
        self.gems = []
        self.twinkles = []
        self.gem, self.star = _gem_path(), _star_path()
        self.brushes = []
        for top, low in (
            (QColor(255, 255, 255), QColor(90, 205, 255)),
            (QColor(245, 240, 255), QColor(170, 140, 255)),
            (QColor(255, 255, 255), QColor(150, 235, 235)),
        ):
            g = QLinearGradient(QPointF(-0.4, -0.45), QPointF(0.3, 0.5))
            g.setColorAt(0, top)
            g.setColorAt(0.45, low.lighter(140))
            g.setColorAt(1, low)
            self.brushes.append(QBrush(g))
        width, s = overlay.width(), self.unit()
        for dx in (-0.15, -0.12, 0.12, 0.15):
            self.twinkles.append(
                (
                    self.born + 0.5 + abs(dx),
                    0.9,
                    width * (0.5 + dx),
                    60 * s,
                    22 * s,
                )
            )

    def active(self, now):
        return bool(self.gems or self.twinkles or self.queue)

    def word_colors(self, i):
        return QColor(90, 210, 255), [
            QColor(190, 240, 255),
            QColor(255, 255, 255),
            QColor(160, 215, 255),
            QColor(225, 205, 255),
            QColor(255, 255, 255),
            QColor(170, 235, 255),
        ]

    def fire(self, i, now):
        rnd = self.rng
        k = (i + 1) / len(self.hits)
        width, height = self.o.width(), self.o.height()
        s = self.unit()
        for _ in range(6 + int(24 * k)):
            a = rnd.uniform(-math.pi, 0)
            v = rnd.uniform(380, 900) * s * (0.8 + 0.4 * k)
            self.add_gem(
                width * rnd.uniform(0.2, 0.8),
                height * 0.44,
                math.cos(a) * v,
                math.sin(a) * v,
                k,
            )
        for _ in range(8 + int(22 * k)):
            self.twinkles.append(
                (
                    now + rnd.uniform(0, 1.2),
                    rnd.uniform(0.5, 1.0),
                    width * rnd.random(),
                    height * rnd.uniform(0.03, 0.75),
                    rnd.uniform(14, 34) * s * (1 + 0.6 * k),
                )
            )
        if i == len(self.hits) - 1:
            for j in range(130):
                self.queue.append((now + 0.5 + j * 0.055, "rain"))
            for j in range(60):
                self.queue.append((now + 0.5 + j * 0.12, "twinkle"))

    def add_gem(self, x, y, vx, vy, k):
        if len(self.gems) >= self.MAX_GEMS:
            return
        rnd = self.rng
        life = rnd.uniform(1.8, 2.8)
        self.gems.append(
            [
                x,
                y,
                vx,
                vy,
                rnd.uniform(-40, 40),
                rnd.uniform(-200, 200),
                rnd.uniform(36, 76) * self.unit() * (0.85 + 0.4 * k),
                life,
                life,
                rnd.randrange(3),
            ]
        )

    def update(self, now, dt):
        rnd = self.rng
        width, height = self.o.width(), self.o.height()
        s = self.unit()
        if self.queue:
            later = []
            for q in self.queue:
                if q[0] > now:
                    later.append(q)
                elif q[1] == "rain":
                    self.add_gem(
                        width * rnd.random(),
                        -40 * s,
                        rnd.uniform(-60, 60) * s,
                        rnd.uniform(150, 420) * s,
                        1.0,
                    )
                else:
                    self.twinkles.append(
                        (
                            now,
                            rnd.uniform(0.5, 1.0),
                            width * rnd.random(),
                            height * rnd.uniform(0.03, 0.8),
                            rnd.uniform(18, 46) * s,
                        )
                    )
            self.queue = later
        g, alive = 780 * s, []
        for gem in self.gems:
            gem[7] -= dt
            if gem[7] <= 0 or gem[1] > height + 80:
                continue
            gem[3] += g * dt
            gem[0] += gem[2] * dt
            gem[1] += gem[3] * dt
            gem[4] += gem[5] * dt
            alive.append(gem)
        self.gems = alive
        self.twinkles = [t for t in self.twinkles if now - t[0] < t[1]]

    def draw_fx(self, p, now):
        base = p.opacity()
        edge = QPen(QColor(255, 255, 255, 235), 0.035)
        facet = QPen(QColor(255, 255, 255, 150), 0.022)
        for x, y, _vx, _vy, rot, _vr, size, life, full, tint in self.gems:
            p.save()
            p.setOpacity(base * clamp(life / 0.5) * clamp((full - life) / 0.12))
            p.translate(x, y)
            p.rotate(rot)
            p.scale(size, size)
            p.setPen(edge)
            p.setBrush(self.brushes[tint])
            p.drawPath(self.gem)
            p.setPen(facet)
            for x0, y0, x1, y1 in self.FACETS:
                p.drawLine(QPointF(x0, y0), QPointF(x1, y1))
            p.restore()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255))
        for t0, life, x, y, size in self.twinkles:
            u = (now - t0) / life
            if u < 0:
                continue
            k = math.sin(math.pi * u)
            p.save()
            p.setOpacity(base * k)
            p.translate(x, y)
            p.rotate(u * 50)
            p.scale(size * k, size * k)
            p.drawPath(self.star)
            p.restore()


SHOWS = [FireworkShow, ThunderShow, LightsShow, DiamondShow]
