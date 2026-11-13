import functools
import importlib
import sys
from typing import cast

from followthelyrics.desktop import ports

SYSTEM_NAMES = {"linux": "Linux", "darwin": "macOS"}


def _package():
    return "windows" if sys.platform == "win32" else "generic"


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
    if sys.platform == "win32":
        return backend.create()
    return backend.create(SYSTEM_NAMES.get(sys.platform, sys.platform))
