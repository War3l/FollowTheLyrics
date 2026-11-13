import logging
import os
import select
import threading

from Xlib import XK
from Xlib import X
from Xlib import display
from Xlib import error

from followthelyrics.desktop import ports

logger = logging.getLogger(__name__)

POLL_SECONDS = 0.1
NUM_LOCK = X.Mod2Mask
LOCK_VARIANTS = (0, X.LockMask, NUM_LOCK, X.LockMask | NUM_LOCK)
MODIFIER_MASKS = (
    (ports.MOD_CTRL, X.ControlMask),
    (ports.MOD_ALT, X.Mod1Mask),
    (ports.MOD_SHIFT, X.ShiftMask),
)
NAMED_KEYSYMS = {
    0x08: "BackSpace",
    0x09: "Tab",
    0x0D: "Return",
    0x13: "Pause",
    0x20: "space",
    0x21: "Prior",
    0x22: "Next",
    0x23: "End",
    0x24: "Home",
    0x25: "Left",
    0x26: "Up",
    0x27: "Right",
    0x28: "Down",
    0x2D: "Insert",
    0x2E: "Delete",
    0x6A: "KP_Multiply",
    0x6B: "KP_Add",
    0x6D: "KP_Subtract",
    0x6E: "KP_Decimal",
    0x6F: "KP_Divide",
}


def keysym_name(virtual_key):
    if 0x41 <= virtual_key <= 0x5A:
        return chr(virtual_key).lower()
    if 0x30 <= virtual_key <= 0x39:
        return chr(virtual_key)
    if 0x60 <= virtual_key <= 0x69:
        return f"KP_{virtual_key - 0x60}"
    if 0x70 <= virtual_key <= 0x87:
        return f"F{virtual_key - 0x6F}"
    return NAMED_KEYSYMS.get(virtual_key)


def modifier_mask(mods):
    mask = 0
    for flag, x_mask in MODIFIER_MASKS:
        if mods & flag:
            mask |= x_mask
    return mask


def available():
    if not os.environ.get("DISPLAY"):
        return False
    try:
        display.Display().close()
    except Exception:
        logger.debug("available failed", exc_info=True)
        return False
    return True


def _keycode(conn, virtual_key):
    name = keysym_name(virtual_key)
    keysym = XK.string_to_keysym(name) if name else 0
    return conn.keysym_to_keycode(keysym) if keysym else 0


class X11Hotkeys:
    def __init__(self):
        self._bindings = {}
        self._dirty = threading.Event()
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread = None
        self._on_pressed = None
        self._on_failed = None

    def start(self, on_pressed, on_failed):
        self._on_pressed = on_pressed
        self._on_failed = on_failed
        self._thread = threading.Thread(
            target=self._run, name="hotkeys", daemon=True
        )
        self._thread.start()

    def bind(self, bindings):
        with self._lock:
            self._bindings = dict(bindings)
        self._dirty.set()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)

    def _run(self):
        try:
            conn = display.Display()
        except Exception:
            logger.warning("_run failed", exc_info=True)
            return
        root = conn.screen().root
        grabbed: dict[tuple[int, int], str] = {}
        try:
            while not self._stop.is_set():
                if self._dirty.is_set():
                    self._dirty.clear()
                    self._release(root, grabbed)
                    grabbed = self._grab(conn, root)
                self._dispatch(conn, grabbed)
        finally:
            self._release(root, grabbed)
            conn.close()

    def _grab(self, conn, root):
        with self._lock:
            bindings = dict(self._bindings)
        grabbed, failed = {}, []
        for name, (mods, virtual_key) in bindings.items():
            keycode = _keycode(conn, virtual_key)
            mask = modifier_mask(mods)
            catcher = error.CatchError(error.BadAccess)
            if keycode:
                for variant in LOCK_VARIANTS:
                    root.grab_key(
                        keycode,
                        mask | variant,
                        True,
                        X.GrabModeAsync,
                        X.GrabModeAsync,
                        onerror=catcher,
                    )
                conn.sync()
            if not keycode or catcher.get_error():
                failed.append(name)
                continue
            grabbed[(keycode, mask)] = name
        if self._on_failed is not None:
            self._on_failed(failed)
        return grabbed

    def _release(self, root, grabbed):
        for keycode, mask in grabbed:
            for variant in LOCK_VARIANTS:
                root.ungrab_key(keycode, mask | variant)

    def _dispatch(self, conn, grabbed):
        if not conn.pending_events():
            select.select([conn], [], [], POLL_SECONDS)
        for _ in range(conn.pending_events()):
            event = conn.next_event()
            if event.type != X.KeyPress:
                continue
            mask = event.state & ~(X.LockMask | NUM_LOCK)
            name = grabbed.get((event.detail, mask))
            if name and self._on_pressed is not None:
                self._on_pressed(name)


def _exe_of(pid):
    try:
        return os.path.basename(os.readlink(f"/proc/{pid}/exe"))
    except OSError:
        return ""


class X11Foreground:
    def __init__(self):
        self._lock = threading.Lock()
        self._conn = display.Display()
        self._atoms = {
            name: self._conn.intern_atom(name)
            for name in (
                "_NET_ACTIVE_WINDOW",
                "_NET_CLIENT_LIST",
                "_NET_WM_PID",
                "_NET_WM_NAME",
                "_NET_WM_STATE",
                "_NET_WM_STATE_FULLSCREEN",
                "UTF8_STRING",
            )
        }

    def current(self):
        with self._lock:
            try:
                window = self._active()
                if window is None:
                    return ports.ForegroundApp()
                return ports.ForegroundApp(
                    exe=self._exe(window), fullscreen=self._fullscreen(window)
                )
            except error.XError:
                logger.debug("current failed", exc_info=True)
                return ports.ForegroundApp()

    def exclusive_fullscreen(self):
        return False

    def window_titles(self, exes):
        wanted = {_stem(e) for e in exes}
        titles = []
        with self._lock:
            for window in self._clients():
                try:
                    if _stem(self._exe(window)) in wanted:
                        title = self._title(window)
                        if title:
                            titles.append(title)
                except error.XError:
                    logger.debug("window_titles failed", exc_info=True)
        return titles

    def _property(self, window, name, kind=X.AnyPropertyType):
        prop = window.get_full_property(self._atoms[name], kind)
        return prop.value if prop is not None else None

    def _active(self):
        value = self._property(self._conn.screen().root, "_NET_ACTIVE_WINDOW")
        if not value or not value[0]:
            return None
        return self._conn.create_resource_object("window", value[0])

    def _clients(self):
        value = self._property(self._conn.screen().root, "_NET_CLIENT_LIST")
        return [
            self._conn.create_resource_object("window", wid)
            for wid in (value or ())
        ]

    def _exe(self, window):
        wm_class = window.get_wm_class()
        if wm_class and wm_class[0].lower().endswith(".exe"):
            return wm_class[0]
        pid = self._property(window, "_NET_WM_PID")
        return _exe_of(pid[0]) if pid else ""

    def _fullscreen(self, window):
        states = self._property(window, "_NET_WM_STATE") or ()
        return self._atoms["_NET_WM_STATE_FULLSCREEN"] in states

    def _title(self, window):
        name = self._property(
            window, "_NET_WM_NAME", self._atoms["UTF8_STRING"]
        )
        if isinstance(name, bytes):
            return name.decode("utf-8", "replace")
        return str(name or window.get_wm_name() or "")


def _stem(exe):
    low = (exe or "").lower()
    return low[:-4] if low.endswith(".exe") else low
