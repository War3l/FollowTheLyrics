import argparse
import ctypes
import logging
import os
import sys
import time
from ctypes import wintypes

from PyQt6.QtCore import Qt
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QAction
from PyQt6.QtNetwork import QLocalServer
from PyQt6.QtNetwork import QLocalSocket
from PyQt6.QtWidgets import QApplication
from PyQt6.QtWidgets import QMenu
from PyQt6.QtWidgets import QSystemTrayIcon

from followthelyrics import diagnostics
from followthelyrics import logs
from followthelyrics.config import games
from followthelyrics.config import settings
from followthelyrics.lyrics import demo_song
from followthelyrics.overlay import window
from followthelyrics.playback import audio
from followthelyrics.playback import sites
from followthelyrics.playback import worker
from followthelyrics.system import hotkeys
from followthelyrics.system import install
from followthelyrics.system import updater
from followthelyrics.ui import panel
from followthelyrics.ui import welcome
from followthelyrics.ui import widgets
from followthelyrics.ui import zone_editor

logger = logging.getLogger(__name__)


class App:
    def __init__(self, app, demo=False, minimized=False, updated=""):

        self.app = app
        self.quitting = False
        self.cfg = settings.load_config()
        self.profiles = games.load_profiles()
        self.profiles_mtime = games.profiles_mtime()
        self.overlay = window.Overlay(self.cfg, self.profiles)
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

        self.sources = []
        self.browsers = {}
        self.worker = worker.MediaWorker(
            self.cfg.get("sources_blocked", []),
            self.cfg.get("sites_off", []),
            self.cfg.get("sites_other", False),
        )
        self.worker.sources.connect(self.w_sources)
        self.worker.browsers.connect(self.w_browsers)
        self.worker.track.connect(self.w_track)
        self.worker.lyrics.connect(self.w_lyrics)
        self.worker.translated.connect(self.w_translated)
        self.worker.cover.connect(self.w_cover)
        self.worker.start()

        self.beat_bridge = worker.BeatBridge()
        self.beat_bridge.beat.connect(self.overlay.on_beat)
        self.audio = None
        try:
            self.audio = audio.AudioBeats(self.beat_bridge.beat.emit)
            self.audio.start()
        except Exception:
            logger.warning("__init__ failed", exc_info=True)
            self.audio = None

        self.profile_timer = QTimer()
        self.profile_timer.timeout.connect(self.check_profile)
        self.profile_timer.start(1000)

        self.cfg["hotkeys"] = hotkeys.normalize(self.cfg.get("hotkeys"))
        self.hotkeys_failed = []
        self.hotkeys = hotkeys.Hotkeys(self.cfg["hotkeys"])
        self.hotkeys.pressed.connect(self.on_hotkey)
        self.hotkeys.failed.connect(self.on_hotkeys_failed)

        self.panel = panel.Panel(self)
        self.hotkeys.start()
        self.tray = QSystemTrayIcon(widgets.make_icon())
        self.tray.setToolTip("FollowTheLyrics")
        menu = QMenu()
        menu.addAction("Ouvrir le panneau", self.show_panel)
        self.act_toggle = QAction("Masquer les paroles", menu)
        self.act_toggle.triggered.connect(self.toggle)
        menu.addAction(self.act_toggle)
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
            self.show_welcome()
        elif not minimized:
            self.show_panel()

    def setup_updates(self, updated):
        self.update_info = None
        self.update_check = None
        self.update_job = None
        self.cleanup_tries = 0
        if updated:
            try:
                self.tray.showMessage(
                    "FollowTheLyrics",
                    f"Mise à jour installée : version {updated}.",
                    self.tray.icon(),
                    5000,
                )
            except Exception:
                logger.debug("setup_updates failed", exc_info=True)
        self.cleanup_timer = QTimer()
        self.cleanup_timer.timeout.connect(self.cleanup_update)
        self.cleanup_timer.start(3000)
        if updater.bootstrap.FROZEN or os.environ.get("FTL_FAKE_VERSION"):
            QTimer.singleShot(5000, self.check_update)
            self.update_timer = QTimer()
            self.update_timer.timeout.connect(self.check_update)
            self.update_timer.start(6 * 3600 * 1000)

    def cleanup_update(self):
        self.cleanup_tries += 1
        if updater.cleanup_leftovers() or self.cleanup_tries >= 10:
            self.cleanup_timer.stop()

    def check_update(self, manual=False):
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
            self.tray.showMessage(
                "FollowTheLyrics",
                f"La version {info['version']} est disponible. "
                "Ouvre le panneau pour mettre à jour.",
                self.tray.icon(),
                6000,
            )
        except Exception:
            logger.debug("on_update_found failed", exc_info=True)
        if os.environ.get("FTL_AUTO_UPDATE"):
            self.install_update()

    def install_update(self):
        if not self.update_info or (
            self.update_job and self.update_job.isRunning()
        ):
            return
        if not updater.bootstrap.FROZEN:
            os.startfile(updater.RELEASES_URL)
            self.panel.update_failed(
                "Version « code » : télécharge la nouvelle version sur la "
                "page ouverte."
            )
            return
        self.update_job = updater.UpdateInstall(self.update_info)
        self.update_job.progress.connect(self.panel.update_progress)
        self.update_job.failed.connect(self.panel.update_failed)
        self.update_job.installed.connect(self.on_update_installed)
        self.update_job.start()

    def on_update_installed(self, version):
        try:
            updater.relaunch(sys.executable, version)
        except Exception as e:
            logger.warning("on_update_installed failed", exc_info=True)
            self.panel.update_failed(
                f"La nouvelle version est installée mais n'a pas pu démarrer "
                f"({e}). "
                "Relance FollowTheLyrics."
            )

    def reload_profiles(self):
        self.profiles = games.load_profiles()
        self.profiles_mtime = games.profiles_mtime()
        self.overlay.profile_key = None

    def open_zone_editor(self, key=None, activate=True):
        if key is None:
            key = (
                self.overlay.profile_key
                if self.overlay.profile_key in self.profiles.get("jeux", {})
                else self.last_game
            )
        if self.zone_editor is None:
            self.zone_editor = zone_editor.ZoneEditor(self, key)
        else:
            self.zone_editor.show_game(key)
        w = self.zone_editor
        w.setAttribute(
            Qt.WidgetAttribute.WA_ShowWithoutActivating, not activate
        )
        w.show()
        if activate:
            w.raise_()
            w.activateWindow()

    def capture_game(self):
        exe, _full = games.foreground_info()
        key, _prof = games.current_profile(self.profiles)
        if key not in self.profiles.get("jeux", {}):
            own = os.path.basename(sys.executable).lower()
            if not exe or exe.lower() in (
                "explorer.exe",
                own,
                "python.exe",
                "pythonw.exe",
            ):
                self.overlay.toast(
                    "Mets-toi dans le jeu, puis " + self.hotkey_text("capture")
                )
                return
            key = exe
        o = self.overlay
        o.setWindowOpacity(0.0)

        def grab():
            try:
                screen = o.screen()
                if screen is None:
                    raise RuntimeError("aucun ecran")
                pm = screen.grabWindow()
                os.makedirs(games.CAPTURES_DIR, exist_ok=True)
                ok = (not pm.isNull()) and pm.save(
                    games.capture_path(key), "JPG", 88
                )
            except Exception:
                logger.debug("grab failed", exc_info=True)
                ok = False
            o.setWindowOpacity(1.0)
            if not ok:
                o.toast("Capture impossible")
                return
            self.last_game = key
            o.toast(
                "Capture prise : reviens sur FollowTheLyrics pour dessiner "
                "les zones"
            )
            self.open_zone_editor(key, activate=False)

        QTimer.singleShot(150, grab)

    def show_welcome(self):
        self.welcome = welcome.Welcome()
        self.welcome.finished.connect(self.on_welcome)
        self.welcome.show()
        self.welcome.raise_()
        self.welcome.activateWindow()

    def on_welcome(self, autostart, shortcut, setup=False):
        self.cfg["welcomed"] = True
        settings.save_config(self.cfg)
        self.welcome = None
        if setup and self.install_here(autostart, shortcut):
            return
        if autostart != settings.autostart_enabled():
            settings.set_autostart(autostart)
        if shortcut:
            settings.create_desktop_shortcut()
        if not self.quitting:
            self.panel.sync_from_cfg()
            self.show_panel()

    def w_track(self, np):
        self.real_track = np
        if self.audio:
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

    def w_browsers(self, seen):
        self.browsers = dict(seen)

    def set_site_enabled(self, site_id, enabled):
        if site_id == sites.OTHER:
            self.cfg["sites_other"] = bool(enabled)
        else:
            off = set(self.cfg.get("sites_off", []))
            (off.discard if enabled else off.add)(site_id)
            self.cfg["sites_off"] = sorted(off)
        settings.save_config(self.cfg)
        self.worker.guard.off = set(self.cfg.get("sites_off", []))
        self.worker.guard.other = bool(self.cfg.get("sites_other", False))

    def set_source_enabled(self, app_id, enabled):
        blocked = set(self.cfg.get("sources_blocked", []))
        (blocked.discard if enabled else blocked.add)(app_id)
        self.cfg["sources_blocked"] = sorted(blocked)
        settings.save_config(self.cfg)
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
            o.on_lyrics(demo_song.DEMO_KEY, demo_song.DEMO_LINES)
            self.demo_timer.start(400)
        else:
            self.demo_timer.stop()
            if self.real_track:
                self.w_track(self.real_track)

    def demo_step(self):
        pos = (time.monotonic() - self.demo_start) % demo_song.DEMO_LENGTH
        self.overlay.on_track(demo_song.demo_track(pos))

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
        excl = games.exclusive_fullscreen()
        if excl and not self.exclusive:
            tip = (
                prof.get("conseil_plein_ecran")
                or "Passe le jeu en « fenêtré sans bordure » dans ses options "
                "vidéo."
            )
            self.exclusive_tip = tip
            try:
                self.tray.showMessage(
                    "FollowTheLyrics : jeu en plein écran exclusif",
                    "Les paroles ne peuvent pas s'afficher par-dessus. " + tip,
                    QSystemTrayIcon.MessageIcon.Warning,
                    8000,
                )
            except Exception:
                logger.debug("check_profile failed", exc_info=True)
        self.exclusive = excl

    def set_cfg(self, key, value):
        self.cfg[key] = value
        settings.save_config(self.cfg)
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
        self.act_toggle.setText(
            "Masquer les paroles" if visible else "Afficher les paroles"
        )

    def toggle(self):
        self.set_visible(self.overlay.user_hidden)
        self.overlay.toast(
            "Paroles affichees"
            if not self.overlay.user_hidden
            else "Paroles masquees"
        )
        self.panel.sync_from_cfg()

    def show_zones(self):
        o = self.overlay
        o.zones_until = o.clock() + 5.0
        o.toast(f"Zones : {o.profile.get('nom', o.profile_key)}")

    def edit_profiles(self):
        try:
            os.startfile(games.PROFILES_PATH)
        except OSError:
            logger.debug("edit_profiles failed", exc_info=True)

    def hotkey_text(self, name):
        return hotkeys.pretty(self.cfg["hotkeys"].get(name, ""))

    def set_hotkey(self, name, combo):
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
        settings.save_config(self.cfg)
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
            cycle("mode", settings.MODES)
            o.toast(f"Mode : {settings.MODES[self.cfg['mode']][0]}")
        elif name == "style":
            cycle("style", settings.STYLES)
            o.toast(f"Animation : {settings.STYLES[self.cfg['style']]}")
        elif name == "color":
            cycle("color", settings.COLORS)
            o.toast(settings.COLORS[self.cfg["color"]])
        elif name in ("earlier", "later"):
            self.set_cfg(
                "offset",
                round(
                    self.cfg["offset"] + (0.2 if name == "earlier" else -0.2), 2
                ),
            )
            o.toast(f"Decalage : {self.cfg['offset']:+.1f} s")
        self.panel.sync_from_cfg()

    def on_tray(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_panel()

    def show_panel(self):
        self.panel.show()
        self.panel.raise_()
        self.panel.activateWindow()

    def install_here(self, autostart=None, shortcut=False):
        try:
            exe = install.install()
        except Exception as e:
            logger.warning("install_here failed", exc_info=True)
            install.message(
                f"L'installation n'a pas pu se faire ({e}).\n\n"
                "L'appli continue de marcher depuis ce fichier.",
                0x30,
            )
            return False
        if autostart is None:
            autostart = settings.autostart_enabled()
        settings.set_autostart(bool(autostart), exe=exe)
        link = settings.desktop_link()
        if shortcut or (link and os.path.exists(link)):
            settings.create_desktop_shortcut(exe=exe)
        install.launch(exe, "--installed")
        self.quit()
        return True

    def uninstall(self):
        if install.run_uninstall():
            self.quit()

    def quit(self):
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
        self.overlay.remove_foreground_hook()
        if self.audio:
            self.audio.stop()
        self.hotkeys.stop()
        self.worker.stop()


INSTANCE_NAME = "LyricsOverlay-instance" + os.environ.get(
    "FTL_TEST_INSTANCE", ""
)
_instance_mutex = None


def take_over_instance():
    global _instance_mutex

    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateMutexW.restype = wintypes.HANDLE
    k.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    asked = False
    deadline = time.monotonic() + 6.0
    while True:
        h = k.CreateMutexW(None, False, "Local\\" + INSTANCE_NAME)
        already = ctypes.get_last_error() == 183
        if not already or time.monotonic() > deadline:
            _instance_mutex = h
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
    ap.add_argument("--updated", default="")
    ap.add_argument("--minimized", action="store_true")
    ap.add_argument("--installed", action="store_true")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--purge", action="store_true")
    ap.add_argument("--selftest")
    ap.add_argument("--snapshot")
    ap.add_argument("--at", type=float, default=7.0)
    ap.add_argument("--mode", default="edit")
    ap.add_argument("--position", default="left")
    ap.add_argument("--color", default="album")
    ap.add_argument("--font", default=settings.DEFAULTS["font"])
    ap.add_argument("--style", default="kinetic")
    ap.add_argument("--game", default="")
    ap.add_argument("--zones", action="store_true")
    ap.add_argument("--cover")
    ap.add_argument("--card", action="store_true")
    ap.add_argument("--translation", action="store_true")
    ap.add_argument("--seed", type=int, default=3)
    args, _unknown = ap.parse_known_args()
    logs.setup()
    logger.info("FollowTheLyrics %s", updater.current_version())

    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "FollowTheLyrics.App"
        )
    except Exception:
        logger.debug("main failed", exc_info=True)
    app = QApplication(sys.argv)
    app.setApplicationName("FollowTheLyrics")
    app.setQuitOnLastWindowClosed(False)
    if args.snapshot:
        diagnostics.snapshot(args.snapshot, args.at, args)
        return
    if args.selftest:
        diagnostics.selftest(app, args.selftest, App)
        return
    if args.uninstall:
        if install.is_installed() and (
            args.quiet
            or install.message("Désinstaller FollowTheLyrics de ce PC ?", 0x24)
            == 6
        ):
            take_over_instance()
            keep = not args.purge
            if not args.quiet:
                keep = (
                    install.message(
                        "Garder tes réglages et tes zones pour une prochaine "
                        "installation ?",
                        0x24,
                    )
                    == 6
                )
            folders = install.uninstall(keep_data=keep)
            if not args.quiet:
                install.message("FollowTheLyrics a été désinstallé.")
            install.delete_later(folders)
        os._exit(0)
    if install.hand_over():
        os._exit(0)
    server = take_over_instance()
    if settings.FROZEN:
        if install.running_installed():
            try:
                install.register()
            except Exception:
                logger.debug("main failed", exc_info=True)
        if not os.environ.get("FTL_TEST_INSTANCE"):
            settings.refresh_autostart()
    a = App(app, demo=args.demo, minimized=args.minimized, updated=args.updated)
    if server is not None:
        server.newConnection.connect(a.quit)
    code = app.exec()
    os._exit(code)
