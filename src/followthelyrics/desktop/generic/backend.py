import logging
import os
import subprocess
import tempfile

from PyQt6.QtCore import QLockFile
from PyQt6.QtWidgets import QMessageBox

from followthelyrics.config import settings
from followthelyrics.desktop import ports
from followthelyrics.desktop.generic import keyboard

logger = logging.getLogger(__name__)


class NoSubscription:
    def close(self):
        pass


class QtWindowing:
    def prepare_overlay(self, window):
        pass

    def raise_overlay(self, window):
        pass

    def on_foreground_change(self, callback):
        return NoSubscription()

    def supports_backdrop(self):
        return False

    def enable_backdrop(self, window):
        return False

    def dark_title_bar(self, window):
        pass

    def round_corners(self, window):
        pass

    def color_title_bar(self, window, colors):
        pass


class UnknownForeground:
    def current(self):
        return ports.ForegroundApp()

    def exclusive_fullscreen(self):
        return False

    def window_titles(self, exes):
        return []


class QtDialogs:
    Button = QMessageBox.StandardButton

    def ask(self, text):
        answer = QMessageBox.question(
            None, settings.APP_NAME, text, self.Button.Yes | self.Button.No
        )
        return answer == self.Button.Yes

    def inform(self, text):
        QMessageBox.information(None, settings.APP_NAME, text)

    def warn(self, text):
        QMessageBox.warning(None, settings.APP_NAME, text)


class FileLock:
    def __init__(self, name):
        self._lock = QLockFile(os.path.join(tempfile.gettempdir(), name))

    def acquire(self):
        return self._lock.isLocked() or self._lock.tryLock(0)


class PosixSession:
    def set_app_id(self, app_id):
        pass

    def spawn_detached(self, argv, cwd, env):
        subprocess.Popen(
            argv,
            env=dict(env),
            cwd=cwd,
            close_fds=True,
            start_new_session=True,
        )

    def instance_lock(self, name):
        return FileLock(name + ".lock")


def create(name):
    return ports.Desktop(
        name=name,
        keyboard=keyboard.QtKeyboard(),
        windowing=QtWindowing(),
        foreground=UnknownForeground(),
        dialogs=QtDialogs(),
        session=PosixSession(),
    )
