import contextlib
import logging
import os
import shutil
import sys

from followthelyrics import version
from followthelyrics.config import settings
from followthelyrics.desktop import ports
from followthelyrics.system import startup
from followthelyrics.system import updater

logger = logging.getLogger(__name__)

TEST_INSTANCE = os.environ.get("FTL_TEST_INSTANCE", "")
UNINSTALL_PROMPT = "Désinstaller FollowTheLyrics de ce PC ?"
KEEP_DATA_PROMPT = (
    "Garder tes réglages et tes zones pour une prochaine installation ?"
)
UNINSTALLED = "FollowTheLyrics a été désinstallé."


def _same(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(
        os.path.abspath(b)
    )


class Installation:
    def __init__(self, installer, desktop_startup, dialogs, session, exe_name):
        self._installer = installer
        self._startup = desktop_startup
        self._dialogs = dialogs
        self._session = session
        self._exe_name = exe_name

    def folder(self):
        return os.environ.get("FTL_INSTALL_DIR") or (
            self._installer.default_folder()
        )

    def exe(self):
        return os.path.join(self.folder(), self._exe_name)

    def is_installed(self):
        return os.path.isfile(self.exe())

    def running_installed(self):
        return settings.FROZEN and _same(sys.executable, self.exe())

    def register(self, installed_version=None):
        exe = self.exe()
        try:
            size_kb = os.path.getsize(exe) // 1024
        except OSError:
            size_kb = 0
        self._installer.register(
            ports.AppEntry(
                exe=exe,
                folder=self.folder(),
                version=installed_version or version.current(),
                size_kb=size_kb,
            )
        )
        link = self._installer.menu_shortcut()
        if not os.path.exists(link) or not self._points_here(link):
            self._startup.create_link(exe, link)

    def install(self, source=None, installed_version=None):
        source = source or sys.executable
        exe = self.exe()
        os.makedirs(self.folder(), exist_ok=True)
        if not _same(source, exe):
            new = exe + ".new"
            shutil.copyfile(source, new)
            if os.path.exists(exe):
                updater.swap(exe, new)
                with contextlib.suppress(OSError):
                    os.remove(exe + ".old")
            else:
                os.replace(new, exe)
        self.register(installed_version)
        return exe

    def launch(self, exe, *args):
        self._session.spawn_detached(
            [exe, *args], os.path.dirname(exe), startup.child_environment()
        )

    def hand_over(self):
        if (
            not settings.FROZEN
            or self.running_installed()
            or not self.is_installed()
            or os.environ.get("FTL_PORTABLE")
        ):
            return False
        try:
            registered = self._installer.registered_version() or "0"
            if updater.is_newer(version.current(), registered):
                self.install()
            self.launch(self.exe())
            return True
        except Exception:
            logger.debug("hand_over failed", exc_info=True)
            return False

    def uninstall(self, keep_data=True):
        exe = self.exe()
        for link in (
            self._installer.menu_shortcut(),
            self._startup.desktop_link(),
        ):
            try:
                if link and os.path.lexists(link) and self._points_here(link):
                    os.remove(link)
            except Exception:
                logger.debug("uninstall failed", exc_info=True)
        try:
            if exe.lower() in self._startup.command().lower():
                self._startup.set(False)
        except Exception:
            logger.debug("uninstall failed", exc_info=True)
        try:
            self._installer.unregister()
        except OSError:
            logger.debug("uninstall failed", exc_info=True)
        folders = [self.folder()]
        if not keep_data and not TEST_INSTANCE:
            folders.append(settings.DATA_DIR)
        return folders

    def confirm_uninstall(self):
        return self._dialogs.ask(UNINSTALL_PROMPT)

    def run_uninstall(self, quiet=False, keep_data=True):
        if not quiet:
            keep_data = self._dialogs.ask(KEEP_DATA_PROMPT)
        folders = self.uninstall(keep_data=keep_data)
        if not quiet:
            self._dialogs.inform(UNINSTALLED)
        self._installer.remove_after_exit(folders)

    def _points_here(self, link):
        return _same(self._startup.link_target(link) or "x", self.exe())
