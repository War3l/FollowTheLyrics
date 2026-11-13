import contextlib
import ctypes
import logging
import os
import sys
from ctypes import wintypes

from followthelyrics.system import win32

logger = logging.getLogger(__name__)

FROZEN = bool(getattr(sys, "frozen", False))
ROOT = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
QT_BIN = os.path.join(ROOT, "PyQt6", "Qt6", "bin")

RUNTIME = (
    "vcruntime140.dll",
    "vcruntime140_1.dll",
    "msvcp140.dll",
    "msvcp140_1.dll",
    "msvcp140_2.dll",
    "msvcp140_atomic_wait.dll",
    "concrt140.dll",
)
QT = ("Qt6Core.dll", "Qt6Gui.dll", "Qt6Network.dll", "Qt6Widgets.dll")

LOG: list[tuple[str, str]] = []

LOAD_WITH_ALTERED_SEARCH_PATH = 0x00000008


def _loaded_path(name):
    h = win32.kernel32().GetModuleHandleW(name)
    if not h:
        return None
    buf = ctypes.create_unicode_buffer(1024)
    win32.kernel32().GetModuleFileNameW(h, buf, 1024)
    return buf.value


def _file_version(path):
    try:
        ver = ctypes.WinDLL("version", use_last_error=True)
        size = ver.GetFileVersionInfoSizeW(path, None)
        if not size:
            return "?"
        data = ctypes.create_string_buffer(size)
        ver.GetFileVersionInfoW(path, 0, size, data)
        p, n = ctypes.c_void_p(), wintypes.UINT()
        if not ver.VerQueryValueW(data, "\\", ctypes.byref(p), ctypes.byref(n)):
            return "?"
        v = ctypes.cast(p, ctypes.POINTER(wintypes.DWORD * 13)).contents
        return f"{v[2] >> 16}.{v[2] & 0xFFFF}.{v[3] >> 16}.{v[3] & 0xFFFF}"
    except (OSError, AttributeError, ctypes.ArgumentError):
        return "?"


def _load(path):
    name = os.path.basename(path)
    before = _loaded_path(name)
    if before and os.path.normcase(before) != os.path.normcase(path):
        LOG.append(
            (
                name,
                f"DEJA CHARGE D'AILLEURS : {before} (v{_file_version(before)})",
            )
        )
        return
    if not os.path.exists(path):
        LOG.append((name, "absent du paquet"))
        return
    h = win32.kernel32().LoadLibraryExW(
        path, None, LOAD_WITH_ALTERED_SEARCH_PATH
    )
    if h:
        LOG.append((name, f"ok v{_file_version(path)}"))
    else:
        err = ctypes.get_last_error()
        LOG.append(
            (
                name,
                f"ECHEC erreur Windows {err} : "
                f"{ctypes.FormatError(err).strip()}",
            )
        )


def prepare():
    if not FROZEN:
        return
    try:
        for name in RUNTIME:
            _load(os.path.join(ROOT, name))
        if os.path.isdir(QT_BIN):
            os.add_dll_directory(QT_BIN)
            for name in QT:
                _load(os.path.join(QT_BIN, name))
    except Exception as e:
        logger.warning("prepare failed", exc_info=True)
        LOG.append(("prepare", f"exception {e!r}"))


def report(error):
    lines = [
        "FollowTheLyrics n'a pas pu demarrer.",
        "",
        f"Erreur : {error}",
        "",
    ]
    try:
        v = sys.getwindowsversion()
        lines.append(
            f"Windows : {v.major}.{v.minor} build {v.build} "
            f"({v.service_pack or 'sans SP'})"
        )
    except AttributeError:
        pass
    lines.append(f"Programme : {sys.executable}")
    lines.append(f"Dossier temporaire : {ROOT}")
    lines.append("")
    lines.append("Chargement des bibliotheques :")
    for name, res in LOG:
        lines.append(f"  {name} : {res}")
    lines.append("")
    lines.append("Bibliotheques presentes en memoire :")
    for name in RUNTIME + QT + ("python3.dll", "python313.dll", "ucrtbase.dll"):
        p = _loaded_path(name)
        lines.append(
            f"  {name} : "
            f"{p + ' (v' + _file_version(p) + ')' if p else 'non chargee'}"
        )
    try:
        here = os.path.dirname(sys.executable)
        stray = [f for f in os.listdir(here) if f.lower().endswith(".dll")]
        lines.append("")
        lines.append(
            f"Fichiers .dll a cote du programme : "
            f"{', '.join(stray) if stray else 'aucun'}"
        )
    except OSError:
        pass
    text = "\n".join(lines)
    path = None
    for folder in (
        os.path.join(os.path.expanduser("~"), "Desktop"),
        os.environ.get("TEMP", ""),
    ):
        try:
            if folder and os.path.isdir(folder):
                path = os.path.join(folder, "FollowTheLyrics-erreur.txt")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
                break
        except OSError:
            path = None
    msg = (
        "FollowTheLyrics n'a pas pu démarrer sur ce PC.\n\n"
        "Essaie d'abord d'installer « Microsoft Visual C++ Redistributable "
        "2015-2022 (x64) » "
        "depuis le site de Microsoft, puis relance.\n\n"
    )
    if path:
        msg += (
            "Si ça ne suffit pas, envoie ce fichier à la personne "
            f"qui t'a donné le logiciel :\n{path}"
        )
    else:
        msg += text
    with contextlib.suppress(OSError, AttributeError):
        ctypes.windll.user32.MessageBoxW(None, msg, "FollowTheLyrics", 0x10)
