import contextlib
import ctypes
import logging
import os
import subprocess
import sys
import winreg
from ctypes import wintypes

from PyQt6.QtCore import QFile
from PyQt6.QtCore import QFileInfo
from PyQt6.QtCore import QStandardPaths

from followthelyrics.config import settings

assert sys.platform == "win32"

logger = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
ERROR_ALREADY_EXISTS = 183
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
MB_ICONINFORMATION = 0x40
MB_ICONWARNING = 0x30
MB_YESNO_QUESTION = 0x24
MB_SETFOREGROUND = 0x10000
IDYES = 6


class MessageBoxDialogs:
    def ask(self, text):
        return self._show(text, MB_YESNO_QUESTION) == IDYES

    def inform(self, text):
        self._show(text, MB_ICONINFORMATION)

    def warn(self, text):
        self._show(text, MB_ICONWARNING)

    def _show(self, text, flags):
        return ctypes.windll.user32.MessageBoxW(
            None, text, settings.APP_NAME, flags | MB_SETFOREGROUND
        )


class MutexLock:
    def __init__(self, name):
        self._name = "Local\\" + name
        self._handle = None
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.CreateMutexW.argtypes = [
            ctypes.c_void_p,
            wintypes.BOOL,
            wintypes.LPCWSTR,
        ]
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self._kernel32 = kernel32

    def acquire(self):
        if self._handle is not None:
            return True
        handle = self._kernel32.CreateMutexW(None, False, self._name)
        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            self._kernel32.CloseHandle(handle)
            return False
        self._handle = handle
        return True


class Win32Session:
    def set_app_id(self, app_id):
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                app_id
            )
        except Exception:
            logger.debug("set_app_id failed", exc_info=True)

    def spawn_detached(self, argv, cwd, env):
        subprocess.Popen(
            argv,
            env=dict(env),
            cwd=cwd,
            close_fds=True,
            creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
        )

    def instance_lock(self, name):
        return MutexLock(name)


class RegistryAutostart:
    def __init__(self, name):
        self._name = name

    def command(self):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                value, _kind = winreg.QueryValueEx(key, self._name)
            return str(value or "")
        except OSError:
            return ""

    def enable(self, command):
        try:
            with self._open(winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, self._name, 0, winreg.REG_SZ, command)
            return True
        except OSError:
            logger.debug("enable failed", exc_info=True)
            return False

    def disable(self):
        try:
            with (
                self._open(winreg.KEY_SET_VALUE) as key,
                contextlib.suppress(FileNotFoundError),
            ):
                winreg.DeleteValue(key, self._name)
            return True
        except OSError:
            logger.debug("disable failed", exc_info=True)
            return False

    def drop_legacy(self, names):
        dropped = False
        try:
            with self._open(
                winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE
            ) as key:
                for name in names:
                    try:
                        winreg.QueryValueEx(key, name)
                        winreg.DeleteValue(key, name)
                        dropped = True
                    except FileNotFoundError:
                        pass
        except OSError:
            logger.debug("drop_legacy failed", exc_info=True)
        return dropped

    def _open(self, access):
        return winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, access)


def _desktop_folder():
    return QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.DesktopLocation
    )


class LinkShortcuts:
    def __init__(self, name, legacy_name):
        self._name = name
        self._legacy_name = legacy_name

    def desktop_path(self):
        return self._in_desktop(self._name)

    def legacy_desktop_path(self):
        return self._in_desktop(self._legacy_name)

    def create(self, target, link):
        try:
            os.makedirs(os.path.dirname(link), exist_ok=True)
            if os.path.lexists(link):
                os.remove(link)
            return bool(QFile.link(target, link))
        except Exception:
            logger.debug("create failed", exc_info=True)
            return False

    def target(self, link):
        return QFileInfo(link).symLinkTarget()

    def _in_desktop(self, name):
        try:
            folder = _desktop_folder()
            return os.path.join(folder, name + ".lnk") if folder else ""
        except Exception:
            logger.debug("_in_desktop failed", exc_info=True)
            return ""
