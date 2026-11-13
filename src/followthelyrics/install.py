import ctypes
import logging
import os
import shutil
import subprocess
import sys

from PyQt6.QtCore import QFile
from PyQt6.QtCore import QFileInfo

if sys.platform == "win32":
    import winreg

import contextlib

from followthelyrics import settings
from followthelyrics import updater

logger = logging.getLogger(__name__)

_TEST = os.environ.get("FTL_TEST_INSTANCE", "")
EXE_NAME = settings.APP_NAME + ".exe"
PUBLISHER = "War3l"
SITE_URL = "https://war3l.github.io/FollowTheLyrics/"
_UNINSTALL_KEY = (
    r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
    + "\\"
    + settings.APP_NAME
    + _TEST
)


def install_dir():
    forced = os.environ.get("FTL_INSTALL_DIR")
    if forced:
        return forced
    base = os.environ.get("LOCALAPPDATA") or os.path.join(
        os.path.expanduser("~"), "AppData", "Local"
    )
    return os.path.join(base, "Programs", settings.APP_NAME)


def installed_exe():
    return os.path.join(install_dir(), EXE_NAME)


def start_menu_link():
    folder = os.environ.get("FTL_STARTMENU_DIR")
    if not folder:
        base = os.environ.get("APPDATA") or os.path.join(
            os.path.expanduser("~"), "AppData", "Roaming"
        )
        folder = os.path.join(
            base, "Microsoft", "Windows", "Start Menu", "Programs"
        )
    return os.path.join(folder, settings.APP_NAME + ".lnk")


def _same(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(
        os.path.abspath(b)
    )


def is_installed():
    return os.path.isfile(installed_exe())


def running_installed():
    return settings.FROZEN and _same(sys.executable, installed_exe())


def installed_version():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _UNINSTALL_KEY) as k:
            return str(winreg.QueryValueEx(k, "DisplayVersion")[0])
    except OSError:
        return ""


def _make_link(target, link):
    os.makedirs(os.path.dirname(link), exist_ok=True)
    if os.path.lexists(link):
        os.remove(link)
    return bool(QFile.link(target, link))


def _link_target(link):
    return QFileInfo(link).symLinkTarget()


def register(version=None):
    exe = installed_exe()
    try:
        size_kb = os.path.getsize(exe) // 1024
    except OSError:
        size_kb = 0
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _UNINSTALL_KEY) as k:
        for name, value in (
            ("DisplayName", settings.APP_NAME),
            ("DisplayVersion", version or updater.current_version()),
            ("Publisher", PUBLISHER),
            ("DisplayIcon", exe),
            ("InstallLocation", install_dir()),
            ("UninstallString", f'"{exe}" --uninstall'),
            ("QuietUninstallString", f'"{exe}" --uninstall --quiet'),
            ("URLInfoAbout", SITE_URL),
        ):
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)
        for name, value in (
            ("NoModify", 1),
            ("NoRepair", 1),
            ("EstimatedSize", size_kb),
        ):
            winreg.SetValueEx(k, name, 0, winreg.REG_DWORD, value)
    link = start_menu_link()
    if not os.path.exists(link) or not _same(_link_target(link) or "x", exe):
        _make_link(exe, link)


def install(source=None, version=None):
    source = source or sys.executable
    exe = installed_exe()
    os.makedirs(install_dir(), exist_ok=True)
    if not _same(source, exe):
        new = exe + ".new"
        shutil.copyfile(source, new)
        if os.path.exists(exe):
            updater.swap(exe, new)
            with contextlib.suppress(OSError):
                os.remove(exe + ".old")
        else:
            os.replace(new, exe)
    register(version)
    return exe


def launch(exe, *args):
    env = dict(os.environ)
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    for key in list(env):
        if key.startswith(("_MEIPASS", "_PYI_")):
            env.pop(key, None)
    subprocess.Popen(
        [exe, *args],
        env=env,
        cwd=os.path.dirname(exe),
        close_fds=True,
        creationflags=0x00000008 | 0x00000200,
    )


def hand_over():
    if (
        not settings.FROZEN
        or running_installed()
        or not is_installed()
        or os.environ.get("FTL_PORTABLE")
    ):
        return False
    try:
        mine = updater.current_version()
        if updater.is_newer(mine, installed_version() or "0"):
            install()
        launch(installed_exe())
        return True
    except Exception:
        logger.debug("hand_over failed", exc_info=True)
        return False


def uninstall(keep_data=True):
    exe = installed_exe()
    for link in (start_menu_link(), settings.desktop_link()):
        try:
            if (
                link
                and os.path.lexists(link)
                and _same(_link_target(link) or "x", exe)
            ):
                os.remove(link)
        except Exception:
            logger.debug("uninstall failed", exc_info=True)
    try:
        if exe.lower() in settings.autostart_command().lower():
            settings.set_autostart(False)
    except Exception:
        logger.debug("uninstall failed", exc_info=True)
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, _UNINSTALL_KEY)
    except OSError:
        logger.debug("uninstall failed", exc_info=True)
    folders = [install_dir()]
    if not keep_data and not _TEST:
        folders.append(settings.DATA_DIR)
    return folders


def delete_later(folders):
    cmd = "ping -n 4 127.0.0.1 >nul" + "".join(
        f' & rmdir /s /q "{f}"' for f in folders
    )
    subprocess.Popen(
        f'cmd /c "{cmd}"',
        cwd=os.environ.get("TEMP") or os.path.expanduser("~"),
        close_fds=True,
        creationflags=0x08000000 | 0x00000200,
    )


def message(text, flags=0x40):
    return ctypes.windll.user32.MessageBoxW(
        None, text, settings.APP_NAME, flags | 0x10000
    )


def run_uninstall():
    if message("Désinstaller FollowTheLyrics de ce PC ?", 0x24) != 6:
        return False
    keep = (
        message(
            "Garder tes réglages et tes zones pour une prochaine installation "
            "?",
            0x24,
        )
        == 6
    )
    folders = uninstall(keep_data=keep)
    message("FollowTheLyrics a été désinstallé.")
    delete_later(folders)
    return True
