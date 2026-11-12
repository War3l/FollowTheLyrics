"""Reglages partages entre l'overlay et le panneau (sauves dans config.json)."""
import json
import os
import sys

APP_NAME = "FollowTheLyrics"
OLD_NAMES = ("LyricsOverlay", "Lyrics Overlay")  # anciens noms du projet
HERE = os.path.dirname(os.path.abspath(__file__))
FROZEN = bool(getattr(sys, "frozen", False))  # True dans le .exe


def _data_dir():
    """Ou ranger reglages, profils et cache. En .exe : AppData (le .exe peut etre
    n'importe ou, meme dans un dossier protege). En mode script : a cote du code."""
    if not FROZEN:
        return HERE
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, APP_NAME)
    old = os.path.join(base, "LyricsOverlay")
    try:  # reglages de l'ancien nom du projet : on les reprend
        if os.path.isdir(old) and not os.path.exists(path):
            os.rename(old, path)
    except Exception:
        pass
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        pass
    return path


DATA_DIR = _data_dir()
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")

# ---- demarrage avec Windows / raccourci bureau -----------------------------
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_NAME = APP_NAME


def launch_command(minimized=False, exe=None):
    """La commande qui relance l'appli (le .exe, ou pythonw + script)."""
    if exe or FROZEN:
        cmd = f'"{exe or sys.executable}"'
    else:
        py = sys.executable
        pyw = os.path.join(os.path.dirname(py), "pythonw.exe")
        cmd = f'"{pyw if os.path.exists(pyw) else py}" "{os.path.join(HERE, "overlay.py")}"'
    return cmd + (" --minimized" if minimized else "")


def autostart_command():
    """La commande inscrite pour le demarrage avec Windows ('' s'il est coupe)."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
            value, _ = winreg.QueryValueEx(k, _RUN_NAME)
        return str(value or "")
    except Exception:
        return ""


def autostart_enabled():
    return bool(autostart_command())


def set_autostart(on, exe=None):
    """Lance (ou non) l'appli a l'ouverture de session, reduite pres de l'heure."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, _RUN_NAME, 0, winreg.REG_SZ, launch_command(minimized=True, exe=exe))
            else:
                try:
                    winreg.DeleteValue(k, _RUN_NAME)
                except FileNotFoundError:
                    pass
        return True
    except Exception:
        return False


def refresh_autostart():
    """Si le .exe a ete deplace, on corrige le chemin enregistre."""
    was_old = False
    try:  # entree de l'ancien nom du projet
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE) as k:
            for old in OLD_NAMES:
                try:
                    winreg.QueryValueEx(k, old)
                    winreg.DeleteValue(k, old)
                    was_old = True
                except FileNotFoundError:
                    pass
    except Exception:
        pass
    if was_old or autostart_enabled():
        set_autostart(True)
    try:  # raccourci bureau de l'ancien nom : il pointe vers un .exe qui n'existe plus
        from PyQt6.QtCore import QStandardPaths
        desktop = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)
        old_link = os.path.join(desktop, "Lyrics Overlay.lnk")
        if os.path.exists(old_link):
            os.remove(old_link)
            create_desktop_shortcut()
    except Exception:
        pass


def desktop_link():
    """Chemin du raccourci « FollowTheLyrics » sur le bureau ('' si le bureau est introuvable)."""
    try:
        from PyQt6.QtCore import QStandardPaths
        desktop = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)
        return os.path.join(desktop, APP_NAME + ".lnk") if desktop else ""
    except Exception:
        return ""


def create_desktop_shortcut(exe=None):
    """Raccourci « FollowTheLyrics » sur le bureau (seulement pour le .exe)."""
    if not (exe or FROZEN):
        return False
    try:
        from PyQt6.QtCore import QFile
        link = desktop_link()
        if not link:
            return False
        if os.path.exists(link):
            os.remove(link)
        return bool(QFile.link(exe or sys.executable, link))
    except Exception:
        return False

MODES = {
    "classic": ("Classique", "Les lignes défilent dans un coin, comme sur Spotify."),
    "edit": ("Edit", "Chaque ligne surgit à un endroit différent de l'écran."),
    "typewriter": ("Machine à écrire", "Les lettres s'écrivent au fil du chant."),
}
POSITIONS = {"left": "Gauche", "center": "Centre", "right": "Droite"}
COLORS = {"album": "Couleurs de l'album", "white": "Blanc lumineux"}
STYLES = {"kinetic": "Cinétique", "karaoke": "Karaoké", "simple": "Simple"}
TITLE_DROP = {"always": "Toujours", "desktop": "Hors jeu", "never": "Jamais"}


def app_label(app_id: str) -> str:
    """Nom lisible d'une appli a partir de son identifiant Windows."""
    low = app_id.lower()
    for needle, name in (("spotify", "Spotify"), ("operagx", "Opera GX"), ("opera", "Opera"),
                         ("chrome", "Google Chrome"), ("msedge", "Microsoft Edge"), ("firefox", "Firefox"),
                         ("brave", "Brave"), ("deezer", "Deezer"), ("applemusic", "Apple Music"),
                         ("itunes", "iTunes"), ("zunemusic", "Lecteur multimédia"), ("vlc", "VLC"),
                         ("tidal", "Tidal"), ("amazon", "Amazon Music"), ("discord", "Discord"),
                         ("riotclient", "Riot Client")):
        if needle in low:
            return name
    name = app_id.split("!")[0].split("\\")[-1]
    return name[:-4] if name.lower().endswith(".exe") else name

# Polices conseillees (affichees en premier si elles sont installees)
RECOMMENDED_FONTS = [
    "Segoe UI Variable Display", "Bahnschrift", "Segoe UI Black", "Arial Black", "Impact",
    "Franklin Gothic Heavy", "Gill Sans Ultra Bold", "Montserrat", "Poppins", "Inter",
    "Ink Free", "Segoe Print", "Cascadia Code", "Consolas", "Courier New", "Georgia",
    "Trebuchet MS",
]

DEFAULTS = {
    "mode": "edit", "position": "left", "color": "album", "font": "Segoe UI Variable Display",
    "style": "kinetic", "scale": 1.0, "offset": 0.0,
    "translation": True, "beat": True, "card": True, "particles": True, "easter": True, "tilt": True, "stack": True,
    "title_drop": "always", "sources_blocked": [], "welcomed": False, "glass": True,
}


def load_config():
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except Exception:
        pass
    if cfg.get("style") == "pop":
        cfg["style"] = "kinetic"
    if not isinstance(cfg.get("sources_blocked"), list):
        cfg["sources_blocked"] = []
    for key, allowed in (("mode", MODES), ("position", POSITIONS), ("color", COLORS), ("style", STYLES),
                         ("title_drop", TITLE_DROP)):
        if cfg.get(key) not in allowed:
            cfg[key] = DEFAULTS[key]
    try:
        cfg["scale"] = min(1.6, max(0.7, float(cfg["scale"])))
        cfg["offset"] = float(cfg["offset"])
    except Exception:
        cfg["scale"], cfg["offset"] = 1.0, 0.0
    for old in ("theme",):
        cfg.pop(old, None)
    return cfg


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception:
        pass
