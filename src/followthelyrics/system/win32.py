import ctypes
import functools
from ctypes import wintypes


class MonitorInfo(ctypes.Structure):
    _fields_ = (
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    )


WinEventProc = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)(
    None,
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.HWND,
    wintypes.LONG,
    wintypes.LONG,
    wintypes.DWORD,
    wintypes.DWORD,
)


@functools.cache
def user32():
    lib = ctypes.WinDLL("user32", use_last_error=True)
    lib.GetForegroundWindow.restype = wintypes.HWND
    lib.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    ]
    lib.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    lib.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    lib.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    lib.MonitorFromWindow.restype = wintypes.HANDLE
    lib.GetMonitorInfoW.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(MonitorInfo),
    ]
    lib.SetWindowPos.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint,
    ]
    lib.SetWindowPos.restype = wintypes.BOOL
    lib.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    lib.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    lib.SetWindowLongPtrW.argtypes = [
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_ssize_t,
    ]
    lib.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    lib.SetWinEventHook.argtypes = [
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
        WinEventProc,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
    ]
    lib.SetWinEventHook.restype = wintypes.HANDLE
    lib.UnhookWinEvent.argtypes = [wintypes.HANDLE]
    lib.UnhookWinEvent.restype = wintypes.BOOL
    return lib


@functools.cache
def kernel32():
    lib = ctypes.WinDLL("kernel32", use_last_error=True)
    lib.OpenProcess.restype = wintypes.HANDLE
    lib.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    lib.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    lib.CloseHandle.argtypes = [wintypes.HANDLE]
    lib.LoadLibraryExW.restype = wintypes.HMODULE
    lib.LoadLibraryExW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.HANDLE,
        wintypes.DWORD,
    ]
    lib.GetModuleHandleW.restype = wintypes.HMODULE
    lib.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    lib.GetModuleFileNameW.argtypes = [
        wintypes.HMODULE,
        wintypes.LPWSTR,
        wintypes.DWORD,
    ]
    return lib


@functools.cache
def shell32():
    return ctypes.WinDLL("shell32", use_last_error=True)
