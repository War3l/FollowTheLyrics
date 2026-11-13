import importlib
import importlib.util
import logging

from followthelyrics.config import settings
from followthelyrics.desktop import ports
from followthelyrics.desktop.generic import backend as generic
from followthelyrics.desktop.generic import keyboard
from followthelyrics.desktop.linux import session

logger = logging.getLogger(__name__)

MPRIS_MODULE = "followthelyrics.desktop.linux.mpris"
PULSE_MODULE = "followthelyrics.desktop.linux.audio"
X11_MODULE = "followthelyrics.desktop.linux.x11"
RELEASE = ports.ReleaseFormat(
    asset=settings.APP_NAME + "-linux", magic=b"\x7fELF", min_size=5_000_000
)


class MprisMedia:
    def open(self):
        return importlib.import_module(MPRIS_MODULE).MprisSession()


class PulseAudio:
    def open(self):
        return importlib.import_module(PULSE_MODULE).PulseLoopback()


def _installed(module):
    return importlib.util.find_spec(module) is not None


def _x11():
    if not _installed("Xlib"):
        return None
    module = importlib.import_module(X11_MODULE)
    return module if module.available() else None


def _status(ok):
    return "ok" if ok else "ABSENT"


def checks():
    return [
        "mpris=" + _status(_installed("PyQt6.QtDBus")),
        "audio=" + _status(_installed("soundcard")),
        "x11=" + _status(_x11() is not None),
    ]


def _foreground(x11):
    if x11 is None:
        return generic.UnknownForeground()
    try:
        return x11.X11Foreground()
    except Exception:
        logger.warning("_foreground failed", exc_info=True)
        return generic.UnknownForeground()


def create():
    x11 = _x11()
    return ports.Desktop(
        name="Linux",
        keyboard=keyboard.QtKeyboard(),
        windowing=generic.QtWindowing(),
        foreground=_foreground(x11),
        dialogs=generic.QtDialogs(),
        session=generic.PosixSession(),
        media=MprisMedia() if _installed("PyQt6.QtDBus") else None,
        audio=PulseAudio() if _installed("soundcard") else None,
        hotkeys=x11.X11Hotkeys() if x11 is not None else None,
        autostart=session.XdgAutostart(settings.APP_NAME),
        shortcuts=session.DesktopEntryShortcuts(
            settings.APP_NAME, "Lyrics Overlay"
        ),
        release=RELEASE,
        checks=checks,
    )
