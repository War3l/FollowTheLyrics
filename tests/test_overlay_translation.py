import random

import pytest
from PyQt6.QtWidgets import QApplication

from followthelyrics import desktop
from followthelyrics.config import games
from followthelyrics.config import settings
from followthelyrics.lyrics import model
from followthelyrics.overlay import window

LONG = (
    "Monte le son encore une fois, laisse la nuit tourner autour de nous "
    "jusqu'au matin"
)


@pytest.fixture
def overlay():
    app = QApplication.instance() or QApplication([])
    o = window.Overlay(
        dict(settings.DEFAULTS, card=False, translation=True),
        games.DEFAULT_PROFILES,
        desktop.current().windowing,
        clock=lambda: 0.0,
        rng=random.Random(3),
    )
    o.timer.stop()
    o.top_timer.stop()
    o.setGeometry(0, 0, 960, 720)
    yield o
    o.close()
    app.processEvents()


def test_long_translation_wraps_instead_of_being_cut(overlay):
    line = model.Line(1.0, "音を上げて", translation=LONG)

    _, fm, rows = overlay.translation_rows(line, 200)

    assert len(rows) > 1
    assert " ".join(rows) == LONG
    limit = fm.averageCharWidth() * window.TRANSLATION_CHARS
    assert all(fm.horizontalAdvance(row) <= limit for row in rows)


def test_block_grows_with_translation_rows(overlay):
    short = model.Line(1.0, "音を上げて", translation="Monte le son")
    long = model.Line(1.0, "音を上げて", translation=LONG)

    assert overlay.block_size(long, 200)[1] > overlay.block_size(short, 200)[1]


def test_endless_translation_is_capped(overlay):
    line = model.Line(1.0, "音を上げて", translation=" ".join([LONG] * 9))

    _, _, rows = overlay.translation_rows(line, 200)

    assert len(rows) == window.TRANSLATION_ROWS
    assert rows[-1].endswith("…")
