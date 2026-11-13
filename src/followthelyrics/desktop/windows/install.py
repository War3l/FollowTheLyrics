import os
import subprocess
import sys
import winreg

from followthelyrics.config import settings

assert sys.platform == "win32"

UNINSTALL_ROOT = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
PUBLISHER = "War3l"
SITE_URL = "https://war3l.github.io/FollowTheLyrics/"
CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_PROCESS_GROUP = 0x00000200


def _roaming():
    return os.environ.get("APPDATA") or os.path.join(
        os.path.expanduser("~"), "AppData", "Roaming"
    )


def _local():
    return os.environ.get("LOCALAPPDATA") or os.path.join(
        os.path.expanduser("~"), "AppData", "Local"
    )


class RegistryInstaller:
    def __init__(self, instance_suffix=""):
        self._key = UNINSTALL_ROOT + "\\" + settings.APP_NAME + instance_suffix

    def default_folder(self):
        return os.path.join(_local(), "Programs", settings.APP_NAME)

    def menu_shortcut(self):
        folder = os.environ.get("FTL_STARTMENU_DIR") or os.path.join(
            _roaming(), "Microsoft", "Windows", "Start Menu", "Programs"
        )
        return os.path.join(folder, settings.APP_NAME + ".lnk")

    def registered_version(self):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self._key) as key:
                return str(winreg.QueryValueEx(key, "DisplayVersion")[0])
        except OSError:
            return ""

    def register(self, entry):
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, self._key) as key:
            for name, text in (
                ("DisplayName", settings.APP_NAME),
                ("DisplayVersion", entry.version),
                ("Publisher", PUBLISHER),
                ("DisplayIcon", entry.exe),
                ("InstallLocation", entry.folder),
                ("UninstallString", f'"{entry.exe}" --uninstall'),
                ("QuietUninstallString", f'"{entry.exe}" --uninstall --quiet'),
                ("URLInfoAbout", SITE_URL),
            ):
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, text)
            for name, number in (
                ("NoModify", 1),
                ("NoRepair", 1),
                ("EstimatedSize", entry.size_kb),
            ):
                winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, number)

    def unregister(self):
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, self._key)

    def remove_after_exit(self, folders):
        command = "ping -n 4 127.0.0.1 >nul" + "".join(
            f' & rmdir /s /q "{folder}"' for folder in folders
        )
        subprocess.Popen(
            f'cmd /c "{command}"',
            cwd=os.environ.get("TEMP") or os.path.expanduser("~"),
            close_fds=True,
            creationflags=CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP,
        )
