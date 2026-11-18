import json
import logging
import socket
import sys
import threading
import traceback

import pytest

from followthelyrics.config import settings
from followthelyrics.desktop.linux import boot
from followthelyrics.desktop.linux import hyprland

PID = 4242
SIGNATURE = "abc"
AREA = hyprland.Area(1920, 0, 2560, 1440)
SMALL = {"id": 1, "x": 0, "y": 0, "width": 1920, "height": 1080}
LARGE = {"id": 0, "x": 1920, "y": 0, "width": 2560, "height": 1440}
MONITORS = [
    SMALL | {"activeWorkspace": {"id": 2}},
    LARGE | {"activeWorkspace": {"id": 4}},
]
OVERLAY_PROPS = [
    (("border_size", "0"), ("bordersize", "0")),
    (("rounding", "0"), ("rounding", "0")),
    (("decorate", "false"), ("decorate", "0")),
    (("no_shadow", "true"), ("noshadow", "1")),
    (("no_anim", "true"), ("noanim", "1")),
    (("no_focus", "true"), ("nofocus", "1")),
]
linux_only = pytest.mark.skipif(
    sys.platform == "win32", reason="Hyprland paths and AF_UNIX"
)


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
    def __init__(self, clients, syntax="lua", refused=()):
        self.listed = clients
        self.syntax = syntax
        self.refused = refused
        self.sent = []

    def clients(self):
        if isinstance(self.listed, type):
            raise self.listed("busy")
        return self.listed

    def monitors(self):
        return MONITORS

    def dispatch(self, command):
        self.sent.append(command)
        if command in self.refused:
            return False
        return command.startswith("hl.dsp.") == (self.syntax == "lua")


class Timers:
    def __init__(self):
        self.pending = []

    def single_shot(self, delay, callback):
        self.pending.append(callback)

    def fire_next(self):
        self.pending.pop(0)()


@pytest.fixture
def timers(monkeypatch):
    recorder = Timers()
    monkeypatch.setattr(hyprland.QTimer, "singleShot", recorder.single_shot)
    return recorder


@pytest.fixture
def hyprland_session(tmp_path):
    environ = {
        "HYPRLAND_INSTANCE_SIGNATURE": SIGNATURE,
        "WAYLAND_DISPLAY": "wayland-1",
        "DISPLAY": ":1",
        "XDG_RUNTIME_DIR": str(tmp_path),
    }
    path = hyprland.socket_path(environ)
    (tmp_path / "hypr" / SIGNATURE).mkdir(parents=True)
    open(path, "w").close()
    return environ


def serve(path, replies):
    received = []
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(path)
    server.listen(len(replies))
    server.settimeout(5)

    def answer():
        for reply in replies:
            conn, _ = server.accept()
            with conn:
                received.append(conn.recv(4096).decode())
                conn.sendall(reply(received[-1]).encode())
        server.close()

    thread = threading.Thread(target=answer)
    thread.start()
    return thread, received


@pytest.mark.parametrize(
    ("requested", "plugin"),
    [(None, "wayland"), ("wayland;xcb", None), ("xcb", None)],
)
def test_hyprland_keeps_native_wayland(hyprland_session, requested, plugin):
    if requested is not None:
        hyprland_session["QT_QPA_PLATFORM"] = requested
    assert boot.platform_plugin(hyprland_session) == plugin


def test_stale_hyprland_signature_falls_back_to_xwayland(hyprland_session):
    stale = hyprland_session | {"HYPRLAND_INSTANCE_SIGNATURE": "gone"}
    assert not hyprland.running(stale)
    assert boot.platform_plugin(stale | {"QT_QPA_PLATFORM": "wayland;xcb"})
    assert hyprland.running(hyprland_session)


@linux_only
def test_socket_path_follows_the_hyprland_layout():
    environ = {
        "XDG_RUNTIME_DIR": "/run/user/1000",
        "HYPRLAND_INSTANCE_SIGNATURE": "s",
    }
    assert hyprland.socket_path(environ) == "/run/user/1000/hypr/s/.socket.sock"


