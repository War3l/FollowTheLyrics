import contextlib
import io
import json
import logging
import os
import socket
import struct
import sys
import threading
import time
import uuid

logger = logging.getLogger(__name__)

APP_ID = os.environ.get("FTL_DISCORD_APP_ID", "1573301626469359647")
SITE_URL = "https://war3l.github.io/FollowTheLyrics/"
GITHUB_URL = "https://github.com/War3l/FollowTheLyrics"
LOGO_URL = "https://war3l.github.io/FollowTheLyrics/img/logo.png"
NAME = "FollowTheLyrics"
LISTENING, PLAYING = 2, 0
MIN_GAP = 4.0
RETRY = 15.0
DRIFT_MS = 2500
TEXT_MAX = 128
LINUX_DIRS = (
    "",
    "app/com.discordapp.Discord",
    "app/com.discordapp.DiscordCanary",
    "snap.discord",
    ".flatpak/dev.vencord.Vesktop/xdg-run",
)


def _clip(text):
    text = " ".join(str(text or "").split())
    if len(text) < 2:
        return None
    return text[: TEXT_MAX - 1] + "…" if len(text) > TEXT_MAX else text


def position_now(np, now=None):
    now = time.monotonic() if now is None else now
    pos = float(np.position or 0.0)
    read_at = getattr(np, "read_at", None)
    if np.playing and read_at is not None:
        pos += max(0.0, now - read_at) * float(getattr(np, "speed", 1.0) or 1.0)
    return pos


def build_activity(np, show_track, wall=None, mono=None):
    wall = time.time() if wall is None else wall
    activity = {
        "type": PLAYING,
        "details": "Lyrics over games",
        "state": "Waiting for music",
        "assets": {"large_image": LOGO_URL, "large_text": NAME},
        "buttons": [
            {"label": "Website", "url": SITE_URL},
            {"label": "GitHub", "url": GITHUB_URL},
        ],
    }
    title = _clip(np.title) if np else None
    if np is not None and np.playing and show_track and title:
        activity["type"] = LISTENING
        activity["details"] = title
        artist = _clip(np.artist)
        if artist:
            activity["state"] = artist
        else:
            activity.pop("state")
        start = int((wall - position_now(np, mono)) * 1000)
        stamps = {"start": start}
        if np.duration and np.duration > 0:
            stamps["end"] = start + int(np.duration * 1000)
        activity["timestamps"] = stamps
    elif np is not None and not np.playing:
        activity["state"] = "Paused"
    return activity


def same_activity(a, b):
    if a is None or b is None:
        return a is b
    if {k: v for k, v in a.items() if k != "timestamps"} != {
        k: v for k, v in b.items() if k != "timestamps"
    }:
        return False
    ta, tb = a.get("timestamps") or {}, b.get("timestamps") or {}
    if set(ta) != set(tb):
        return False
    return all(abs(ta[k] - tb[k]) <= DRIFT_MS for k in ta)


def frame(op, payload):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return struct.pack("<II", op, len(data)) + data


def candidate_paths(env=None, platform=None):
    env = os.environ if env is None else env
    platform = sys.platform if platform is None else platform
    if platform == "win32":
        return [rf"\\?\pipe\discord-ipc-{i}" for i in range(10)]
    bases = []
    for key in ("XDG_RUNTIME_DIR", "TMPDIR", "TMP", "TEMP"):
        value = env.get(key)
        if value and value not in bases:
            bases.append(value)
    if "/tmp" not in bases:
        bases.append("/tmp")
    return [
        os.path.join(base, sub, f"discord-ipc-{i}")
        for base in bases
        for sub in LINUX_DIRS
        for i in range(10)
    ]


