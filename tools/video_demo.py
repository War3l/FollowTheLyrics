import math
import os
import random
import subprocess
import sys

from PyQt6.QtCore import QPointF
from PyQt6.QtCore import QRectF
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush
from PyQt6.QtGui import QColor
from PyQt6.QtGui import QFont
from PyQt6.QtGui import QImage
from PyQt6.QtGui import QLinearGradient
from PyQt6.QtGui import QPainter
from PyQt6.QtGui import QPen
from PyQt6.QtGui import QPolygonF
from PyQt6.QtGui import QRadialGradient
from PyQt6.QtWidgets import QApplication

from followthelyrics import desktop
from followthelyrics.config import games
from followthelyrics.config import settings
from followthelyrics.lyrics import demo_song
from followthelyrics.overlay import window

root, ffmpeg, dest, poster = sys.argv[1:5]
cover = sys.argv[5] if len(sys.argv) > 5 else None
os.chdir(root)

app = QApplication(sys.argv)

FPS, START, LENGTH = 30, 0.6, 15.0
fake = [0.0]
o = window.Overlay(
    dict(settings.DEFAULTS, scale=1.45),
    games.DEFAULT_PROFILES,
    desktop.current().windowing,
    clock=lambda: fake[0],
    rng=random.Random(11),
)
o.timer.stop()
o.top_timer.stop()
W, H = o.width(), o.height()
HORIZON = H * 0.56
rng = random.Random(5)
STARS = [
    (rng.random() * W, rng.random() * HORIZON * 0.9, rng.random())
    for _ in range(160)
]


def ridge(seed, base, amp, step):
    r = random.Random(seed)
    pts, x, y = [], -step, base
    while x < W * 2 + step:
        pts.append((x, y))
        x += step * (0.6 + r.random() * 0.8)
        y = base - amp * r.random()
    return pts


RIDGES = [
    (ridge(1, HORIZON, H * 0.20, 150), QColor("#1a2140"), 9.0),
    (ridge(2, HORIZON, H * 0.11, 110), QColor("#10142a"), 22.0),
]


def box(p, r, radius=10):
    p.setPen(QPen(QColor(255, 255, 255, 46), 1.5))
    p.setBrush(QColor(6, 8, 14, 150))
    p.drawRoundedRect(r, radius, radius)


