import ctypes
import sys
import threading
from ctypes import wintypes

assert sys.platform == "win32"

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
WM_RELOAD = 0x8001
MOD_NOREPEAT = 0x4000
PM_NOREMOVE = 0


class MessageLoopHotkeys:
    def __init__(self):
        self._bindings = {}
        self._lock = threading.Lock()
        self._thread = None
        self._thread_id = 0
        self._ready = threading.Event()
        self._on_pressed = None
        self._on_failed = None

    def start(self, on_pressed, on_failed):
        self._on_pressed = on_pressed
        self._on_failed = on_failed
        self._thread = threading.Thread(
            target=self._run, name="hotkeys", daemon=True
        )
        self._thread.start()
        self._ready.wait(1.0)

    def bind(self, bindings):
        with self._lock:
            self._bindings = dict(bindings)
        self._post(WM_RELOAD)

    def stop(self):
        self._post(WM_QUIT)
        if self._thread is not None:
            self._thread.join(timeout=1.0)

    def _post(self, message):
        if self._thread_id:
            ctypes.windll.user32.PostThreadMessageW(
                self._thread_id, message, 0, 0
            )

    def _register(self):
        user32 = ctypes.windll.user32
        with self._lock:
            bindings = dict(self._bindings)
        ids, failed = {}, []
        for hotkey_id, (name, (mods, vk)) in enumerate(
            bindings.items(), start=1
        ):
            if user32.RegisterHotKey(None, hotkey_id, mods | MOD_NOREPEAT, vk):
                ids[hotkey_id] = name
            else:
                failed.append(name)
        if self._on_failed is not None:
            self._on_failed(failed)
        return ids

    def _unregister(self, ids):
        user32 = ctypes.windll.user32
        for hotkey_id in ids:
            user32.UnregisterHotKey(None, hotkey_id)

    def _run(self):
        user32 = ctypes.windll.user32
        msg = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_NOREMOVE)
        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        self._ready.set()
        ids = self._register()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY and msg.wParam in ids:
                if self._on_pressed is not None:
                    self._on_pressed(ids[msg.wParam])
            elif msg.message == WM_RELOAD:
                self._unregister(ids)
                ids = self._register()
        self._unregister(ids)
        self._thread_id = 0


MAPVK_VK_TO_CHAR = 2
DEAD_KEY_BIT = 0x8000


class Win32Keyboard:
    def virtual_key(self, native_key, qt_key):
        return native_key

    def key_char(self, virtual_key):
        try:
            code = ctypes.windll.user32.MapVirtualKeyW(
                virtual_key, MAPVK_VK_TO_CHAR
            )
        except (OSError, AttributeError):
            return None
        code &= DEAD_KEY_BIT - 1
        return chr(code).upper() if code > 32 else None
