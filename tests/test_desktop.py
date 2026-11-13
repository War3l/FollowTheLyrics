import sys

import pytest
from PyQt6.QtCore import Qt

from followthelyrics import desktop
from followthelyrics.config import games
from followthelyrics.desktop import ports
from followthelyrics.desktop.generic import keyboard
from followthelyrics.system import hotkeys
from followthelyrics.system import startup

PROFILES = {
    "jeux": {
        "League of Legends.exe": {"nom": "LoL", "autres_exe": ["lol.exe"]}
    },
    "jeu_inconnu": {"nom": "Jeu"},
    "bureau": {"nom": "Bureau"},
}


@pytest.mark.skipif(sys.platform == "win32", reason="backend generique")
def test_generic_desktop_degrades_without_native_services():
    system = desktop.current()

    assert system.name == desktop.SYSTEM_NAMES.get(sys.platform, sys.platform)
    assert system.media is None
    assert system.hotkeys is None
    assert system.installer is None
    assert system.release is None
    assert system.foreground.current() == ports.ForegroundApp()


@pytest.mark.parametrize(
    ("qt_key", "virtual_key"),
    [
        (Qt.Key.Key_L, ord("L")),
        (Qt.Key.Key_7, ord("7")),
        (Qt.Key.Key_F1, 0x70),
        (Qt.Key.Key_F24, 0x87),
        (Qt.Key.Key_Escape, 0x1B),
        (Qt.Key.Key_Delete, 0x2E),
        (Qt.Key.Key_Up, 0x26),
        (Qt.Key.Key_Control, 0x11),
        (Qt.Key.Key_Eacute, 0),
    ],
)
def test_qt_keyboard_maps_to_virtual_keys(qt_key, virtual_key):
    assert keyboard.QtKeyboard().virtual_key(0, qt_key.value) == virtual_key


@pytest.mark.parametrize(
    ("foreground", "key"),
    [
        (
            ports.ForegroundApp("LOL.EXE", fullscreen=True),
            "League of Legends.exe",
        ),
        (ports.ForegroundApp("game.exe", fullscreen=True), "jeu_inconnu"),
        (ports.ForegroundApp("notepad.exe"), "bureau"),
        (ports.ForegroundApp(), "bureau"),
    ],
)
def test_current_profile_follows_the_foreground_app(foreground, key):
    assert games.current_profile(PROFILES, foreground)[0] == key


class FakeHotkeyBackend:
    def __init__(self):
        self.bound = []
        self.on_pressed = None
        self.on_failed = None

    def start(self, on_pressed, on_failed):
        self.on_pressed, self.on_failed = on_pressed, on_failed

    def bind(self, bindings):
        self.bound.append(dict(bindings))

    def stop(self):
        self.on_pressed = None


def test_hotkeys_bind_the_parsed_combos_and_release_them_while_paused():
    backend = FakeHotkeyBackend()
    manager = hotkeys.Hotkeys(
        backend, keyboard.QtKeyboard(), {"toggle": "Ctrl+Alt+L"}
    )

    manager.start()
    manager.pause()
    manager.resume()

    assert backend.bound == [
        {"toggle": hotkeys.parse("Ctrl+Alt+L")},
        {},
        {"toggle": hotkeys.parse("Ctrl+Alt+L")},
    ]


def test_hotkeys_forward_presses_and_ignore_failures_while_paused():
    backend = FakeHotkeyBackend()
    manager = hotkeys.Hotkeys(backend, keyboard.QtKeyboard(), {})
    pressed, failed = [], []
    manager.pressed.connect(pressed.append)
    manager.failed.connect(failed.append)
    manager.start()

    backend.on_pressed("toggle")
    backend.on_failed(["mode"])
    manager.pause()
    backend.on_failed(["color"])

    assert pressed == ["toggle"]
    assert failed == [["mode"]]


def test_hotkeys_without_backend_stay_inert():
    manager = hotkeys.Hotkeys(None, keyboard.QtKeyboard(), hotkeys.DEFAULTS)

    manager.start()
    manager.pause()
    manager.stop()

    assert not manager.available
    assert manager.pretty("Ctrl+Alt+L") == hotkeys.pretty("Ctrl+Alt+L")


class FakeAutostart:
    def __init__(self, command=""):
        self.saved = command
        self.legacy = False

    def command(self):
        return self.saved

    def enable(self, command):
        self.saved = command
        return True

    def disable(self):
        self.saved = ""
        return True

    def drop_legacy(self, names):
        return self.legacy


def test_startup_enables_a_minimized_launch():
    autostart = FakeAutostart()
    service = startup.Startup(autostart, None)

    service.set(True, exe="/opt/ftl/FollowTheLyrics")

    assert service.enabled()
    assert autostart.saved == '"/opt/ftl/FollowTheLyrics" --minimized'


def test_startup_refresh_migrates_a_legacy_entry():
    autostart = FakeAutostart()
    autostart.legacy = True

    startup.Startup(autostart, None).refresh()

    assert autostart.saved.endswith("--minimized")


def test_startup_without_backends_reports_nothing_supported():
    service = startup.Startup(None, None)

    assert not service.supports_autostart
    assert not service.supports_shortcuts
    assert not service.set(True)
    assert not service.create_desktop_shortcut(exe="x")
    assert service.desktop_link() == ""


def test_child_environment_drops_frozen_and_requested_keys(monkeypatch):
    monkeypatch.setenv("_MEIPASS2", "x")
    monkeypatch.setenv("FTL_FAKE_VERSION", "9.9.9")

    env = startup.child_environment(drop=("FTL_FAKE_VERSION",))

    assert "_MEIPASS2" not in env
    assert "FTL_FAKE_VERSION" not in env
    assert env["PYINSTALLER_RESET_ENVIRONMENT"] == "1"
