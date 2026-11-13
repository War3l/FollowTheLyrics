import functools
import importlib
import sys
from typing import cast

from followthelyrics.desktop import ports

SYSTEM_NAMES = {"linux": "Linux", "darwin": "macOS"}


def _package():
    if sys.platform == "win32":
        return "windows"
    if sys.platform.startswith("linux"):
        return "linux"
    return "generic"


def boot() -> ports.Boot:
    module = importlib.import_module(
        f"followthelyrics.desktop.{_package()}.boot"
    )
    return cast(ports.Boot, module)


@functools.cache
def current() -> ports.Desktop:
    backend = importlib.import_module(
        f"followthelyrics.desktop.{_package()}.backend"
    )
    if _package() != "generic":
        return backend.create()
    return backend.create(SYSTEM_NAMES.get(sys.platform, sys.platform))