def test_linux_backend_picks_hyprland_windowing(monkeypatch, hyprland_session):
    backend = pytest.importorskip("followthelyrics.desktop.linux.backend")
    for name, value in hyprland_session.items():
        monkeypatch.setenv(name, value)
    assert isinstance(backend._windowing(), hyprland.HyprlandWindowing)
    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE")
    assert not isinstance(backend._windowing(), hyprland.HyprlandWindowing)


def test_find_overlay_ignores_the_panel_and_other_processes():
    panel = overlay_client(title=settings.APP_NAME)
    stranger = overlay_client(pid=PID + 1)
    overlay = overlay_client(address="0x9")
    assert hyprland.find_overlay([panel, stranger, overlay], PID) is overlay
    assert hyprland.find_overlay([panel, stranger], PID) is None


@pytest.mark.parametrize(("lua", "classic"), OVERLAY_PROPS)
def test_both_syntaxes_set_the_properties_hyprland_accepts(lua, classic):
    index = [p for p, _ in hyprland.LUA_OVERLAY_PROPS].index(lua[0])
    assert hyprland.LUA_OVERLAY_PROPS[index] == lua
    assert hyprland.CLASSIC_OVERLAY_PROPS[index] == classic


def test_no_other_property_is_set():
    assert len(hyprland.LUA_OVERLAY_PROPS) == len(OVERLAY_PROPS)
    assert len(hyprland.CLASSIC_OVERLAY_PROPS) == len(OVERLAY_PROPS)


def test_commands_do_not_toggle_float_or_pin_twice():
    for builder in (hyprland.lua_commands, hyprland.classic_commands):
        fresh = builder(overlay_client(), AREA)
        settled = builder(overlay_client(floating=True, pinned=True), AREA)
        assert len(fresh) == len(settled) + 2
        assert "1920" in fresh[-1]
        assert "2560" in fresh[-2]


def test_lua_syntax_is_used_when_hyprland_accepts_it(timers):
    ipc = FakeIpc([overlay_client()])
    windowing = hyprland.HyprlandWindowing(ipc, pid=PID)
    windowing.place_overlay(0, *vars(AREA).values())
    assert ipc.sent == hyprland.lua_commands(overlay_client(), AREA)
    assert not timers.pending


def test_classic_syntax_is_the_fallback(timers):
    ipc = FakeIpc([overlay_client()], syntax="classic")
    windowing = hyprland.HyprlandWindowing(ipc, pid=PID)
    windowing.place_overlay(0, *vars(AREA).values())
    lua_probe = hyprland.lua_commands(overlay_client(), AREA)[0]
    classic = hyprland.classic_commands(overlay_client(), AREA)
    assert ipc.sent == [lua_probe, *classic]


def test_refused_commands_are_logged_and_the_rest_still_sent(timers, caplog):
    commands = hyprland.lua_commands(overlay_client(), AREA)
    ipc = FakeIpc([overlay_client()], refused={commands[-2]})
    windowing = hyprland.HyprlandWindowing(ipc, pid=PID)
    with caplog.at_level(logging.WARNING):
        windowing.place_overlay(0, *vars(AREA).values())
    assert ipc.sent == commands
    assert commands[-2] in caplog.text


def test_overlay_not_listed_yet_is_placed_on_a_retry(timers):
    ipc = FakeIpc([])
    windowing = hyprland.HyprlandWindowing(ipc, pid=PID)
    windowing.place_overlay(0, *vars(AREA).values())
    assert ipc.sent == []
    ipc.listed = [overlay_client()]
    timers.fire_next()
    assert ipc.sent == hyprland.lua_commands(overlay_client(), AREA)


def test_transient_ipc_error_is_retried(timers):
    ipc = FakeIpc(ConnectionRefusedError)
    windowing = hyprland.HyprlandWindowing(ipc, pid=PID)
    windowing.place_overlay(0, *vars(AREA).values())
    ipc.listed = [overlay_client()]
    timers.fire_next()
    assert ipc.sent == hyprland.lua_commands(overlay_client(), AREA)


