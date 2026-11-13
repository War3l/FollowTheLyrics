import importlib
import importlib.util
import os
import sys

from followthelyrics.config import settings
from followthelyrics.desktop import ports
from followthelyrics.desktop.windows import boot
from followthelyrics.desktop.windows import foreground
from followthelyrics.desktop.windows import hotkeys
from followthelyrics.desktop.windows import install
from followthelyrics.desktop.windows import session
from followthelyrics.desktop.windows import windowing

assert sys.platform == "win32"

SMTC_MODULE = "followthelyrics.desktop.windows.smtc"
WASAPI_MODULE = "followthelyrics.desktop.windows.audio"
RELEASE = ports.ReleaseFormat(
    asset=settings.APP_NAME + ".exe", magic=b"MZ", min_size=5_000_000
)


class SmtcMedia:
    def open(self):
        return importlib.import_module(SMTC_MODULE).SmtcSession()


class WasapiAudio:
    def open(self):
        return importlib.import_module(WASAPI_MODULE).WasapiLoopback()


def _has_wasapi():
    return importlib.util.find_spec("pyaudiowpatch") is not None


def checks():
    lines = [f"boot {name}: {result}" for name, result in boot.LOG]
    try:
        importlib.import_module(SMTC_MODULE)
        lines.append("winrt=ok")
    except (ImportError, OSError) as error:
        lines.append(f"winrt=ERREUR {error!r}")
    lines.append("audio=" + ("ok" if _has_wasapi() else "ABSENT"))
    return lines


def create():
    test_suffix = os.environ.get("FTL_TEST_INSTANCE", "")
    return ports.Desktop(
        name="Windows",
        keyboard=hotkeys.Win32Keyboard(),
        windowing=windowing.DwmWindowing(),
        foreground=foreground.Win32Foreground(),
        dialogs=session.MessageBoxDialogs(),
        session=session.Win32Session(),
        media=SmtcMedia(),
        audio=WasapiAudio() if _has_wasapi() else None,
        hotkeys=hotkeys.MessageLoopHotkeys(),
        autostart=session.RegistryAutostart(settings.APP_NAME),
        shortcuts=session.LinkShortcuts(settings.APP_NAME, "Lyrics Overlay"),
        installer=install.RegistryInstaller(test_suffix),
        release=RELEASE,
        checks=checks,
    )
