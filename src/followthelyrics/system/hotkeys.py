from PyQt6.QtCore import QObject
from PyQt6.QtCore import pyqtSignal

from followthelyrics.desktop import ports

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

MOD_ALT, MOD_CTRL, MOD_SHIFT = ports.MOD_ALT, ports.MOD_CTRL, ports.MOD_SHIFT
MODS = (("Ctrl", MOD_CTRL), ("Alt", MOD_ALT), ("Shift", MOD_SHIFT))
MODIFIER_VKS = {
    0x10,
    0x11,
    0x12,
    0x5B,
    0x5C,
    0xA0,
    0xA1,
    0xA2,
    0xA3,
    0xA4,
    0xA5,
}

NAMED = {
    0x26: "Up",
    0x28: "Down",
    0x25: "Left",
    0x27: "Right",
    0x20: "Space",
    0x09: "Tab",
    0x0D: "Enter",
    0x2D: "Insert",
    0x2E: "Delete",
    0x24: "Home",
    0x23: "End",
    0x21: "PageUp",
    0x22: "PageDown",
    0x13: "Pause",
    0x08: "Backspace",
    0x6A: "NumMul",
    0x6B: "NumAdd",
    0x6D: "NumSub",
    0x6E: "NumDec",
    0x6F: "NumDiv",
}
for _i in range(26):
    NAMED[0x41 + _i] = chr(0x41 + _i)
for _i in range(10):
    NAMED[0x30 + _i] = str(_i)
    NAMED[0x60 + _i] = f"Num{_i}"
for _i in range(24):
    NAMED[0x70 + _i] = f"F{_i + 1}"
BY_NAME = {name.lower(): vk for vk, name in NAMED.items()}

PRETTY = {
    "Up": "↑",
    "Down": "↓",
    "Left": "←",
    "Right": "→",
    "Space": "Espace",
    "Enter": "Entrée",
    "Delete": "Suppr",
    "Home": "Début",
    "End": "Fin",
    "PageUp": "Pg préc",
    "PageDown": "Pg suiv",
    "Insert": "Inser",
    "Backspace": "Retour",
    "Shift": "Maj",
    "NumMul": "Num *",
    "NumAdd": "Num +",
    "NumSub": "Num −",
    "NumDec": "Num .",
    "NumDiv": "Num /",
}


def is_function_key(vk):
    return 0x70 <= vk <= 0x87


def parse(combo):
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
    parts = [name for name, flag in MODS if mods & flag]
    parts.append(NAMED.get(vk) or f"VK_{vk:02X}")
    return "+".join(parts)


def allowed(mods, vk):
    if vk in MODIFIER_VKS or vk == 0x1B:
        return False
    return bool(mods & (MOD_CTRL | MOD_ALT)) or is_function_key(vk)


def key_names(combo, char_of=None):
    out = []
    for raw in (combo or "").split("+"):
        part = raw.strip()
        if not part:
            continue
        if char_of is not None and part.upper().startswith("VK_"):
            try:
                char = char_of(int(part[3:], 16))
            except ValueError:
                char = None
            part = char or part
        out.append(PRETTY.get(part, part))
    return out


def pretty(combo, char_of=None):
    if not combo:
        return "aucun raccourci"
    return " + ".join(key_names(combo, char_of))


def normalize(saved):
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


def bindings_of(combos):
    out = {}
    for name, _label, _default in ACTIONS:
        parsed = parse(combos.get(name, ""))
        if parsed:
            out[name] = parsed
    return out


class Hotkeys(QObject):
    pressed = pyqtSignal(str)
    failed = pyqtSignal(list)

    def __init__(self, backend, keyboard, combos):
        super().__init__()
        self._backend = backend
        self.keyboard = keyboard
        self._combos = dict(combos)
        self._paused = False

    @property
    def available(self):
        return self._backend is not None

    def start(self):
        if self._backend is None:
            return
        self._backend.start(self.pressed.emit, self._report_failed)
        self._apply()

    def stop(self):
        if self._backend is not None:
            self._backend.stop()

    def set_bindings(self, combos):
        self._combos = dict(combos)
        self._apply()

    def pause(self):
        self._paused = True
        self._apply()

    def resume(self):
        self._paused = False
        self._apply()

    def key_names(self, combo):
        return key_names(combo, self.keyboard.key_char)

    def pretty(self, combo):
        return pretty(combo, self.keyboard.key_char)

    def _apply(self):
        if self._backend is not None:
            self._backend.bind(
                {} if self._paused else bindings_of(self._combos)
            )

    def _report_failed(self, names):
        if not self._paused:
            self.failed.emit(list(names))
