"""Quand le son vient d'un navigateur : de quel site ?

Windows ne donne que le nom du navigateur (Chrome, Opera, Brave...), jamais le site. On le
retrouve dans le titre de ses fenetres, la ou s'affiche l'onglet ouvert :
"Titre - YouTube Music – Opera". Rien d'autre n'est lu : ni les pages, ni l'historique, ni
les cookies.

Seuls les sites de musique de la liste (reglable dans le panneau) donnent des paroles.
Netflix, Twitch ou une video quelconque sont ignores.
"""
import ctypes
import re
import time
from ctypes import wintypes

OTHER = "other"  # site non reconnu

# (identifiant, nom affiche, ce qu'on cherche dans le titre de l'onglet). L'ordre compte :
# "YouTube Music" doit etre teste avant "YouTube".
SITES = [
    ("ytmusic", "YouTube Music", r"youtube\s*music"),
    ("youtube", "YouTube", r"\byoutube\b"),
    ("spotify", "Spotify", r"\bspotify\b"),
    ("soundcloud", "SoundCloud", r"soundcloud"),
    ("applemusic", "Apple Music", r"apple\s*music"),
    ("deezer", "Deezer", r"\bdeezer\b"),
    ("tidal", "Tidal", r"\btidal\b"),
    ("amazon", "Amazon Music", r"amazon\s*music"),
    ("qobuz", "Qobuz", r"\bqobuz\b"),
    ("bandcamp", "Bandcamp", r"\bbandcamp\b"),
    ("audiomack", "Audiomack", r"audiomack"),
    ("napster", "Napster", r"\bnapster\b"),
    ("pandora", "Pandora", r"\bpandora\b"),
    ("jiosaavn", "JioSaavn", r"jiosaavn"),
]
SITE_NAMES = dict((s[0], s[1]) for s in SITES)
# Adresse du site, pour les pages qui n'annoncent pas d'artiste : le navigateur met alors
# le nom de domaine a la place ("www.youtube.com").
DOMAINS = [
    ("ytmusic", "music.youtube.com"), ("youtube", "youtube.com"), ("spotify", "spotify.com"),
    ("soundcloud", "soundcloud.com"), ("applemusic", "music.apple.com"), ("deezer", "deezer.com"),
    ("tidal", "tidal.com"), ("amazon", "music.amazon."), ("qobuz", "qobuz.com"),
    ("bandcamp", "bandcamp.com"), ("audiomack", "audiomack.com"), ("napster", "napster.com"),
    ("pandora", "pandora.com"), ("jiosaavn", "jiosaavn.com"),
]
_HOST = re.compile(r"^(?:[a-z0-9-]+\.)+[a-z]{2,}$")


def site_of_host(artist):
    """Si "l'artiste" est en fait un nom de domaine : le site de musique, ou OTHER. Sinon None."""
    host = (artist or "").strip().lower()
    if not _HOST.match(host):
        return None
    for sid, dom in DOMAINS:
        if host == dom or ("." + dom) in ("." + host) or (dom.endswith(".") and dom in host):
            return sid
    return OTHER
_SITE_RE = [(sid, re.compile(rx, re.I)) for sid, _name, rx in SITES]

# (morceau de l'identifiant Windows, nom, programmes dont on lit les titres de fenetres)
BROWSERS = [
    ("operagx", "Opera GX", ("opera.exe",)),
    ("opera", "Opera", ("opera.exe",)),
    ("chrome", "Google Chrome", ("chrome.exe",)),
    ("msedge", "Microsoft Edge", ("msedge.exe",)),
    ("firefox", "Firefox", ("firefox.exe",)),
    ("brave", "Brave", ("brave.exe",)),
    ("vivaldi", "Vivaldi", ("vivaldi.exe",)),
    ("thebrowsercompany", "Arc", ("arc.exe",)),
    ("chromium", "Chromium", ("chromium.exe",)),
    ("librewolf", "LibreWolf", ("librewolf.exe",)),
    ("waterfox", "Waterfox", ("waterfox.exe",)),
    ("floorp", "Floorp", ("floorp.exe",)),
    ("zen.exe", "Zen", ("zen.exe",)),
    ("yandex", "Yandex", ("browser.exe",)),
    ("duckduckgo", "DuckDuckGo", ("duckduckgo.exe",)),
    ("thorium", "Thorium", ("thorium.exe",)),
]
# Firefox et ses cousins s'annoncent par un code de 16 caracteres au lieu d'un nom.
MOZILLA = ("firefox.exe", "zen.exe", "librewolf.exe", "waterfox.exe", "floorp.exe", "mullvadbrowser.exe")
_HEX16 = re.compile(r"^[0-9a-f]{16}$", re.I)
_BROWSER_TAIL = re.compile(r"^(google chrome|opera( gx)?|brave|microsoft edge|mozilla firefox.*|firefox|vivaldi|"
                           r"arc|chromium|librewolf|waterfox|floorp|zen( browser)?|yandex.*|duckduckgo|thorium)$",
                           re.I)
_SPLIT = re.compile(r"\s+[-–—|]\s+")


def browser_of(app_id):
    """(nom, programmes) si l'appli est un navigateur, sinon None."""
    low = (app_id or "").lower()
    if not low:
        return None
    if _HEX16.match(low):
        return ("Firefox", MOZILLA)
    for needle, name, exes in BROWSERS:
        if needle in low:
            return (name, exes)
    return None


