import json
import logging
import os
import socket
import sys
from dataclasses import dataclass

from PyQt6.QtCore import QTimer

from followthelyrics.config import settings
from followthelyrics.desktop.generic import backend as generic

logger = logging.getLogger(__name__)

SOCKET_NAME = ".socket.sock"
REQUEST_TIMEOUT_S = 0.5
RETRY_DELAYS_MS = (100, 300, 1000, 3000)
OK_REPLY = "ok"

LUA_OVERLAY_PROPS = (
    ("border_size", "0"),
    ("rounding", "0"),
    ("decorate", "false"),
    ("no_shadow", "true"),
    ("no_anim", "true"),
    ("no_focus", "true"),
)
CLASSIC_OVERLAY_PROPS = (
    ("bordersize", "0"),
    ("rounding", "0"),
    ("decorate", "0"),
    ("noshadow", "1"),
    ("noanim", "1"),
    ("nofocus", "1"),
)


@dataclass(frozen=True)
class Area:
    x: int
    y: int
    width: int
    height: int


def running(environ=os.environ):
    return bool(
        environ.get("HYPRLAND_INSTANCE_SIGNATURE")
        and environ.get("WAYLAND_DISPLAY")
        and os.path.exists(socket_path(environ))
    )


def socket_path(environ=os.environ):
    return os.path.join(
        environ.get("XDG_RUNTIME_DIR", ""),
        "hypr",
        environ.get("HYPRLAND_INSTANCE_SIGNATURE", ""),
        SOCKET_NAME,
    )


def find_overlay(clients, pid):
    for client in clients:
        if (
            client.get("pid") == pid
            and client.get("title") == settings.OVERLAY_TITLE
        ):
            return client
    return None


def logical_size(monitor):
    width = monitor["width"] / monitor.get("scale", 1)
    height = monitor["height"] / monitor.get("scale", 1)
    if monitor.get("transform", 0) % 2:
        return height, width
    return width, height


def monitor_at(monitors, area):
    for monitor in monitors:
        width, height = logical_size(monitor)
        if (
            monitor["x"] <= area.x < monitor["x"] + width
            and monitor["y"] <= area.y < monitor["y"] + height
        ):
            return monitor
    return None


def workspace_to_join(client, monitors, area):
    monitor = monitor_at(monitors, area)
    if monitor is None or client.get("monitor") == monitor["id"]:
        return None
    return monitor["activeWorkspace"]["id"]


def lua_commands(client, area, workspace=None):
    target = f'window="address:{client["address"]}"'
    pin = f"hl.dsp.window.pin({{{target}}})"
    commands = [
        f'hl.dsp.window.set_prop({{{target}, prop="{prop}", value="{value}"}})'
        for prop, value in LUA_OVERLAY_PROPS
    ]
    if not client.get("floating"):
        commands.append(f"hl.dsp.window.float({{{target}}})")
    pinned = client.get("pinned")
    if workspace is not None:
        if pinned:
            commands.append(pin)
            pinned = False
        commands.append(
            f"hl.dsp.window.move({{workspace={workspace},"
            f" follow=false, {target}}})"
        )
    if not pinned:
        commands.append(pin)
    commands += [
        f"hl.dsp.window.resize({{x={area.width}, y={area.height},"
        f" exact=true, {target}}})",
        f"hl.dsp.window.move({{x={area.x}, y={area.y}, exact=true, {target}}})",
    ]
    return commands


def classic_commands(client, area, workspace=None):
    target = f"address:{client['address']}"
    pin = f"pin {target}"
    commands = [
        f"setprop {target} {prop} {value}"
        for prop, value in CLASSIC_OVERLAY_PROPS
    ]
    if not client.get("floating"):
        commands.append(f"setfloating {target}")
    pinned = client.get("pinned")
    if workspace is not None:
        if pinned:
            commands.append(pin)
            pinned = False
        commands.append(f"movetoworkspacesilent {workspace},{target}")
    if not pinned:
        commands.append(pin)
    commands += [
        f"resizewindowpixel exact {area.width} {area.height},{target}",
        f"movewindowpixel exact {area.x} {area.y},{target}",
    ]
    return commands


class HyprlandIpc:
    def __init__(self, path):
        self.path = path

    def request(self, command):
        if sys.platform == "win32":
            raise OSError("Hyprland only runs on Linux")
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            conn.settimeout(REQUEST_TIMEOUT_S)
            conn.connect(self.path)
            conn.sendall(command.encode())
            chunks = []
            while chunk := conn.recv(65536):
                chunks.append(chunk)
        return b"".join(chunks).decode(errors="replace").strip()

    def clients(self):
        return json.loads(self.request("j/clients"))

    def monitors(self):
        return json.loads(self.request("j/monitors"))

    def dispatch(self, command):
        return self.request("/dispatch " + command) == OK_REPLY


class HyprlandWindowing(generic.QtWindowing):
    def __init__(self, ipc, pid=None):
        self.ipc = ipc
        self.pid = os.getpid() if pid is None else pid
        self.area = None
        self.pending = 0

    def place_overlay(self, window, x, y, width, height):
        self.area = Area(x, y, width, height)
        self.pending += 1
        self._attempt(self.pending, 0)

    def _attempt(self, generation, retry):
        if generation != self.pending:
            return
        try:
            client = find_overlay(self.ipc.clients(), self.pid)
            if client is not None:
                self._apply(client)
                return
            failure = "Hyprland never listed the overlay window"
        except (OSError, ValueError) as error:
            failure = f"Hyprland IPC unavailable: {error}"
        if retry < len(RETRY_DELAYS_MS):
            QTimer.singleShot(
                RETRY_DELAYS_MS[retry],
                lambda: self._attempt(generation, retry + 1),
            )
        else:
            logger.warning(failure)

    def _apply(self, client):
        workspace = workspace_to_join(client, self.ipc.monitors(), self.area)
        lua = lua_commands(client, self.area, workspace)
        if self.ipc.dispatch(lua[0]):
            remaining = lua[1:]
        else:
            remaining = classic_commands(client, self.area, workspace)
        refused = [c for c in remaining if not self.ipc.dispatch(c)]
        if refused:
            logger.warning("Hyprland refused %s", refused)
