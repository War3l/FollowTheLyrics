import os
import random
import sys
from types import SimpleNamespace

from PyQt6.QtCore import QBuffer
from PyQt6.QtCore import QPointF
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush
from PyQt6.QtGui import QColor
from PyQt6.QtGui import QImage
from PyQt6.QtGui import QLinearGradient
from PyQt6.QtGui import QPainter
from PyQt6.QtGui import QRadialGradient
from PyQt6.QtWidgets import QApplication

from followthelyrics import desktop
from followthelyrics.config import games
from followthelyrics.config import settings
from followthelyrics.lyrics import demo_song
from followthelyrics.overlay import window

root, out = sys.argv[1], sys.argv[2]
os.chdir(root)


app = QApplication(sys.argv)

S, SH = 960, 720


def cover_bytes(c1, c2, c3):
    im = QImage(300, 300, QImage.Format.Format_RGB32)
    p = QPainter(im)
    p.fillRect(0, 0, 300, 100, QColor(c1))
    p.fillRect(0, 100, 300, 100, QColor(c2))
    p.fillRect(0, 200, 300, 100, QColor(c3))
    p.end()
    buf = QBuffer()
    buf.open(QBuffer.OpenModeFlag.WriteOnly)
    im.save(buf, "PNG")
    return bytes(buf.data())


def backdrop(colors, seed):
    im = QImage(S, SH, QImage.Format.Format_ARGB32_Premultiplied)
    im.fill(QColor("#07080d"))
    p = QPainter(im)
    r = random.Random(seed)
    for k, c in enumerate(colors * 2):
        col = QColor(c)
        cx, cy, rad = (
            r.uniform(0, S),
            r.uniform(0, SH),
            r.uniform(S * 0.45, S * 0.8),
        )
        g = QRadialGradient(QPointF(cx, cy), rad)
        g.setColorAt(
            0, QColor(col.red(), col.green(), col.blue(), 120 if k < 3 else 60)
        )
        g.setColorAt(1, QColor(col.red(), col.green(), col.blue(), 0))
        p.fillRect(im.rect(), QBrush(g))
    shade = QLinearGradient(0, 0, 0, SH)
    shade.setColorAt(0, QColor(0, 0, 0, 40))
    shade.setColorAt(1, QColor(0, 0, 0, 150))
    p.fillRect(im.rect(), QBrush(shade))
    p.end()
    return im


def make(name, at, colors, seed=3, track=None, lines=None, key=None, **cfg):
    fake = [0.0]
    o = window.Overlay(
        dict(settings.DEFAULTS, card=False, **cfg),
        games.DEFAULT_PROFILES,
        desktop.current().windowing,
        clock=lambda: fake[0],
        rng=random.Random(seed),
    )
    o.timer.stop()
    o.top_timer.stop()
    o.setGeometry(0, 0, S, SH)
    start = max(0.0, at - 8.0)
    if track is None:
        o.on_track(demo_song.demo_track(start))
        o.on_lyrics(demo_song.DEMO_KEY, demo_song.DEMO_LINES)
    else:
        o.on_track(track)
        o.on_lyrics(o.track_key, lines)
        start = 0.0
    o.on_cover(o.track_key, cover_bytes(*colors))
    o.card_since = -99
    while fake[0] < at - start:
        fake[0] += 1 / 60
        o.tick(1 / 60)
    im = backdrop(colors, seed)
    o.render(im)
    path = os.path.join(out, name + ".jpg")
    im.scaledToWidth(800, Qt.TransformationMode.SmoothTransformation).save(
        path, "JPG", 84
    )
    print(name, o.width(), o.height(), os.path.getsize(path), flush=True)


seeds = [int(x) for x in sys.argv[3].split(",")] if len(sys.argv) > 3 else [3]
for sd in seeds:
    tag = "" if len(seeds) == 1 else f"_{sd}"
    make(
        "classique" + tag,
        7.6,
        ("#39d6ff", "#3b6cff", "#9fe8ff"),
        seed=sd,
        mode="classic",
        position="center",
        scale=1.6,
    )
    make(
        "edit" + tag,
        14.4,
        ("#8B7CFF", "#FF6FB5", "#5EE7FF"),
        seed=sd,
        mode="edit",
        scale=1.5,
    )
    make(
        "machine" + tag,
        7.2,
        ("#ffb347", "#ff7a3d", "#ffe29a"),
        seed=sd,
        mode="typewriter",
        position="center",
        scale=1.6,
    )
    make(
        "titre" + tag,
        9.5,
        ("#ff5fa2", "#ff9a3d", "#ffd36b"),
        seed=sd,
        mode="edit",
        scale=1.2,
    )
    L = demo_song.demo_line
    tr = SimpleNamespace(
        title="Firework",
        artist="Katy Perry",
        album="",
        duration=60,
        position=0.0,
        playing=True,
        app="test",
        key=("firework", "katy perry"),
    )
    ls = [
        L(1.0, "la la la firework"),
        L(3.0, "la la la firework"),
        L(5.0, "firework la la"),
        L(7.0, "la la firework"),
        L(9.0, "mm firework"),
        L(20.0, ""),
    ]
    for at in (12.9,):
        make(
            f"easter{tag}_{at}",
            at,
            ("#ffd36b", "#ff5fa2", "#8B7CFF"),
            seed=sd,
            track=tr,
            lines=ls,
            mode="edit",
        )
os._exit(0)
