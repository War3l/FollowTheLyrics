import os

from followthelyrics.desktop.generic import boot as generic_boot
from followthelyrics.desktop.linux import hyprland

report = generic_boot.report


def platform_plugin(environ):
    requested = [
        name.strip()
        for name in environ.get("QT_QPA_PLATFORM", "").split(";")
        if name.strip()
    ]
    if not environ.get("WAYLAND_DISPLAY"):
        return None
    if hyprland.running(environ):
        return None if requested else "wayland"
    if len(requested) == 1 or (requested and "xcb" not in requested):
        return None
    if environ.get("DISPLAY"):
        return "xcb"
    return None


def prepare():
    plugin = platform_plugin(os.environ)
    if plugin:
        os.environ["QT_QPA_PLATFORM"] = plugin
