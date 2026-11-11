"""Easter eggs : des morceaux precis qui declenchent un spectacle a part.

Pour l'instant un seul : « Firework » de Katy Perry. A chaque fois que le mot est chante,
il s'affiche en geant au milieu de l'ecran a la place de la ligne, avec des feux d'artifice.
Plus la chanson avance, plus il y en a ; le dernier declenche le bouquet final.
"""
import bisect
import math
import re

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (QBrush, QColor, QFont, QFontMetricsF, QLinearGradient, QPainterPath, QPen,
                         QRadialGradient)

BADGE_TIME = 7.0     # duree du bandeau « EASTER EGG » en debut de morceau
WORD_TIME = 2.4      # duree du mot geant
MAX_SPARKS = 1300
LEVELS = 6           # niveaux d'opacite des etincelles (les stylos sont prepares une fois)

# teintes des fusees : or, orange, rouge, rose, violet, cyan, vert
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
    """Le spectacle qui va avec ce morceau, ou None (presque toujours)."""
    title, artist = _squash(getattr(track, "title", "")), _squash(getattr(track, "artist", ""))
    if "firework" in title and "katyperry" in title + artist:
        return FireworkShow(overlay)
    return None


class FireworkShow:
    WORD = "FIREWORK"
    name = "Firework"

    def __init__(self, overlay):
        self.o = overlay
        self.rng = overlay.rng
        self.born = overlay.clock()
        self.hits = []        # moments (s) ou le mot est chante
        self.line_hit = {}    # ligne -> moment du premier mot de cette ligne
        self.last_pos = None
        self.queue = []       # (heure, x, y, force, fusee ?)
        self.rockets = []
        self.sparks = []
        self.flashes = []
        self.colors = [QColor.fromHsv(h, 215, 255) for h in HUES] + [QColor(255, 250, 235)]
        self._pens = {}
        self._font = None
        s = self.unit()
        W = overlay.width()
        for dx in (-0.16, 0.16):  # deux petites gerbes de chaque cote du bandeau
            self.queue.append((self.born + 0.55, W * (0.5 + dx), 70 * s, 0.0, False))

    def unit(self):
        return self.o.height() / 1080.0

    # ---- ou le mot est-il chante ? ------------------------------------------
    def set_lines(self, lines):
        o = self.o
        self.hits, self.line_hit = [], {}
        for idx, line in enumerate(lines):
            for m in re.finditer(r"firework", line.text.lower()):
                c = m.start()
                if line.chars and c < len(line.chars):
                    t = line.chars[c][0]
                else:  # pas de timing mot par mot : on estime d'apres la place dans la ligne
                    t = line.time + (o.sung_end(idx) - line.time) * c / max(1, len(line.text))
                self.hits.append(t)
                self.line_hit.setdefault(idx, t)
        self.hits.sort()
        self.last_pos = None

    def line_alpha(self, idx, pos, rect=None):
        """La ligne normale s'efface au moment ou le mot geant la remplace ; les autres
        lignes se cachent le temps du mot si elles sont dessous."""
        t = self.line_hit.get(idx)
        if t is not None:
            return clamp((t - pos) / 0.15)
        st = self.word_state(pos)
        if st and rect is not None and rect.intersects(self.word_rect()):
            return 1 - clamp(st[1] / 0.15) * clamp((st[2] - pos) / 0.4)
        return 1.0

    def word_rect(self):
        W, H = self.o.width(), self.o.height()
        h = self.word_font().pixelSize() * 1.5
        return QRectF(W * 0.06, H * 0.44 - h / 2, W * 0.88, h)

    def word_state(self, pos):
        """-> (numero, secondes depuis le debut, fin) du mot geant a l'ecran, ou None."""
        i = bisect.bisect_right(self.hits, pos) - 1
        if i < 0:
            return None
        t = self.hits[i]
        end = t + WORD_TIME
        if pos >= end:
            return None
        return i, pos - t, end

    def busy(self, now, pos):
        return bool(self.sparks or self.rockets or self.queue or self.flashes
                    or now - self.born < BADGE_TIME or self.word_state(pos))

    # ---- animation ---------------------------------------------------------------
    def tick(self, now, dt, pos):
        if self.last_pos is not None and 0 < pos - self.last_pos < 1.0:  # pas un saut dans le morceau
            for i, t in enumerate(self.hits):
                if self.last_pos < t <= pos:
                    self.fire(i, now)
        self.last_pos = pos

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
        """Le mot vient d'etre chante pour la (i+1)e fois : de plus en plus de fusees."""
        n = len(self.hits)
        k = (i + 1) / n
        W, H = self.o.width(), self.o.height()
        rnd = self.rng
        # deux explosions tout de suite, de part et d'autre du mot
        for side in (0.22, 0.78):
            self.burst(W * (side + rnd.uniform(-0.06, 0.06)), H * rnd.uniform(0.16, 0.34), k, now)
        count = 2 + round(20 * k ** 1.5)
        span = 0.5 + 1.9 * k
        for _ in range(count):
            self.queue.append((now + rnd.uniform(0.0, span), W * rnd.uniform(0.06, 0.94),
                               H * rnd.uniform(0.10, 0.58), k, True))
        if i == n - 1:  # bouquet final
            for j in range(75):
                self.queue.append((now + 0.6 + j * 0.11 + rnd.uniform(0, 0.1), W * rnd.uniform(0.05, 0.95),
                                   H * rnd.uniform(0.08, 0.62), 1.0, j % 3 != 0))

    def launch(self, x, y, k, now):
        H = self.o.height()
        dur = self.rng.uniform(0.45, 0.75)
        self.rockets.append({"x0": x + self.rng.uniform(-90, 90) * self.unit(), "x1": x, "y1": y, "y0": H + 10,
                             "t0": now, "t1": now + dur, "k": k, "col": self.rng.randrange(len(HUES))})

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
                v, life, drag, grav = speed * rnd.uniform(0.95, 1.05), rnd.uniform(0.9, 1.3), 1.9, 0.7
            elif kind == "willow":
                v, life, drag, grav = speed * rnd.uniform(0.3, 1.0), rnd.uniform(1.6, 2.3), 2.3, 1.1
            else:
                v, life, drag, grav = speed * math.sqrt(rnd.random()) * 1.1, rnd.uniform(0.8, 1.5), 1.7, 0.9
            c = 0 if kind == "willow" else (white if rnd.random() < 0.12 else (col if j % 2 else second))
            # x, y, vx, vy, vie, vie max, couleur, taille, frein, poids, scintillement
            self.sparks.append([x, y, math.cos(a) * v, math.sin(a) * v, life, life, c,
                                rnd.choice((1, 1, 2)), drag, grav, rnd.uniform(0, 6.28)])
        self.flashes.append((x, y, now, col, (90 + 70 * max(k, 0)) * s))

    # ---- dessin ------------------------------------------------------------------
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
        self.draw_fireworks(p, now)
        p.restore()
        self.draw_word(p, pos)
        self.draw_badge(p, now)

    def draw_fireworks(self, p, now):
        s = self.unit()
        p.setPen(Qt.PenStyle.NoPen)
        for x, y, t0, col, radius in self.flashes:
            k = clamp((now - t0) / 0.22)
            grad = QRadialGradient(QPointF(x, y), radius * (0.5 + k))
            c0, c1 = QColor(255, 255, 255, int(230 * (1 - k))), QColor(self.colors[col])
            c1.setAlpha(0)
            grad.setColorAt(0, c0)
            grad.setColorAt(1, c1)
            p.setBrush(QBrush(grad))
            p.drawEllipse(QPointF(x, y), radius * (0.5 + k), radius * (0.5 + k))
        for r in self.rockets:
            u = clamp((now - r["t0"]) / (r["t1"] - r["t0"]))
            e, e0 = ease_out(u), ease_out(max(0.0, u - 0.12))
            x, y = r["x0"] + (r["x1"] - r["x0"]) * e, r["y0"] + (r["y1"] - r["y0"]) * e
            x0, y0 = r["x0"] + (r["x1"] - r["x0"]) * e0, r["y0"] + (r["y1"] - r["y0"]) * e0
            p.setPen(self.pen(0, 3, 1))
            p.drawLine(QPointF(x0, y0), QPointF(x, y))
            p.setPen(self.pen(len(self.colors) - 1, LEVELS, 2))
            p.drawPoint(QPointF(x, y))
        for sp in self.sparks:
            f = sp[4] / sp[5]
            if f < 0.45 and math.sin(sp[4] * 38 + sp[10]) < -0.2:
                continue  # scintille avant de s'eteindre
            level = max(1, min(LEVELS, int(f * 1.6 * LEVELS) + 1))
            p.setPen(self.pen(sp[6], level, sp[7]))
            p.drawLine(QPointF(sp[0] - sp[2] * 0.045, sp[1] - sp[3] * 0.045), QPointF(sp[0], sp[1]))

    def word_font(self):
        base = self.o.main_font()
        key = (base.family(), self.o.width(), self.o.height())
        if self._font is None or self._font[0] != key:
            W, H = self.o.width(), self.o.height()
            probe = QFont(base)
            probe.setPixelSize(100)
            probe.setBold(True)
            w100 = max(1.0, QFontMetricsF(probe).horizontalAdvance(self.WORD))
            font = QFont(probe)
            font.setPixelSize(int(min(H * 0.30, 100 * W * 0.78 / w100)))
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
        W, H = o.width(), o.height()
        shake = 9 * self.unit() * math.exp(-u * 5)
        sc = (0.3 + 0.7 * ease_out_back(k)) * (1 + 0.035 * u) * (1 + 0.06 * o.beat_pulse())
        p.save()
        p.setOpacity(clamp(o.alpha * a))
        p.translate(W / 2 + shake * math.sin(u * 70), H * 0.44 + shake * math.cos(u * 57))
        p.rotate((-2.5, 2.0, -1.5, 2.5)[i % 4])
        p.scale(sc, sc)
        x, y = -tw / 2, fm.ascent() - fm.height() / 2
        px = min(font.pixelSize(), 110)
        o.blit_halo(p, self.WORD, font, x, y, QColor(0, 0, 0), px * 0.09, 2.0, 0.7, px * 0.05)
        glow = self.colors[i % len(HUES)]
        o.blit_halo(p, self.WORD, font, x, y, glow, px * 0.5, 1.7, 0.9)
        grad = QLinearGradient(x, 0, x + tw, 0)
        for j in range(5):
            grad.setColorAt(j / 4, self.colors[(i + j * 2) % len(HUES)].lighter(125))
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
        w = max(fb.horizontalAdvance(title) + 2 * star + 16 * s, fs.horizontalAdvance(sub)) + 44 * s
        h = fb.height() + fs.height() + 20 * s
        rect = QRectF((o.width() - w) / 2, 18 * s, w, h)
        card = o.card_rect() if o.card_visible() else None
        if card is not None and card.adjusted(-10, -10, 10, 10).intersects(rect):
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
            grad.setColorAt(j / 5, QColor.fromHsvF((shift + j / 5 * 0.6) % 1.0, 0.55, 1.0))
        tw = fb.horizontalAdvance(title)
        base = rect.top() + 9 * s + fb.ascent()
        path = QPainterPath()
        path.addText(QPointF(rect.center().x() - tw / 2, base), big, title)
        p.setPen(Qt.PenStyle.NoPen)
        p.fillPath(path, QBrush(grad))
        for side in (-1, 1):  # une petite etoile de chaque cote, qui tourne et pulse
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
        p.drawText(QRectF(rect.left(), base + fb.descent() + 1 * s, rect.width(), fs.height()),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, sub)
        p.restore()