class PipeTransport:
    def __init__(self, path):
        self.path = path
        self.handle = None
        self.sock = None

    def open(self):
        if sys.platform == "win32":
            self.handle = io.FileIO(self.path, "r+")
        else:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect(self.path)
            self.sock = sock

    def write(self, data):
        if self.handle is not None:
            self.handle.write(data)
        elif self.sock is not None:
            self.sock.sendall(data)

    def read(self, size):
        out = b""
        while len(out) < size:
            if self.handle is not None:
                chunk = self.handle.read(size - len(out))
            elif self.sock is not None:
                chunk = self.sock.recv(size - len(out))
            else:
                chunk = b""
            if not chunk:
                raise ConnectionError("discord closed the connection")
            out += chunk
        return out

    def close(self):
        for thing in (self.handle, self.sock):
            if thing is not None:
                with contextlib.suppress(OSError):
                    thing.close()
        self.handle = self.sock = None


def default_connect(app_id):
    for path in candidate_paths():
        transport = PipeTransport(path)
        try:
            transport.open()
        except OSError:
            continue
        try:
            handshake(transport, app_id)
            return transport
        except (OSError, ValueError, ConnectionError):
            transport.close()
    return None


def read_frame(transport):
    op, size = struct.unpack("<II", transport.read(8))
    body = transport.read(size) if size else b"{}"
    return op, json.loads(body.decode("utf-8"))


def handshake(transport, app_id):
    transport.write(frame(0, {"v": 1, "client_id": app_id}))
    op, reply = read_frame(transport)
    if op != 1 or reply.get("evt") != "READY":
        raise ConnectionError(f"discord refused the handshake: {reply}")


def send_activity(transport, activity, pid=None):
    payload = {
        "cmd": "SET_ACTIVITY",
        "args": {"pid": pid or os.getpid(), "activity": activity},
        "nonce": uuid.uuid4().hex,
    }
    transport.write(frame(1, payload))
    op, reply = read_frame(transport)
    if op == 2:
        raise ConnectionError("discord closed the connection")
    if reply.get("evt") == "ERROR":
        raise ValueError(str(reply.get("data")))


class DiscordPresence:
    def __init__(
        self, app_id=APP_ID, connect=default_connect, clock=time.monotonic
    ):
        self.app_id = app_id
        self.connect = connect
        self.clock = clock
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.wanted = None
        self.enabled = False
        self.stopped = False
        self.thread = None
        self.status = "off"

    @property
    def available(self):
        return bool(self.app_id)

    def update(self, np, enabled, show_track):
        if not self.available:
            return
        activity = build_activity(np, show_track) if enabled else None
        with self.lock:
            if self.enabled == enabled and same_activity(self.wanted, activity):
                return
            self.wanted, self.enabled = activity, enabled
        if enabled and self.thread is None:
            self.thread = threading.Thread(
                target=self.run, name="discord", daemon=True
            )
            self.thread.start()
        self.wake.set()

    def stop(self):
        self.stopped = True
        self.wake.set()

    def run(self):
        transport = None
        sent = None
        last = -MIN_GAP
        retry_at = 0.0
        while not self.stopped:
            self.wake.wait(timeout=RETRY)
            self.wake.clear()
            with self.lock:
                wanted, enabled = self.wanted, self.enabled
            if not enabled:
                if transport is not None:
                    with contextlib.suppress(Exception):
                        send_activity(transport, None)
                    transport.close()
                    transport, sent = None, None
                self.status = "off"
                continue
            if transport is None:
                if self.clock() < retry_at:
                    continue
                transport = self.connect(self.app_id)
                if transport is None:
                    self.status = "discord not running"
                    retry_at = self.clock() + RETRY
                    continue
                sent = None
            if same_activity(sent, wanted):
                continue
            wait = MIN_GAP - (self.clock() - last)
            if wait > 0:
                time.sleep(wait)
                with self.lock:
                    wanted = self.wanted
            try:
                send_activity(transport, wanted)
                sent, last = wanted, self.clock()
                self.status = "connected"
            except (OSError, ValueError, ConnectionError):
                logger.debug("discord presence failed", exc_info=True)
                transport.close()
                transport, sent = None, None
                self.status = "discord not running"
                retry_at = self.clock() + RETRY
        if transport is not None:
            with contextlib.suppress(Exception):
                send_activity(transport, None)
            transport.close()