def is_browser(app_id):
    return browser_of(app_id) is not None


def _fold(s):
    return re.sub(r"\s+", " ", (s or "").replace("​", "")).strip().casefold()


def core_title(window_title):
    """Le titre de l'onglet, sans le nom du navigateur a la fin."""
    parts = _SPLIT.split((window_title or "").replace("​", "").strip())
    if len(parts) > 1 and len(parts[-1]) < 40 and _BROWSER_TAIL.search(parts[-1]):
        cut = (window_title or "").replace("​", "").strip()
        return cut[: cut.rfind(parts[-1])].rstrip(" -–—|")
    return (window_title or "").strip()


def site_of(tab_title):
    """Le site de musique nomme dans un titre d'onglet, ou None. Le nom du site est en general
    le dernier morceau ("Titre - YouTube") : on regarde la d'abord, pour qu'une video appelee
    "Spotify" sur YouTube reste bien du YouTube."""
    parts = _SPLIT.split(tab_title or "")
    for text in (parts[-1], tab_title or ""):
        for sid, rx in _SITE_RE:
            if rx.search(text):
                return sid
    return None


# ---- titres des fenetres ---------------------------------------------------------------
_exe_cache = {}
_exe_cache_at = [0.0]


def _exe_name(pid):
    now = time.monotonic()
    if now - _exe_cache_at[0] > 60:  # les numeros de processus sont reutilises
        _exe_cache.clear()
        _exe_cache_at[0] = now
    if pid in _exe_cache:
        return _exe_cache[pid]
    k = ctypes.windll.kernel32
    k.OpenProcess.restype = wintypes.HANDLE
    name = ""
    h = k.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if h:
        buf = ctypes.create_unicode_buffer(520)
        n = wintypes.DWORD(520)
        if k.QueryFullProcessImageNameW(wintypes.HANDLE(h), 0, buf, ctypes.byref(n)):
            name = buf.value.replace("/", "\\").split("\\")[-1].lower()
        k.CloseHandle(wintypes.HANDLE(h))
    _exe_cache[pid] = name
    return name


def window_titles(exes):
    """Titres des fenetres visibles (meme reduites) des programmes donnes."""
    out = []
    try:
        u = ctypes.windll.user32
        exes = tuple(e.lower() for e in exes)

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def each(hwnd, _):
            if not u.IsWindowVisible(hwnd):
                return True
            n = u.GetWindowTextLengthW(hwnd)
            if n <= 0:
                return True
            pid = wintypes.DWORD()
            u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if _exe_name(pid.value) in exes:
                buf = ctypes.create_unicode_buffer(n + 1)
                u.GetWindowTextW(hwnd, buf, n + 1)
                if buf.value:
                    out.append(buf.value)
            return True

        u.EnumWindows(each, 0)
    except Exception:
        pass
    return out


# ---- la decision -----------------------------------------------------------------------
class SiteGuard:
    """Dit si un media venu d'un navigateur est de la musique a suivre."""

    def __init__(self, off=(), other=False, titles=window_titles):
        self.off = set(off)        # sites decoches
        self.other = bool(other)   # suivre aussi les sites non reconnus
        self.titles = titles
        self.last = {}             # navigateur -> dernier site reconnu (l'onglet peut passer derriere)
        self.seen = {}             # navigateur -> (site, suivi ?) : pour le panneau

    def site(self, app_id, title, artist):
        """None si ce n'est pas un navigateur ; sinon l'identifiant du site, ou OTHER."""
        b = browser_of(app_id)
        if b is None:
            return None
        tabs = []
        for w in self.titles(b[1]):
            c = core_title(w)
            tabs.append((_fold(c), site_of(c)))
        t, a = _fold(title), _fold(artist)
        # 0. La page n'annonce pas d'artiste : le navigateur donne son adresse a la place.
        host = site_of_host(artist)
        if host is not None and host != OTHER:
            self.last[app_id] = host
            return host
        if host == OTHER:
            a = ""
        # 1. L'onglet affiche est celui qui joue, et son site est connu.
        if len(t) >= 2:
            for text, sid in tabs:
                if sid and t in text:
                    self.last[app_id] = sid
                    return sid
        # 2. Une page qui n'annonce aucun artiste n'est pas un lecteur de musique
        #    (Netflix, un direct, une video dans une page...).
        if not a:
            return OTHER
        # 3. Spotify affiche "Titre • Artiste" pendant la lecture, sans son nom.
        first = a.split(",")[0].strip()
        for text, sid in tabs:
            if not sid and t and t in text and first and first in text and re.search(r"\s[•·]\s", text):
                self.last[app_id] = "spotify"
                return "spotify"
        # 4. L'onglet de la musique est passe derriere un autre : on garde le dernier site reconnu.
        if app_id in self.last:
            return self.last[app_id]
        # 5. Un site de musique est ouvert dans ce navigateur, meme si son titre ne dit pas le morceau.
        #    Sauf YouTube, dont l'onglet porte toujours le titre de la video : s'il ne correspond
        #    pas, ce n'est pas lui qui joue.
        for _text, sid in tabs:
            if sid and sid != "youtube":
                return sid
        return OTHER

    def enabled(self, sid):
        return self.other if sid == OTHER else sid not in self.off

    def allows(self, app_id, title, artist):
        sid = self.site(app_id, title, artist)
        if sid is None:
            return True, ""
        ok = self.enabled(sid)
        self.seen[app_id] = (sid, ok)
        return ok, sid
