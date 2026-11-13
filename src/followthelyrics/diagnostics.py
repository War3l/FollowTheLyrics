import dataclasses
import importlib
import logging
import os
import random
import traceback

from PyQt6.QtCore import Qt
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QBrush
from PyQt6.QtGui import QColor
from PyQt6.QtGui import QImage
from PyQt6.QtGui import QLinearGradient
from PyQt6.QtGui import QPainter

from followthelyrics.config import games
from followthelyrics.config import settings
from followthelyrics.lyrics import demo_song
from followthelyrics.overlay import window
from followthelyrics.playback import audio
from followthelyrics.system import bootstrap

logger = logging.getLogger(__name__)


def snapshot(path, at, args):
    fake = [0.0]
    cfg = dict(
        settings.DEFAULTS,
        style=args.style,
        mode=args.mode,
        position=args.position,
        color=args.color,
        font=args.font,
    )
    profiles = games.DEFAULT_PROFILES
    o = window.Overlay(
        cfg, profiles, clock=lambda: fake[0], rng=random.Random(args.seed)
    )
    o.timer.stop()
    o.top_timer.stop()
    if args.game:
        o.set_profile(
            args.game, profiles["jeux"].get(args.game, profiles["jeu_inconnu"])
        )
    start = max(0.0, at - 8.0) if not args.card else at
    o.on_track(demo_song.demo_track(start))
    lines = demo_song.DEMO_LINES
    if args.translation:
        lines = [
            dataclasses.replace(
                line, translation="Traduction : " + line.text.lower()
            )
            if line.text
            else line
            for line in lines
        ]
    o.on_lyrics(demo_song.DEMO_KEY, lines)
    if args.cover:
        with open(args.cover, "rb") as f:
            o.on_cover(o.track_key, f.read())
    if not args.card:
        o.card_since = -99
    while fake[0] < (at - start) + (1.2 if args.card else 0):
        fake[0] += 0.016
        o.tick(0.016)
    if args.zones:
        o.zones_until = fake[0] + 5
    img = QImage(o.size(), QImage.Format.Format_ARGB32_Premultiplied)
    bg = QLinearGradient(0, 0, o.width(), o.height())
    bg.setColorAt(0, QColor("#1d2b22"))
    bg.setColorAt(1, QColor("#3d4f5c"))
    p = QPainter(img)
    p.fillRect(img.rect(), QBrush(bg))
    p.end()
    o.render(img)
    img.scaledToWidth(960, Qt.TransformationMode.SmoothTransformation).save(
        path
    )


def selftest(app, out_dir, app_factory):
    report = [f"frozen={settings.FROZEN}", f"data_dir={settings.DATA_DIR}"]
    report += [f"boot {n}: {r}" for n, r in bootstrap.LOG]
    try:
        importlib.import_module("followthelyrics.playback.media")
        report.append("winrt=ok")
    except (ImportError, OSError) as e:
        report.append(f"winrt=ERREUR {e!r}")
    report.append("audio=" + ("ok" if audio.pyaudio is not None else "ABSENT"))

    def finish(a):
        try:
            o = a.overlay
            report.append(
                f"paroles={len(o.lines)} "
                f"piste={o.track.title if o.track else None}"
            )
            report.append(f"sources={a.sources}")
            report.append(f"navigateurs={a.browsers}")
            report.append(
                f"reel={a.real_track.title if a.real_track else None}"
            )
            if a.welcome is not None:
                a.welcome.grab().save(
                    os.path.join(out_dir, "selftest_welcome.png")
                )
            a.panel.show()
            app.processEvents()
            a.panel.grab().save(os.path.join(out_dir, "selftest_panel.png"))
            img = QImage(o.size(), QImage.Format.Format_ARGB32_Premultiplied)
            img.fill(QColor("#26303a"))
            o.render(img)
            img.scaledToWidth(
                960, Qt.TransformationMode.SmoothTransformation
            ).save(os.path.join(out_dir, "selftest_overlay.png"))
            report.append("fin=ok")
        except Exception:
            logger.exception("selftest finish failed")
            report.append("fin=ERREUR\n" + traceback.format_exc())
        with open(
            os.path.join(out_dir, "selftest.txt"), "w", encoding="utf-8"
        ) as f:
            f.write("\n".join(report))
        os._exit(0)

    try:
        a = app_factory(app, demo=True)
        QTimer.singleShot(7000, lambda: finish(a))
        app.exec()
    except Exception:
        logger.exception("selftest startup failed")
        report.append("demarrage=ERREUR\n" + traceback.format_exc())
        with open(
            os.path.join(out_dir, "selftest.txt"), "w", encoding="utf-8"
        ) as f:
            f.write("\n".join(report))
        os._exit(1)
