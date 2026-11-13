import ctypes
import json
import logging
import os
from ctypes import wintypes

from followthelyrics import settings
from followthelyrics import win32

logger = logging.getLogger(__name__)

PROFILES_PATH = os.path.join(settings.DATA_DIR, "profiles.json")

DEFAULT_PROFILES = {
    "_aide": "Zones en fraction de l'ecran (0 a 1) : x,y = coin haut-gauche, "
    "l,h = largeur,hauteur. "
    "En jeu, le raccourci « Voir les zones » (Ctrl+Alt+Z au depart) les "
    "affiche en rouge. Le fichier est relu automatiquement.",
    "jeux": {
        "League of Legends.exe": {
            "nom": "League of Legends",
            "zones_interdites": [
                {
                    "nom": "Combat (centre)",
                    "x": 0.26,
                    "y": 0.13,
                    "l": 0.48,
                    "h": 0.65,
                },
                {
                    "nom": "Sorts, vie, objets",
                    "x": 0.24,
                    "y": 0.78,
                    "l": 0.52,
                    "h": 0.22,
                },
                {"nom": "Minimap", "x": 0.76, "y": 0.64, "l": 0.24, "h": 0.36},
                {
                    "nom": "Score, KDA, temps",
                    "x": 0.68,
                    "y": 0.0,
                    "l": 0.32,
                    "h": 0.07,
                },
                {"nom": "Chat", "x": 0.0, "y": 0.66, "l": 0.27, "h": 0.34},
                {
                    "nom": "Annonces (kills, objectifs)",
                    "x": 0.32,
                    "y": 0.04,
                    "l": 0.36,
                    "h": 0.11,
                },
                {
                    "nom": "Allies / kill feed",
                    "x": 0.88,
                    "y": 0.07,
                    "l": 0.12,
                    "h": 0.57,
                },
            ],
            "conseil_plein_ecran": (
                "Dans LoL : Echap > Video > Mode fenetre > « Sans bordure »."
            ),
        },
        "Cyberpunk2077.exe": {
            "nom": "Cyberpunk 2077",
            "zones_interdites": [
                {
                    "nom": "Vie, niveau, effets",
                    "x": 0.0,
                    "y": 0.0,
                    "l": 0.30,
                    "h": 0.16,
                },
                {
                    "nom": "Appels (holocall)",
                    "x": 0.0,
                    "y": 0.16,
                    "l": 0.22,
                    "h": 0.18,
                },
                {
                    "nom": "Minimap, recherche",
                    "x": 0.80,
                    "y": 0.0,
                    "l": 0.20,
                    "h": 0.30,
                },
                {
                    "nom": "Objectif de quete",
                    "x": 0.72,
                    "y": 0.28,
                    "l": 0.28,
                    "h": 0.17,
                },
                {
                    "nom": "Viseur / combat",
                    "x": 0.33,
                    "y": 0.30,
                    "l": 0.34,
                    "h": 0.40,
                },
                {
                    "nom": "Dialogues, interactions",
                    "x": 0.55,
                    "y": 0.44,
                    "l": 0.30,
                    "h": 0.32,
                },
                {
                    "nom": "Sous-titres",
                    "x": 0.18,
                    "y": 0.78,
                    "l": 0.64,
                    "h": 0.16,
                },
                {
                    "nom": "Armes, munitions, objets",
                    "x": 0.74,
                    "y": 0.76,
                    "l": 0.26,
                    "h": 0.24,
                },
                {
                    "nom": "Notifications",
                    "x": 0.0,
                    "y": 0.68,
                    "l": 0.26,
                    "h": 0.32,
                },
            ],
            "conseil_plein_ecran": (
                "Dans Cyberpunk : Parametres > Graphismes (ou Video) > "
                "Mode fenetre > « Fenetre sans bordure »."
            ),
        },
        "Wow.exe": {
            "nom": "World of Warcraft",
            "autres_exe": [
                "WowClassic.exe",
                "WowClassicT.exe",
                "WowT.exe",
                "WowB.exe",
                "Wow-64.exe",
            ],
            "zones_interdites": [
                {
                    "nom": "Portraits joueur / cible",
                    "x": 0.0,
                    "y": 0.0,
                    "l": 0.30,
                    "h": 0.16,
                },
                {
                    "nom": "Groupe / raid",
                    "x": 0.0,
                    "y": 0.16,
                    "l": 0.14,
                    "h": 0.40,
                },
                {
                    "nom": "Minimap, buffs",
                    "x": 0.70,
                    "y": 0.0,
                    "l": 0.30,
                    "h": 0.22,
                },
                {
                    "nom": "Suivi des quetes",
                    "x": 0.80,
                    "y": 0.22,
                    "l": 0.20,
                    "h": 0.38,
                },
                {
                    "nom": "Messages (erreurs, zone)",
                    "x": 0.34,
                    "y": 0.16,
                    "l": 0.32,
                    "h": 0.08,
                },
                {
                    "nom": "Personnage / combat",
                    "x": 0.30,
                    "y": 0.24,
                    "l": 0.40,
                    "h": 0.34,
                },
                {
                    "nom": "Portraits (interface moderne)",
                    "x": 0.24,
                    "y": 0.58,
                    "l": 0.52,
                    "h": 0.14,
                },
                {
                    "nom": "Barre d'incantation",
                    "x": 0.38,
                    "y": 0.72,
                    "l": 0.24,
                    "h": 0.08,
                },
                {
                    "nom": "Barres d'action",
                    "x": 0.25,
                    "y": 0.82,
                    "l": 0.50,
                    "h": 0.18,
                },
                {"nom": "Chat", "x": 0.0, "y": 0.62, "l": 0.30, "h": 0.38},
                {
                    "nom": "Sacs, menu",
                    "x": 0.78,
                    "y": 0.80,
                    "l": 0.22,
                    "h": 0.20,
                },
            ],
            "conseil_plein_ecran": (
                "Dans WoW : Echap > Options > Graphismes > "
                "Mode d'affichage > « Fenetre (plein ecran) »."
            ),
        },
    },
    "jeu_inconnu": {
        "nom": "Jeu inconnu (plein ecran)",
        "zones_interdites": [
            {"nom": "Centre", "x": 0.28, "y": 0.22, "l": 0.44, "h": 0.56},
            {
                "nom": "Bas centre (HUD)",
                "x": 0.26,
                "y": 0.80,
                "l": 0.48,
                "h": 0.20,
            },
            {"nom": "Haut centre", "x": 0.34, "y": 0.0, "l": 0.32, "h": 0.08},
        ],
    },
    "bureau": {"nom": "Bureau", "zones_interdites": []},
}


