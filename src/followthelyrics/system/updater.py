import hashlib
import json
import logging
import os
import subprocess
import sys
import urllib.request

from PyQt6.QtCore import QThread
from PyQt6.QtCore import pyqtSignal

from followthelyrics import version
from followthelyrics.system import bootstrap

logger = logging.getLogger(__name__)

API_URL = f"https://api.github.com/repos/{version.REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{version.REPO}/releases/latest"
ASSET_NAME = "FollowTheLyrics.exe"
DOWNLOAD_PREFIX = f"https://github.com/{version.REPO}/releases/download/"
USER_AGENT = "FollowTheLyrics-updater"


def parse_version(text):
    out = []
    for part in str(text).strip().lstrip("vV").split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        out.append(int(digits) if digits else 0)
    return tuple(out)


def is_newer(candidate, current):
    a, b = parse_version(candidate), parse_version(current)
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


def fetch_latest(timeout=8):
    api = os.environ.get("FTL_UPDATE_API") or API_URL
    if not api.startswith(f"https://api.github.com/repos/{version.REPO}/"):
        api = API_URL
    req = urllib.request.Request(
        api,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8"))
    for asset in data.get("assets", []):
        url = asset.get("browser_download_url", "")
        if asset.get("name") == ASSET_NAME and url.startswith(DOWNLOAD_PREFIX):
            digest = asset.get("digest") or ""
            return {
                "version": str(data.get("tag_name", "")).lstrip("vV"),
                "url": url,
                "size": int(asset.get("size") or 0),
                "sha256": digest.split(":", 1)[1].lower()
                if digest.startswith("sha256:")
                else "",
                "notes": (data.get("body") or "").strip(),
            }
    return None


def download(info, dest, progress=None, timeout=20):
    if not info["url"].startswith(DOWNLOAD_PREFIX):
        raise ValueError("adresse de telechargement inattendue")
    req = urllib.request.Request(
        info["url"], headers={"User-Agent": USER_AGENT}
    )
    sha = hashlib.sha256()
    done = 0
    with (
        urllib.request.urlopen(req, timeout=timeout) as r,
        open(dest, "wb") as f,
    ):
        total = info["size"] or int(r.headers.get("Content-Length") or 0)
        while True:
            chunk = r.read(256 * 1024)
            if not chunk:
                break
            f.write(chunk)
            sha.update(chunk)
            done += len(chunk)
            if progress and total:
                progress(min(1.0, done / total))
    with open(dest, "rb") as f:
        head = f.read(2)
    if head != b"MZ" or done < 5_000_000:
        raise ValueError("le fichier telecharge n'est pas un programme valide")
    if info["size"] and done != info["size"]:
        raise ValueError("telechargement incomplet")
    if info["sha256"] and sha.hexdigest() != info["sha256"]:
        raise ValueError(
            "le fichier telecharge ne correspond pas a celui publie"
        )


def swap(exe, new):
    old = exe + ".old"
    if os.path.exists(old):
        os.remove(old)
    os.replace(exe, old)
    try:
        os.replace(new, exe)
    except Exception:
        os.replace(old, exe)
        raise


def relaunch(exe, version):
    env = dict(os.environ)
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    for key in list(env):
        if key.startswith(("_MEIPASS", "_PYI_")):
            env.pop(key, None)
    env.pop("FTL_FAKE_VERSION", None)
    subprocess.Popen(
        [exe, "--updated", version],
        env=env,
        cwd=os.path.dirname(exe),
        close_fds=True,
        creationflags=0x00000008 | 0x00000200,
    )


def cleanup_leftovers():
    if not bootstrap.FROZEN:
        return True
    ok = True
    for suffix in (".old", ".new"):
        path = sys.executable + suffix
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                ok = False
    return ok


class UpdateCheck(QThread):
    found = pyqtSignal(dict)
    nothing = pyqtSignal(bool)

    def run(self):
        try:
            info = fetch_latest()
            if (
                info
                and info["version"]
                and is_newer(info["version"], version.current())
            ):
                self.found.emit(info)
            else:
                self.nothing.emit(False)
        except Exception:
            logger.warning("run failed", exc_info=True)
            self.nothing.emit(True)


class UpdateInstall(QThread):
    progress = pyqtSignal(float)
    failed = pyqtSignal(str)
    installed = pyqtSignal(str)

    def __init__(self, info):
        super().__init__()
        self.info = info

    def run(self):
        exe = sys.executable
        new = exe + ".new"
        try:
            download(self.info, new, self.progress.emit)
            swap(exe, new)
        except PermissionError:
            self._clean(new)
            self.failed.emit(
                "Impossible d'écrire dans le dossier du programme. Déplace "
                "FollowTheLyrics.exe "
                "dans un dossier à toi (Bureau, Documents…) puis réessaie."
            )
            return
        except Exception as e:
            logger.warning("run failed", exc_info=True)
            self._clean(new)
            self.failed.emit(
                f"La mise à jour a échoué ({e}). Réessaie plus tard."
            )
            return
        self.installed.emit(self.info["version"])

    @staticmethod
    def _clean(path):
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass
