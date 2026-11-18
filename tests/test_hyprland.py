import socket
import sys
import threading

import pytest

from followthelyrics.config import settings
from followthelyrics.desktop.linux import boot
from followthelyrics.desktop.linux import hyprland

PID = 4242
HYPRLAND_SESSION = {
    "HYPRLAND_INSTANCE_SIGNATURE": "abc",
    "WAYLAND_DISPLAY": "wayland-1",
    "DISPLAY": ":1",
}
AREA = hyprland.Area(1920, 0, 2560, 1440)
SMALL = {"id": 1, "x": 0, "y": 0, "width": 1920, "height": 1080}
LARGE = {"id": 0, "x": 1920, "y": 0, "width": 2560, "height": 1440}
MONITORS = [
    SMALL | {"activeWorkspace": {"id": 2}},
    LARGE | {"activeWorkspace": {"id": 4}},
]


def overlay_client(**state):
    return {
        "address": "0x1",
        "pid": PID,
        "title": settings.OVERLAY_TITLE,
        "floating": False,
        "pinned": False,
        "monitor": 0,
    } | state


class FakeIpc:
    def __init__(self, clients, syntax="lua"):
        self.listed = clients
        self.syntax = syntax
        self.sent = []

    def clients(self):
        return self.listed

    def monitors(self):
        return MONITORS

    def dispatch(self, command):
        self.sent.append(command)
        return command.startswith("hl.dsp.") == (self.syntax == "lua")


@pytest.mark.parametrize(
    ("requested", "plugin"),
    [(None, "wayland"), ("wayland;xcb", None), ("xcb", None)],
)
def test_hyprland_keeps_native_wayland(requested, plugin):
    environ = dict(HYPRLAND_SESSION)
    if requested is not None:
        environ["QT_QPA_PLATFORM"] = requested
    assert boot.platform_plugin(environ) == plugin


def test_find_overlay_ignores_the_panel_and_other_processes():
    panel = overlay_client(title=settings.APP_NAME)
    stranger = overlay_client(pid=PID + 1)
    overlay = overlay_client(address="0x9")
    assert hyprland.find_overlay([panel, stranger, overlay], PID) is overlay
    assert hyprland.find_overlay([panel, stranger], PID) is None


def test_commands_do_not_toggle_float_or_pin_twice():
    for builder in (hyprland.lua_commands, hyprland.classic_commands):
        fresh = builder(overlay_client(), AREA)
        settled = builder(overlay_client(floating=True, pinned=True), AREA)
        assert len(fresh) == len(settled) + 2
        assert "1920" in fresh[-1]
        assert "2560" in fresh[-2]


def test_lua_syntax_is_used_when_hyprland_accepts_it():
    ipc = FakeIpc([overlay_client()])
    windowing = hyprland.HyprlandWindowing(ipc, pid=PID)
    windowing.place_overlay(0, *vars(AREA).values())
    assert ipc.sent == hyprland.lua_commands(overlay_client(), AREA)


def test_classic_syntax_is_the_fallback():
    ipc = FakeIpc([overlay_client()], syntax="classic")
    windowing = hyprland.HyprlandWindowing(ipc, pid=PID)
    windowing.place_overlay(0, *vars(AREA).values())
    lua_probe = hyprland.lua_commands(overlay_client(), AREA)[0]
    classic = hyprland.classic_commands(overlay_client(), AREA)
    assert ipc.sent == [lua_probe, *classic]


@pytest.mark.skipif(sys.platform == "win32", reason="no AF_UNIX")
def test_ipc_speaks_the_hyprland_socket_protocol(tmp_path):
    path = str(tmp_path / hyprland.SOCKET_NAME)
    received = []
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(path)
    server.listen(1)

    def answer():
        conn, _ = server.accept()
        with conn:
            received.append(conn.recv(4096).decode())
            conn.sendall(b"ok")

    thread = threading.Thread(target=answer)
    thread.start()
    try:
        assert hyprland.HyprlandIpc(path).dispatch("pin address:0x1")
    finally:
        thread.join()
        server.close()
    assert received == ["/dispatch pin address:0x1"]


def test_overlay_born_elsewhere_joins_the_target_workspace_first():
    born_left = overlay_client(monitor=1)
    assert hyprland.workspace_to_join(born_left, MONITORS, AREA) == 4
    assert hyprland.workspace_to_join(overlay_client(), MONITORS, AREA) is None
    commands = hyprland.lua_commands(born_left, AREA, 4)
    joins = next(i for i, c in enumerate(commands) if "workspace=4" in c)
    assert joins < commands.index('hl.dsp.window.pin({window="address:0x1"})')


def test_pinned_overlay_is_unpinned_to_change_monitor():
    pinned = overlay_client(monitor=1, floating=True, pinned=True)
    for builder in (hyprland.lua_commands, hyprland.classic_commands):
        commands = builder(pinned, AREA, 4)
        pins = [i for i, c in enumerate(commands) if "pin" in c]
        joins = [i for i, c in enumerate(commands) if "workspace" in c]
        assert len(pins) == 2
        assert pins[0] < joins[0] < pins[1]


def test_monitor_lookup_uses_logical_size():
    scaled = SMALL | {"width": 3840, "height": 2160, "scale": 2.0}
    assert hyprland.monitor_at([scaled], hyprland.Area(1900, 0, 1, 1))
    assert not hyprland.monitor_at([scaled], hyprland.Area(1920, 0, 1, 1))
