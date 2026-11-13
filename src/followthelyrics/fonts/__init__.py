import logging
import os

from PyQt6.QtGui import QFontDatabase

logger = logging.getLogger(__name__)

BUNDLED = "TeX Gyre Heros"

FOLDER = os.path.dirname(os.path.abspath(__file__))

_state = {"loaded": False}


def load() -> None:
    if _state["loaded"]:
        return
    _state["loaded"] = True
    try:
        names = sorted(n for n in os.listdir(FOLDER) if n.endswith(".otf"))
    except OSError:
        logger.warning("bundled fonts missing", exc_info=True)
        return
    for name in names:
        if QFontDatabase.addApplicationFont(os.path.join(FOLDER, name)) < 0:
            logger.warning("bundled font not loaded: %s", name)


def families() -> set[str]:
    load()
    return set(QFontDatabase.families())
