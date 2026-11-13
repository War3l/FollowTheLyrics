import os
import struct
import subprocess
import sys
import time

from PyQt6.QtCore import QBuffer
from PyQt6.QtCore import QByteArray
from PyQt6.QtCore import QIODevice
from PyQt6.QtNetwork import QLocalSocket
from PyQt6.QtWidgets import QApplication

from followthelyrics.ui import widgets

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.join(HERE, "src", "followthelyrics")
NAME = "FollowTheLyrics"
WINDOWS = sys.platform == "win32"
EXE = NAME + ".exe" if WINDOWS else NAME


def _version():
    try:
        with open(os.path.join(PACKAGE, "VERSION"), encoding="utf-8") as f:
            return f.read().strip() or "1.0.0"
    except OSError:
        return "1.0.0"


VERSION = _version()


def make_ico(path):
    app = QApplication.instance() or QApplication([])
    blobs = []
    for size in (16, 24, 32, 48, 64, 128, 256):
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        widgets.icon_pixmap(size).save(buf, "PNG")
        buf.close()
        blobs.append((size, bytes(ba)))
    out = struct.pack("<HHH", 0, 1, len(blobs))
    offset = 6 + 16 * len(blobs)
    for size, data in blobs:
        out += struct.pack(
            "<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset
        )
        offset += len(data)
    for _, data in blobs:
        out += data
    with open(path, "wb") as f:
        f.write(out)
    del app


def version_file(path):
    v = ((*tuple(int(x) for x in VERSION.split(".")), 0, 0, 0, 0))[:4]
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={v}, prodvers={v}, mask=0x3f, flags=0x0,
                    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040C04B0', [
      StringStruct('FileDescription', '{NAME}'),
      StringStruct('ProductName', '{NAME}'),
      StringStruct('FileVersion', '{VERSION}'),
      StringStruct('ProductVersion', '{VERSION}'),
      StringStruct('InternalName', 'FollowTheLyrics'),
      StringStruct('OriginalFilename', '{NAME}.exe')])]),
    VarFileInfo([VarStruct('Translation', [0x040C, 1200])])
  ]
)
""")


def close_running(exe):
    def locked():
        if not os.path.exists(exe):
            return False
        try:
            with open(exe, "ab"):
                return False
        except OSError:
            return True

    if not locked():
        return False
    print(
        "L'appli est ouverte : fermeture le temps de la construction...",
        flush=True,
    )
    sock = QLocalSocket()
    sock.connectToServer("LyricsOverlay-instance")
    if sock.waitForConnected(800):
        sock.write(b"quit")
        sock.flush()
        sock.waitForBytesWritten(500)
    sock.close()
    for _ in range(40):
        if not locked():
            break
        time.sleep(0.25)
    return True


RUNTIME_DLLS = (
    "msvcp140.dll",
    "msvcp140_1.dll",
    "msvcp140_2.dll",
    "msvcp140_atomic_wait.dll",
    "concrt140.dll",
    "vcruntime140.dll",
    "vcruntime140_1.dll",
)
EXCLUDED_MODULES = (
    "tkinter",
    "unittest",
    "pydoc",
    "doctest",
    "pdb",
    "lib2to3",
    "test",
    "setuptools",
    "pip",
    "PyQt6.QtQml",
    "PyQt6.QtQuick",
    "PyQt6.QtPdf",
    "PyQt6.QtSvg",
    "PyQt6.QtBluetooth",
    "PyQt6.QtMultimedia",
    "PyQt6.QtSql",
    "PyQt6.QtTest",
    "PyQt6.QtOpenGL",
    "PyQt6.QtDesigner",
    "PyQt6.QtHelp",
    "PyQt6.QtPrintSupport",
    "PyQt6.QtXml",
    "numpy.f2py",
    "numpy.testing",
    "numpy.tests",
)


def windows_options(work):
    ico = os.path.join(work, "icon.ico")
    ver = os.path.join(work, "version.txt")
    make_ico(ico)
    version_file(ver)
    options = [
        "--windowed",
        "--icon",
        ico,
        "--version-file",
        ver,
        "--hidden-import",
        "pyaudiowpatch",
        "--collect-submodules",
        "winrt",
        "--exclude-module",
        "PyQt6.QtDBus",
    ]
    sysdir = os.path.join(
        os.environ.get("SYSTEMROOT", r"C:\Windows"), "System32"
    )
    for dll in RUNTIME_DLLS:
        src = os.path.join(sysdir, dll)
        if os.path.exists(src):
            options += ["--add-binary", f"{src}{os.pathsep}."]
    return options


def linux_options():
    return [
        "--hidden-import",
        "soundcard",
        "--collect-data",
        "soundcard",
        "--collect-submodules",
        "Xlib",
    ]


def main():
    exe = os.path.join(HERE, "dist", EXE)
    was_running = close_running(exe)
    work = os.path.join(HERE, "build")
    os.makedirs(work, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--name",
        NAME,
        "--distpath",
        os.path.join(HERE, "dist"),
        "--workpath",
        work,
        "--specpath",
        work,
        "--paths",
        os.path.join(HERE, "src"),
        "--collect-submodules",
        "followthelyrics",
        "--add-data",
        f"{os.path.join(PACKAGE, 'VERSION')}{os.pathsep}followthelyrics",
    ]
    cmd += windows_options(work) if WINDOWS else linux_options()
    for mod in EXCLUDED_MODULES:
        cmd += ["--exclude-module", mod]
    cmd.append(os.path.join(HERE, "tools", "pyinstaller_entry.py"))
    print("Construction en cours (2 a 4 minutes)...", flush=True)
    code = subprocess.call(cmd, cwd=HERE)
    if code == 0 and os.path.exists(exe):
        size = os.path.getsize(exe) / 1e6
        print(f"\nOK : {os.path.relpath(exe, HERE)} ({size:.0f} Mo)")
        if was_running:
            print("Relance de l'appli.")
            subprocess.Popen(
                [exe],
                cwd=os.path.dirname(exe),
                env=dict(os.environ, FTL_PORTABLE="1"),
            )
        return 0
    print("\nEchec de la construction.")
    return code or 1


if __name__ == "__main__":
    sys.exit(main())
