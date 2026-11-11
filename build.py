"""Fabrique « dist/FollowTheLyrics.exe » : un seul fichier, sans Python a installer.

Lancer avec Construire.bat (ou : .venv\\Scripts\\python build.py).
"""
import os
import shutil
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = "FollowTheLyrics"
def _version():
    try:
        with open(os.path.join(HERE, "VERSION"), encoding="utf-8") as f:
            return f.read().strip() or "1.0.0"
    except Exception:
        return "1.0.0"


VERSION = _version()  # numero dans le fichier VERSION (mis a jour par Publier.bat)


def make_ico(path):
    """Dessine le logo a toutes les tailles et l'ecrit en .ico (images PNG dedans)."""
    from PyQt6.QtCore import QBuffer, QByteArray, QIODevice
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from panel import icon_pixmap

    blobs = []
    for size in (16, 24, 32, 48, 64, 128, 256):
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        icon_pixmap(size).save(buf, "PNG")
        buf.close()
        blobs.append((size, bytes(ba)))
    out = struct.pack("<HHH", 0, 1, len(blobs))
    offset = 6 + 16 * len(blobs)
    for size, data in blobs:
        out += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    for _, data in blobs:
        out += data
    with open(path, "wb") as f:
        f.write(out)
    del app


def version_file(path):
    v = (tuple(int(x) for x in VERSION.split(".")) + (0, 0, 0, 0))[:4]
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={v}, prodvers={v}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1,
                    subtype=0x0, date=(0, 0)),
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
    """Windows interdit de remplacer un .exe en cours d'execution : on demande a
    l'appli ouverte de quitter (comme le fait un relancement). Renvoie True si elle tournait."""
    import time
    from PyQt6.QtNetwork import QLocalSocket

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
    print("L'appli est ouverte : fermeture le temps de la construction...", flush=True)
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


def main():
    was_running = close_running(os.path.join(HERE, "dist", NAME + ".exe"))
    work = os.path.join(HERE, "build")
    os.makedirs(work, exist_ok=True)
    ico = os.path.join(work, "icon.ico")
    ver = os.path.join(work, "version.txt")
    make_ico(ico)
    version_file(ver)
    cmd = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", NAME, "--icon", ico, "--version-file", ver,
        "--distpath", os.path.join(HERE, "dist"), "--workpath", work, "--specpath", work,
        "--hidden-import", "pyaudiowpatch", "--hidden-import", "welcome",
        "--collect-submodules", "winrt",
        "--hidden-import", "updater", "--hidden-import", "zone_editor",
        "--hidden-import", "panel", "--hidden-import", "widgets", "--hidden-import", "hotkeys", "--hidden-import", "easter",
        "--add-data", f"{os.path.join(HERE, 'VERSION')}{os.pathsep}.",
    ]
    # Bibliotheques C++ de Microsoft, version la plus recente, a la racine du paquet :
    # celles livrees avec Qt sont plus vieilles que le compilateur de PyQt, et un PC
    # peut en avoir d'encore plus vieilles (voir bootstrap.py).
    sysdir = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
    for dll in ("msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll", "msvcp140_atomic_wait.dll",
                "concrt140.dll", "vcruntime140.dll", "vcruntime140_1.dll"):
        src = os.path.join(sysdir, dll)
        if os.path.exists(src):
            cmd += ["--add-binary", f"{src}{os.pathsep}."]
    # tout ce dont l'appli n'a pas besoin : .exe plus petit, demarrage plus rapide
    for mod in ("tkinter", "unittest", "pydoc", "doctest", "pdb", "lib2to3", "test", "setuptools", "pip",
                "PyQt6.QtQml", "PyQt6.QtQuick", "PyQt6.QtPdf", "PyQt6.QtSvg", "PyQt6.QtBluetooth",
                "PyQt6.QtMultimedia", "PyQt6.QtDBus", "PyQt6.QtSql", "PyQt6.QtTest", "PyQt6.QtOpenGL",
                "PyQt6.QtDesigner", "PyQt6.QtHelp", "PyQt6.QtPrintSupport", "PyQt6.QtXml",
                "numpy.f2py", "numpy.testing", "numpy.tests"):
        cmd += ["--exclude-module", mod]
    cmd.append(os.path.join(HERE, "overlay.py"))
    print("Construction en cours (2 a 4 minutes)...", flush=True)
    code = subprocess.call(cmd, cwd=HERE)
    exe = os.path.join(HERE, "dist", NAME + ".exe")
    if code == 0 and os.path.exists(exe):
        print(f"\nOK : dist\\{NAME}.exe ({os.path.getsize(exe) / 1e6:.0f} Mo)")
        if was_running:
            print("Relance de l'appli.")
            subprocess.Popen([exe], cwd=os.path.dirname(exe))
    else:
        print("\nEchec de la construction.")
    shutil.rmtree(os.path.join(HERE, "__pycache__"), ignore_errors=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
