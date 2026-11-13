"""Raccourcis clavier globaux (marchent meme quand le jeu a le focus), modifiables.

Une combinaison est rangee en texte : « Ctrl+Alt+L », « Ctrl+Shift+F5 », « F9 »…
Une chaine vide veut dire « pas de raccourci pour cette action ».
"""
import ctypes
from ctypes import wintypes

from PyQt6.QtCore import QThread, pyqtSignal

# (action, ce que ca fait, combinaison d'origine) : l'ordre est celui du panneau
ACTIONS = [
    ("toggle", "Afficher / masquer les paroles", "Ctrl+Alt+L"),
    ("mode", "Changer de mode d'affichage", "Ctrl+Alt+M"),
    ("color", "Couleurs de l'album / blanc", "Ctrl+Alt+T"),
    ("style", "Changer d'animation", "Ctrl+Alt+S"),
    ("earlier", "Paroles plus tôt (+0,2 s)", "Ctrl+Alt+Up"),
    ("later", "Paroles plus tard (−0,2 s)", "Ctrl+Alt+Down"),
    ("zones", "Voir les zones du jeu (5 s)", "Ctrl+Alt+Z"),
    ("capture", "Capturer le jeu pour dessiner les zones", "Ctrl+Alt+E"),
]
DEFAULTS = {name: combo for name, _label, combo in ACTIONS}
LABELS = {name: label for name, label, _combo in ACTIONS}

MOD_ALT, MOD_CTRL, MOD_SHIFT, MOD_NOREPEAT = 0x0001, 0x0002, 0x0004, 0x4000
MODS = (("Ctrl", MOD_CTRL), ("Alt", MOD_ALT), ("Shift", MOD_SHIFT))
MODIFIER_VKS = {0x10, 0x11, 0x12, 0x5B, 0x5C, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5}

NAMED = {0x26: "Up", 0x28: "Down", 0x25: "Left", 0x27: "Right", 0x20: "Space", 0x09: "Tab",
         0x0D: "Enter", 0x2D: "Insert", 0x2E: "Delete", 0x24: "Home", 0x23: "End",
         0x21: "PageUp", 0x22: "PageDown", 0x13: "Pause", 0x08: "Backspace",
         0x6A: "NumMul", 0x6B: "NumAdd", 0x6D: "NumSub", 0x6E: "NumDec", 0x6F: "NumDiv"}
for _i in range(26):
    NAMED[0x41 + _i] = chr(0x41 + _i)
for _i in range(10):
    NAMED[0x30 + _i] = str(_i)
    NAMED[0x60 + _i] = f"Num{_i}"
for _i in range(24):
    NAMED[0x70 + _i] = f"F{_i + 1}"
BY_NAME = {name.lower(): vk for vk, name in NAMED.items()}

PRETTY = {"Up": "↑", "Down": "↓", "Left": "←", "Right": "→", "Space": "Espace", "Enter": "Entrée",
          "Delete": "Suppr", "Home": "Début", "End": "Fin", "PageUp": "Pg préc", "PageDown": "Pg suiv",
          "Insert": "Inser", "Backspace": "Retour", "Shift": "Maj", "NumMul": "Num *", "NumAdd": "Num +",
          "NumSub": "Num −", "NumDec": "Num .", "NumDiv": "Num /"}


def is_function_key(vk):
    return 0x70 <= vk <= 0x87


def parse(combo):
    """« Ctrl+Alt+L » -> (modificateurs, touche), ou None si ce n'est pas une combinaison."""
    if not isinstance(combo, str) or not combo.strip():
        return None
    mods, vk = 0, None
    for part in combo.split("+"):
        low = part.strip().lower()
        for name, flag in MODS:
            if low == name.lower():
                mods |= flag
                break
        else:
            if vk is not None:
                return None
            if low in BY_NAME:
                vk = BY_NAME[low]
            elif low.startswith("vk_"):
                try:
                    vk = int(low[3:], 16)
                except ValueError:
                    return None
            else:
                return None
    if vk is None or not 0 < vk < 0xFF or vk in MODIFIER_VKS:
        return None
    return mods, vk


