import argparse
import logging
import os
import sys
import time

from PyQt6.QtCore import Qt
from PyQt6.QtCore import QTimer
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QAction
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtNetwork import QLocalServer
from PyQt6.QtNetwork import QLocalSocket
from PyQt6.QtWidgets import QApplication
from PyQt6.QtWidgets import QMenu
from PyQt6.QtWidgets import QSystemTrayIcon

from followthelyrics import desktop as platform_desktop
from followthelyrics import diagnostics
from followthelyrics import i18n
from followthelyrics import logs
from followthelyrics import version
from followthelyrics.config import games
from followthelyrics.config import settings
from followthelyrics.lyrics import demo_song
from followthelyrics.overlay import window
from followthelyrics.playback import audio
from followthelyrics.playback import sites
from followthelyrics.playback import worker
from followthelyrics.system import hotkeys
from followthelyrics.system import install
from followthelyrics.system import startup
from followthelyrics.system import updater
from followthelyrics.ui import panel
from followthelyrics.ui import welcome
from followthelyrics.ui import widgets
from followthelyrics.ui import zone_editor

logger = logging.getLogger(__name__)


class App:
    def __init__(
        self, app, demo=False, minimized=False, updated="", desktop=None
    ):
        self.app = app
        self.desktop = desktop or platform_desktop.current()
        self.startup = startup.Startup(
            self.desktop.autostart, self.desktop.shortcuts
        )
        self.installation = installation_of(self.desktop, self.startup)
        self.quitting = False
        self.cfg = settings.load_config()
        i18n.set_language(self.cfg.get("lang", i18n.DEFAULT))
        self.profiles = games.load_profiles()
        self.profiles_mtime = games.profiles_mtime()
        self.overlay = window.Overlay(
            self.cfg, self.profiles, self.desktop.windowing
        )
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
            self.desktop.media,
            self.desktop.foreground.window_titles,
            self.cfg.get("sources_blocked", []),
            self.cfg.get("sites_off", []),
            self.cfg.get("sites_other", False),
            self.cfg.get("liriqo", True),
        )
        self.worker.sources.connect(self.w_sources)
        self.worker.browsers.connect(self.w_browsers)
        self.worker.track.connect(self.w_track)
        self.worker.lyrics.connect(self.w_lyrics)
        self.worker.translated.connect(self.w_translated)
        self.worker.upgrading.connect(self.overlay.on_upgrading)
        self.worker.cover.connect(self.w_cover)
        self.worker.start()

        self.beat_bridge = worker.BeatBridge()
        self.beat_bridge.beat.connect(self.overlay.on_beat)
        self.audio = audio.AudioBeats(
            self.desktop.audio, self.beat_bridge.beat.emit
        )
        self.audio.start()

        self.profile_timer = QTimer()
        self.profile_timer.timeout.connect(self.check_profile)
        self.profile_timer.start(1000)

        self.cfg["hotkeys"] = hotkeys.normalize(self.cfg.get("hotkeys"))
        self.hotkeys_failed = []
        self.hotkeys = hotkeys.Hotkeys(
            self.desktop.hotkeys, self.desktop.keyboard, self.cfg["hotkeys"]
        )
        self.hotkeys.pressed.connect(self.on_hotkey)
        self.hotkeys.failed.connect(self.on_hotkeys_failed)

        self.panel = panel.Panel(self)
        self.hotkeys.start()
        self.tray = QSystemTrayIcon(widgets.make_icon())
        self.tray.setToolTip("FollowTheLyrics")
        menu = QMenu()
        self.act_open = menu.addAction(
            i18n.tr("Ouvrir le panneau"), self.show_panel
        )
        self.act_toggle = QAction(i18n.tr("Masquer les paroles"), menu)
        self.act_toggle.triggered.connect(self.toggle)
        menu.addAction(self.act_toggle)
        menu.addSeparator()
        self.act_quit = menu.addAction(i18n.tr("Quitter"), self.quit)
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
                    i18n.tr("Mise à jour installée : version {}.").format(
                        updated
                    ),
                    self.tray.icon(),
                    5000,
                )
            except Exception:
                logger.debug("setup_updates failed", exc_info=True)
        self.cleanup_timer = QTimer()
        self.cleanup_timer.timeout.connect(self.cleanup_update)
        self.cleanup_timer.start(3000)
        if self.desktop.release is not None and (
            settings.FROZEN or os.environ.get("FTL_FAKE_VERSION")
        ):
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
        self.update_check = updater.UpdateCheck(self.desktop.release)
        self.update_check.found.connect(self.on_update_found)
        if manual:
            self.update_check.nothing.connect(self._update_none)
        self.update_check.start()

    def on_update_found(self, info):
        self.update_info = info
        self.panel.show_update(info)
        try:
            self.tray.showMessage(
                "FollowTheLyrics",
                i18n.tr(
                    "La version {} est disponible. Ouvre le panneau pour "
                    "mettre à jour."
                ).format(info["version"]),
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
        if not settings.FROZEN:
            QDesktopServices.openUrl(QUrl(updater.RELEASES_URL))
            self.panel.update_failed(
                i18n.tr(
                    "Version « code » : télécharge la nouvelle version sur la "
                    "page ouverte."
                )
            )
            return
        self.update_job = updater.UpdateInstall(
            self.update_info, self.desktop.release
        )
        self.update_job.progress.connect(self._update_progress)
        self.update_job.failed.connect(self._update_failed)
        self.update_job.installed.connect(self.on_update_installed)
        self.update_job.start()

    def on_update_installed(self, version):
        try:
            updater.relaunch(self.desktop.session, sys.executable, version)
        except Exception as e:
            logger.warning("on_update_installed failed", exc_info=True)
            self.panel.update_failed(
                i18n.tr(
                    "La nouvelle version est installée mais n'a pas pu "
                    "démarrer ({}). Relance FollowTheLyrics."
                ).format(e)
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
        foreground = self.desktop.foreground.current()
        exe = foreground.exe
        key, _prof = games.current_profile(self.profiles, foreground)
        if key not in self.profiles.get("jeux", {}):
            own = os.path.basename(sys.executable).lower()
            if not exe or exe.lower() in (
                "explorer.exe",
                own,
                "python.exe",
                "pythonw.exe",
            ):
                self.overlay.toast(
                    i18n.tr("Mets-toi dans le jeu, puis ")
                    + self.hotkey_text("capture")
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
                o.toast(i18n.tr("Capture impossible"))
                return
            self.last_game = key
            o.toast(
                i18n.tr(
                    "Capture prise : reviens sur FollowTheLyrics pour dessiner "
                    "les zones"
                )
            )
            self.open_zone_editor(key, activate=False)

        QTimer.singleShot(150, grab)

    def show_welcome(self):
        self.welcome = welcome.Welcome(
            self.startup, self.installation, self.desktop
        )
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
        if autostart != self.startup.enabled():
            self.startup.set(autostart)
        if shortcut:
            self.startup.create_desktop_shortcut()
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
        key, prof = games.current_profile(
            self.profiles, self.desktop.foreground.current()
        )
        if key != self.overlay.profile_key:
            self.overlay.set_profile(key, prof)
        excl = self.desktop.foreground.exclusive_fullscreen()
        moved = self.overlay.set_elsewhere(excl)
        if excl and not self.exclusive:
            tip = i18n.tr(prof.get("conseil_plein_ecran") or "") or i18n.tr(
                "Passe le jeu en « fenêtré sans bordure » dans ses options "
                "vidéo."
            )
            if moved:
                tip = i18n.tr("Elles s'affichent sur ton autre écran. ") + tip
            self.exclusive_tip = tip
            try:
                self.tray.showMessage(
                    i18n.tr("FollowTheLyrics : jeu en plein écran exclusif"),
                    i18n.tr(
                        "Les paroles ne peuvent pas s'afficher par-dessus. "
                    )
                    + tip,
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
        elif key == "liriqo":
            self.worker.upgrade = bool(value)
        o.poke()

    def _update_none(self, error):
        self.panel.update_none(error)

    def _update_progress(self, frac):
        self.panel.update_progress(frac)

    def _update_failed(self, message):
        self.panel.update_failed(message)

    def set_language(self, code):
        if code == i18n.language():
            return
        self.cfg["lang"] = code
        settings.save_config(self.cfg)
        i18n.set_language(code)
        if self.act_open is not None:
            self.act_open.setText(i18n.tr("Ouvrir le panneau"))
        if self.act_quit is not None:
            self.act_quit.setText(i18n.tr("Quitter"))
        self.set_visible(not self.overlay.user_hidden)
        old = self.panel
        was_open = old.isVisible()
        geometry = old.geometry()
        self.panel = panel.Panel(self)
        self.panel.setGeometry(geometry)
        self.panel.go("general", animate=False)
        if self.update_info:
            self.panel.show_update(self.update_info)
        if was_open:
            self.panel.show()
        old.timer.stop()
        old.anim_timer.stop()
        old.hide()
        old.deleteLater()
        self.worker.retranslate()
        self.overlay.poke()

    def set_visible(self, visible):
        self.overlay.user_hidden = not visible
        self.act_toggle.setText(
            i18n.tr("Masquer les paroles")
            if visible
            else i18n.tr("Afficher les paroles")
        )

    def toggle(self):
        self.set_visible(self.overlay.user_hidden)
        self.overlay.toast(
            i18n.tr("Paroles affichees")
            if not self.overlay.user_hidden
            else i18n.tr("Paroles masquees")
        )
        self.panel.sync_from_cfg()

    def show_zones(self):
        o = self.overlay
        o.zones_until = o.clock() + 5.0
        o.toast(
            i18n.tr("Zones : {}").format(o.profile.get("nom", o.profile_key))
        )

    def edit_profiles(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(games.PROFILES_PATH))

    def hotkey_text(self, name):
        return self.hotkeys.pretty(self.cfg["hotkeys"].get(name, ""))

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
            o.toast(
                i18n.tr("Mode : {}").format(
                    i18n.tr(settings.MODES[self.cfg["mode"]][0])
                )
            )
        elif name == "style":
            cycle("style", settings.STYLES)
            o.toast(
                i18n.tr("Animation : {}").format(
                    i18n.tr(settings.STYLES[self.cfg["style"]])
                )
            )
        elif name == "color":
            cycle("color", settings.COLORS)
            o.toast(i18n.tr(settings.COLORS[self.cfg["color"]]))
        elif name in ("earlier", "later"):
            self.set_cfg(
                "offset",
                round(
                    self.cfg["offset"] + (0.2 if name == "earlier" else -0.2), 2
                ),
            )
            o.toast(
                i18n.tr("Decalage : {} s").format(
                    format(self.cfg["offset"], "+.1f")
                )
            )
        self.panel.sync_from_cfg()

    def on_tray(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_panel()

    def show_panel(self):
        self.panel.show()
        self.panel.raise_()
        self.panel.activateWindow()

    def install_here(self, autostart=None, shortcut=False):
        if self.installation is None:
            return False
        try:
            exe = self.installation.install()
        except Exception as e:
            logger.warning("install_here failed", exc_info=True)
            self.desktop.dialogs.warn(
                i18n.tr(
                    "L'installation n'a pas pu se faire ({}).\n\nL'appli "
                    "continue de marcher depuis ce fichier."
                ).format(e)
            )
            return False
        if autostart is None:
            autostart = self.startup.enabled()
        self.startup.set(bool(autostart), exe=exe)
        link = self.startup.desktop_link()
        if shortcut or (link and os.path.exists(link)):
            self.startup.create_desktop_shortcut(exe=exe)
        self.installation.launch(exe, "--installed")
        self.quit()
        return True

    def uninstall(self):
        if self.installation and self.installation.confirm_uninstall():
            self.installation.run_uninstall()
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


INSTANCE_NAME = "LyricsOverlay-instance" + install.TEST_INSTANCE
_instance_lock = None


def installation_of(desktop, desktop_startup):
    if desktop.installer is None or desktop.release is None:
        return None
    return install.Installation(
        desktop.installer,
        desktop_startup,
        desktop.dialogs,
        desktop.session,
        desktop.release.asset,
    )


def _ask_running_instance_to_quit():
    sock = QLocalSocket()
    sock.connectToServer(INSTANCE_NAME)
    if sock.waitForConnected(500):
        sock.write(b"quit")
        sock.flush()
        sock.waitForBytesWritten(300)
    sock.close()


def take_over_instance(session):
    global _instance_lock

    _instance_lock = session.instance_lock(INSTANCE_NAME)
    asked = False
    deadline = time.monotonic() + 6.0
    while not _instance_lock.acquire() and time.monotonic() <= deadline:
        if not asked:
            asked = True
            _ask_running_instance_to_quit()
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
    logger.info("FollowTheLyrics %s", version.current())

    desktop = platform_desktop.current()
    desktop.session.set_app_id("FollowTheLyrics.App")
    app = QApplication(sys.argv)
    app.setApplicationName("FollowTheLyrics")
    app.setQuitOnLastWindowClosed(False)
    if args.snapshot:
        diagnostics.snapshot(args.snapshot, args.at, args)
        return
    if args.selftest:
        diagnostics.selftest(app, args.selftest, App)
        return
    desktop_startup = startup.Startup(desktop.autostart, desktop.shortcuts)
    installation = installation_of(desktop, desktop_startup)
    if args.uninstall:
        if (
            installation is not None
            and installation.is_installed()
            and (args.quiet or installation.confirm_uninstall())
        ):
            take_over_instance(desktop.session)
            installation.run_uninstall(
                quiet=args.quiet, keep_data=not args.purge
            )
        os._exit(0)
    if installation is not None and installation.hand_over():
        os._exit(0)
    server = take_over_instance(desktop.session)
    if settings.FROZEN:
        if installation is not None and installation.running_installed():
            try:
                installation.register()
            except Exception:
                logger.debug("main failed", exc_info=True)
        if not install.TEST_INSTANCE:
            desktop_startup.refresh()
    a = App(
        app,
        demo=args.demo,
        minimized=args.minimized,
        updated=args.updated,
        desktop=desktop,
    )
    if server is not None:
        server.newConnection.connect(a.quit)
    code = app.exec()
    os._exit(code)
