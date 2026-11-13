import os

from followthelyrics.desktop.generic import boot as generic_boot

report = generic_boot.report


def platform_plugin(environ):
    if environ.get("QT_QPA_PLATFORM"):
        return None
    if environ.get("WAYLAND_DISPLAY") and environ.get("DISPLAY"):
        return "xcb"
    return None


def prepare():
    plugin = platform_plugin(os.environ)
    if plugin:
        os.environ["QT_QPA_PLATFORM"] = plugin