def make(mods, vk):
    """(modificateurs, touche) -> texte range dans les reglages."""
    parts = [name for name, flag in MODS if mods & flag]
    parts.append(NAMED.get(vk) or f"VK_{vk:02X}")
    return "+".join(parts)


def allowed(mods, vk):
    """Ctrl ou Alt obligatoire (sinon on ne pourrait plus taper la touche), sauf F1…F24."""
    if vk in MODIFIER_VKS or vk == 0x1B:
        return False
    return bool(mods & (MOD_CTRL | MOD_ALT)) or is_function_key(vk)


def key_names(combo):
    """Les touches a afficher, une par une : « Ctrl+Alt+Up » -> ["Ctrl", "Alt", "↑"]."""
    out = []
    for part in (combo or "").split("+"):
        part = part.strip()
        if not part:
            continue
        if part.upper().startswith("VK_"):
            try:
                ch = ctypes.windll.user32.MapVirtualKeyW(int(part[3:], 16), 2) & 0x7FFF
                part = chr(ch).upper() if ch > 32 else part
            except Exception:
                pass
        out.append(PRETTY.get(part, part))
    return out


def pretty(combo):
    return " + ".join(key_names(combo)) if combo else "aucun raccourci"


def normalize(saved):
    """Reglages lus sur le disque -> une combinaison valide (ou vide) par action, sans doublon."""
    saved = saved if isinstance(saved, dict) else {}
    out, used = {}, set()
    for name, _label, default in ACTIONS:
        combo = saved.get(name, default)
        if combo != "":
            parsed = parse(combo)
            combo = make(*parsed) if parsed else default
        if combo and combo in used:
            combo = ""
        if combo:
            used.add(combo)
        out[name] = combo
    return out


class Hotkeys(QThread):
    pressed = pyqtSignal(str)
    failed = pyqtSignal(list)  # actions dont la combinaison est refusee (deja prise par une autre appli)
    WM_HOTKEY, WM_QUIT, WM_RELOAD = 0x0312, 0x0012, 0x8001

    def __init__(self, bindings):
        super().__init__()
        self.bindings = dict(bindings)
        self.paused = False
        self.tid = 0

    # ---- appele depuis l'appli -------------------------------------------------
    def set_bindings(self, bindings):
        self.bindings = dict(bindings)
        self._reload()

    def pause(self):
        """Pendant qu'on choisit une nouvelle combinaison : plus aucun raccourci actif."""
        self.paused = True
        self._reload()

    def resume(self):
        self.paused = False
        self._reload()

    def _reload(self):
        if self.tid:  # RegisterHotKey doit etre appele par le fil qui lit les messages
            ctypes.windll.user32.PostThreadMessageW(self.tid, self.WM_RELOAD, 0, 0)

    def stop(self):
        if self.tid:
            ctypes.windll.user32.PostThreadMessageW(self.tid, self.WM_QUIT, 0, 0)
        self.wait(1000)

    # ---- fil des raccourcis ------------------------------------------------------
    def _register(self):
        user32 = ctypes.windll.user32
        ids, bad = {}, []
        if not self.paused:
            for i, (name, _label, _default) in enumerate(ACTIONS):
                parsed = parse(self.bindings.get(name, ""))
                if not parsed:
                    continue
                mods, vk = parsed
                if user32.RegisterHotKey(None, i + 1, mods | MOD_NOREPEAT, vk):
                    ids[i + 1] = name
                else:
                    bad.append(name)
            self.failed.emit(bad)
        return ids

    def run(self):
        user32 = ctypes.windll.user32
        msg = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)  # cree la file de messages du fil
        self.tid = ctypes.windll.kernel32.GetCurrentThreadId()
        ids = self._register()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == self.WM_HOTKEY and msg.wParam in ids:
                self.pressed.emit(ids[msg.wParam])
            elif msg.message == self.WM_RELOAD:
                for hid in ids:
                    user32.UnregisterHotKey(None, hid)
                ids = self._register()
        for hid in ids:
            user32.UnregisterHotKey(None, hid)
