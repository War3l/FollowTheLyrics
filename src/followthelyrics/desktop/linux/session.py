import logging
import os
import shlex
import stat

from PyQt6.QtCore import QStandardPaths

from followthelyrics.config import settings

logger = logging.getLogger(__name__)

ENTRY_SUFFIX = ".desktop"
EXEC_KEY = "Exec="


def config_home(environ=os.environ):
    return environ.get("XDG_CONFIG_HOME") or os.path.join(
        os.path.expanduser("~"), ".config"
    )


def desktop_entry(name, command):
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={name}\n"
        f"Exec={command}\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n"
    )


def exec_line(path):
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.startswith(EXEC_KEY):
                    return line[len(EXEC_KEY) :].strip()
    except OSError:
        return ""
    return ""


def _write_entry(path, name, command):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(desktop_entry(name, command))
    mode = os.stat(path).st_mode
    os.chmod(path, mode | stat.S_IXUSR)


def _remove(path):
    if os.path.exists(path):
        os.remove(path)
        return True
    return False


class XdgAutostart:
    def __init__(self, name, folder=None):
        self._name = name
        self._folder = folder or os.path.join(config_home(), "autostart")

    def command(self):
        return exec_line(self._path(self._name))

    def enable(self, command):
        try:
            _write_entry(self._path(self._name), self._name, command)
            return True
        except OSError:
            logger.debug("enable failed", exc_info=True)
            return False

    def disable(self):
        try:
            _remove(self._path(self._name))
            return True
        except OSError:
            logger.debug("disable failed", exc_info=True)
            return False

    def drop_legacy(self, names):
        dropped = False
        for name in names:
            try:
                dropped = _remove(self._path(name)) or dropped
            except OSError:
                logger.debug("drop_legacy failed", exc_info=True)
        return dropped

    def _path(self, name):
        return os.path.join(self._folder, name + ENTRY_SUFFIX)


class DesktopEntryShortcuts:
    def __init__(self, name, legacy_name):
        self._name = name
        self._legacy_name = legacy_name

    def desktop_path(self):
        return self._in_desktop(self._name)

    def legacy_desktop_path(self):
        return self._in_desktop(self._legacy_name)

    def create(self, target, link):
        try:
            _write_entry(link, settings.APP_NAME, shlex.quote(target))
            return True
        except OSError:
            logger.debug("create failed", exc_info=True)
            return False

    def target(self, link):
        try:
            words = shlex.split(exec_line(link))
        except ValueError:
            return ""
        return words[0] if words else ""

    def _in_desktop(self, name):
        folder = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DesktopLocation
        )
        return os.path.join(folder, name + ENTRY_SUFFIX) if folder else ""
