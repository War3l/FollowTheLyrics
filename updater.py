"""Mise a jour : regarde la derniere version publiee sur GitHub et remplace le .exe
sur place (meme fichier, meme dossier : raccourcis et demarrage avec Windows restent bons).

Comment le remplacement marche : Windows interdit d'effacer un .exe en cours
d'execution, mais permet de le RENOMMER. On telecharge donc « X.exe.new », on renomme
« X.exe » en « X.exe.old », « X.exe.new » en « X.exe », puis on lance le nouveau,
qui prend la place de l'ancien et efface le « .old ».
"""
import hashlib
import json
import os
import subprocess
import sys
import urllib.request

from PyQt6.QtCore import QThread, pyqtSignal

import bootstrap

REPO = "War3l/FollowTheLyrics"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{REPO}/releases/latest"
ASSET_NAME = "FollowTheLyrics.exe"
DOWNLOAD_PREFIX = f"https://github.com/{REPO}/releases/download/"  # seule origine acceptee
USER_AGENT = "FollowTheLyrics-updater"


def current_version():
    fake = os.environ.get("FTL_FAKE_VERSION")  # pour tester la mise a jour
    if fake:
        return fake
    try:
        with open(os.path.join(bootstrap.ROOT, "VERSION"), encoding="utf-8") as f:
            return f.read().strip() or "0"
    except Exception:
        return "0"


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
    """-> dict(version, url, size, sha256, notes) de la derniere version, ou None."""
    api = os.environ.get("FTL_UPDATE_API") or API_URL  # variable de test
    if not api.startswith(f"https://api.github.com/repos/{REPO}/"):
        api = API_URL
    req = urllib.request.Request(api, headers={"User-Agent": USER_AGENT,
                                                   "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8"))
    for asset in data.get("assets", []):
        url = asset.get("browser_download_url", "")
        if asset.get("name") == ASSET_NAME and url.startswith(DOWNLOAD_PREFIX):
            digest = asset.get("digest") or ""
            return {"version": str(data.get("tag_name", "")).lstrip("vV"), "url": url,
                    "size": int(asset.get("size") or 0),
                    "sha256": digest.split(":", 1)[1].lower() if digest.startswith("sha256:") else "",
                    "notes": (data.get("body") or "").strip()}
    return None


def download(info, dest, progress=None, timeout=20):
    """Telecharge le nouveau .exe dans `dest` et verifie qu'il est complet et intact."""
    if not info["url"].startswith(DOWNLOAD_PREFIX):
        raise ValueError("adresse de telechargement inattendue")
    req = urllib.request.Request(info["url"], headers={"User-Agent": USER_AGENT})
    sha = hashlib.sha256()
    done = 0
    with urllib.request.urlopen(req, timeout=timeout) as r, open(dest, "wb") as f:
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
        raise ValueError("le fichier telecharge ne correspond pas a celui publie")


def swap(exe, new):
    """Met `new` a la place de `exe` (l'ancien devient `exe`.old). Annule tout si ca rate."""
    old = exe + ".old"
    if os.path.exists(old):
        os.remove(old)
    os.replace(exe, old)
    try:
        os.replace(new, exe)
    except Exception:
        os.replace(old, exe)  # on remet l'ancien en place
        raise


def relaunch(exe, version):
    """Lance le nouveau .exe, independant de celui-ci (il se deballe de son cote)."""
    env = dict(os.environ)
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    for key in list(env):
        if key.startswith(("_MEIPASS", "_PYI_")):
            env.pop(key, None)
    env.pop("FTL_FAKE_VERSION", None)
    subprocess.Popen([exe, "--updated", version], env=env, cwd=os.path.dirname(exe), close_fds=True,
                     creationflags=0x00000008 | 0x00000200)  # DETACHED_PROCESS | NEW_PROCESS_GROUP


def cleanup_leftovers():
    """Efface les restes d'une mise a jour (ancien .exe, telechargement interrompu).
    Renvoie False s'il faudra reessayer (l'ancienne version n'a pas encore fini de quitter)."""
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
    """Regarde s'il existe une version plus recente."""
    found = pyqtSignal(dict)
    nothing = pyqtSignal(bool)  # rien de neuf (True = on n'a pas pu joindre GitHub)

    def run(self):
        try:
            info = fetch_latest()
            if info and info["version"] and is_newer(info["version"], current_version()):
                self.found.emit(info)
            else:
                self.nothing.emit(False)
        except Exception:
            self.nothing.emit(True)  # pas de reseau, GitHub injoignable : on reessaiera plus tard


class UpdateInstall(QThread):
    """Telecharge la nouvelle version et la met a la place du .exe en cours."""
    progress = pyqtSignal(float)
    failed = pyqtSignal(str)
    installed = pyqtSignal(str)  # le nouveau .exe est en place : il n'y a plus qu'a le lancer

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
            self.failed.emit("Impossible d'écrire dans le dossier du programme. Déplace FollowTheLyrics.exe "
                             "dans un dossier à toi (Bureau, Documents…) puis réessaie.")
            return
        except Exception as e:
            self._clean(new)
            self.failed.emit(f"La mise à jour a échoué ({e}). Réessaie plus tard.")
            return
        self.installed.emit(self.info["version"])

    @staticmethod
    def _clean(path):
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass
