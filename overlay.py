"""FollowTheLyrics.

Affiche les paroles de la musique en cours (Spotify, YouTube Music, Deezer...)
par-dessus les jeux, dans la moitie haute de l'ecran. Trois modes :
  - Classique        : les lignes defilent dans un coin (gauche / centre / droite)
  - Edit             : chaque ligne surgit a un endroit different de l'ecran
  - Machine a ecrire : les lettres s'ecrivent au fil du chant

Un panneau de controle s'ouvre au lancement (icone ♪ pres de l'heure pour le rouvrir).

Raccourcis (modifiables dans le panneau, page « Raccourcis ») :
  Ctrl+Alt+L      afficher / masquer
  Ctrl+Alt+M      changer de mode
  Ctrl+Alt+T      couleurs : album / blanc lumineux
  Ctrl+Alt+S      changer d'animation (cinetique, karaoke, simple)
  Ctrl+Alt+Z      voir les zones interdites du jeu actuel
  Ctrl+Alt+Haut   paroles plus tot   (+0.2 s)
  Ctrl+Alt+Bas    paroles plus tard  (-0.2 s)

Options : --demo (paroles de demo)
          --snapshot fichier.png --at 7.5 [--mode classic] [--position left] [--color white]
                     [--font "Bahnschrift"] [--style kinetic] [--game "League of Legends.exe"]
                     [--zones] [--cover image.png] [--card] [--translation]
"""
import argparse
import bisect
import ctypes
import math
import os
import random
import re
import statistics
import sys
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from ctypes import wintypes
from types import SimpleNamespace

import bootstrap

bootstrap.prepare()  # nos bibliotheques C++ et Qt d'abord (voir bootstrap.py)

import numpy as np  # noqa: E402

try:
    from PyQt6.QtCore import QPointF, QRectF, Qt, QThread, QTimer, pyqtSignal
except ImportError as _qt_error:
    bootstrap.report(_qt_error)
    raise SystemExit(1)
from PyQt6.QtGui import (
    QAction, QBrush, QColor, QFont, QFontDatabase, QFontMetricsF, QGuiApplication,
    QImage, QLinearGradient, QPainter, QPainterPath, QPen, QRegion, QTransform,
)
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidget

import colors as cover_colors
import easter
import games
import hotkeys
from lyrics import (Line, build_line, cache_load, cache_save, extract_singers, fetch_lyrics_ex,
                    mark_title_lines, split_adlibs, translate_lines)
from settings import COLORS, DEFAULTS, MODES, POSITIONS, STYLES, load_config, save_config

PREV_ALPHA = 0.42      # opacite de la ligne precedente
HIDE_AFTER = 3.0       # une ligne disparait 3 s apres avoir ete chantee
CARD_TIME = 4.5        # duree de la carte "pochette + titre" en debut de morceau
UPPER = 0.5            # les paroles restent dans la moitie haute de l'ecran
NEUTRAL_PALETTE = ["#FFFFFF", "#E8ECF4", "#CBD3E3"]  # en attendant la pochette
WHITE_PALETTE = ["#FFFFFF", "#F4F6FB", "#E6EAF3"]


def clamp(x, lo=0.0, hi=1.0):
    return lo if x < lo else hi if x > hi else x


def ease_out(x):
    return 1 - (1 - x) ** 3


def ease_out_back(x):
    c = 1.9
    return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2


def lerp(a, b, k):
    return a + (b - a) * k


def area(r: QRectF):
    return r.width() * r.height() if r.isValid() else 0.0


def mix(c1: QColor, c2: QColor, k):
    return QColor(int(lerp(c1.red(), c2.red(), k)), int(lerp(c1.green(), c2.green(), k)),
                  int(lerp(c1.blue(), c2.blue(), k)))


def _box_blur(a, r, axis):
    """Moyenne glissante de largeur 2r+1 le long d'un axe (via sommes cumulees)."""
    if r < 1:
        return a
    pad = [(0, 0), (0, 0)]
    pad[axis] = (r + 1, r)
    c = np.cumsum(np.pad(a, pad), axis=axis)
    n = 2 * r + 1
    if axis == 1:
        return (c[:, n:] - c[:, :-n]) / n
    return (c[n:, :] - c[:-n, :]) / n


def gaussian_blur(a, sigma):
    """Flou gaussien approche par 3 flous "boite" successifs (rapide, rendu doux)."""
    r = max(1, int(round(sigma * 0.95)))
    for _ in range(3):
        a = _box_blur(a, r, 1)
        a = _box_blur(a, r, 0)
    return a


_FAMILIES = None


def family_or_default(name):
    global _FAMILIES
    if _FAMILIES is None:
        _FAMILIES = set(QFontDatabase.families())
    return name if name in _FAMILIES else "Segoe UI"


# --------------------------------------------------------------------------
# Couleurs de la pochette
# --------------------------------------------------------------------------
def palette_from_cover(data):
    """Les 2-3 couleurs dominantes de la pochette, eclaircies pour rester lisibles."""
    img = QImage.fromData(data) if not isinstance(data, QImage) else data
    if img.isNull():
        return None
    # reduite a 64x64 puis analysee dans colors.py (familles de couleurs en OKLCH)
    img = img.convertToFormat(QImage.Format.Format_RGBA8888).scaled(
        64, 64, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    try:
        ptr = img.constBits()
        ptr.setsize(img.sizeInBytes())
        arr = np.frombuffer(ptr, dtype=np.uint8).reshape(img.height(), img.bytesPerLine())
        arr = arr[:, :img.width() * 4].reshape(img.height(), img.width(), 4)[:, :, :3].copy()
        pal = cover_colors.palette_rgb(arr)
    except Exception:
        pal = None
    return [QColor(*c) for c in pal] if pal else None


# --------------------------------------------------------------------------
# Analyse des paroles : mots tenus, refrain
# --------------------------------------------------------------------------
def compute_word_meta(lines):
    """Pour chaque mot : (debut, fin, intensite 0..1 du "mot tenu")."""
    per_char = []
    for l in lines:
        if not l.chars:
            continue
        c = 0
        for w in l.text.split():
            seg = l.chars[c:c + len(w)]
            if len(w) >= 2 and seg:
                d = seg[-1][1] - seg[0][0]
                if d > 0:
                    per_char.append(d / len(w))
            c += len(w) + 1
    base = statistics.median(per_char) if per_char else 0.07
    for l in lines:
        meta = {}
        if l.chars:
            c = 0
            for w in l.text.split():
                seg = l.chars[c:c + len(w)]
                if seg:
                    start, end = seg[0][0], seg[-1][1]
                    d = end - start
                    ratio = d / (len(w) * base + 0.12)
                    meta[c] = (start, end, clamp((ratio - 2.0) / 2.5) if d >= 0.45 else 0.0)
                c += len(w) + 1
        l.word_meta = meta


def mark_chorus(lines):
    """Les lignes qui reviennent plusieurs fois = le refrain."""
    def key(t):
        return " ".join(re.sub(r"[^\w]+", " ", t.lower()).split())
    counts = {}
    for l in lines:
        k = key(l.text)
        if len(k) >= 6:
            counts[k] = counts.get(k, 0) + 1
    texts = [l for l in lines if l.text]
    rep = sum(1 for l in texts if counts.get(key(l.text), 0) >= 2)
    need = 3 if texts and rep / len(texts) > 0.6 else 2
    for l in lines:
        l.chorus = counts.get(key(l.text), 0) >= need


def held_fx(meta, pos):
    """-> (echelle, dx, dy, lueur 0..1, etirement horizontal)"""
    none = (1.0, 0.0, 0.0, 0.0, 1.0)
    if not meta:
        return none
    start, end, inten = meta
    if inten <= 0 or pos < start:
        return none
    amp = 0.10 + 0.24 * inten
    if pos <= end:
        k = ease_out(clamp((pos - start) / max(0.25, end - start)))
        shake = (0.8 + 2.8 * inten) * k if (end - start) > 0.8 else 0.0
        dx = shake * math.sin(pos * 61 + start * 13)
        dy = shake * math.sin(pos * 47 + start * 7 + 1.3)
        return 1 + amp * k, dx, dy, k, 1 + 0.07 * inten * k
    after = pos - end
    if after > 0.5:
        return none
    sc = 1 + amp * math.exp(-after * 9) * math.cos(after * 22)
    return sc, 0.0, 0.0, max(0.0, 1 - after * 3), 1.0


# --------------------------------------------------------------------------
# Sources de donnees
# --------------------------------------------------------------------------
class MediaWorker(QThread):
    """Interroge Windows toutes les 400 ms, cherche paroles, traduction et pochette."""
    track = pyqtSignal(object)
    lyrics = pyqtSignal(object, object)
    translated = pyqtSignal(object)
    cover = pyqtSignal(object, object)
    sources = pyqtSignal(object)  # applis qui diffusent un media en ce moment
    COVER_READS = (0.8, 3.5)
    MAX_DURATION = 20 * 60  # plus long = film, video ou mix : on ne cherche pas de paroles
    RETRY_DELAYS = (10, 30, 60, 120, 300)  # nouvelles tentatives apres un souci de reseau

    def __init__(self, blocked=()):
        super().__init__()
        self._stop = False
        self._cache = {}
        self._retry = {}     # cle -> (heure de la prochaine tentative, nb d'essais)
        self._pending = set()
        self.blocked = set(blocked)  # applis ignorees (reglable dans le panneau)

    def run(self):
        import asyncio
        from media import get_manager, get_now_playing, get_thumbnail, list_sources  # winrt dans ce thread

        loop = asyncio.new_event_loop()
        manager = loop.run_until_complete(get_manager())
        pool = ThreadPoolExecutor(max_workers=2)
        last_key = None
        last_sources = None
        changed_at, cover_step, last_cover = 0.0, 0, None
        while not self._stop:
            blocked = frozenset(self.blocked)
            try:
                np = loop.run_until_complete(get_now_playing(manager, blocked))
            except Exception:
                np = None
            self.track.emit(np)
            src = list_sources(manager)
            if src != last_sources:
                last_sources = src
                self.sources.emit(src)
            now = time.monotonic()
            if np and np.key != last_key:
                last_key = np.key
                changed_at, cover_step = now, 0
                if np.key in self._cache:
                    self.lyrics.emit(np.key, self._cache[np.key])
                    self.translated.emit(np.key)
                elif np.key not in self._pending:
                    self._pending.add(np.key)
                    pool.submit(self._fetch, np)
            elif np and np.key in self._retry and np.key not in self._pending \
                    and now >= self._retry[np.key][0]:
                self._pending.add(np.key)
                pool.submit(self._fetch, np)
            if np and np.key == last_key and cover_step < len(self.COVER_READS) \
                    and now - changed_at >= self.COVER_READS[cover_step]:
                cover_step += 1
                try:
                    data = loop.run_until_complete(get_thumbnail(manager, blocked))
                except Exception:
                    data = None
                if data and data != last_cover:
                    last_cover = data
                    self.cover.emit(np.key, data)
            time.sleep(0.4)
        pool.shutdown(wait=False)

    def _fetch(self, np):
        try:
            self._fetch_inner(np)
        finally:
            self._pending.discard(np.key)

    def _fetch_inner(self, np):
        if np.duration and np.duration > self.MAX_DURATION:
            self._cache[np.key] = None
            self.lyrics.emit(np.key, None)
            return
        found, lines = cache_load(np.title, np.artist, np.duration)
        if found:  # deja cherche une autre fois : instantane, meme hors ligne
            self._cache[np.key] = lines
            self.lyrics.emit(np.key, lines)
            self.translated.emit(np.key)
            return
        try:
            lines, reliable = fetch_lyrics_ex(np.title, np.artist, np.album, np.duration)
        except Exception:
            lines, reliable = None, False
        if not reliable:
            # Souci de reseau : on ne retient PAS "pas de paroles", on reessaiera.
            n = self._retry.get(np.key, (0, 0))[1]
            if n < len(self.RETRY_DELAYS):
                self._retry[np.key] = (time.monotonic() + self.RETRY_DELAYS[n], n + 1)
            else:
                self._retry.pop(np.key, None)
            self.lyrics.emit(np.key, None)
            return
        self._retry.pop(np.key, None)
        self._cache[np.key] = lines
        self.lyrics.emit(np.key, lines)
        translated_ok = True
        if lines:
            try:
                translated_ok = translate_lines(lines) is not None
            except Exception:
                translated_ok = False
            self.translated.emit(np.key)
        if translated_ok:
            cache_save(np.title, np.artist, np.duration, lines)

    def stop(self):
        self._stop = True
        self.wait(2000)


def _demo_line(t, text, singer=""):
    """Ligne de demo avec un faux timing mot par mot. Un "~" en fin de mot = mot tenu."""
    if not text:
        return Line(t, "")
    segs = [(t, 0.01, f"({singer}) ")] if singer else []
    for k, w in enumerate(text.split()):
        held = w.endswith("~")
        w = w.rstrip("~")
        dur = 1.6 if held else 0.12 + 0.045 * len(w) + (0.25 if k % 4 == 3 else 0)
        segs.append((t, dur, w + " "))
        t += dur + (0.08 if w.endswith(",") else 0.02)
    return build_line(segs)


DEMO_LINES = split_adlibs(extract_singers([
    _demo_line(2.0, "Les neons dansent sur l'ecran"),
    _demo_line(5.5, "Je joue la nuit (oh oh), je perds le temps"),
    _demo_line(9.0, "Monte le son, garde le rythme~", "Nova"),
    _demo_line(12.5, "Comme un refrain qui revient~"),
    _demo_line(16.0, ""),
    _demo_line(19.0, "Monte le son, garde le rythme~", "Kai"),
    _demo_line(22.5, "Les paroles brillent (yeah), rien ne s'arrete"),
    _demo_line(26.5, "Une derniere ligne pour la route, et on relance la partie"),
    _demo_line(32.0, ""),
]))
DEMO_LENGTH = 34.0
DEMO_KEY = ("monte le son", "followthelyrics (demo)")


def demo_track(position):
    return SimpleNamespace(
        title="Monte le son", artist="FollowTheLyrics (demo)", album="Demo", duration=DEMO_LENGTH,
        position=position, playing=True, app="demo", key=DEMO_KEY,
    )


class BeatBridge(QThread):
    """Fait passer les beats du thread audio vers l'interface."""
    beat = pyqtSignal(float)


# --------------------------------------------------------------------------
# L'overlay plein ecran
# --------------------------------------------------------------------------
class Overlay(QWidget):
    def __init__(self, cfg, profiles, clock=time.monotonic, rng=None):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.NoDropShadowWindowHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self.cfg = cfg
        self.clock = clock
        self.rng = rng or random.Random()
        self.profile_key, self.profile = "bureau", profiles["bureau"]
        self.zones: list[QRectF] = []
        self.track = None
        self.track_key = None
        self.track_changed_at = -99.0
        self.card_since = -99.0
        self.cover_img: QImage | None = None
        self.lines: list[Line] | None = None
        self.times: list[float] = []
        self.word_sync = False
        self.state = "idle"  # idle | loading | ok | missing
        self.anchor_pos = 0.0
        self.anchor_t = clock()
        self.playing = False
        self.alpha = 0.0
        self.user_hidden = False
        self.toast_text = ""
        self.toast_until = -99.0
        self.zones_until = -99.0
        self.beat_t, self.beat_k = -99.0, 0.0
        self.last_tick = clock()
        self.cur = None       # ligne en cours : {"idx", "place", "since"}
        self.prev = None      # ligne d'avant : idem + "prev_since"
        self.exiting = []     # lignes qui disparaissent : [(entree, depuis)]
        self.particles = []
        self.last_region = QRegion()
        self._layout_cache = {}
        self._band = None
        self._halo_cache = OrderedDict()
        self.flash = None          # titre du morceau affiche en geant
        self.egg = None            # easter egg du morceau en cours (voir easter.py)
        self.force_paint = True
        self.was_animating = False
        self.accent = [QColor(c) for c in NEUTRAL_PALETTE]
        self.apply_geometry()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(16)
        self.top_timer = QTimer(self)
        self.top_timer.timeout.connect(self.keep_on_top)
        self.top_timer.start(500)

    # ---- fenetre ---------------------------------------------------------
    def apply_geometry(self):
        self.setGeometry(QGuiApplication.primaryScreen().geometry())
        self.update_zones()
        self.reset_layout()

    def reset_layout(self):
        """Apres un changement de mode / police / taille : on replace tout."""
        self._layout_cache.clear()
        self._band = None
        self.cur = self.prev = None
        self.exiting = []
        self.flash = None
        self.force_paint = True
        self.update()

    def poke(self):
        """Quelque chose a change (couleur, pochette...) : redessiner au prochain tick."""
        self.force_paint = True

    def set_profile(self, key, profile):
        self.profile_key, self.profile = key, profile
        self.update_zones()
        self._band = None

    def update_zones(self):
        W, H = self.width(), self.height()
        self.zones = []
        for z in self.profile.get("zones_interdites", []):
            try:
                self.zones.append(QRectF(z["x"] * W, z["y"] * H, z["l"] * W, z["h"] * H))
            except Exception:
                pass

    def keep_on_top(self):
        """Repasse devant le jeu (qui se met souvent lui-meme "au premier plan")."""
        if not self.isVisible():
            return
        try:
            u = ctypes.windll.user32
            u.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                       ctypes.c_int, ctypes.c_int, ctypes.c_uint]
            u.SetWindowPos.restype = wintypes.BOOL
            # HWND_TOPMOST = -1 : doit etre passe comme un pointeur 64 bits, sinon l'appel echoue
            u.SetWindowPos(int(self.winId()), wintypes.HWND(-1), 0, 0, 0, 0,
                           0x0001 | 0x0002 | 0x0010 | 0x0200)  # NOSIZE|NOMOVE|NOACTIVATE|NOOWNERZORDER
        except Exception:
            pass

    def install_foreground_hook(self):
        """Des qu'une autre fenetre (le jeu) passe au premier plan, on se remet devant."""
        try:
            u = ctypes.windll.user32
            proto = ctypes.WINFUNCTYPE(None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND, wintypes.LONG,
                                       wintypes.LONG, wintypes.DWORD, wintypes.DWORD)

            def on_foreground(*_):
                for delay in (0, 300, 1000, 2500):  # le jeu peut se remettre devant juste apres
                    QTimer.singleShot(delay, self.keep_on_top)

            self._fg_proc = proto(on_foreground)  # garder une reference (sinon effacee)
            u.SetWinEventHook.restype = wintypes.HANDLE
            u.SetWinEventHook.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE, proto,
                                          wintypes.DWORD, wintypes.DWORD, wintypes.DWORD]
            self._fg_hook = u.SetWinEventHook(3, 3, None, self._fg_proc, 0, 0, 0)  # EVENT_SYSTEM_FOREGROUND
        except Exception:
            self._fg_hook = None

    def harden_window(self):
        """Clic traversant + jamais de focus, au niveau Windows."""
        try:
            hwnd = int(self.winId())
            u = ctypes.windll.user32
            u.GetWindowLongPtrW.restype = ctypes.c_ssize_t
            u.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
            ex = u.GetWindowLongPtrW(hwnd, -20)
            u.SetWindowLongPtrW(hwnd, -20, ex | 0x20 | 0x80 | 0x08000000)
        except Exception:
            pass

    # ---- donnees ---------------------------------------------------------
    def raw_position(self):
        return self.anchor_pos + ((self.clock() - self.anchor_t) if self.playing else 0.0)

    def position(self):
        return self.raw_position() + self.cfg["offset"]

    def on_track(self, np):
        now = self.clock()
        if np is None:
            self.playing = False
            self.track = None
            return
        if np.key != self.track_key:
            self.track_key = np.key
            self.track_changed_at = self.card_since = now
            self.lines, self.times = None, []
            self.state = "loading"
            self.cur = self.prev = None
            self.exiting = []
            self.flash = None
            self.cover_img = None
            self.accent = [QColor(c) for c in NEUTRAL_PALETTE]
            self.anchor_pos, self.anchor_t = np.position, now
            self.egg = easter.pick(np, self) if self.cfg.get("easter", True) else None
            self.force_paint = True
        elif np.playing != self.playing or abs(np.position - self.raw_position()) > 0.35:
            self.anchor_pos, self.anchor_t = np.position, now
        self.playing = np.playing
        self.track = np

    def on_lyrics(self, key, lines):
        if key != self.track_key:
            return
        if lines:
            if lines[0].time > 0.5:
                lines = [Line(0.0, "")] + list(lines)
            compute_word_meta(lines)
            mark_chorus(lines)
            if self.track is not None:
                mark_title_lines(lines, self.track.title, self.track.artist)
            self.cur = self.prev = None
            self.exiting = []
            self.lines = lines
            self.times = [l.time for l in lines]
            self.word_sync = any(l.chars for l in lines)
            self.state = "ok"
            if self.egg:
                self.egg.set_lines(lines)
        else:
            self.state = "missing"
        self.track_changed_at = self.clock()
        self.force_paint = True

    def on_translated(self, key):
        self._layout_cache.clear()
        self.force_paint = True

    def on_cover(self, key, data):
        if key != self.track_key:
            return
        img = QImage.fromData(data)
        if img.isNull():
            return
        self.cover_img = img
        pal = palette_from_cover(img)
        if pal:
            self.accent = pal
        self.force_paint = True

    def on_beat(self, strength):
        if self.cfg.get("beat", True):
            self.beat_t, self.beat_k = self.clock(), strength

    def beat_pulse(self):
        return self.beat_k * math.exp(-(self.clock() - self.beat_t) * 7.0)

    def toast(self, text):
        self.toast_text = text
        self.toast_until = self.clock() + 2.0

    def current_index(self, pos):
        return bisect.bisect_right(self.times, pos) - 1

    def current_text(self):
        if self.state == "ok" and self.cur and self.lines:
            return self.lines[self.cur["idx"]].text
        return ""

    # ---- couleurs ----------------------------------------------------------
    def colors(self):
        if self.cfg.get("color") == "white":
            return [QColor(c) for c in WHITE_PALETTE]
        return self.accent

    def fill_brush(self, x0, roww, chorus):
        cols = self.colors()
        if self.cfg.get("color") == "white":
            return QBrush(cols[0])
        # coeur des lettres plus clair que le halo : effet neon
        g = QLinearGradient(QPointF(x0, 0), QPointF(x0 + max(roww, 1), 0))
        white = QColor(255, 255, 255)
        # degrade calcule en OKLab (pas de milieu grisatre) ; les couleurs sont deja
        # a la bonne clarte, donc on ne les delave presque plus avec du blanc
        key = tuple((c.red(), c.green(), c.blue()) for c in cols)
        for pos, rgb in cover_colors.ramp(key):
            g.setColorAt(pos, mix(QColor(*rgb), white, 0.26 if chorus else 0.12))
        return QBrush(g)

    def outline_pen(self):
        if self.cfg.get("color") == "white":
            pen = QPen(QColor(0, 0, 0, 105), 3.0)
        else:
            pen = QPen(QColor(0, 0, 0, 170), 4.5)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return pen

    def glow_pens(self, boost):
        """Halo autour des lettres (blanc doux, ou couleur de l'album)."""
        if self.cfg.get("color") == "white":
            c, base = QColor(255, 255, 255), 55
        else:
            c, base = self.accent[1], 65
        pen = QPen(QColor(c.red(), c.green(), c.blue(), int(clamp(base + 150 * boost, 0, 255))), 10 + 8 * boost)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return [pen]

    # ---- polices et mise en page -------------------------------------------
    def main_font(self):
        f = QFont(family_or_default(self.cfg.get("font", DEFAULTS["font"])), 1)
        f.setPixelSize(int(34 * self.cfg["scale"]))
        f.setWeight(QFont.Weight.Black)
        return f

    def small_font(self, k=0.5, italic=True):
        f = QFont(self.main_font())
        f.setPixelSize(max(9, int(f.pixelSize() * k)))
        f.setWeight(QFont.Weight.DemiBold)
        f.setItalic(italic)
        return f

    def label_font(self):
        f = QFont("Segoe UI Variable Text", 1)
        f.setPixelSize(int(14 * self.cfg["scale"]))
        f.setWeight(QFont.Weight.Bold)
        return f

    def label_height(self):
        return QFontMetricsF(self.label_font()).height() * 1.05

    def show_translation(self, line):
        return self.cfg.get("translation", True) and bool(line.translation)

    def layout(self, text, font, maxw):
        key = (text, font.family(), font.pixelSize(), int(maxw))
        if key in self._layout_cache:
            return self._layout_cache[key]
        fm = QFontMetricsF(font)
        space = fm.horizontalAdvance(" ")
        rows, row, x, c = [], [], 0.0, 0
        for word in text.split():
            w = fm.horizontalAdvance(word)
            if row and x + w > maxw:
                rows.append((row, x - space))
                row, x = [], 0.0
            row.append((word, x, w, c))
            x += w + space
            c += len(word) + 1
        if row:
            rows.append((row, x - space))
        res = (rows, fm.height() * 1.05, fm.ascent())
        self._layout_cache[key] = res
        return res

    def block_size(self, line, maxw):
        """Taille (non zoomee) du bloc : nom du chanteur + lignes + traduction + choeur."""
        font = self.main_font()
        rows, lh, _ = self.layout(line.text, font, maxw)
        w = max(rw for _, rw in rows)
        h = lh * len(rows) + (self.label_height() if line.singer else 0)
        if self.show_translation(line):
            tf = self.small_font(0.5)
            tw = QFontMetricsF(tf).horizontalAdvance(line.translation)
            w = max(w, min(tw, maxw * 1.2))
            h += QFontMetricsF(tf).height() * 1.1
        if line.adlib:
            w += QFontMetricsF(self.small_font(0.6)).horizontalAdvance(f"({line.adlib})") + 12
        return w, h

    def column_mode(self):
        return self.cfg.get("mode") in ("classic", "typewriter")

    def stacked(self):
        """Mode Edit : rangees de tailles differentes, une seule en couleur."""
        return self.cfg.get("mode") == "edit" and self.cfg.get("stack", True)

    @staticmethod
    def row_scales(rows):
        """-> (rangee vedette, taille de chaque rangee). La vedette est celle du mot le plus
        long ; les autres rapetissent en s'en eloignant."""
        hero = max(range(len(rows)), key=lambda r: (max(len(w[0].strip(",.!?;:")) for w in rows[r][0]), -r))
        return hero, [1.0 if r == hero else max(0.46, 0.64 - 0.12 * (abs(r - hero) - 1)) for r in range(len(rows))]

    # ---- placement : mode Edit (au hasard, moitie haute) --------------------
    def place_line(self, line, avoid):
        if self.column_mode():
            return self.column_place(line)
        W, H = self.width(), self.height()
        s = self.cfg["scale"]
        rng = self.rng
        margin = 26 * s
        top_limit = H * UPPER
        chorus = getattr(line, "chorus", False)
        best = None
        for attempt in range(200):
            if line.text:
                n = len(line.text)
                mul = rng.uniform(0.95, 1.1) * (1.35 if n < 14 else 1.15 if n < 26 else 1.0)
                if chorus:
                    mul *= 1.22
                if attempt >= 100:  # pas de place parfaite : on reduit plutot que d'empieter
                    mul *= 0.78 if attempt < 150 else 0.62
                if self.stacked():  # mots empiles : rangees courtes, bloc un peu plus gros
                    mul *= 1.45
                    maxw = rng.choice([0.11, 0.14, 0.18, 0.22]) * W / mul
                else:
                    maxw = rng.choice([0.18, 0.24, 0.30, 0.36]) * W / mul
                bw, bh = self.block_size(line, maxw)
                bw, bh = bw * mul, bh * mul
            else:
                mul, maxw, bw, bh = 1.0, 0, 90 * s, 34 * s
            room = top_limit - margin - bh
            if bw > W - 2 * margin or room < 0:
                continue
            y = margin + room * (rng.random() ** 1.6)
            r = QRectF(rng.uniform(margin, W - margin - bw), y, bw, bh)
            padded = r.adjusted(-20 * s, -14 * s, 20 * s, 14 * s)
            score = sum(area(padded.intersected(z)) for z in self.zones) / (bw * bh) * 10
            for a in avoid:
                score += area(padded.adjusted(-30 * s, -30 * s, 30 * s, 30 * s).intersected(a)) / (bw * bh) * 5
                if abs(r.center().x() - a.center().x()) < W * 0.18 and abs(r.center().y() - a.center().y()) < H * 0.15:
                    score += 0.6
            card = self.card_rect()
            if self.card_visible() and card is not None:
                score += area(padded.intersected(card)) / (bw * bh) * 5
            if best is None or score < best[0]:
                best = (score, r, mul, maxw)
            if score == 0:
                break
        if best is None:
            r, mul, maxw = QRectF(margin, margin, 300 * s, 60 * s), 1.0, W * 0.3
        else:
            _, r, mul, maxw = best
        cx = r.center().x()
        align = "left" if cx < W / 3 else "right" if cx > 2 * W / 3 else "center"
        ax = {"left": r.left(), "right": r.right(), "center": cx}[align]
        if line.adlib and align == "right":
            ax -= QFontMetricsF(self.small_font(0.6)).horizontalAdvance(f"({line.adlib})") * mul + 12
        enter = "pop" if chorus else rng.choice(["slide", "slide", "pop", "drop"])
        direction = {"left": (-1, 0), "right": (1, 0)}.get(align, (0, -1))
        return SimpleNamespace(rect=r, ax=ax, cy=r.center().y(), align=align, mul=mul, maxw=maxw,
                               rot=rng.choice([-4, -3, -2, -1, 0, 0, 1, 2, 3, 4]),
                               enter=enter, dir=direction, chorus=chorus,
                               tilt={"left": 1, "right": -1}.get(align, 0) * rng.uniform(26, 34))

    # ---- placement : modes Classique / Machine a ecrire ---------------------
    def column_band(self):
        """Bande en haut de l'ecran (gauche / centre / droite) ou defilent les lignes."""
        if self._band is not None:
            return self._band
        W, H = self.width(), self.height()
        s = self.cfg["scale"]
        m = 36 * s
        lh = QFontMetricsF(self.main_font()).height() * 1.05
        band_h = lh * 3.6
        mw = W * 0.36
        pos = self.cfg.get("position", "left")
        x = {"left": m, "right": W - m - mw}.get(pos, (W - mw) / 2)
        best = QRectF(x, m, mw, band_h)
        y = m
        while y + band_h <= H * UPPER + lh:  # premiere hauteur libre (hors zones du jeu)
            r = QRectF(x, y, mw, band_h)
            if not any(r.intersects(z) for z in self.zones):
                best = r
                break
            y += 12 * s
        self._band = best
        return best

    def column_place(self, line):
        band = self.column_band()
        pos = self.cfg.get("position", "left")
        chorus = getattr(line, "chorus", False)
        mul = 1.12 if (chorus and self.cfg.get("mode") == "classic") else 1.0
        ax = {"left": band.left(), "right": band.right()}.get(pos, band.center().x())
        return SimpleNamespace(rect=band, ax=ax, cy=band.center().y(), align=pos, mul=mul,
                               maxw=band.width() / mul, rot=0, enter="column", dir=(0, 1), chorus=chorus)

    def entry_height(self, e):
        line = self.lines[e["idx"]]
        if not line.text:
            return 30 * self.cfg["scale"]
        return self.block_size(line, e["place"].maxw)[1] * e["place"].mul

    def advance(self, idx, now):
        """La chanson passe a la ligne idx."""
        old = self.cur
        if self.prev:
            self.exiting.append((self.prev, now))
        self.prev = None
        if old:
            if self.lines[old["idx"]].text and idx > old["idx"]:
                self.prev = dict(old, prev_since=now)
            else:
                self.exiting.append((old, now))
        if idx < 0 or idx >= len(self.lines):
            self.cur = None
            return
        avoid = [self.prev["place"].rect] if self.prev else []
        self.cur = {"idx": idx, "place": self.place_line(self.lines[idx], avoid), "since": now}
        self.maybe_flash(idx)

    # ---- titre du morceau en geant ----------------------------------------
    def maybe_flash(self, idx):
        """Le chanteur dit le titre du morceau : on l'affiche en tres grand."""
        line = self.lines[idx]
        mode = self.cfg.get("title_drop", "always")
        if mode == "never" or self.egg or not getattr(line, "title_drop", False):
            return
        in_game = self.profile_key != "bureau"
        if in_game and mode == "desktop":
            return
        i, n = line.title_span
        words = line.text.split()
        text = " ".join(words[i:i + n]).strip(",.!?;:…\"'()").upper()
        cstart = sum(len(w) + 1 for w in words[:i])
        start = line.chars[cstart][0] if (line.chars and cstart < len(line.chars)) else line.time
        place = self.flash_place(text, in_game)
        if place is None:
            return
        font, rect = place
        self.flash = {"text": text, "font": font, "rect": rect, "start": start,
                      "end": max(self.sung_end(idx) + 1.2, start + 2.2),
                      "rot": self.rng.choice([-3, -2, -1, 1, 2, 3])}

    def flash_place(self, text, in_game):
        """-> (police, rectangle). Hors jeu : presque tout l'ecran. En jeu : le plus grand
        possible dans un espace libre de la moitie haute (jamais sur une zone du jeu)."""
        W, H = self.width(), self.height()
        base = self.main_font()
        probe = QFont(base)
        probe.setPixelSize(100)
        fm = QFontMetricsF(probe)
        w100, h100 = max(1.0, fm.horizontalAdvance(text)), fm.height()

        def font_for(px):
            f = QFont(base)
            f.setPixelSize(int(px))
            return f

        if not in_game:
            px = min(H * 0.26, 100 * W * 0.84 / w100)
            w, h = w100 * px / 100, h100 * px / 100
            return font_for(px), QRectF((W - w) / 2, H * 0.58 - h / 2, w, h)
        m = 24 * self.cfg["scale"]
        busy = [e["place"].rect for e in (self.cur, self.prev) if e]
        for frac in (0.62, 0.5, 0.42, 0.34, 0.27, 0.21):
            px = min(H * 0.15, 100 * W * frac / w100)
            if px < base.pixelSize() * 1.5:
                break  # pas plus grand que les paroles : sans interet
            w, h = w100 * px / 100, h100 * px / 100
            xs = sorted((m + k * (W - 2 * m - w) / 12 for k in range(13)), key=lambda x: abs(x + w / 2 - W / 2))
            y = m
            while y + h <= H * UPPER:
                for x in xs:
                    r = QRectF(x, y, w, h)
                    pad = r.adjusted(-12, -8, 12, 8)
                    if not any(pad.intersects(z) for z in self.zones) and not any(pad.intersects(b) for b in busy):
                        return font_for(px), r
                y += H * 0.03
        return None

    def draw_flash(self, p, pos):
        f = self.flash
        if not f or pos < f["start"]:
            return
        k = clamp((pos - f["start"]) / 0.38)
        out = clamp((f["end"] - pos) / 0.6)
        a = ease_out(clamp(k * 1.6)) * out
        if a <= 0.003:
            return
        sc = lerp(1.4, 1.0, ease_out_back(k)) * (1 + 0.05 * self.beat_pulse()) * (1 + 0.05 * (1 - out))
        font = f["font"]
        fm = QFontMetricsF(font)
        tw = fm.horizontalAdvance(f["text"])
        c = f["rect"].center()
        p.save()
        p.setOpacity(clamp(self.alpha * a * 0.95))
        p.translate(c)
        p.rotate(f["rot"])
        p.scale(sc, sc)
        x, y = -tw / 2, fm.ascent() - fm.height() / 2
        self.draw_text_fx(p, f["text"], font, x, y, self.fill_brush(x, tw, True), glow=1.5)
        p.restore()

    def is_animating(self, now, pos):
        """Faux quand l'image est figee : inutile de redessiner (moins de charge en jeu)."""
        if self.exiting or self.particles or self.flash:
            return True
        if self.egg and self.egg.busy(now, pos):
            return True
        if now < self.toast_until or now < self.zones_until or self.card_visible():
            return True
        if self.beat_pulse() > 0.01:
            return True
        if self.state != "ok" or not self.lines:
            return False
        typewriter = self.cfg.get("mode") == "typewriter"
        for e in (self.cur, self.prev):
            if not e:
                continue
            if now - e["since"] < 0.8 or now - e.get("prev_since", -99) < 0.8:
                return True
            line = self.lines[e["idx"]]
            if not line.text:
                if e is self.cur:
                    return True  # petits points animes
                continue
            fade = self.done_fade(e["idx"], pos)
            if 0 < fade < 1:
                return True
            if e is self.cur and fade > 0:
                if typewriter:
                    return True  # curseur qui clignote
                if pos < max(self.sung_end(e["idx"]), line.time + len(line.text.split()) * 0.06) + 0.8:
                    return True
        return False

    # ---- animation -------------------------------------------------------
    def tick(self, dt=None):
        now = self.clock()
        if dt is None:
            dt = min(0.1, now - self.last_tick)
        self.last_tick = now

        if self.state == "ok" and self.lines:
            idx = self.current_index(self.position())
            if self.cur is None or idx != self.cur["idx"]:
                self.advance(idx, now)
        self.exiting = [(e, t) for e, t in self.exiting if now - t < 0.45]
        pos_now = self.position()
        if self.flash and (pos_now > self.flash["end"] or pos_now < self.flash["start"] - 6):
            self.flash = None

        alive = []
        for pt in self.particles:
            pt["life"] -= dt
            if pt["life"] > 0:
                pt["x"] += pt["vx"] * dt
                pt["y"] += pt["vy"] * dt
                pt["vy"] -= 20 * dt
                pt["vx"] *= 0.97
                alive.append(pt)
        self.particles = alive
        if self.egg:
            self.egg.tick(now, dt, pos_now)

        toast_on = now < self.toast_until or now < self.zones_until
        since = now - self.track_changed_at
        show = (
            not self.user_hidden and self.track is not None and self.playing
            and (self.state == "ok" or since < 4.0)
        ) or toast_on
        target = 1.0 if show else 0.0
        self.alpha += (target - self.alpha) * (1 - math.exp(-dt * (8 if show else 4)))

        # On ne redessine que les zones utiles (sinon tout l'ecran 60x/s = plus lourd).
        region = QRegion()
        if self.alpha > 0.003:
            pad = int(120 * self.cfg["scale"])
            if self.column_mode():
                b = self.column_band()
                region = QRegion(b.toAlignedRect().adjusted(-pad, -int(b.height()), pad, int(b.height())))
            else:
                for e in self.visible_entries():
                    region = region.united(QRegion(e["place"].rect.toAlignedRect().adjusted(-pad, -pad, pad, pad)))
            card = self.card_rect()
            if card is not None and (self.card_visible() or toast_on):
                region = region.united(QRegion(card.toAlignedRect().adjusted(-40, -10, 40, 70)))
            for pt in self.particles:
                region = region.united(QRegion(int(pt["x"]) - 8, int(pt["y"]) - 8, 16, 16))
            if self.flash:
                g = int(self.flash["font"].pixelSize() * 0.9) + 40
                region = region.united(QRegion(self.flash["rect"].toAlignedRect().adjusted(-g, -g, g, g)))
            if now < self.zones_until or (self.egg and self.egg.busy(now, pos_now)):
                region = QRegion(self.rect())  # feux d'artifice : partout sur l'ecran
        dirty = region.united(self.last_region)
        # On ne redessine que si quelque chose bouge (texte fige = aucun travail).
        animating = abs(target - self.alpha) > 0.002 or self.is_animating(now, pos_now)
        if not dirty.isEmpty() and (animating or self.was_animating or self.force_paint
                                    or region != self.last_region):
            self.update(dirty)
        self.was_animating = animating
        self.force_paint = False
        self.last_region = region

    def visible_entries(self):
        out = [e for e, _ in self.exiting]
        if self.prev:
            out.append(self.prev)
        if self.cur:
            out.append(self.cur)
        return out

    # ---- dessin ----------------------------------------------------------
    def paintEvent(self, ev):
        if self.alpha < 0.003:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        now = self.clock()
        pos = self.position()

        if now < self.zones_until:
            self.draw_zones(p)

        if self.state == "ok" and self.lines:
            if self.column_mode():
                self.draw_column(p, now, pos)
            else:
                for e, t in self.exiting:
                    k = clamp((now - t) / 0.4)
                    a = PREV_ALPHA * self.done_fade(e["idx"], pos) * (1 - k)
                    self.draw_entry(p, e, a, 0.88 - 0.06 * k, 0, -14 * k, "prev", pos)
                if self.prev:
                    k = ease_out(clamp((now - self.prev["prev_since"]) / 0.3))
                    a = lerp(1.0, PREV_ALPHA, k) * self.done_fade(self.prev["idx"], pos)
                    self.draw_entry(p, self.prev, a, lerp(1.0, 0.88, k), 0, 0, "prev", pos)
                if self.cur:
                    self.draw_current(p, self.cur, now, pos)

            self.draw_flash(p, pos)

        self.draw_particles(p)
        self.draw_card(p)
        if self.egg:
            self.egg.draw(p, now, pos)
        p.end()

    def sung_end(self, idx):
        line = self.lines[idx]
        if line.end:
            return line.end
        nxt = self.times[idx + 1] if idx + 1 < len(self.times) else line.time + 6.0
        return min(nxt, line.time + max(2.0, len(line.text) * 0.09))

    def done_fade(self, idx, pos):
        """1 tant que la ligne est fraiche, puis 0 en 0,5 s, 3 s apres la fin du chant."""
        if not self.lines[idx].text:
            return 1.0
        return clamp(1 - (pos - self.sung_end(idx) - HIDE_AFTER) / 0.5)

    def beat_scale(self, chorus):
        """Pulsation : le texte grossit un peu sur le beat (rien d'autre)."""
        return 1 + (0.09 if chorus else 0.05) * self.beat_pulse()

    def draw_current(self, p, e, now, pos):
        pl = e["place"]
        k = clamp((now - e["since"]) / (0.55 if pl.chorus else 0.45))
        a, sc, ox, oy = ease_out(k) * self.done_fade(e["idx"], pos), 1.0, 0.0, 0.0
        d = 90 * self.cfg["scale"]
        if pl.enter == "slide":
            ox, oy = pl.dir[0] * d * (1 - ease_out(k)), pl.dir[1] * d * (1 - ease_out(k))
        elif pl.enter == "pop":
            sc = lerp(1.7 if pl.chorus else 1.4, 1.0, ease_out_back(k))
        else:
            oy = -60 * self.cfg["scale"] * (1 - ease_out_back(k))
        sc *= self.beat_scale(pl.chorus)
        self.draw_entry(p, e, a, sc, ox, oy, "current", pos)

    def draw_column(self, p, now, pos):
        """Modes Classique / Machine a ecrire : la ligne en cours en bas de la bande,
        la precedente remonte au-dessus en plus petit."""
        band = self.column_band()
        s = self.cfg["scale"]
        gap = 8 * s
        cur_y = band.top() + band.height() * 0.64
        hc = self.entry_height(self.cur) if self.cur else 0
        for e, t in self.exiting:
            k = clamp((now - t) / 0.4)
            y = band.top() + band.height() * 0.18 - 30 * s * k
            a = PREV_ALPHA * self.done_fade(e["idx"], pos) * (1 - k)
            self.draw_entry(p, e, a, 0.72, 0, 0, "prev", pos, at=(e["place"].ax, y))
        if self.prev:
            k = ease_out(clamp((now - self.prev["prev_since"]) / 0.4))
            hp = self.entry_height(self.prev)
            target = cur_y - hc / 2 - hp * 0.72 / 2 - gap
            y = lerp(cur_y, target, k)
            a = lerp(1.0, PREV_ALPHA, k) * self.done_fade(self.prev["idx"], pos)
            self.draw_entry(p, self.prev, a, lerp(1.0, 0.72, k), 0, 0, "prev", pos,
                            at=(self.prev["place"].ax, y))
        if self.cur:
            pl = self.cur["place"]
            k = ease_out(clamp((now - self.cur["since"]) / 0.4))
            typewriter = self.cfg.get("mode") == "typewriter"
            y = cur_y + (0 if typewriter else (1 - k) * 28 * s)
            a = (1.0 if typewriter else k) * self.done_fade(self.cur["idx"], pos)
            self.draw_entry(p, self.cur, a, self.beat_scale(pl.chorus), 0, 0, "current", pos, at=(pl.ax, y))

    def draw_entry(self, p, e, alpha, scale_k, ox, oy, mode, pos, at=None):
        if alpha <= 0.003:
            return
        line = self.lines[e["idx"]]
        if self.egg:
            alpha *= self.egg.line_alpha(e["idx"], pos, e["place"].rect)
            if alpha <= 0.003:
                return
        pl = e["place"]
        x, y = at if at else (pl.ax, pl.cy)
        p.save()
        p.setOpacity(clamp(self.alpha * alpha))
        p.translate(x + ox, y + oy)
        tilt = getattr(pl, "tilt", 0) if self.cfg.get("tilt", True) else 0
        if tilt and line.text:
            # effet 3D : le texte pivote comme sur un mur, le bord de l'ecran devant, le centre au fond
            ang = math.radians(abs(tilt))
            depth = max(120.0, pl.rect.width()) * 2.1  # camera proche : la perspective se voit meme sur une ligne courte
            k = math.copysign(math.sin(ang) / depth, tilt)
            p.setTransform(QTransform(math.cos(ang), 0, k, 0, 1, 0, 0, 0, 1), True)
        p.rotate(pl.rot)
        p.scale(pl.mul * scale_k, pl.mul * scale_k)
        if not line.text:
            if mode == "current":
                self.draw_dots(p, pl.align)
        else:
            self.draw_block(p, line, pl, mode, pos)
        p.restore()

    def draw_dots(self, p, align):
        s = self.cfg["scale"]
        t = self.clock()
        r, step = 6 * s, 22 * s
        total = step * 2
        x0 = {"left": r, "right": -total - r}.get(align, -total / 2)
        p.setPen(Qt.PenStyle.NoPen)
        beat = self.beat_pulse()
        cols = self.colors()
        for k in range(3):
            pulse = 0.5 + 0.5 * math.sin(t * 4 - k * 0.9)
            c = QColor(cols[k])
            c.setAlphaF(clamp(0.35 + 0.65 * pulse))
            p.setBrush(c)
            rr = r * (0.8 + 0.35 * pulse + 0.3 * beat)
            p.drawEllipse(QPointF(x0 + k * step, -4 * s * pulse), rr, rr)

    def typed_times(self, line, idx):
        """Moment d'apparition de chaque lettre (machine a ecrire)."""
        n = len(line.text)
        if line.chars and len(line.chars) == n:
            return [c[0] for c in line.chars]
        nxt = self.times[idx + 1] if idx + 1 < len(self.times) else line.time + 4.0
        d = min((nxt - line.time) * 0.9, 0.35 + 0.045 * n)
        return [line.time + d * i / max(1, n) for i in range(n)]

    # ---- vrai glow : halo flou (gaussien) derriere les lettres ----------------
    def glow_color(self):
        if self.cfg.get("color") == "white":
            return QColor(236, 244, 255)
        # halo bien colore (comme un neon) : teinte de la pochette, saturation renforcee
        c = self.accent[0]  # la couleur la plus marquante de la pochette
        h, s, v = c.hsvHueF(), c.hsvSaturationF(), c.valueF()
        if s < 0.10:  # pochette grise : halo blanc
            return QColor(236, 244, 255)
        return QColor.fromHsvF(max(h, 0), min(1.0, s * 1.25 + 0.1), 1.0)

    def base_glow(self):
        return 0.85 if self.cfg.get("color") == "white" else 1.0

    def halo(self, text, font, color, radius, strength):
        """Image floutee du texte (calculee une fois puis gardee en memoire)."""
        key = (text, font.family(), font.pixelSize(), str(font.weight()), font.italic(),
               color.rgb(), int(radius * 10), int(strength * 10))
        hit = self._halo_cache.get(key)
        if hit is not None:
            self._halo_cache.move_to_end(key)
            return hit
        k = 0.5  # le flou est calcule en demi-resolution : plus leger, invisible a l'oeil
        f2 = QFont(font)
        f2.setPixelSize(max(4, int(round(font.pixelSize() * k))))
        r2 = max(0.8, radius * k)
        fm = QFontMetricsF(f2)
        pad = int(r2 * 3) + 2
        W = int(fm.horizontalAdvance(text)) + 2 * pad + 4
        H = int(fm.height()) + 2 * pad + 2
        img = QImage(W, H, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        qp = QPainter(img)
        qp.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addText(QPointF(pad, pad + fm.ascent()), f2, text)
        qp.fillPath(path, QColor(255, 255, 255))
        qp.end()
        raw = np.frombuffer(img.constBits().asstring(img.sizeInBytes()), dtype=np.uint8)
        a = raw.reshape(H, img.bytesPerLine())[:, :W * 4].reshape(H, W, 4)[:, :, 3].astype(np.float32)
        a = np.clip(gaussian_blur(a, r2) * strength, 0, 255)
        out = np.empty((H, W, 4), dtype=np.uint8)
        out[..., 0] = a * (color.blue() / 255)
        out[..., 1] = a * (color.green() / 255)
        out[..., 2] = a * (color.red() / 255)
        out[..., 3] = a
        q = QImage(out.tobytes(), W, H, W * 4, QImage.Format.Format_ARGB32_Premultiplied).copy()
        entry = (q, pad / k, fm.ascent() / k, W / k, H / k)
        self._halo_cache[key] = entry
        if len(self._halo_cache) > 700:
            self._halo_cache.popitem(last=False)
        return entry

    def blit_halo(self, p, text, font, x, base_y, color, radius, strength, alpha, dy=0.0):
        if alpha <= 0.01 or not text.strip():
            return
        img, pad, asc, w, h = self.halo(text, font, color, radius, strength)
        p.save()
        p.setOpacity(p.opacity() * clamp(alpha))
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.drawImage(QRectF(x - pad, base_y - asc - pad + dy, w, h), img)
        p.restore()

    def draw_text_fx(self, p, text, font, x, base_y, brush, glow=1.0, shadow=1.0, path=None):
        """Texte lumineux : ombre douce (lisibilite sur le jeu) + halo large + halo serre + lettres."""
        px = min(font.pixelSize(), 110)  # texte geant : le halo ne grossit pas a l'infini
        white = self.cfg.get("color") == "white"
        if shadow > 0:
            # ombre large et douce (lisible meme sur un decor clair) + ombre serree sous les lettres
            self.blit_halo(p, text, font, x, base_y, QColor(0, 0, 0), px * 0.32, 1.2, 0.32 * shadow, px * 0.04)
            self.blit_halo(p, text, font, x, base_y, QColor(0, 0, 0), px * 0.09, 2.0, 0.7 * shadow, px * 0.05)
        if glow > 0:
            gc = self.glow_color()
            self.blit_halo(p, text, font, x, base_y, gc, px * 0.5, 1.7, 0.55 * glow)
            self.blit_halo(p, text, font, x, base_y, gc, px * 0.14, 1.8,
                           min(1.0, (0.65 if white else 0.5) * glow))
        if path is None:
            path = QPainterPath()
            path.addText(QPointF(x, base_y), font, text)
        p.fillPath(path, brush)

    def draw_block(self, p, line, pl, mode, pos):
        font = self.main_font()
        rows, lh, ascent = self.layout(line.text, font, pl.maxw)
        label_h = self.label_height() if line.singer else 0
        tf = self.small_font(0.5)
        trans_h = QFontMetricsF(tf).height() * 1.1 if self.show_translation(line) else 0
        stack = self.stacked() and len(rows) > 1
        hero, scales = self.row_scales(rows) if stack else (-1, [1.0] * len(rows))
        rows_h = lh * sum(scales)
        h = rows_h + label_h + trans_h
        style = self.cfg["style"]
        align = pl.align
        current = mode == "current"
        cols = self.colors()
        base_glow = self.base_glow()
        p.translate(0, -h / 2)
        if line.singer:
            lf = self.label_font()
            fm = QFontMetricsF(lf)
            label = line.singer.upper()
            lw = fm.horizontalAdvance(label)
            lx = {"left": 0, "right": -lw}.get(align, -lw / 2)
            self.draw_text_fx(p, label, lf, lx, fm.ascent(), QBrush(cols[0]), glow=0.35 if current else 0)
            p.translate(0, label_h)

        last_row_end = (0.0, 0.0)
        if current and self.cfg.get("mode") == "typewriter":
            last_row_end = self.draw_typed(p, line, rows, lh, ascent, font, align, pos, pl.chorus)
        else:
            timed = current and bool(line.chars)
            meta = getattr(line, "word_meta", {}) or {}
            chorus = pl.chorus
            word_i = 0
            lit = []
            white = self.cfg.get("color") == "white"
            row_top = 0.0
            for r, (row, roww) in enumerate(rows):
                x0 = {"left": 0, "right": -roww}.get(align, -roww / 2)
                rs = scales[r]
                p.save()  # chaque rangee a sa taille (autour du point d'ancrage : l'alignement tient)
                p.translate(0, row_top)
                p.scale(rs, rs)
                base_y = ascent
                plain = stack and r != hero  # rangee secondaire : blanche, peu de halo
                brush = QBrush(QColor(255, 255, 255, 215 if white else 245)) if plain \
                    else self.fill_brush(x0, roww, chorus or stack)
                for word, wx, ww, cstart in row:
                    x = x0 + wx
                    if not current:
                        self.draw_text_fx(p, word, font, x, base_y, QBrush(QColor(255, 255, 255, 235)), glow=0.12)
                        word_i += 1
                        continue
                    sc, dx, dy, glow_k, sx = held_fx(meta.get(cstart), pos) if timed else (1, 0, 0, 0, 1)
                    glow = base_glow * (1 + 1.4 * glow_k) + (0.25 if chorus else 0)
                    if plain:
                        glow *= 0.4
                    elif stack:
                        glow *= 1.25
                    cxw, cyw = x + ww / 2, base_y - ascent * 0.35
                    p.save()
                    if sc != 1 or dx or dy or sx != 1:
                        p.translate(cxw + dx, cyw + dy)
                        p.scale(sc * sx, sc)
                        p.translate(-cxw, -cyw)
                    if self.cfg.get("particles", True) and glow_k > 0.15 \
                            and pos <= meta.get(cstart, (0, 0, 0))[1]:
                        self.spawn_particles(p, x, base_y - ascent, ww, ascent, glow_k)
                    if style == "kinetic":
                        start = line.chars[cstart][0] if (timed and cstart < len(line.chars)) \
                            else line.time + word_i * 0.06
                        k = clamp((pos - start) / 0.3)
                        if k <= 0:
                            p.restore()
                            word_i += 1
                            continue
                        e = ease_out_back(k)
                        rot0 = ((cstart * 37) % 25) - 12
                        p.translate(cxw, cyw)
                        p.rotate(rot0 * (1 - e))
                        p.scale(lerp(1.45, 1.0, e), lerp(1.45, 1.0, e))
                        p.translate(-cxw, -cyw + 22 * (1 - e))
                        p.setOpacity(p.opacity() * ease_out(clamp(k * 1.7)))
                        self.draw_text_fx(p, word, font, x, base_y, brush, glow)
                    elif style == "simple" or not timed:
                        self.draw_text_fx(p, word, font, x, base_y, brush, glow)
                    else:  # karaoke : lettres grises ici ; la partie chantee s'allume apres la ligne
                        wf = self.word_fill(line, cstart, len(word), pos)
                        self.draw_text_fx(p, word, font, x, base_y, QBrush(QColor(255, 255, 255, 105)), glow=0)
                        if wf > 0:
                            lit.append((word, x, ww, wf, sc, dx, dy, sx, glow, cxw, cyw))
                    p.restore()
                    word_i += 1
                if style == "karaoke" and timed and lit:
                    # Un seul decoupage par ligne, a l'endroit ou en est le chant :
                    # le halo coule d'un mot a l'autre, sans bandes.
                    m = font.pixelSize()
                    _, lx, lw_, lwf = lit[-1][:4]
                    fill_x = lx + lw_ * lwf
                    left, top = x0 - 2 * m, base_y - ascent - 2 * m
                    lw_img, lh_img = fill_x - left + m, lh + 4 * m
                    layer = QImage(int(lw_img) + 2, int(lh_img) + 2, QImage.Format.Format_ARGB32_Premultiplied)
                    layer.fill(Qt.GlobalColor.transparent)
                    lp = QPainter(layer)
                    lp.setRenderHint(QPainter.RenderHint.Antialiasing)
                    lp.translate(-left, -top)
                    for word, x, ww, wf, sc, dx, dy, sx, glow, cxw, cyw in lit:
                        lp.save()
                        if sc != 1 or dx or dy or sx != 1:
                            lp.translate(cxw + dx, cyw + dy)
                            lp.scale(sc * sx, sc)
                            lp.translate(-cxw, -cyw)
                        self.draw_text_fx(lp, word, font, x, base_y, brush, glow, shadow=0)
                        lp.restore()
                    # fondu doux a l'endroit ou en est le chant (pas de coupure nette)
                    lp.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
                    fade = QLinearGradient(QPointF(fill_x - m * 0.08, 0), QPointF(fill_x + m * 0.22, 0))
                    fade.setColorAt(0, QColor(0, 0, 0, 255))
                    fade.setColorAt(1, QColor(0, 0, 0, 0))
                    lp.fillRect(QRectF(left, top, lw_img + 2, lh_img + 2), QBrush(fade))
                    lp.end()
                    p.drawImage(QPointF(left, top), layer)
                lit = []
                p.restore()
                last_row_end = ((x0 + roww) * rs, row_top + ascent * rs)
                row_top += lh * rs

        # choeur "(yeah)" : petit, en italique, a cote de la fin de ligne
        if line.adlib and current:
            ad_t = line.adlib_time if line.adlib_time is not None else line.time
            if self.cfg.get("mode") == "typewriter":  # attend que la ligne soit ecrite
                ad_t = max(ad_t, self.typed_times(line, self.cur["idx"])[-1])
            k = clamp((pos - ad_t) / 0.3) if (line.chars or self.cfg.get("mode") == "typewriter") else 1.0
            if k > 0:
                af = self.small_font(0.6)
                ex, ey = last_row_end
                ox, oy = ex + 12, ey - lh * 0.45
                p.save()
                p.setOpacity(p.opacity() * 0.92 * ease_out(k))
                p.translate(ox, oy)
                p.rotate(-6)
                p.translate(-ox, -oy - 8 * (1 - ease_out(k)))
                self.draw_text_fx(p, f"({line.adlib})", af, ox, oy,
                                  QBrush(mix(cols[2], QColor(255, 255, 255), 0.45)), glow=0.5)
                p.restore()

        # traduction francaise sous la ligne
        if current and self.show_translation(line):
            fm = QFontMetricsF(tf)
            text = fm.elidedText(line.translation, Qt.TextElideMode.ElideRight, pl.maxw * 1.2)
            tw = fm.horizontalAdvance(text)
            tx = {"left": 0, "right": -tw}.get(align, -tw / 2)
            ty = rows_h + fm.ascent() + 2
            self.draw_text_fx(p, text, tf, tx, ty, QBrush(QColor(255, 255, 255, 205)), glow=0)

    def draw_typed(self, p, line, rows, lh, ascent, font, align, pos, chorus):
        """Machine a ecrire : seules les lettres deja chantees sont ecrites, + curseur."""
        times = self.typed_times(line, self.cur["idx"])
        fm = QFontMetricsF(font)
        glow = self.base_glow() + (0.25 if chorus else 0)
        cursor = None
        last_row_end = (0.0, 0.0)
        for r, (row, roww) in enumerate(rows):
            x0 = {"left": 0, "right": -roww}.get(align, -roww / 2)
            base_y = r * lh + ascent
            if cursor is None:
                cursor = (x0, base_y)
            brush = self.fill_brush(x0, roww, chorus)
            for word, wx, ww, cstart in row:
                vis = sum(1 for i in range(cstart, min(cstart + len(word), len(times))) if times[i] <= pos)
                if vis == 0:
                    continue
                sub = word[:vis]
                self.draw_text_fx(p, sub, font, x0 + wx, base_y, brush, glow)
                cursor = (x0 + wx + fm.horizontalAdvance(sub), base_y)
            last_row_end = (x0 + roww, base_y)
        typing = bool(times) and pos < times[-1] + 0.15
        if cursor and (typing or int(self.clock() * 2.4) % 2 == 0):
            cx, cy = cursor
            s = self.cfg["scale"]
            rect = QRectF(cx + 4 * s, cy - ascent * 0.8, 4 * s, ascent * 0.95)
            gc = self.glow_color()
            for grow, al in ((7 * s, 40), (3 * s, 90)):  # petit halo autour du curseur
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(gc.red(), gc.green(), gc.blue(), al))
                p.drawRoundedRect(rect.adjusted(-grow, -grow * 0.5, grow, grow * 0.5), grow, grow)
            p.setBrush(self.colors()[0])
            p.drawRoundedRect(rect, 1.5, 1.5)
        return last_row_end

    @staticmethod
    def word_fill(line, cstart, wlen, pos):
        seg = line.chars[cstart:cstart + wlen] if line.chars else None
        if not seg:
            return 1.0
        done = 0.0
        for a, b in seg:
            if pos >= b:
                done += 1
            elif pos > a:
                done += (pos - a) / (b - a)
        return done / len(seg)

    # ---- particules (mots tenus) -------------------------------------------
    def spawn_particles(self, p, x, y, w, h, k):
        if len(self.particles) > 160 or self.rng.random() > 0.35 + 0.5 * k:
            return
        tr = p.transform()
        cols = self.colors()
        for _ in range(1 + int(k * 2)):
            pt = tr.map(QPointF(x + self.rng.random() * w, y + self.rng.random() * h))
            self.particles.append({
                "x": pt.x(), "y": pt.y(),
                "vx": self.rng.uniform(-40, 40), "vy": self.rng.uniform(-70, -20),
                "life": self.rng.uniform(0.5, 1.0), "max": 1.0,
                "col": QColor(cols[self.rng.randrange(3)]),
                "size": self.rng.uniform(1.5, 3.5) * self.cfg["scale"],
            })

    def draw_particles(self, p):
        if not self.particles:
            return
        p.save()
        p.setPen(Qt.PenStyle.NoPen)
        for pt in self.particles:
            c = QColor(pt["col"])
            c.setAlphaF(clamp(pt["life"] / pt["max"]) * self.alpha)
            p.setBrush(c)
            p.drawEllipse(QPointF(pt["x"], pt["y"]), pt["size"], pt["size"])
        p.restore()

    # ---- carte pochette + titre (debut de morceau) --------------------------
    def card_visible(self):
        return self.cfg.get("card", True) and self.track is not None and \
            self.clock() - self.card_since < CARD_TIME

    def card_fonts(self):
        s = self.cfg["scale"]
        title = QFont("Segoe UI Variable Display", 1)
        title.setPixelSize(int(16 * s))
        title.setWeight(QFont.Weight.Bold)
        artist = QFont("Segoe UI Variable Text", 1)
        artist.setPixelSize(int(13 * s))
        badge = QFont("Segoe UI Variable Text", 1)
        badge.setPixelSize(max(8, int(10 * s)))
        badge.setWeight(QFont.Weight.Bold)
        return title, artist, badge

    def card_badge(self):
        if self.state == "ok":
            return "MOT À MOT" if self.word_sync else "LIGNE"
        return {"loading": "RECHERCHE...", "missing": "PAS DE PAROLES"}.get(self.state, "")

    def card_rect(self):
        s = self.cfg["scale"]
        tf, af, bf = self.card_fonts()
        t = self.track
        title = t.title if t else "FollowTheLyrics"
        artist = t.artist if t else ""
        tw = min(QFontMetricsF(tf).horizontalAdvance(title), 260 * s)
        aw = min(QFontMetricsF(af).horizontalAdvance(artist), 260 * s)
        bw = QFontMetricsF(bf).horizontalAdvance(self.card_badge()) + 12 * s
        w = 12 * s + 64 * s + 14 * s + max(tw, aw, bw) + 18 * s
        h = 88 * s
        W = self.width()
        m = 18 * s
        spots = [(m, m), (W - m - w, m), ((W - w) / 2, m)]
        band = None
        if self.column_mode():
            band = self.column_band()
            if self.cfg.get("position") == "left":
                spots = [(W - m - w, m), ((W - w) / 2, m), (m, m)]
        for x, y in spots:
            r = QRectF(x, y, w, h)
            if any(r.intersects(z) for z in self.zones):
                continue
            if band is not None and r.intersects(band):
                continue
            return r
        return QRectF(*spots[0], w, h)

    def draw_card(self, p):
        now = self.clock()
        toast = now < self.toast_until
        if not (self.card_visible() or toast):
            return
        s = self.cfg["scale"]
        rect = self.card_rect()
        tf, af, bf = self.card_fonts()
        p.save()
        if self.card_visible():
            t = now - self.card_since
            a = ease_out(clamp(t / 0.35)) * clamp((CARD_TIME - t) / 0.5)
            slide = (1 - ease_out(clamp(t / 0.35))) * 30 * s * (-1 if rect.center().x() < self.width() / 2 else 1)
            p.setOpacity(self.alpha * a)
            r = rect.translated(slide, 0)
            g = QLinearGradient(r.topLeft(), r.bottomRight())
            g.setColorAt(0, mix(QColor(14, 14, 20), self.accent[0], 0.22))
            g.setColorAt(1, QColor(12, 12, 18))
            p.setPen(QPen(QColor(self.accent[0].red(), self.accent[0].green(), self.accent[0].blue(), 110), 1.2))
            p.setBrush(QBrush(g))
            p.drawRoundedRect(r, 14 * s, 14 * s)
            cov = QRectF(r.left() + 12 * s, r.top() + 12 * s, 64 * s, 64 * s)
            if self.cover_img is not None:
                path = QPainterPath()
                path.addRoundedRect(cov, 9 * s, 9 * s)
                p.save()
                p.setClipPath(path)
                p.drawImage(cov, self.cover_img)
                p.restore()
            else:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(255, 255, 255, 25))
                p.drawRoundedRect(cov, 9 * s, 9 * s)
                p.setPen(QColor(255, 255, 255, 150))
                p.setFont(tf)
                p.drawText(cov, Qt.AlignmentFlag.AlignCenter, "♪")
            tx = cov.right() + 14 * s
            tr = self.track
            p.setFont(tf)
            p.setPen(QColor(255, 255, 255, 240))
            fm = QFontMetricsF(tf)
            p.drawText(QPointF(tx, r.top() + 14 * s + fm.ascent()),
                       fm.elidedText(tr.title if tr else "", Qt.TextElideMode.ElideRight, 260 * s))
            p.setFont(af)
            p.setPen(QColor(255, 255, 255, 170))
            afm = QFontMetricsF(af)
            p.drawText(QPointF(tx, r.top() + 14 * s + fm.height() + afm.ascent()),
                       afm.elidedText(tr.artist if tr else "", Qt.TextElideMode.ElideRight, 260 * s))
            badge = self.card_badge()
            if badge:
                bfm = QFontMetricsF(bf)
                br = QRectF(tx, r.bottom() - 12 * s - bfm.height() - 4 * s,
                            bfm.horizontalAdvance(badge) + 12 * s, bfm.height() + 4 * s)
                col = QColor(self.accent[0]) if (self.state == "ok" and self.word_sync) else QColor(180, 180, 190)
                p.setPen(QPen(col, 1))
                p.setBrush(QColor(col.red(), col.green(), col.blue(), 40))
                p.drawRoundedRect(br, br.height() / 2, br.height() / 2)
                p.setFont(bf)
                p.setPen(col)
                p.drawText(br, Qt.AlignmentFlag.AlignCenter, badge)
        if toast:
            p.setOpacity(1.0)
            fm = QFontMetricsF(af)
            tw = fm.horizontalAdvance(self.toast_text)
            r = QRectF(rect.left(), rect.bottom() + 8 * s, tw + 24 * s, fm.height() + 12 * s)
            if rect.left() > self.width() / 2:
                r.moveRight(rect.right())
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(12, 12, 18, 215))
            p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
            p.setFont(af)
            p.setPen(QColor(255, 255, 255, 235))
            p.drawText(QPointF(r.left() + 12 * s, r.top() + 6 * s + fm.ascent()), self.toast_text)
        p.restore()

    def draw_zones(self, p):
        p.save()
        p.setOpacity(1.0)
        _, af, _ = self.card_fonts()
        p.setFont(af)
        for z, info in zip(self.zones, self.profile.get("zones_interdites", [])):
            p.setPen(QPen(QColor(255, 70, 70, 220), 2))
            p.setBrush(QColor(255, 40, 40, 55))
            p.drawRect(z)
            p.setPen(QColor(255, 255, 255, 230))
            p.drawText(z.adjusted(8, 6, -8, -6), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                       info.get("nom", ""))
        p.setPen(QPen(QColor(120, 200, 255, 160), 1.5, Qt.PenStyle.DashLine))
        y = self.height() * UPPER
        p.drawLine(QPointF(0, y), QPointF(self.width(), y))
        p.restore()


