import contextlib
import json
import logging
import os
import sys
import tempfile
from typing import Any

logger = logging.getLogger(__name__)

APP_NAME = "FollowTheLyrics"
OLD_NAMES = ("LyricsOverlay", "Lyrics Overlay")
PACKAGE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(os.path.dirname(PACKAGE_DIR))
FROZEN = bool(getattr(sys, "frozen", False))


def _user_config_root():
    if sys.platform == "win32":
        return os.environ.get("APPDATA") or os.path.expanduser("~")
    if sys.platform == "darwin":
        return os.path.join(
            os.path.expanduser("~"), "Library", "Application Support"
        )
    return os.environ.get("XDG_CONFIG_HOME") or os.path.join(
        os.path.expanduser("~"), ".config"
    )


def _data_dir():
    if not FROZEN:
        return os.environ.get("FTL_DATA_DIR") or PROJECT_ROOT
    base = _user_config_root()
    path = os.path.join(base, APP_NAME)
    old = os.path.join(base, "LyricsOverlay")
    try:
        if os.path.isdir(old) and not os.path.exists(path):
            os.rename(old, path)
    except OSError:
        pass
    with contextlib.suppress(OSError):
        os.makedirs(path, exist_ok=True)
    return path


DATA_DIR = _data_dir()
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")

MODES = {
    "classic": (
        "Classique",
        "Les lignes défilent dans un coin, comme sur Spotify.",
    ),
    "edit": ("Edit", "Chaque ligne surgit à un endroit différent de l'écran."),
    "typewriter": (
        "Machine à écrire",
        "Les lettres s'écrivent au fil du chant.",
    ),
}
POSITIONS = {"left": "Gauche", "center": "Centre", "right": "Droite"}
COLORS = {"album": "Couleurs de l'album", "white": "Blanc lumineux"}
STYLES = {"kinetic": "Cinétique", "karaoke": "Karaoké", "simple": "Simple"}
TITLE_DROP = {"always": "Toujours", "desktop": "Hors jeu", "never": "Jamais"}


def app_label(app_id: str) -> str:
    low = app_id.lower()
    for needle, name in (
        ("spotify", "Spotify"),
        ("operagx", "Opera GX"),
        ("opera", "Opera"),
        ("chrome", "Google Chrome"),
        ("msedge", "Microsoft Edge"),
        ("firefox", "Firefox"),
        ("brave", "Brave"),
        ("deezer", "Deezer"),
        ("applemusic", "Apple Music"),
        ("itunes", "iTunes"),
        ("zunemusic", "Lecteur multimédia"),
        ("vlc", "VLC"),
        ("tidal", "Tidal"),
        ("amazon", "Amazon Music"),
        ("discord", "Discord"),
        ("riotclient", "Riot Client"),
    ):
        if needle in low:
            return name
    name = app_id.split("!", maxsplit=1)[0].rsplit("\\", maxsplit=1)[-1]
    return name[:-4] if name.lower().endswith(".exe") else name


RECOMMENDED_FONTS = [
    "Segoe UI Variable Display",
    "Bahnschrift",
    "Segoe UI Black",
    "Arial Black",
    "Impact",
    "Franklin Gothic Heavy",
    "Gill Sans Ultra Bold",
    "Montserrat",
    "Poppins",
    "Inter",
    "Ink Free",
    "Segoe Print",
    "Cascadia Code",
    "Consolas",
    "Courier New",
    "Georgia",
    "Trebuchet MS",
]

DEFAULTS: dict[str, Any] = {
    "mode": "edit",
    "position": "left",
    "color": "album",
    "font": "Segoe UI Variable Display",
    "style": "kinetic",
    "scale": 1.0,
    "offset": 0.0,
    "translation": True,
    "liriqo": True,
    "beat": True,
    "card": True,
    "particles": True,
    "easter": True,
    "tilt": True,
    "stack": True,
    "title_drop": "always",
    "sources_blocked": [],
    "sites_off": [],
    "sites_other": False,
    "welcomed": False,
    "glass": True,
}


def load_config():
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    if cfg.get("style") == "pop":
        cfg["style"] = "kinetic"
    for key in ("sources_blocked", "sites_off"):
        if not isinstance(cfg.get(key), list):
            cfg[key] = []
    for key, allowed in (
        ("mode", MODES),
        ("position", POSITIONS),
        ("color", COLORS),
        ("style", STYLES),
        ("title_drop", TITLE_DROP),
    ):
        if cfg.get(key) not in allowed:
            cfg[key] = DEFAULTS[key]
    try:
        cfg["scale"] = min(1.6, max(0.7, float(cfg["scale"])))
        cfg["offset"] = float(cfg["offset"])
    except (TypeError, ValueError):
        cfg["scale"], cfg["offset"] = 1.0, 0.0
    for old in ("theme",):
        cfg.pop(old, None)
    return cfg


def write_json(path, data, indent=2):
    folder = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(tmp)
        raise


def save_config(cfg):
    try:
        write_json(CONFIG_PATH, cfg)
    except OSError:
        logger.warning("save_config failed", exc_info=True)
