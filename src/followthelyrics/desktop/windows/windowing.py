import ctypes
import logging
import sys
from ctypes import wintypes

from followthelyrics.desktop.windows import api

assert sys.platform == "win32"

logger = logging.getLogger(__name__)

HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_NOOWNERZORDER = 0x0200
GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x20
WS_EX_TOOLWINDOW = 0x80
WS_EX_NOACTIVATE = 0x08000000
EVENT_SYSTEM_FOREGROUND = 3
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_BORDER_COLOR = 34
DWMWA_CAPTION_COLOR = 35
DWMWA_TEXT_COLOR = 36
DWMWA_SYSTEMBACKDROP_TYPE = 38
DWMWCP_ROUND = 2
DWMSBT_TRANSIENTWINDOW = 3
BACKDROP_MIN_BUILD = 22621


class Margins(ctypes.Structure):
    _fields_ = (
        ("left", ctypes.c_int),
        ("right", ctypes.c_int),
        ("top", ctypes.c_int),
        ("bottom", ctypes.c_int),
    )


def _set_attribute(window, attribute, value):
    return ctypes.windll.dwmapi.DwmSetWindowAttribute(
        ctypes.c_void_p(int(window)),
        attribute,
        ctypes.byref(value),
        ctypes.sizeof(value),
    )


def _bgr(color):
    rgb = int(color.lstrip("#"), 16)
    red, green, blue = rgb >> 16, (rgb >> 8) & 0xFF, rgb & 0xFF
    return (blue << 16) | (green << 8) | red


class ForegroundHook:
    def __init__(self, callback):
        self._proc = api.WinEventProc(lambda *_: callback())
        self._handle = api.user32().SetWinEventHook(
            EVENT_SYSTEM_FOREGROUND,
            EVENT_SYSTEM_FOREGROUND,
            None,
            self._proc,
            0,
            0,
            0,
        )

    def close(self):
        if not self._handle:
            return
        try:
            api.user32().UnhookWinEvent(self._handle)
        except OSError:
            logger.debug("close failed", exc_info=True)
        self._handle = None


class NoHook:
    def close(self):
        pass


class DwmWindowing:
    def prepare_overlay(self, window):
        try:
            user32 = api.user32()
            style = user32.GetWindowLongPtrW(window, GWL_EXSTYLE)
            user32.SetWindowLongPtrW(
                window,
                GWL_EXSTYLE,
                style | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
            )
        except Exception:
            logger.debug("prepare_overlay failed", exc_info=True)

    def raise_overlay(self, window):
        try:
            api.user32().SetWindowPos(
                window,
                wintypes.HWND(HWND_TOPMOST),
                0,
                0,
                0,
                0,
                SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_NOOWNERZORDER,
            )
        except Exception:
            logger.debug("raise_overlay failed", exc_info=True)

    def on_foreground_change(self, callback):
        try:
            return ForegroundHook(callback)
        except Exception:
            logger.debug("on_foreground_change failed", exc_info=True)
            return NoHook()

    def supports_backdrop(self):
        return sys.getwindowsversion().build >= BACKDROP_MIN_BUILD

    def enable_backdrop(self, window):
        if not self.supports_backdrop():
            return False
        try:
            margins = Margins(-1, -1, -1, -1)
            ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(
                ctypes.c_void_p(int(window)), ctypes.byref(margins)
            )
            kind = ctypes.c_int(DWMSBT_TRANSIENTWINDOW)
            return _set_attribute(window, DWMWA_SYSTEMBACKDROP_TYPE, kind) == 0
        except Exception:
            logger.debug("enable_backdrop failed", exc_info=True)
            return False

    def dark_title_bar(self, window):
        try:
            _set_attribute(
                window, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.c_int(1)
            )
        except Exception:
            logger.debug("dark_title_bar failed", exc_info=True)

    def round_corners(self, window):
        try:
            _set_attribute(
                window,
                DWMWA_WINDOW_CORNER_PREFERENCE,
                ctypes.c_int(DWMWCP_ROUND),
            )
        except Exception:
            logger.debug("round_corners failed", exc_info=True)

    def color_title_bar(self, window, colors):
        try:
            for attribute, color in (
                (DWMWA_CAPTION_COLOR, colors.caption),
                (DWMWA_BORDER_COLOR, colors.border),
                (DWMWA_TEXT_COLOR, colors.text),
            ):
                _set_attribute(window, attribute, ctypes.c_uint(_bgr(color)))
        except Exception:
            logger.debug("color_title_bar failed", exc_info=True)
