"""Detection du jeu au premier plan et zones de l'ecran a ne pas couvrir.

Le logiciel demande juste a Windows quel programme est au premier plan :
il ne touche pas au jeu (rien d'injecte), donc aucun souci d'anti-cheat.
"""
import ctypes
import json
import os
from ctypes import wintypes

from settings import DATA_DIR

PROFILES_PATH = os.path.join(DATA_DIR, "profiles.json")

# Zones en fraction de l'ecran : x, y = coin haut-gauche ; l, h = largeur, hauteur.
DEFAULT_PROFILES = {
    "_aide": "Zones en fraction de l'ecran (0 a 1) : x,y = coin haut-gauche, l,h = largeur,hauteur. "
             "En jeu, Ctrl+Alt+Z affiche les zones en rouge. Le fichier est relu automatiquement.",
    "jeux": {
        "League of Legends.exe": {
            "nom": "League of Legends",
            "zones_interdites": [
                {"nom": "Combat (centre)", "x": 0.26, "y": 0.13, "l": 0.48, "h": 0.65},
                {"nom": "Sorts, vie, objets", "x": 0.24, "y": 0.78, "l": 0.52, "h": 0.22},
                {"nom": "Minimap", "x": 0.76, "y": 0.64, "l": 0.24, "h": 0.36},
                {"nom": "Score, KDA, temps", "x": 0.68, "y": 0.0, "l": 0.32, "h": 0.07},
                {"nom": "Chat", "x": 0.0, "y": 0.66, "l": 0.27, "h": 0.34},
                {"nom": "Annonces (kills, objectifs)", "x": 0.32, "y": 0.04, "l": 0.36, "h": 0.11},
                {"nom": "Allies / kill feed", "x": 0.88, "y": 0.07, "l": 0.12, "h": 0.57},
            ],
            "conseil_plein_ecran": "Dans LoL : Echap > Video > Mode fenetre > « Sans bordure ».",
        },
        "Cyberpunk2077.exe": {
            "nom": "Cyberpunk 2077",
            "zones_interdites": [
                {"nom": "Vie, niveau, effets", "x": 0.0, "y": 0.0, "l": 0.30, "h": 0.16},
                {"nom": "Appels (holocall)", "x": 0.0, "y": 0.16, "l": 0.22, "h": 0.18},
                {"nom": "Minimap, recherche", "x": 0.80, "y": 0.0, "l": 0.20, "h": 0.30},
                {"nom": "Objectif de quete", "x": 0.72, "y": 0.28, "l": 0.28, "h": 0.17},
                {"nom": "Viseur / combat", "x": 0.33, "y": 0.30, "l": 0.34, "h": 0.40},
                {"nom": "Dialogues, interactions", "x": 0.55, "y": 0.44, "l": 0.30, "h": 0.32},
                {"nom": "Sous-titres", "x": 0.18, "y": 0.78, "l": 0.64, "h": 0.16},
                {"nom": "Armes, munitions, objets", "x": 0.74, "y": 0.76, "l": 0.26, "h": 0.24},
                {"nom": "Notifications", "x": 0.0, "y": 0.68, "l": 0.26, "h": 0.32},
            ],
            "conseil_plein_ecran": "Dans Cyberpunk : Parametres > Graphismes (ou Video) > Mode fenetre > "
                                   "« Fenetre sans bordure ».",
        },
        "Wow.exe": {
            "nom": "World of Warcraft",
            # autres noms du jeu selon la version (Classic, PTR, anciens clients)
            "autres_exe": ["WowClassic.exe", "WowClassicT.exe", "WowT.exe", "WowB.exe", "Wow-64.exe"],
            "zones_interdites": [
                {"nom": "Portraits joueur / cible", "x": 0.0, "y": 0.0, "l": 0.30, "h": 0.16},
                {"nom": "Groupe / raid", "x": 0.0, "y": 0.16, "l": 0.14, "h": 0.40},
                {"nom": "Minimap, buffs", "x": 0.70, "y": 0.0, "l": 0.30, "h": 0.22},
                {"nom": "Suivi des quetes", "x": 0.80, "y": 0.22, "l": 0.20, "h": 0.38},
                {"nom": "Messages (erreurs, zone)", "x": 0.34, "y": 0.16, "l": 0.32, "h": 0.08},
                {"nom": "Personnage / combat", "x": 0.30, "y": 0.24, "l": 0.40, "h": 0.34},
                {"nom": "Portraits (interface moderne)", "x": 0.24, "y": 0.58, "l": 0.52, "h": 0.14},
                {"nom": "Barre d'incantation", "x": 0.38, "y": 0.72, "l": 0.24, "h": 0.08},
                {"nom": "Barres d'action", "x": 0.25, "y": 0.82, "l": 0.50, "h": 0.18},
                {"nom": "Chat", "x": 0.0, "y": 0.62, "l": 0.30, "h": 0.38},
                {"nom": "Sacs, menu", "x": 0.78, "y": 0.80, "l": 0.22, "h": 0.20},
            ],
            "conseil_plein_ecran": "Dans WoW : Echap > Options > Graphismes > Mode d'affichage > "
                                   "« Fenetre (plein ecran) ».",
        },
    },
    "jeu_inconnu": {
        "nom": "Jeu inconnu (plein ecran)",
        "zones_interdites": [
            {"nom": "Centre", "x": 0.28, "y": 0.22, "l": 0.44, "h": 0.56},
            {"nom": "Bas centre (HUD)", "x": 0.26, "y": 0.80, "l": 0.48, "h": 0.20},
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
        except Exception:
            pass
        return DEFAULT_PROFILES
    try:
        with open(PROFILES_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return DEFAULT_PROFILES
    changed = False
    for k in ("jeux", "jeu_inconnu", "bureau"):
        if k not in data:
            data[k] = DEFAULT_PROFILES[k]
            changed = True
    # nouveaux jeux ajoutes dans une mise a jour : on les ajoute sans toucher a tes reglages
    for name, prof in DEFAULT_PROFILES["jeux"].items():
        if name not in data["jeux"]:
            data["jeux"][name] = prof
            changed = True
        elif "conseil_plein_ecran" not in data["jeux"][name] and "conseil_plein_ecran" in prof:
            data["jeux"][name]["conseil_plein_ecran"] = prof["conseil_plein_ecran"]
            changed = True
    if changed:
        try:
            with open(PROFILES_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
    return data


CAPTURES_DIR = os.path.join(DATA_DIR, "captures")


def _safe(key):
    return "".join(ch if ch.isalnum() or ch in " ._-" else "_" for ch in key)


def capture_path(key):
    """Fichier de la capture d'ecran d'un jeu (pour l'editeur de zones)."""
    return os.path.join(CAPTURES_DIR, _safe(key or "aucun") + ".jpg")


def captured_games():
    """Cles des jeux dont on a une capture."""
    try:
        return sorted(f[:-4] for f in os.listdir(CAPTURES_DIR) if f.lower().endswith(".jpg"))
    except Exception:
        return []


def pretty_name(exe):
    name = exe[:-4] if exe.lower().endswith(".exe") else exe
    return name.replace("_", " ").replace("-", " ").strip() or exe


def save_zones(key, zones):
    """Enregistre les zones d'un jeu (le cree s'il est nouveau). key = nom du .exe,
    ou "jeu_inconnu" pour le profil des autres jeux en plein ecran."""
    data = load_profiles()
    if data is DEFAULT_PROFILES:
        data = json.loads(json.dumps(DEFAULT_PROFILES))
    if key == "jeu_inconnu":
        data.setdefault("jeu_inconnu", {"nom": "Jeu (profil generique)"})["zones_interdites"] = zones
    else:
        prof = data.setdefault("jeux", {}).setdefault(key, {"nom": pretty_name(key)})
        prof["zones_interdites"] = zones
    try:
        with open(PROFILES_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False


def profiles_mtime():
    try:
        return os.path.getmtime(PROFILES_PATH)
    except Exception:
        return 0


# --------------------------------------------------------------------------
# Fenetre au premier plan
# --------------------------------------------------------------------------
_u = ctypes.windll.user32
_k = ctypes.windll.kernel32
_u.GetForegroundWindow.restype = wintypes.HWND
_u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
_u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_u.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_u.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
_u.MonitorFromWindow.restype = wintypes.HANDLE
_k.OpenProcess.restype = wintypes.HANDLE
_k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_k.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                          ctypes.POINTER(wintypes.DWORD)]
_k.CloseHandle.argtypes = [wintypes.HANDLE]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


_u.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_MONITORINFO)]


def foreground_info():
    """-> (nom_exe, plein_ecran)"""
    try:
        hwnd = _u.GetForegroundWindow()
        if not hwnd:
            return "", False
        pid = wintypes.DWORD()
        _u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        exe = ""
        h = _k.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED_INFORMATION
        if h:
            buf = ctypes.create_unicode_buffer(520)
            size = wintypes.DWORD(520)
            if _k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                exe = os.path.basename(buf.value)
            _k.CloseHandle(h)
        cls = ctypes.create_unicode_buffer(256)
        _u.GetClassNameW(hwnd, cls, 256)
        if cls.value in ("Progman", "WorkerW", "Shell_TrayWnd") or exe.lower() == "explorer.exe":
            return exe, False
        r = wintypes.RECT()
        _u.GetWindowRect(hwnd, ctypes.byref(r))
        mi = _MONITORINFO()
        mi.cbSize = ctypes.sizeof(mi)
        _u.GetMonitorInfoW(_u.MonitorFromWindow(hwnd, 2), ctypes.byref(mi))
        m = mi.rcMonitor
        full = r.left <= m.left and r.top <= m.top and r.right >= m.right and r.bottom >= m.bottom
        return exe, full
    except Exception:
        return "", False


_s = ctypes.windll.shell32


def exclusive_fullscreen():
    """True si un jeu est en plein ecran EXCLUSIF (Direct3D) : dans ce mode, Windows
    n'affiche aucune autre fenetre par-dessus, meme "toujours au premier plan"."""
    try:
        state = ctypes.c_int(0)
        if _s.SHQueryUserNotificationState(ctypes.byref(state)) == 0:
            return state.value == 3  # QUNS_RUNNING_D3D_FULL_SCREEN
    except Exception:
        pass
    return False


def current_profile(profiles):
    """-> (cle, profil) pour la fenetre au premier plan."""
    exe, full = foreground_info()
    for name, prof in profiles.get("jeux", {}).items():
        names = [name] + list(prof.get("autres_exe", []))
        if exe and any(n.lower() == exe.lower() for n in names):
            return name, prof
    if full:
        return "jeu_inconnu", profiles["jeu_inconnu"]
    return "bureau", profiles["bureau"]


if __name__ == "__main__":
    print(foreground_info(), current_profile(load_profiles())[0])
