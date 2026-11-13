import logging
import os
import sys

from followthelyrics.config import settings

logger = logging.getLogger(__name__)

FROZEN_ENV_PREFIXES = ("_MEIPASS", "_PYI_")


def launch_command(minimized=False, exe=None):
    if exe or settings.FROZEN:
        command = f'"{exe or sys.executable}"'
    else:
        python = sys.executable
        windowless = os.path.join(os.path.dirname(python), "pythonw.exe")
        interpreter = windowless if os.path.exists(windowless) else python
        command = f'"{interpreter}" -m followthelyrics'
    return command + (" --minimized" if minimized else "")


def child_environment(drop=()):
    env = dict(os.environ)
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    for key in list(env):
        if key.startswith(FROZEN_ENV_PREFIXES) or key in drop:
            env.pop(key)
    return env


class Startup:
    def __init__(self, autostart, shortcuts):
        self._autostart = autostart
        self._shortcuts = shortcuts

    @property
    def supports_autostart(self):
        return self._autostart is not None

    @property
    def supports_shortcuts(self):
        return self._shortcuts is not None

    def command(self):
        return self._autostart.command() if self._autostart else ""

    def enabled(self):
        return bool(self.command())

    def set(self, on, exe=None):
        if self._autostart is None:
            return False
        if on:
            return self._autostart.enable(
                launch_command(minimized=True, exe=exe)
            )
        return self._autostart.disable()

    def refresh(self):
        if self._autostart is not None and (
            self._autostart.drop_legacy(settings.OLD_NAMES) or self.enabled()
        ):
            self.set(True)
        if self._shortcuts is not None:
            try:
                legacy = self._shortcuts.legacy_desktop_path()
                if legacy and os.path.exists(legacy):
                    os.remove(legacy)
                    self.create_desktop_shortcut()
            except Exception:
                logger.debug("refresh failed", exc_info=True)

    def desktop_link(self):
        return self._shortcuts.desktop_path() if self._shortcuts else ""

    def create_desktop_shortcut(self, exe=None):
        if self._shortcuts is None or not (exe or settings.FROZEN):
            return False
        link = self.desktop_link()
        if not link:
            return False
        return self._shortcuts.create(exe or sys.executable, link)

    def link_target(self, link):
        return self._shortcuts.target(link) if self._shortcuts else ""

    def create_link(self, target, link):
        return (
            self._shortcuts.create(target, link) if self._shortcuts else False
        )