def test_persistent_ipc_error_is_reported_with_its_trace(timers, caplog):
    windowing = hyprland.HyprlandWindowing(
        FakeIpc(ConnectionRefusedError), pid=PID
    )
    with caplog.at_level(logging.WARNING):
        windowing.place_overlay(0, *vars(AREA).values())
        for _ in hyprland.RETRY_DELAYS_MS:
            timers.fire_next()
    assert "Hyprland IPC unavailable" in caplog.text
    error = caplog.records[-1].exc_info[1]
    assert isinstance(error, ConnectionRefusedError)
    frames = traceback.extract_tb(error.__traceback__)
    assert [frame.name for frame in frames] == ["_attempt", "clients"]


def test_malformed_monitor_list_is_retried_not_raised(timers, caplog):
    ipc = FakeIpc([overlay_client(monitor=1)])
    ipc.monitors = lambda: [LARGE]
    windowing = hyprland.HyprlandWindowing(ipc, pid=PID)
    with caplog.at_level(logging.WARNING):
        windowing.place_overlay(0, *vars(AREA).values())
        for _ in hyprland.RETRY_DELAYS_MS:
            timers.fire_next()
    assert ipc.sent == []
    assert "Unexpected reply from Hyprland" in caplog.text
    assert isinstance(caplog.records[-1].exc_info[1], KeyError)


def test_retries_stop_after_the_last_delay(timers, caplog):
    windowing = hyprland.HyprlandWindowing(FakeIpc([]), pid=PID)
    with caplog.at_level(logging.WARNING):
        windowing.place_overlay(0, *vars(AREA).values())
        for _ in hyprland.RETRY_DELAYS_MS:
            timers.fire_next()
    assert not timers.pending
    assert "never listed" in caplog.text


def test_a_newer_placement_cancels_the_pending_retry(timers):
    ipc = FakeIpc([])
    windowing = hyprland.HyprlandWindowing(ipc, pid=PID)
    windowing.place_overlay(0, 0, 0, 1920, 1080)
    windowing.place_overlay(0, *vars(AREA).values())
    ipc.listed = [overlay_client()]
    timers.fire_next()
    assert ipc.sent == []
    timers.fire_next()
    assert ipc.sent == hyprland.lua_commands(overlay_client(), AREA)


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


def test_monitor_lookup_swaps_sides_of_a_rotated_screen():
    portrait = SMALL | {"transform": 1}
    assert hyprland.monitor_at([portrait], hyprland.Area(0, 1900, 1, 1))
    assert not hyprland.monitor_at([portrait], hyprland.Area(1900, 0, 1, 1))


@linux_only
def test_ipc_reads_the_dispatch_verdict(tmp_path):
    path = str(tmp_path / hyprland.SOCKET_NAME)
    thread, received = serve(path, [lambda _: "ok", lambda _: "Invalid"])
    try:
        ipc = hyprland.HyprlandIpc(path)
        assert ipc.dispatch("pin address:0x1")
        assert not ipc.dispatch("pin address:0x1")
    finally:
        thread.join()
    assert received == ["/dispatch pin address:0x1"] * 2


@linux_only
def test_placement_over_a_real_socket_falls_back_to_classic(tmp_path, timers):
    path = str(tmp_path / hyprland.SOCKET_NAME)
    client = overlay_client(monitor=1)
    lua = hyprland.lua_commands(client, AREA, 4)
    classic = hyprland.classic_commands(client, AREA, 4)

    def reply(request):
        if request == "j/clients":
            return json.dumps([client])
        if request == "j/monitors":
            return json.dumps(MONITORS)
        return "Invalid dispatcher" if "hl.dsp." in request else "ok"

    thread, received = serve(path, [reply] * (3 + len(classic)))
    try:
        windowing = hyprland.HyprlandWindowing(
            hyprland.HyprlandIpc(path), pid=PID
        )
        windowing.place_overlay(0, *vars(AREA).values())
    finally:
        thread.join()
    assert received == [
        "j/clients",
        "j/monitors",
        "/dispatch " + lua[0],
        *("/dispatch " + c for c in classic),
    ]