# --------------------------------------------------------------------------
# Application : panneau + icone + raccourcis
# --------------------------------------------------------------------------
class App:
    def __init__(self, app, demo=False, minimized=False, updated=""):
        from panel import Panel, make_icon

        self.app = app
        self.quitting = False
        self.cfg = load_config()
        self.profiles = games.load_profiles()
        self.profiles_mtime = games.profiles_mtime()
        self.overlay = Overlay(self.cfg, self.profiles)
        self.overlay.show()
        self.overlay.harden_window()
        self.overlay.keep_on_top()
        self.overlay.install_foreground_hook()
        self.exclusive = False
        self.exclusive_tip = ""
        self.check_profile()

        self.demo = False
        self.real_track = None
        self.store_lyrics, self.store_cover = {}, {}
        self.demo_timer = QTimer()
        self.demo_timer.timeout.connect(self.demo_step)

        self.sources = []  # applis vues cette session (pour le panneau)
        self.worker = MediaWorker(self.cfg.get("sources_blocked", []))
        self.worker.sources.connect(self.w_sources)
        self.worker.track.connect(self.w_track)
        self.worker.lyrics.connect(self.w_lyrics)
        self.worker.translated.connect(self.w_translated)
        self.worker.cover.connect(self.w_cover)
        self.worker.start()

        self.beat_bridge = BeatBridge()
        self.beat_bridge.beat.connect(self.overlay.on_beat)
        self.audio = None
        try:
            from audio import AudioBeats
            self.audio = AudioBeats(lambda k: self.beat_bridge.beat.emit(k))
            self.audio.start()
        except Exception:
            self.audio = None

        self.profile_timer = QTimer()
        self.profile_timer.timeout.connect(self.check_profile)
        self.profile_timer.start(1000)

        self.cfg["hotkeys"] = hotkeys.normalize(self.cfg.get("hotkeys"))
        self.hotkeys_failed = []  # combinaisons refusees par Windows (prises par une autre appli)
        self.hotkeys = hotkeys.Hotkeys(self.cfg["hotkeys"])
        self.hotkeys.pressed.connect(self.on_hotkey)
        self.hotkeys.failed.connect(self.on_hotkeys_failed)

        self.panel = Panel(self)
        self.hotkeys.start()
        self.tray = QSystemTrayIcon(make_icon())
        self.tray.setToolTip("FollowTheLyrics")
        menu = QMenu()
        menu.addAction("Ouvrir le panneau", self.show_panel)
        self.act_toggle = menu.addAction("Masquer les paroles", self.toggle)
        menu.addSeparator()
        menu.addAction("Quitter", self.quit)
        self.tray_menu = menu
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.on_tray)
        self.tray.show()
        app.aboutToQuit.connect(self.cleanup)

        if demo:
            self.set_demo(True)
            self.panel.sync_from_cfg()
        self.welcome = None
        self.zone_editor = None
        self.last_game = None
        self.setup_updates(updated)
        if not self.cfg.get("welcomed"):
            self.show_welcome()  # tout premier lancement
        elif not minimized:
            self.show_panel()

    # ---- mises a jour ---------------------------------------------------------
    def setup_updates(self, updated):
        import updater
        self.update_info = None
        self.update_check = None
        self.update_job = None
        self.cleanup_tries = 0
        if updated:  # on vient d'etre installe par l'ancienne version
            try:
                self.tray.showMessage("FollowTheLyrics", f"Mise à jour installée : version {updated}.",
                                      self.tray.icon(), 5000)
            except Exception:
                pass
        # restes d'une mise a jour (l'ancien .exe ne peut etre efface qu'une fois ferme)
        self.cleanup_timer = QTimer()
        self.cleanup_timer.timeout.connect(self.cleanup_update)
        self.cleanup_timer.start(3000)
        if updater.bootstrap.FROZEN or os.environ.get("FTL_FAKE_VERSION"):
            QTimer.singleShot(5000, lambda: self.check_update())
            self.update_timer = QTimer()
            self.update_timer.timeout.connect(lambda: self.check_update())
            self.update_timer.start(6 * 3600 * 1000)

    def cleanup_update(self):
        import updater
        self.cleanup_tries += 1
        if updater.cleanup_leftovers() or self.cleanup_tries >= 10:
            self.cleanup_timer.stop()

    def check_update(self, manual=False):
        """manual : demande depuis le panneau (on repond meme s'il n'y a rien de neuf)."""
        import updater
        if self.update_info:
            if manual:
                self.panel.show_update(self.update_info)
            return
        if self.update_check and self.update_check.isRunning():
            return
        self.update_check = updater.UpdateCheck()
        self.update_check.found.connect(self.on_update_found)
        if manual:
            self.update_check.nothing.connect(self.panel.update_none)
        self.update_check.start()

    def on_update_found(self, info):
        self.update_info = info
        self.panel.show_update(info)
        try:
            self.tray.showMessage("FollowTheLyrics", f"La version {info['version']} est disponible. "
                                  "Ouvre le panneau pour mettre à jour.", self.tray.icon(), 6000)
        except Exception:
            pass
        if os.environ.get("FTL_AUTO_UPDATE"):  # test de bout en bout
            self.install_update()

    def install_update(self):
        import updater
        if not self.update_info or (self.update_job and self.update_job.isRunning()):
            return
        if not updater.bootstrap.FROZEN:  # version « code » : on ouvre juste la page
            os.startfile(updater.RELEASES_URL)
            self.panel.update_failed("Version « code » : télécharge la nouvelle version sur la page ouverte.")
            return
        self.update_job = updater.UpdateInstall(self.update_info)
        self.update_job.progress.connect(self.panel.update_progress)
        self.update_job.failed.connect(self.panel.update_failed)
        self.update_job.installed.connect(self.on_update_installed)
        self.update_job.start()

    def on_update_installed(self, version):
        import updater
        try:
            updater.relaunch(sys.executable, version)  # la nouvelle version nous demandera de quitter
        except Exception as e:
            self.panel.update_failed(f"La nouvelle version est installée mais n'a pas pu démarrer ({e}). "
                                     "Relance FollowTheLyrics.")

    # ---- editeur de zones -------------------------------------------------------
    def reload_profiles(self):
        self.profiles = games.load_profiles()
        self.profiles_mtime = games.profiles_mtime()
        self.overlay.profile_key = None  # reapplique au prochain passage

    def open_zone_editor(self, key=None, activate=True):
        from zone_editor import ZoneEditor
        if key is None:
            key = self.overlay.profile_key if self.overlay.profile_key in self.profiles.get("jeux", {}) else self.last_game
        if self.zone_editor is None:
            self.zone_editor = ZoneEditor(self, key)
        else:
            self.zone_editor.show_game(key)
        w = self.zone_editor
        w.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, not activate)
        w.show()
        if activate:
            w.raise_()
            w.activateWindow()

    def capture_game(self):
        """Raccourci « capture » en jeu : capture l'ecran (sans les paroles) pour l'editeur de zones."""
        exe, _full = games.foreground_info()
        key, _prof = games.current_profile(self.profiles)
        if key not in self.profiles.get("jeux", {}):
            own = os.path.basename(sys.executable).lower()
            if not exe or exe.lower() in ("explorer.exe", own, "python.exe", "pythonw.exe"):
                self.overlay.toast("Mets-toi dans le jeu, puis " + self.hotkey_text("capture"))
                return
            key = exe  # jeu pas encore connu : il sera cree a l'enregistrement
        o = self.overlay
        o.setWindowOpacity(0.0)  # les paroles ne doivent pas etre sur la capture

        def grab():
            try:
                pm = o.screen().grabWindow(0)
                os.makedirs(games.CAPTURES_DIR, exist_ok=True)
                ok = (not pm.isNull()) and pm.save(games.capture_path(key), "JPG", 88)
            except Exception:
                ok = False
            o.setWindowOpacity(1.0)
            if not ok:
                o.toast("Capture impossible")
                return
            self.last_game = key
            o.toast("Capture prise : reviens sur FollowTheLyrics pour dessiner les zones")
            self.open_zone_editor(key, activate=False)

        QTimer.singleShot(150, grab)

    # ---- premier lancement ---------------------------------------------------
    def show_welcome(self):
        from welcome import Welcome
        self.welcome = Welcome()
        self.welcome.finished.connect(self.on_welcome)
        self.welcome.show()
        self.welcome.raise_()
        self.welcome.activateWindow()

    def on_welcome(self, autostart, shortcut):
        import settings
        if autostart != settings.autostart_enabled():
            settings.set_autostart(autostart)
        if shortcut:
            settings.create_desktop_shortcut()
        self.cfg["welcomed"] = True
        save_config(self.cfg)
        self.welcome = None
        if not self.quitting:
            self.panel.sync_from_cfg()
            self.show_panel()

    # ---- musique reelle / demo -------------------------------------------
    def w_track(self, np):
        self.real_track = np
        if self.audio:  # seulement la vraie musique (la demo ne fait pas de son)
            self.audio.music_playing = bool(np and np.playing)
        if self.demo:
            return
        o = self.overlay
        before = o.track_key
        o.on_track(np)
        if np and o.track_key != before:
            if np.key in self.store_lyrics:
                o.on_lyrics(np.key, self.store_lyrics[np.key])
            if np.key in self.store_cover:
                o.on_cover(np.key, self.store_cover[np.key])

    def w_sources(self, ids):
        for a in ids:
            if a not in self.sources:
                self.sources.append(a)

    def set_source_enabled(self, app_id, enabled):
        """Cocher / decocher une appli dans le panneau : elle est ecoutee ou ignoree."""
        blocked = set(self.cfg.get("sources_blocked", []))
        (blocked.discard if enabled else blocked.add)(app_id)
        self.cfg["sources_blocked"] = sorted(blocked)
        save_config(self.cfg)
        self.worker.blocked = set(blocked)

    def w_lyrics(self, key, lines):
        self.store_lyrics[key] = lines
        if not self.demo:
            self.overlay.on_lyrics(key, lines)

    def w_translated(self, key):
        if not self.demo:
            self.overlay.on_translated(key)

    def w_cover(self, key, data):
        self.store_cover[key] = data
        if not self.demo:
            self.overlay.on_cover(key, data)

    def set_demo(self, on):
        self.demo = bool(on)
        o = self.overlay
        o.track_key = None
        o.track = None
        if self.demo:
            self.demo_start = time.monotonic()
            self.demo_step()
            o.on_lyrics(DEMO_KEY, DEMO_LINES)
            self.demo_timer.start(400)
        else:
            self.demo_timer.stop()
            if self.real_track:
                self.w_track(self.real_track)

    def demo_step(self):
        pos = (time.monotonic() - self.demo_start) % DEMO_LENGTH
        self.overlay.on_track(demo_track(pos))

    def check_profile(self):
        mt = games.profiles_mtime()
        if mt != self.profiles_mtime:
            self.profiles_mtime = mt
            self.profiles = games.load_profiles()
            self.overlay.profile_key = None
        key, prof = games.current_profile(self.profiles)
        if key != self.overlay.profile_key:
            self.overlay.set_profile(key, prof)
            if key != "bureau":
                self.overlay.toast(f"Profil : {prof.get('nom', key)}")
        # Plein ecran EXCLUSIF : Windows interdit toute fenetre par-dessus -> on previent
        excl = games.exclusive_fullscreen()
        if excl and not self.exclusive:
            tip = prof.get("conseil_plein_ecran") or \
                "Passe le jeu en « fenêtré sans bordure » dans ses options vidéo."
            self.exclusive_tip = tip
            try:
                self.tray.showMessage("FollowTheLyrics : jeu en plein écran exclusif",
                                      "Les paroles ne peuvent pas s'afficher par-dessus. " + tip,
                                      QSystemTrayIcon.MessageIcon.Warning, 8000)
            except Exception:
                pass
        self.exclusive = excl

    # ---- reglages (appeles par le panneau et les raccourcis) ----------------
    def set_cfg(self, key, value):
        self.cfg[key] = value
        save_config(self.cfg)
        o = self.overlay
        if key == "scale":
            o.apply_geometry()
        elif key in ("mode", "position", "font", "translation", "stack"):
            o.reset_layout()
        elif key == "easter" and not value:
            o.egg = None
        o.poke()

    def set_visible(self, visible):
        self.overlay.user_hidden = not visible
        self.act_toggle.setText("Masquer les paroles" if visible else "Afficher les paroles")

    def toggle(self):
        self.set_visible(self.overlay.user_hidden)
        self.overlay.toast("Paroles affichees" if not self.overlay.user_hidden else "Paroles masquees")
        self.panel.sync_from_cfg()

    def show_zones(self):
        o = self.overlay
        o.zones_until = o.clock() + 5.0
        o.toast(f"Zones : {o.profile.get('nom', o.profile_key)}")

    def edit_profiles(self):
        try:
            os.startfile(games.PROFILES_PATH)
        except Exception:
            pass

    # ---- raccourcis modifiables -------------------------------------------------
    def hotkey_text(self, name):
        """La combinaison actuelle d'une action, telle qu'on l'affiche (« Ctrl + Alt + E »)."""
        return hotkeys.pretty(self.cfg["hotkeys"].get(name, ""))

    def set_hotkey(self, name, combo):
        """Change un raccourci. Si une autre action avait deja cette combinaison, elle la perd.
        Renvoie le nom de cette autre action (ou None)."""
        keys = dict(self.cfg["hotkeys"])
        stolen = None
        for other, used in keys.items():
            if combo and other != name and used == combo:
                keys[other] = ""
                stolen = other
        keys[name] = combo
        self.apply_hotkeys(keys)
        return stolen

    def reset_hotkeys(self):
        self.apply_hotkeys(dict(hotkeys.DEFAULTS))

    def apply_hotkeys(self, keys):
        self.cfg["hotkeys"] = keys
        save_config(self.cfg)
        self.hotkeys.set_bindings(keys)

    def on_hotkeys_failed(self, names):
        self.hotkeys_failed = list(names)
        self.panel.hotkeys_changed()

    def on_hotkey(self, name):
        o = self.overlay

        def cycle(key, options):
            keys = list(options)
            self.set_cfg(key, keys[(keys.index(self.cfg[key]) + 1) % len(keys)])

        if name == "toggle":
            self.toggle()
            return
        if name == "capture":
            self.capture_game()
            return
        if name == "zones":
            self.show_zones()
        elif name == "mode":
            cycle("mode", MODES)
            o.toast(f"Mode : {MODES[self.cfg['mode']][0]}")
        elif name == "style":
            cycle("style", STYLES)
            o.toast(f"Animation : {STYLES[self.cfg['style']]}")
        elif name == "color":
            cycle("color", COLORS)
            o.toast(COLORS[self.cfg["color"]])
        elif name in ("earlier", "later"):
            self.set_cfg("offset", round(self.cfg["offset"] + (0.2 if name == "earlier" else -0.2), 2))
            o.toast(f"Decalage : {self.cfg['offset']:+.1f} s")
        self.panel.sync_from_cfg()

    def on_tray(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_panel()

    def show_panel(self):
        self.panel.show()
        self.panel.raise_()
        self.panel.activateWindow()

    def quit(self):
        """Quitter pour de vrai (le panneau accepte alors de se fermer)."""
        self.quitting = True
        if self.welcome is not None:
            self.welcome.close()
        if self.zone_editor is not None:
            self.zone_editor.close()
        self.panel.close()
        self.app.quit()

    def cleanup(self):
        self.quitting = True
        self.tray.hide()
        if self.audio:
            self.audio.stop()
        self.hotkeys.stop()
        self.worker.stop()


# --------------------------------------------------------------------------
# Mode capture (pour tester le rendu sans ecran)
# --------------------------------------------------------------------------
def snapshot(path, at, args):
    fake = [0.0]
    cfg = dict(DEFAULTS, style=args.style, mode=args.mode, position=args.position,
               color=args.color, font=args.font)
    profiles = games.DEFAULT_PROFILES
    o = Overlay(cfg, profiles, clock=lambda: fake[0], rng=random.Random(args.seed))
    o.timer.stop()
    o.top_timer.stop()
    if args.game:
        o.set_profile(args.game, profiles["jeux"].get(args.game, profiles["jeu_inconnu"]))
    start = max(0.0, at - 8.0) if not args.card else at
    o.on_track(demo_track(start))
    lines = DEMO_LINES
    if args.translation:
        for l in lines:
            if l.text:
                l.translation = "Traduction : " + l.text.lower()
    o.on_lyrics(DEMO_KEY, lines)
    if args.cover:
        with open(args.cover, "rb") as f:
            o.on_cover(o.track_key, f.read())
    if not args.card:
        o.card_since = -99
    while fake[0] < (at - start) + (1.2 if args.card else 0):
        fake[0] += 0.016
        o.tick(0.016)
    if args.zones:
        o.zones_until = fake[0] + 5
    img = QImage(o.size(), QImage.Format.Format_ARGB32_Premultiplied)
    bg = QLinearGradient(0, 0, o.width(), o.height())
    bg.setColorAt(0, QColor("#1d2b22"))
    bg.setColorAt(1, QColor("#3d4f5c"))
    p = QPainter(img)
    p.fillRect(img.rect(), QBrush(bg))
    p.end()
    o.render(img)
    img.scaledToWidth(960, Qt.TransformationMode.SmoothTransformation).save(path)


def selftest(app, out_dir):
    """Demarre tout en mode demo quelques secondes, ecrit un rapport et des captures,
    puis quitte. Ne remplace pas l'appli deja ouverte et n'enregistre aucun reglage."""
    import traceback
    import settings
    report = [f"frozen={settings.FROZEN}", f"data_dir={settings.DATA_DIR}"]
    report += [f"boot {n}: {r}" for n, r in bootstrap.LOG]
    try:
        import media  # noqa: F401
        report.append("winrt=ok")
    except Exception as e:
        report.append(f"winrt=ERREUR {e!r}")
    try:
        import audio
        report.append("audio=" + ("ok" if audio.pyaudio is not None else "ABSENT"))
    except Exception as e:
        report.append(f"audio=ERREUR {e!r}")

    def finish(a):
        try:
            o = a.overlay
            report.append(f"paroles={len(o.lines)} piste={o.track.title if o.track else None}")
            report.append(f"sources={a.sources}")
            report.append(f"reel={a.real_track.title if a.real_track else None}")
            if a.welcome is not None:
                a.welcome.grab().save(os.path.join(out_dir, "selftest_welcome.png"))
            a.panel.show()
            app.processEvents()
            a.panel.grab().save(os.path.join(out_dir, "selftest_panel.png"))
            img = QImage(o.size(), QImage.Format.Format_ARGB32_Premultiplied)
            img.fill(QColor("#26303a"))
            o.render(img)
            img.scaledToWidth(960, Qt.TransformationMode.SmoothTransformation).save(
                os.path.join(out_dir, "selftest_overlay.png"))
            report.append("fin=ok")
        except Exception:
            report.append("fin=ERREUR\n" + traceback.format_exc())
        with open(os.path.join(out_dir, "selftest.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(report))
        os._exit(0)

    try:
        a = App(app, demo=True)
        QTimer.singleShot(7000, lambda: finish(a))
        app.exec()
    except Exception:
        report.append("demarrage=ERREUR\n" + traceback.format_exc())
        with open(os.path.join(out_dir, "selftest.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(report))
        os._exit(1)


INSTANCE_NAME = "LyricsOverlay-instance" + os.environ.get("FTL_TEST_INSTANCE", "")  # ancien nom du projet, garde pour remplacer les vieilles versions
_instance_mutex = None


def take_over_instance():
    """Une seule appli a la fois : si une ancienne tourne, on lui demande de quitter
    et on prend sa place. Renvoie le serveur qui ecoutera la prochaine relance."""
    global _instance_mutex
    from PyQt6.QtNetwork import QLocalServer, QLocalSocket

    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateMutexW.restype = wintypes.HANDLE
    k.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    asked = False
    deadline = time.monotonic() + 6.0
    while True:
        h = k.CreateMutexW(None, False, "Local\\" + INSTANCE_NAME)
        already = ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS
        if not already or time.monotonic() > deadline:
            _instance_mutex = h  # garde tant que l'appli vit
            break
        k.CloseHandle(h)
        if not asked:
            asked = True
            sock = QLocalSocket()
            sock.connectToServer(INSTANCE_NAME)
            if sock.waitForConnected(500):
                sock.write(b"quit")
                sock.flush()
                sock.waitForBytesWritten(300)
            sock.close()
        time.sleep(0.15)
    QLocalServer.removeServer(INSTANCE_NAME)
    server = QLocalServer()
    return server if server.listen(INSTANCE_NAME) else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--updated", default="")  # lance par l'ancienne version apres une mise a jour
    ap.add_argument("--minimized", action="store_true")  # demarrage avec Windows : pas de panneau
    ap.add_argument("--selftest")  # dossier : verifie que le .exe demarre, sans rien deranger
    ap.add_argument("--snapshot")
    ap.add_argument("--at", type=float, default=7.0)
    ap.add_argument("--mode", default="edit")
    ap.add_argument("--position", default="left")
    ap.add_argument("--color", default="album")
    ap.add_argument("--font", default=DEFAULTS["font"])
    ap.add_argument("--style", default="kinetic")
    ap.add_argument("--game", default="")
    ap.add_argument("--zones", action="store_true")
    ap.add_argument("--cover")
    ap.add_argument("--card", action="store_true")
    ap.add_argument("--translation", action="store_true")
    ap.add_argument("--seed", type=int, default=3)
    args, _unknown = ap.parse_known_args()

    try:  # icone et regroupement propres dans la barre des taches
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("FollowTheLyrics.App")
    except Exception:
        pass
    app = QApplication(sys.argv)
    app.setApplicationName("FollowTheLyrics")
    app.setQuitOnLastWindowClosed(False)
    if args.snapshot:
        snapshot(args.snapshot, args.at, args)
        return
    if args.selftest:
        selftest(app, args.selftest)
        return
    server = take_over_instance()
    import settings
    if settings.FROZEN:
        settings.refresh_autostart()  # le .exe a peut-etre ete deplace
    a = App(app, demo=args.demo, minimized=args.minimized, updated=args.updated)
    if server is not None:
        # une nouvelle version se lance : celle-ci lui laisse la place
        server.newConnection.connect(a.quit)
    code = app.exec()
    # Sortie directe : evite qu'un thread audio/Windows encore actif bloque la fermeture.
    os._exit(code)


if __name__ == "__main__":
    main()