def load_profiles():
    if not os.path.exists(PROFILES_PATH):
        try:
            with open(PROFILES_PATH, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_PROFILES, f, indent=2, ensure_ascii=False)
        except OSError:
            logger.warning("load_profiles failed", exc_info=True)
        return DEFAULT_PROFILES
    try:
        with open(PROFILES_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return DEFAULT_PROFILES
    changed = False
    for k in ("jeux", "jeu_inconnu", "bureau"):
        if k not in data:
            data[k] = DEFAULT_PROFILES[k]
            changed = True
    for name, prof in DEFAULT_PROFILES["jeux"].items():
        if name not in data["jeux"]:
            data["jeux"][name] = prof
            changed = True
        elif (
            "conseil_plein_ecran" not in data["jeux"][name]
            and "conseil_plein_ecran" in prof
        ):
            data["jeux"][name]["conseil_plein_ecran"] = prof[
                "conseil_plein_ecran"
            ]
            changed = True
    if changed:
        try:
            with open(PROFILES_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except OSError:
            logger.warning("load_profiles failed", exc_info=True)
    return data


CAPTURES_DIR = os.path.join(settings.DATA_DIR, "captures")


def _safe(key):
    return "".join(ch if ch.isalnum() or ch in " ._-" else "_" for ch in key)


def capture_path(key):
    return os.path.join(CAPTURES_DIR, _safe(key or "aucun") + ".jpg")


def captured_games():
    try:
        return sorted(
            f[:-4]
            for f in os.listdir(CAPTURES_DIR)
            if f.lower().endswith(".jpg")
        )
    except OSError:
        return []


def pretty_name(exe):
    name = exe[:-4] if exe.lower().endswith(".exe") else exe
    return name.replace("_", " ").replace("-", " ").strip() or exe


def save_zones(key, zones):
    data = load_profiles()
    if data is DEFAULT_PROFILES:
        data = json.loads(json.dumps(DEFAULT_PROFILES))
    if key == "jeu_inconnu":
        data.setdefault("jeu_inconnu", {"nom": "Jeu (profil generique)"})[
            "zones_interdites"
        ] = zones
    else:
        prof = data.setdefault("jeux", {}).setdefault(
            key, {"nom": pretty_name(key)}
        )
        prof["zones_interdites"] = zones
    try:
        with open(PROFILES_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except OSError:
        logger.warning("save_zones failed", exc_info=True)
        return False


def profiles_mtime():
    try:
        return os.path.getmtime(PROFILES_PATH)
    except OSError:
        return 0


def foreground_info():
    try:
        user32 = win32.user32()
        kernel32 = win32.kernel32()
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return "", False
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        exe = ""
        h = kernel32.OpenProcess(0x1000, False, pid.value)
        if h:
            buf = ctypes.create_unicode_buffer(520)
            size = wintypes.DWORD(520)
            if kernel32.QueryFullProcessImageNameW(
                h, 0, buf, ctypes.byref(size)
            ):
                exe = os.path.basename(buf.value)
            kernel32.CloseHandle(h)
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        if (
            cls.value in ("Progman", "WorkerW", "Shell_TrayWnd")
            or exe.lower() == "explorer.exe"
        ):
            return exe, False
        r = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        mi = win32.MonitorInfo()
        mi.cbSize = ctypes.sizeof(mi)
        user32.GetMonitorInfoW(
            user32.MonitorFromWindow(hwnd, 2), ctypes.byref(mi)
        )
        m = mi.rcMonitor
        full = (
            r.left <= m.left
            and r.top <= m.top
            and r.right >= m.right
            and r.bottom >= m.bottom
        )
        return exe, full
    except Exception:
        logger.debug("foreground_info failed", exc_info=True)
        return "", False


def exclusive_fullscreen():
    try:
        state = ctypes.c_int(0)
        if (
            win32.shell32().SHQueryUserNotificationState(ctypes.byref(state))
            == 0
        ):
            return state.value == 3
    except Exception:
        logger.debug("exclusive_fullscreen failed", exc_info=True)
    return False


def current_profile(profiles):
    exe, full = foreground_info()
    for name, prof in profiles.get("jeux", {}).items():
        names = [name, *list(prof.get("autres_exe", []))]
        if exe and any(n.lower() == exe.lower() for n in names):
            return name, prof
    if full:
        return "jeu_inconnu", profiles["jeu_inconnu"]
    return "bureau", profiles["bureau"]