def draw_game(p, t):
    sky = QLinearGradient(0, 0, 0, HORIZON)
    sky.setColorAt(0, QColor("#070912"))
    sky.setColorAt(0.7, QColor("#1b1f4a"))
    sky.setColorAt(1, QColor("#5a2c6e"))
    p.fillRect(QRectF(0, 0, W, HORIZON), QBrush(sky))
    p.setPen(Qt.PenStyle.NoPen)
    for x, y, s in STARS:
        a = 90 + 120 * (0.5 + 0.5 * math.sin(t * (1 + s * 2) + s * 40))
        p.setBrush(QColor(255, 255, 255, int(a * (0.4 + 0.6 * s))))
        p.drawEllipse(QPointF(x, y), 0.8 + s * 1.4, 0.8 + s * 1.4)
    glow = QRadialGradient(QPointF(W / 2, HORIZON), W * 0.42)
    glow.setColorAt(0, QColor(255, 120, 190, 110))
    glow.setColorAt(1, QColor(255, 120, 190, 0))
    p.fillRect(QRectF(0, 0, W, HORIZON), QBrush(glow))
    for pts, col, speed in RIDGES:
        dx = (t * speed) % W
        poly = QPolygonF(
            [QPointF(x - dx, y) for x, y in pts]
            + [QPointF(W * 2, HORIZON + 2), QPointF(-200, HORIZON + 2)]
        )
        p.setBrush(col)
        p.drawPolygon(poly)
    ground = QLinearGradient(0, HORIZON, 0, H)
    ground.setColorAt(0, QColor("#1a1030"))
    ground.setColorAt(1, QColor("#05060c"))
    p.fillRect(QRectF(0, HORIZON, W, H - HORIZON), QBrush(ground))
    for i in range(-14, 15):
        a = 70 if i else 150
        p.setPen(QPen(QColor(120, 220, 255, a), 2))
        p.drawLine(
            QPointF(W / 2 + i * 26, HORIZON), QPointF(W / 2 + i * 330, H)
        )
    phase = (t * 0.55) % 1.0
    for k in range(13):
        z = (k + phase) / 13
        y = HORIZON + (H - HORIZON) * z**2.4
        p.setPen(QPen(QColor(255, 110, 190, int(40 + 150 * z)), 1 + 2.5 * z))
        p.drawLine(QPointF(0, y), QPointF(W, y))
    f = QFont("Segoe UI", 11, QFont.Weight.DemiBold)
    p.setFont(f)
    m = QRectF(W - 330, H - 330, 300, 300)
    box(p, m)
    p.setPen(QPen(QColor(255, 255, 255, 26), 1))
    for k in range(1, 5):
        p.drawLine(
            QPointF(m.left() + k * 60, m.top()),
            QPointF(m.left() + k * 60, m.bottom()),
        )
        p.drawLine(
            QPointF(m.left(), m.top() + k * 60),
            QPointF(m.right(), m.top() + k * 60),
        )
    p.setPen(Qt.PenStyle.NoPen)
    for k, col in enumerate(
        ("#5EE7FF", "#5EE7FF", "#FF6FB5", "#FF6FB5", "#FF6FB5")
    ):
        ang = t * (0.25 + k * 0.07) + k * 1.9
        p.setBrush(QColor(col))
        p.drawEllipse(
            QPointF(
                m.center().x() + math.cos(ang) * (50 + k * 16),
                m.center().y() + math.sin(ang * 1.3) * (40 + k * 14),
            ),
            6,
            6,
        )
    p.setBrush(QColor("#ffffff"))
    p.drawEllipse(m.center(), 7, 7)
    bar = QRectF(W / 2 - 330, H - 130, 660, 100)
    box(p, bar, 14)
    for k in range(6):
        r = QRectF(bar.left() + 18 + k * 76, bar.top() + 14, 64, 64)
        p.setPen(QPen(QColor(255, 255, 255, 60), 1.5))
        p.setBrush(QColor(40, 46, 70, 220))
        p.drawRoundedRect(r, 9, 9)
        cd = (t * (0.11 + 0.05 * k) + k * 0.37) % 1.6
        if cd < 1.0:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 150))
            p.drawRoundedRect(
                QRectF(
                    r.left(),
                    r.top() + r.height() * cd,
                    r.width(),
                    r.height() * (1 - cd),
                ),
                9,
                9,
            )
        p.setPen(QColor(255, 255, 255, 150))
        p.drawText(
            r.adjusted(5, 2, 0, 0),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
            "AZERDF"[k],
        )
    for k, (col, fill) in enumerate(
        (("#58d68d", 0.78 + 0.05 * math.sin(t)), ("#5dade2", 0.52))
    ):
        r = QRectF(bar.left() + 486, bar.top() + 22 + k * 32, 156, 20)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 28))
        p.drawRoundedRect(r, 6, 6)
        p.setBrush(QColor(col))
        p.drawRoundedRect(
            QRectF(r.left(), r.top(), r.width() * fill, r.height()), 6, 6
        )
    chat = QRectF(30, H - 300, 400, 270)
    box(p, chat)
    p.setPen(Qt.PenStyle.NoPen)
    for k in range(6):
        p.setBrush(QColor(("#5EE7FF", "#FF6FB5", "#c9cedb")[k % 3]))
        p.drawRoundedRect(
            QRectF(chat.left() + 18, chat.top() + 24 + k * 40, 52, 10), 5, 5
        )
        p.setBrush(QColor(255, 255, 255, 70))
        p.drawRoundedRect(
            QRectF(
                chat.left() + 80,
                chat.top() + 24 + k * 40,
                120 + (k * 67) % 170,
                10,
            ),
            5,
            5,
        )
    p.setPen(QColor(255, 255, 255, 120))
    p.drawText(
        QRectF(W - 330, 24, 300, 30),
        Qt.AlignmentFlag.AlignRight,
        "144 FPS    23 ms",
    )


o.on_track(demo_song.demo_track(START))
o.on_lyrics(demo_song.DEMO_KEY, demo_song.DEMO_LINES)
if cover:
    with open(cover, "rb") as fh:
        o.on_cover(o.track_key, fh.read())

enc = subprocess.Popen(
    [
        ffmpeg,
        "-y",
        "-loglevel",
        "error",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgra",
        "-s",
        f"{W}x{H}",
        "-r",
        str(FPS),
        "-i",
        "-",
        "-vf",
        "scale=1280:720:flags=lanczos",
        "-c:v",
        "libx264",
        "-preset",
        "slow",
        "-crf",
        "27",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-an",
        dest,
    ],
    stdin=subprocess.PIPE,
)
img = QImage(W, H, QImage.Format.Format_ARGB32_Premultiplied)
frames = int(LENGTH * FPS)
next_beat, beat_n = 0.0, 0
for _frame in range(frames):
    for _ in range(2):
        fake[0] += 1 / (FPS * 2)
        if fake[0] >= next_beat:
            o.on_beat(1.0 if beat_n % 4 == 0 else 0.6)
            beat_n += 1
            next_beat += 0.5
        o.tick(1 / (FPS * 2))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    draw_game(p, fake[0])
    p.end()
    o.render(img)
    enc.stdin.write(bytes(img.constBits().asarray(img.sizeInBytes())))
    if abs(fake[0] - 9.4) < 0.5 / FPS:
        img.scaledToWidth(
            1280, Qt.TransformationMode.SmoothTransformation
        ).save(poster, "JPG", 82)
enc.stdin.close()
print("ffmpeg", enc.wait(), "frames", frames, flush=True)
os._exit(0)
