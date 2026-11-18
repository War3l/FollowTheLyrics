import random

import pytest
from PyQt6.QtWidgets import QApplication

from followthelyrics.config import games
from followthelyrics.config import settings
from followthelyrics.desktop.generic import backend as generic
from followthelyrics.overlay import window


class RecordingWindowing(generic.QtWindowing):
    def __init__(self):
        self.placed = []

    def place_overlay(self, window, x, y, width, height):
        self.placed.append((x, y, width, height))


@pytest.fixture
def overlay():
    app = QApplication.instance() or QApplication([])
    o = window.Overlay(
        dict(settings.DEFAULTS, card=False),
        games.DEFAULT_PROFILES,
        RecordingWindowing(),
        clock=lambda: 0.0,
        rng=random.Random(3),
    )
    o.timer.stop()
    o.top_timer.stop()
    yield o
    o.close()
    app.processEvents()


def geometry_of(o):
    area = o.geometry()
    return (area.x(), area.y(), area.width(), area.height())


def test_hardening_places_the_overlay_where_qt_put_it(overlay):
    overlay.setGeometry(10, 20, 960, 720)
    overlay.harden_window()
    assert overlay.windowing.placed[-1] == (10, 20, 960, 720)


def test_screen_change_places_a_visible_overlay_again(overlay):
    overlay.show()
    overlay.setGeometry(10, 20, 960, 720)
    overlay.windowing.placed.clear()
    overlay.apply_geometry()
    assert overlay.windowing.placed == [geometry_of(overlay)]


def test_hidden_overlay_is_not_placed_on_screen_change(overlay):
    overlay.hide()
    overlay.windowing.placed.clear()
    overlay.apply_geometry()
    assert overlay.windowing.placed == []
