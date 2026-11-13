from collections.abc import Callable
from collections.abc import Collection
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

import numpy as np
import numpy.typing as npt

from followthelyrics.playback import track

WindowHandle = int
Samples = npt.NDArray[np.float32]


class TrackFilter(Protocol):
    def allows(
        self, app_id: str, title: str, artist: str
    ) -> tuple[bool, str]: ...


class MediaSession(Protocol):
    def now_playing(
        self, blocked: Collection[str], guard: TrackFilter | None
    ) -> track.NowPlaying | None: ...

    def sources(self) -> list[str]: ...

    def cover(
        self, blocked: Collection[str], guard: TrackFilter | None
    ) -> bytes | None: ...

    def close(self) -> None: ...


class MediaBackend(Protocol):
    def open(self) -> MediaSession: ...


@dataclass(frozen=True)
class AudioDevice:
    index: int
    name: str
    channels: int
    rate: int


class AudioCapture(Protocol):
    @property
    def rate(self) -> int: ...

    def read(self) -> Samples: ...

    def close(self) -> None: ...


class LoopbackAudio(Protocol):
    def devices(self) -> list[AudioDevice]: ...

    def preferred(self, devices: list[AudioDevice]) -> AudioDevice: ...

    def capture(self, device: AudioDevice) -> AudioCapture: ...

    def close(self) -> None: ...


class AudioBackend(Protocol):
    def open(self) -> LoopbackAudio: ...


class Keyboard(Protocol):
    def virtual_key(self, native_key: int, qt_key: int) -> int: ...

    def key_char(self, virtual_key: int) -> str | None: ...


Binding = tuple[int, int]
MOD_ALT = 0x0001
MOD_CTRL = 0x0002
MOD_SHIFT = 0x0004


class HotkeyBackend(Protocol):
    def start(
        self,
        on_pressed: Callable[[str], None],
        on_failed: Callable[[list[str]], None],
    ) -> None: ...

    def bind(self, bindings: Mapping[str, Binding]) -> None: ...

    def stop(self) -> None: ...


class Subscription(Protocol):
    def close(self) -> None: ...


@dataclass(frozen=True)
class TitleBarColors:
    caption: str
    border: str
    text: str


class Windowing(Protocol):
    def prepare_overlay(self, window: WindowHandle) -> None: ...

    def raise_overlay(self, window: WindowHandle) -> None: ...

    def on_foreground_change(
        self, callback: Callable[[], None]
    ) -> Subscription: ...

    def supports_backdrop(self) -> bool: ...

    def enable_backdrop(self, window: WindowHandle) -> bool: ...

    def dark_title_bar(self, window: WindowHandle) -> None: ...

    def round_corners(self, window: WindowHandle) -> None: ...

    def color_title_bar(
        self, window: WindowHandle, colors: TitleBarColors
    ) -> None: ...


@dataclass(frozen=True)
class ForegroundApp:
    exe: str = ""
    fullscreen: bool = False


class Foreground(Protocol):
    def current(self) -> ForegroundApp: ...

    def exclusive_fullscreen(self) -> bool: ...

    def window_titles(self, exes: Collection[str]) -> list[str]: ...


class Autostart(Protocol):
    def command(self) -> str: ...

    def enable(self, command: str) -> bool: ...

    def disable(self) -> bool: ...

    def drop_legacy(self, names: Collection[str]) -> bool: ...


class Shortcuts(Protocol):
    def desktop_path(self) -> str: ...

    def legacy_desktop_path(self) -> str: ...

    def create(self, target: str, link: str) -> bool: ...

    def target(self, link: str) -> str: ...


class Dialogs(Protocol):
    def ask(self, text: str) -> bool: ...

    def inform(self, text: str) -> None: ...

    def warn(self, text: str) -> None: ...


class InstanceLock(Protocol):
    def acquire(self) -> bool: ...


class Session(Protocol):
    def set_app_id(self, app_id: str) -> None: ...

    def spawn_detached(
        self, argv: list[str], cwd: str, env: Mapping[str, str]
    ) -> None: ...

    def instance_lock(self, name: str) -> InstanceLock: ...


@dataclass(frozen=True)
class AppEntry:
    exe: str
    folder: str
    version: str
    size_kb: int


class Installer(Protocol):
    def default_folder(self) -> str: ...

    def menu_shortcut(self) -> str: ...

    def registered_version(self) -> str: ...

    def register(self, entry: AppEntry) -> None: ...

    def unregister(self) -> None: ...

    def remove_after_exit(self, folders: list[str]) -> None: ...


@dataclass(frozen=True)
class ReleaseFormat:
    asset: str
    magic: bytes
    min_size: int


class Boot(Protocol):
    def prepare(self) -> None: ...

    def report(self, error: BaseException) -> None: ...


@dataclass(frozen=True)
class Desktop:
    name: str
    keyboard: Keyboard
    windowing: Windowing
    foreground: Foreground
    dialogs: Dialogs
    session: Session
    media: MediaBackend | None = None
    audio: AudioBackend | None = None
    hotkeys: HotkeyBackend | None = None
    autostart: Autostart | None = None
    shortcuts: Shortcuts | None = None
    installer: Installer | None = None
    release: ReleaseFormat | None = None
    checks: Callable[[], list[str]] = list
