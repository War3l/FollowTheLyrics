import ctypes
import logging
import os
import sys
import time
from ctypes import wintypes

from followthelyrics.desktop import ports
from followthelyrics.desktop.windows import api

assert sys.platform == "win32"

logger = logging.getLogger(__name__)

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
MONITOR_DEFAULTTONEAREST = 2
QUNS_RUNNING_D3D_FULL_SCREEN = 3
SHELL_CLASSES = ("Progman", "WorkerW", "Shell_TrayWnd")
EXE_CACHE_SECONDS = 60


def _image_path(pid):
    kernel32 = api.kernel32()
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(520)
        size = wintypes.DWORD(520)
        if kernel32.QueryFullProcessImageNameW(
            handle, 0, buf, ctypes.byref(size)
        ):
            return buf.value
        return ""
    finally:
        kernel32.CloseHandle(handle)


def _window_pid(hwnd):
    pid = wintypes.DWORD()
    api.user32().GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def _covers_monitor(hwnd):
    user32 = api.user32()
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    info = api.MonitorInfo()
    info.cbSize = ctypes.sizeof(info)
    user32.GetMonitorInfoW(
        user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST),
        ctypes.byref(info),
    )
    monitor = info.rcMonitor
    return (
        rect.left <= monitor.left
        and rect.top <= monitor.top
        and rect.right >= monitor.right
        and rect.bottom >= monitor.bottom
    )


class Win32Foreground:
    def __init__(self):
        self._exe_cache = {}
        self._exe_cache_at = 0.0

    def current(self):
        try:
            user32 = api.user32()
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return ports.ForegroundApp()
            exe = os.path.basename(_image_path(_window_pid(hwnd)))
            cls = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls, 256)
            if cls.value in SHELL_CLASSES or exe.lower() == "explorer.exe":
                return ports.ForegroundApp(exe, fullscreen=False)
            title = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, title, 256)
            return ports.ForegroundApp(
                exe, fullscreen=_covers_monitor(hwnd), title=title.value
            )
        except Exception:
            logger.debug("current failed", exc_info=True)
            return ports.ForegroundApp()

    def exclusive_fullscreen(self):
        try:
            state = ctypes.c_int(0)
            if (
                api.shell32().SHQueryUserNotificationState(ctypes.byref(state))
                == 0
            ):
                return state.value == QUNS_RUNNING_D3D_FULL_SCREEN
        except Exception:
            logger.debug("exclusive_fullscreen failed", exc_info=True)
        return False

    def window_titles(self, exes):
        titles = []
        wanted = tuple(e.lower() for e in exes)
        try:
            user32 = ctypes.windll.user32

            @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            def collect(hwnd, _):
                if not user32.IsWindowVisible(hwnd):
                    return True
                length = user32.GetWindowTextLengthW(hwnd)
                if length <= 0:
                    return True
                if self._exe_name(_window_pid(hwnd)) in wanted:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    if buf.value:
                        titles.append(buf.value)
                return True

            user32.EnumWindows(collect, 0)
        except Exception:
            logger.debug("window_titles failed", exc_info=True)
        return titles

    def _exe_name(self, pid):
        now = time.monotonic()
        if now - self._exe_cache_at > EXE_CACHE_SECONDS:
            self._exe_cache.clear()
            self._exe_cache_at = now
        if pid not in self._exe_cache:
            path = _image_path(pid).replace("/", "\\")
            self._exe_cache[pid] = path.split("\\")[-1].lower()
        return self._exe_cache[pid]
