"""Installation sur le PC, sans installeur a part : le .exe s'installe lui-meme.

Installer = se copier dans le dossier d'applications de l'utilisateur, poser une icone
dans le menu Demarrer et s'inscrire dans « Applications installees » de Windows (avec
un bouton Desinstaller). Rien ne demande les droits administrateur : tout reste dans
le compte de l'utilisateur.

Le .exe telecharge peut ensuite etre jete. S'il est relance alors qu'une copie est
installee, il lui passe la main (et la met a jour s'il est plus recent).
"""
import os
import shutil
import subprocess
import sys

import updater
from settings import APP_NAME, DATA_DIR, FROZEN

_TEST = os.environ.get("FTL_TEST_INSTANCE", "")  # les essais n'ecrivent pas a la vraie place
EXE_NAME = APP_NAME + ".exe"
PUBLISHER = "War3l"
SITE_URL = "https://war3l.github.io/FollowTheLyrics/"
_UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall" + "\\" + APP_NAME + _TEST


def install_dir():
    forced = os.environ.get("FTL_INSTALL_DIR")
    if forced:
        return forced
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    return os.path.join(base, "Programs", APP_NAME)


def installed_exe():
    return os.path.join(install_dir(), EXE_NAME)


def start_menu_link():
    folder = os.environ.get("FTL_STARTMENU_DIR")
    if not folder:
        base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
        folder = os.path.join(base, "Microsoft", "Windows", "Start Menu", "Programs")
    return os.path.join(folder, APP_NAME + ".lnk")


def _same(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def is_installed():
    return os.path.isfile(installed_exe())


def running_installed():
    """Vrai si c'est la copie installee qui tourne."""
    return FROZEN and _same(sys.executable, installed_exe())


def installed_version():
    """Version inscrite dans Windows pour la copie installee ('' si inconnue)."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _UNINSTALL_KEY) as k:
            return str(winreg.QueryValueEx(k, "DisplayVersion")[0])
    except Exception:
        return ""


def _make_link(target, link):
    from PyQt6.QtCore import QFile
    os.makedirs(os.path.dirname(link), exist_ok=True)
    if os.path.lexists(link):
        os.remove(link)
    return bool(QFile.link(target, link))


def _link_target(link):
    from PyQt6.QtCore import QFileInfo
    return QFileInfo(link).symLinkTarget()


def register(version=None):
    """Inscrit (ou rafraichit) l'appli dans « Applications installees » et le menu Demarrer."""
    import winreg
    exe = installed_exe()
    try:
        size_kb = os.path.getsize(exe) // 1024
    except OSError:
        size_kb = 0
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _UNINSTALL_KEY) as k:
        for name, value in (("DisplayName", APP_NAME), ("DisplayVersion", version or updater.current_version()),
                            ("Publisher", PUBLISHER), ("DisplayIcon", exe), ("InstallLocation", install_dir()),
                            ("UninstallString", f'"{exe}" --uninstall'),
                            ("QuietUninstallString", f'"{exe}" --uninstall --quiet'),
                            ("URLInfoAbout", SITE_URL)):
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)
        for name, value in (("NoModify", 1), ("NoRepair", 1), ("EstimatedSize", size_kb)):
            winreg.SetValueEx(k, name, 0, winreg.REG_DWORD, value)
    link = start_menu_link()
    if not os.path.exists(link) or not _same(_link_target(link) or "x", exe):
        _make_link(exe, link)


def install(source=None, version=None):
    """Copie `source` (ce .exe par defaut) a sa place definitive et l'inscrit dans Windows.
    -> chemin du .exe installe. Leve une exception si la copie echoue."""
    source = source or sys.executable
    exe = installed_exe()
    os.makedirs(install_dir(), exist_ok=True)
    if not _same(source, exe):
        new = exe + ".new"
        shutil.copyfile(source, new)
        if os.path.exists(exe):
            updater.swap(exe, new)  # marche meme si l'ancienne copie tourne encore
            try:
                os.remove(exe + ".old")
            except OSError:
                pass  # encore en cours d'execution : la nouvelle copie l'effacera au lancement
        else:
            os.replace(new, exe)
    register(version)
    return exe


def launch(exe, *args):
    """Lance un .exe independant de celui-ci (il se deballe de son cote)."""
    env = dict(os.environ)
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    for key in list(env):
        if key.startswith(("_MEIPASS", "_PYI_")):
            env.pop(key, None)
    subprocess.Popen([exe, *args], env=env, cwd=os.path.dirname(exe), close_fds=True,
                     creationflags=0x00000008 | 0x00000200)  # DETACHED_PROCESS | NEW_PROCESS_GROUP


def hand_over():
    """Appele au lancement d'un .exe qui n'est PAS la copie installee.
    S'il existe une copie installee : on la met a jour si ce .exe est plus recent, on la
    lance et on renvoie True (ce .exe n'a plus qu'a quitter)."""
    if not FROZEN or running_installed() or not is_installed() or os.environ.get("FTL_PORTABLE"):
        return False
    try:
        mine = updater.current_version()
        if updater.is_newer(mine, installed_version() or "0"):
            install()
        launch(installed_exe())
        return True
    except Exception:
        return False  # en cas de souci on tourne simplement d'ici


def uninstall(keep_data=True):
    """Retire tout ce que l'installation a pose et renvoie les dossiers restant a effacer :
    celui du programme ne peut pas l'etre tant que ce .exe tourne (voir delete_later)."""
    import settings
    exe = installed_exe()
    for link in (start_menu_link(), settings.desktop_link()):
        try:  # seulement les raccourcis qui menent a la copie installee
            if link and os.path.lexists(link) and _same(_link_target(link) or "x", exe):
                os.remove(link)
        except Exception:
            pass
    try:
        if exe.lower() in settings.autostart_command().lower():
            settings.set_autostart(False)
    except Exception:
        pass
    try:
        import winreg
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, _UNINSTALL_KEY)
    except Exception:
        pass
    folders = [install_dir()]
    if not keep_data and not _TEST:
        folders.append(DATA_DIR)
    return folders


def delete_later(folders):
    """Efface les dossiers dans quelques secondes, quand ce programme aura quitte."""
    cmd = "ping -n 4 127.0.0.1 >nul" + "".join(f' & rmdir /s /q "{f}"' for f in folders)
    subprocess.Popen(f'cmd /c "{cmd}"', cwd=os.environ.get("TEMP") or os.path.expanduser("~"),
                     close_fds=True, creationflags=0x08000000 | 0x00000200)  # CREATE_NO_WINDOW


def message(text, flags=0x40):
    """Petite fenetre Windows. -> bouton choisi (6 = Oui, 7 = Non)."""
    import ctypes
    return ctypes.windll.user32.MessageBoxW(None, text, APP_NAME, flags | 0x10000)  # au premier plan


def run_uninstall():
    """Desinstallation demandee depuis l'appli. -> True si elle a ete retiree (il faut quitter)."""
    if message("Désinstaller FollowTheLyrics de ce PC ?", 0x24) != 6:
        return False
    keep = message("Garder tes réglages et tes zones pour une prochaine installation ?", 0x24) == 6
    folders = uninstall(keep_data=keep)
    message("FollowTheLyrics a été désinstallé.")
    delete_later(folders)
    return True
