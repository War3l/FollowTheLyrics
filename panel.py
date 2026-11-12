"""Panneau de controle : un menu a gauche, une page par sujet a droite.

Accueil (musique en cours) · Affichage · Style · Musique · Jeux · Raccourcis · Général.
Tout s'applique en direct ; les briques dessinees a la main sont dans widgets.py.
"""
import ctypes
import os
import sys

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QBrush, QColor, QFont, QFontDatabase, QFontMetricsF, QLinearGradient, QPainter, QPen, QRadialGradient
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtWidgets import (
    QButtonGroup, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QScrollArea, QSlider, QStackedWidget, QVBoxLayout, QWidget,
)

import hotkeys
from settings import (COLORS, FROZEN, MODES, POSITIONS, RECOMMENDED_FONTS, STYLES, TITLE_DROP, app_label,
                      autostart_enabled, set_autostart)
from widgets import (BG, BRAND, CARD, CARD_BORDER, DEFAULT_ACCENT, DIM, FIELD, TEXT, UI,  # noqa: F401
                     dark_caption, enable_backdrop, mix, qss,
                     ColorCard, CoverView, Equalizer, HotkeyButton, MiniPlayer, ModeCard, NavTile,
                     ProgressView, Segmented, SideNav, Toggle, alpha, fmt_time, icon_pixmap,
                     make_anim, make_icon, run_anim, ui_font)

SITE_URL = "https://war3l.github.io/FollowTheLyrics/"

# (cle, nom dans le menu, icone, titre de la page, phrase d'explication)
PAGES = [
    ("home", "Accueil", "home", "Accueil", "Ce qui joue en ce moment, et tes réglages en un coup d'œil."),
    ("display", "Affichage", "screen", "Affichage", "Où et comment les paroles apparaissent à l'écran."),
    ("style", "Style", "style", "Style", "Couleurs, animation des mots et police d'écriture."),
    ("music", "Musique", "music", "Musique", "Les applis écoutées, la traduction et le calage des paroles."),
    ("games", "Jeux", "game", "Jeux", "Les paroles évitent les zones importantes de tes jeux."),
    ("keys", "Raccourcis", "keys", "Raccourcis clavier", "Ils marchent partout, même en pleine partie. Choisis tes touches."),
    ("general", "Général", "sliders", "Général", "Démarrage, mises à jour et à propos."),
]


class FontPreview(QWidget):
    """Apercu du texte avec la police et les couleurs choisies (meme rendu qu'a l'ecran)."""

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.setFixedHeight(104)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, QColor(0, 0, 0, 104))  # un petit ecran sombre dans le verre
        g.setColorAt(1, QColor(0, 0, 0, 56))
        p.setPen(QPen(QColor(CARD_BORDER), 1))
        p.setBrush(QBrush(g))
        p.drawRoundedRect(r, 20, 20)
        p.setPen(QColor(255, 255, 255, 120))
        p.setFont(ui_font(11, QFont.Weight.Bold))
        p.drawText(r.adjusted(16, 10, 0, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, "APERÇU")
        cfg = self.app.cfg
        o = self.app.overlay
        f = QFont(cfg.get("font", "Segoe UI"))
        f.setPixelSize(34)
        f.setWeight(QFont.Weight.Black)
        text = "Les paroles prennent vie"
        fm = QFontMetricsF(f)
        tw = fm.horizontalAdvance(text)
        if tw > r.width() - 40:
            f.setPixelSize(int(34 * (r.width() - 40) / tw))
            fm = QFontMetricsF(f)
            tw = fm.horizontalAdvance(text)
        x = r.center().x() - tw / 2
        y = r.center().y() + fm.ascent() / 2 - 2
        o.draw_text_fx(p, text, f, x, y, o.fill_brush(x, tw, False), o.base_glow())


class Card(QFrame):
    """Bloc de reglages : un titre, une phrase, puis des lignes separees par un trait fin."""

    def __init__(self, title=None, hint=None):
        super().__init__()
        self.setProperty("role", "card")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(22, 20, 22, 20)
        self.lay.setSpacing(14)
        self.rows = 0
        if title:
            t = QLabel(title)
            t.setProperty("role", "cardtitle")
            self.lay.addWidget(t)
            self.title_label = t
        if hint:
            h = QLabel(hint)
            h.setProperty("role", "hint")
            h.setWordWrap(True)
            self.lay.addWidget(h)
            self.hint_label = h

    def add(self, widget):
        self.lay.addWidget(widget)
        return widget

    def add_row(self, label, widget, hint=None):
        """Une ligne : le nom du reglage a gauche, sa commande a droite."""
        if self.rows:
            sep = QFrame()
            sep.setFixedHeight(1)
            sep.setProperty("role", "sep")
            self.lay.addWidget(sep)
        self.rows += 1
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(16)
        box = QVBoxLayout()
        box.setSpacing(2)
        l1 = QLabel(label)
        l1.setProperty("role", "rowtitle")
        box.addWidget(l1)
        w.hint_label = None
        if hint:
            l2 = QLabel(hint)
            l2.setProperty("role", "hint")
            l2.setWordWrap(True)
            box.addWidget(l2)
            w.hint_label = l2
        lay.addLayout(box, 1)
        lay.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)
        w.title_label = l1
        self.lay.addWidget(w)
        return w


def button(text, role="ghost"):
    b = QPushButton(text)
    b.setProperty("role", role)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def hbox(*widgets, spacing=10, stretch=True):
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(spacing)
    for x in widgets:
        lay.addWidget(x)
    if stretch:
        lay.addStretch(1)
    return w


# --------------------------------------------------------------------------
# Le panneau
# --------------------------------------------------------------------------
class Panel(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setObjectName("Panel")
        self.setWindowTitle("FollowTheLyrics")
        self.setWindowIcon(make_icon())
        self.resize(1160, 770)
        self.setMinimumSize(1020, 660)
        self._accent_name = None
        self._cover_src = None
        # Verre : sous Windows 11 la fenetre est transparente et Windows floute ce qu'il y a derriere.
        self._can_glass = sys.getwindowsversion().build >= 22621
        self._glass_ok = False  # Windows a-t-il accepte ?
        if self._can_glass:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._aura = [QColor(c) for c in BRAND]  # couleurs des lueurs du fond (celles de la pochette)
        self._aura_from = list(self._aura)
        self._aura_to = list(self._aura)
        self._aura_anim = make_anim(self, self._aura_step, 900)
        self._building = True
        self._key_note = ""

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.build_sidebar())
        main = QVBoxLayout()
        main.setContentsMargins(34, 26, 20, 0)
        main.setSpacing(16)
        self.page_title = QLabel()
        self.page_title.setProperty("role", "pagetitle")
        self.page_hint = QLabel()
        self.page_hint.setProperty("role", "pagehint")
        head = QVBoxLayout()
        head.setSpacing(2)
        head.addWidget(self.page_title)
        head.addWidget(self.page_hint)
        main.addLayout(head)
        ub = QHBoxLayout()
        ub.setContentsMargins(0, 0, 14, 0)
        ub.addWidget(self.build_update_bar())
        main.addLayout(ub)
        self.stack = QStackedWidget()
        self.pages = {}
        for key, builder in (("home", self.build_home), ("display", self.build_display),
                             ("style", self.build_style), ("music", self.build_music),
                             ("games", self.build_games), ("keys", self.build_keys),
                             ("general", self.build_general)):
            self.pages[key] = self.make_page(builder())
            self.stack.addWidget(self.pages[key])
        main.addWidget(self.stack, 1)
        root.addLayout(main, 1)

        self._fade_fx = None
        self._fade_anim = make_anim(self, self._fade_step, 240)
        self._fade_anim.finished.connect(self._fade_done)
        self._building = False
        self.apply_style(DEFAULT_ACCENT)
        self.go("home", animate=False)
        self.sync_from_cfg()
        self.hotkeys_changed()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(200)
        self.anim_timer = QTimer(self)  # petites animations en boucle (egaliseur, cartes de mode)
        self.anim_timer.timeout.connect(self.tick)
        self.anim_timer.start(33)
        self.refresh()

    # ---- menu lateral ---------------------------------------------------------
    def build_sidebar(self):
        side = QFrame()
        side.setObjectName("Side")
        side.setFixedWidth(244)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(16, 22, 16, 16)
        lay.setSpacing(10)
        brand = QHBoxLayout()
        brand.setSpacing(11)
        logo = QLabel()
        logo.setPixmap(make_icon().pixmap(38, 38))
        brand.addWidget(logo)
        box = QVBoxLayout()
        box.setSpacing(0)
        name = QLabel("FollowTheLyrics")
        name.setProperty("role", "brand")
        import updater
        self.version = updater.current_version()
        ver = QLabel(f"version {self.version}")
        ver.setProperty("role", "hint")
        box.addWidget(name)
        box.addWidget(ver)
        brand.addLayout(box, 1)
        lay.addLayout(brand)
        lay.addSpacing(16)
        self.nav = SideNav([(k, label, icon) for k, label, icon, _t, _h in PAGES])
        self.nav.changed.connect(lambda k: self.go(k))
        lay.addWidget(self.nav)
        lay.addStretch(1)
        self.mini = MiniPlayer()
        self.mini.clicked.connect(lambda: self.nav.select("home"))
        lay.addWidget(self.mini)
        power = QFrame()
        power.setProperty("role", "power")
        pl = QHBoxLayout(power)
        pl.setContentsMargins(14, 12, 12, 12)
        box = QVBoxLayout()
        box.setSpacing(0)
        lbl = QLabel("Paroles à l'écran")
        lbl.setProperty("role", "rowtitle")
        self.master_state = QLabel()
        self.master_state.setProperty("role", "hint")
        box.addWidget(lbl)
        box.addWidget(self.master_state)
        pl.addLayout(box, 1)
        self.master = Toggle()
        self.master.toggled.connect(self.on_master)
        pl.addWidget(self.master)
        lay.addWidget(power)
        return side

    def on_master(self, on):
        self.master_state.setText("Affichées" if on else "Masquées")
        if not self._building:
            self.app.set_visible(on)

    def make_page(self, widgets):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("Content")
        lay = QVBoxLayout(content)
        lay.setContentsMargins(0, 0, 14, 24)
        lay.setSpacing(16)
        for w in widgets:
            lay.addWidget(w)
        lay.addStretch(1)
        scroll.setWidget(content)
        return scroll

    def go(self, key, animate=True):
        """Affiche une page (fondu + leger glissement vers le haut)."""
        info = next(p for p in PAGES if p[0] == key)
        self.nav.select(key, emit=False)
        self.page_title.setText(info[3])
        self.page_hint.setText(info[4])
        page = self.pages[key]
        if self.stack.currentWidget() is page:
            return
        self._fade_done()
        self.stack.setCurrentWidget(page)
        page.verticalScrollBar().setValue(0)
        if animate and self.isVisible():
            self._fade_fx = QGraphicsOpacityEffect(page)
            self._fade_fx.setOpacity(0.0)
            page.setGraphicsEffect(self._fade_fx)
            run_anim(self._fade_anim, 0.0, 1.0)

    def _fade_step(self, v):
        page = self.stack.currentWidget()
        if self._fade_fx is not None and page is not None:
            self._fade_fx.setOpacity(v)
            page.move(0, int(round(16 * (1.0 - v))))

    def _fade_done(self):
        self._fade_anim.stop()
        page = self.stack.currentWidget()
        if self._fade_fx is not None and page is not None:
            page.setGraphicsEffect(None)
            page.move(0, 0)
        self._fade_fx = None

    def tick(self):
        if not self.isVisible():
            return
        page = self.nav.key()
        if page == "home" and self.eq.playing:
            self.eq.update()
        elif page == "display":
            for c in self.mode_cards.values():
                if c.alive():
                    c.update()

    # ---- mise a jour ---------------------------------------------------------
    def build_update_bar(self):
        bar = QFrame()
        bar.setProperty("role", "update")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(18, 12, 12, 12)
        lay.setSpacing(14)
        self.update_lbl = QLabel()
        self.update_lbl.setProperty("role", "rowtitle")
        self.update_lbl.setWordWrap(True)
        lay.addWidget(self.update_lbl, 1)
        self.update_btn = button("Mettre à jour", "main")
        self.update_btn.clicked.connect(self.on_update_click)
        lay.addWidget(self.update_btn)
        bar.hide()
        self.update_bar = bar
        return bar

    def show_update(self, info):
        self.update_lbl.setText(f"La version {info['version']} est disponible. "
                                "La mise à jour se fait toute seule, en gardant tes réglages.")
        self.update_btn.setText("Mettre à jour")
        self.update_btn.setEnabled(True)
        self.update_bar.show()
        self.nav.set_badge("general", True)
        self.check_lbl.setText(f"La version {info['version']} est disponible (bandeau en haut).")
        self.check_btn.setEnabled(True)

    def on_update_click(self):
        self.update_btn.setEnabled(False)
        self.update_btn.setText("Téléchargement…")
        self.app.install_update()

    def update_progress(self, frac):
        self.update_btn.setText(f"Téléchargement {int(frac * 100)} %")
        if frac >= 1.0:
            self.update_lbl.setText("Installation… l'appli va redémarrer toute seule.")

    def update_failed(self, message):
        self.update_lbl.setText(message)
        self.update_btn.setText("Réessayer")
        self.update_btn.setEnabled(True)

    def on_check_click(self):
        self.check_btn.setEnabled(False)
        self.check_lbl.setText("Recherche…")
        self.app.check_update(manual=True)

    def update_none(self, error):
        """Reponse a « Rechercher une mise a jour » quand il n'y a rien de neuf."""
        self.check_btn.setEnabled(True)
        self.check_lbl.setText("Impossible de joindre GitHub. Vérifie ta connexion." if error
                               else "Tu as déjà la dernière version.")

    # ---- page Accueil -----------------------------------------------------------
    def build_home(self):
        hero = Card()
        hero.lay.setSpacing(16)
        top = QHBoxLayout()
        top.setSpacing(22)
        self.cover = CoverView(168, 20)
        top.addWidget(self.cover, 0, Qt.AlignmentFlag.AlignTop)
        box = QVBoxLayout()
        box.setSpacing(4)
        state = QHBoxLayout()
        state.setSpacing(9)
        self.eq = Equalizer()
        state.addWidget(self.eq)
        self.state_lbl = QLabel("EN COURS")
        self.state_lbl.setProperty("role", "section")
        state.addWidget(self.state_lbl)
        state.addStretch(1)
        self.badge = QLabel()
        self.badge.setProperty("role", "badge")
        state.addWidget(self.badge)
        box.addLayout(state)
        box.addSpacing(6)
        self.np_title = QLabel()
        self.np_title.setProperty("role", "nptitle")
        self.np_title.setWordWrap(True)
        self.np_artist = QLabel()
        self.np_artist.setProperty("role", "npartist")
        self.np_artist.setWordWrap(True)
        box.addWidget(self.np_title)
        box.addWidget(self.np_artist)
        box.addStretch(1)
        self.progress = ProgressView()
        box.addWidget(self.progress)
        top.addLayout(box, 1)
        hero.lay.addLayout(top)
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setProperty("role", "sep")
        hero.add(sep)
        cap = QLabel("PAROLES EN DIRECT")
        cap.setProperty("role", "section")
        hero.add(cap)
        self.lyric = QLabel()
        self.lyric.setProperty("role", "lyric")
        self.lyric.setWordWrap(True)
        self.lyric.setMinimumHeight(34)
        hero.add(self.lyric)
        self.lyric_tr = QLabel()
        self.lyric_tr.setProperty("role", "hint")
        self.lyric_tr.setWordWrap(True)
        hero.add(self.lyric_tr)

        self.fs_warn = QLabel()
        self.fs_warn.setProperty("role", "warn")
        self.fs_warn.setWordWrap(True)
        self.fs_warn.hide()

        self.tile_display = NavTile("screen", "Affichage")
        self.tile_style = NavTile("style", "Style")
        self.tile_game = NavTile("game", "Jeu détecté")
        self.tile_display.clicked.connect(lambda: self.nav.select("display"))
        self.tile_style.clicked.connect(lambda: self.nav.select("style"))
        self.tile_game.clicked.connect(lambda: self.nav.select("games"))
        tiles = hbox(self.tile_display, self.tile_style, self.tile_game, spacing=14, stretch=False)

        demo = Card()
        self.demo = Toggle()
        self.demo.toggled.connect(lambda v: None if self._building else self.app.set_demo(v))
        demo.add_row("Essayer sans musique", self.demo,
                     "Des paroles de démonstration tournent en boucle : pratique pour régler le style.")
        return [hero, self.fs_warn, tiles, demo]

    # ---- page Affichage -----------------------------------------------------------
    def build_display(self):
        modes = Card("Mode", "Passe la souris sur une carte pour voir le mode en action.")
        cards = QHBoxLayout()
        cards.setSpacing(12)
        self.mode_group = QButtonGroup(self)
        self.mode_cards = {}
        for key, (title, desc) in MODES.items():
            c = ModeCard(key, title, desc)
            self.mode_group.addButton(c)
            c.clicked.connect(lambda _=False, k=key: self.set("mode", k))
            cards.addWidget(c)
            self.mode_cards[key] = c
        modes.lay.addLayout(cards)

        place = Card("Placement et taille")
        self.position = Segmented(POSITIONS)
        self.position.changed.connect(lambda k: self.set("position", k))
        self.position_row = place.add_row("Position", self.position, "En haut de l'écran : à gauche, au centre ou à droite.")
        self.size = QSlider(Qt.Orientation.Horizontal)
        self.size.setRange(70, 160)
        self.size.setSingleStep(5)
        self.size.setFixedWidth(240)
        self.size_lbl = QLabel()
        self.size_lbl.setProperty("role", "value")
        self.size_lbl.setFixedWidth(52)
        self.size_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.size.valueChanged.connect(self.on_size)
        self.size.sliderReleased.connect(lambda: self.set("scale", self.size.value() / 100))
        place.add_row("Taille du texte", hbox(self.size, self.size_lbl, stretch=False))

        extra = Card("Moments forts")
        self.opt = {}
        self.title_drop = Segmented(TITLE_DROP)
        self.title_drop.changed.connect(lambda k: self.set("title_drop", k))
        extra.add_row("Titre en géant", self.title_drop,
                      "Quand le chanteur dit le titre du morceau, il s'affiche en très grand "
                      "(en jeu : dans un espace libre, jamais sur l'action).")
        self.opt["card"] = Toggle()
        extra.add_row("Carte de la pochette", self.opt["card"],
                      "Pochette, titre et artiste quelques secondes au début du morceau.")
        return [modes, place, extra]

    # ---- page Style -----------------------------------------------------------------
    def build_style(self):
        self.preview = FontPreview(self.app)

        colors = Card("Couleurs du texte")
        row = QHBoxLayout()
        row.setSpacing(12)
        self.color_group = QButtonGroup(self)
        self.color_cards = {
            "album": ColorCard("album", "Couleurs de l'album", "Tirées de la pochette du morceau.",
                               lambda: self.app.overlay.accent[:3]),
            "white": ColorCard("white", "Blanc lumineux", "Blanc avec un léger halo.",
                               lambda: [QColor("#ffffff")]),
        }
        for key, c in self.color_cards.items():
            self.color_group.addButton(c)
            c.clicked.connect(lambda _=False, k=key: self.set("color", k))
            row.addWidget(c)
        colors.lay.addLayout(row)

        motion = Card("Animation")
        self.style = Segmented(STYLES)
        self.style.changed.connect(lambda k: self.set("style", k))
        self.style_row = motion.add_row("Arrivée des mots", self.style, "Pour les modes Classique et Edit.")
        self.opt["beat"] = Toggle()
        motion.add_row("Pulsation sur le beat", self.opt["beat"], "Le texte grossit légèrement sur la grosse caisse.")
        self.opt["particles"] = Toggle()
        motion.add_row("Particules sur les mots tenus", self.opt["particles"],
                       "De petites étincelles quand le chanteur tient une note.")
        self.opt["stack"] = Toggle()
        self.stack_row = motion.add_row("Mots empilés", self.opt["stack"],
                                        "En mode Edit, des rangées de tailles différentes, la plus forte en couleur.")
        self.opt["tilt"] = Toggle()
        self.tilt_row = motion.add_row("Effet 3D sur les côtés", self.opt["tilt"],
                                       "En mode Edit, les lignes à gauche et à droite partent en perspective.")
        self.opt["easter"] = Toggle()
        motion.add_row("Easter eggs", self.opt["easter"],
                       "Quelques morceaux cachent un spectacle spécial. À toi de les trouver.")

        fonts = Card("Police")
        self.font_search = QLineEdit()
        self.font_search.setPlaceholderText("\U0001F50D  Rechercher une police…")
        self.font_search.setClearButtonEnabled(True)
        self.font_search.textChanged.connect(self.filter_fonts)
        fonts.add(self.font_search)
        self.font_list = QListWidget()
        self.font_list.setFixedHeight(264)
        self.font_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.populate_fonts()
        self.font_list.currentItemChanged.connect(self.on_font)
        fonts.add(self.font_list)
        return [self.preview, colors, motion, fonts]

    # ---- page Musique ---------------------------------------------------------------
    def build_music(self):
        src = Card("Applis écoutées",
                   "Décoche celles qui ne servent pas à la musique (par exemple le navigateur où tu regardes "
                   "des vidéos). Les médias de plus de 20 minutes sont toujours ignorés.")
        self.sources_box = QVBoxLayout()
        self.sources_box.setSpacing(12)
        src.lay.addLayout(self.sources_box)
        self._sources_shown = None

        lyr = Card("Paroles")
        self.opt["translation"] = Toggle()
        lyr.add_row("Traduction en français", self.opt["translation"],
                    "Sous la ligne, pour les chansons qui ne sont pas en français.")
        later = button("−", "round")
        earlier = button("+", "round")
        reset = button("Remettre à zéro", "link")
        self.offset_lbl = QLabel()
        self.offset_lbl.setProperty("role", "bigvalue")
        self.offset_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.offset_lbl.setFixedWidth(78)
        later.clicked.connect(lambda: self.set("offset", round(self.app.cfg["offset"] - 0.1, 2)))
        earlier.clicked.connect(lambda: self.set("offset", round(self.app.cfg["offset"] + 0.1, 2)))
        reset.clicked.connect(lambda: self.set("offset", 0.0))
        self.offset_row = lyr.add_row("Calage des paroles", hbox(reset, later, self.offset_lbl, earlier, stretch=False), " ")
        for key, t in self.opt.items():
            t.toggled.connect(lambda v, k=key: self.set(k, bool(v)))
        return [src, lyr]

    def refresh_sources(self):
        blocked = list(self.app.cfg.get("sources_blocked", []))
        ids = list(dict.fromkeys(list(getattr(self.app, "sources", [])) + blocked))
        state = (tuple(ids), tuple(blocked))
        if state == self._sources_shown:
            return
        self._sources_shown = state
        while self.sources_box.count():
            w = self.sources_box.takeAt(0).widget()
            if w:
                w.deleteLater()
        if not ids:
            lbl = QLabel("Aucune appli détectée pour l'instant. Lance une musique.")
            lbl.setProperty("role", "empty")
            self.sources_box.addWidget(lbl)
            return
        for app_id in ids:
            t = Toggle()
            t.setChecked(app_id not in blocked)
            t.toggled.connect(lambda v, a=app_id: self.app.set_source_enabled(a, v))
            line = QWidget()
            lay = QHBoxLayout(line)
            lay.setContentsMargins(0, 0, 0, 0)
            name = QLabel(app_label(app_id))
            name.setProperty("role", "rowtitle")
            lay.addWidget(name, 1)
            lay.addWidget(t)
            self.sources_box.addWidget(line)

    # ---- page Jeux -------------------------------------------------------------------
    def build_games(self):
        cur = Card()
        cap = QLabel("JEU DÉTECTÉ")
        cap.setProperty("role", "section")
        cur.add(cap)
        self.profile_lbl = QLabel("Bureau")
        self.profile_lbl.setProperty("role", "nptitle")
        cur.add(self.profile_lbl)
        hint = QLabel("Les paroles contournent les zones importantes du jeu : vie, minimap, score, sorts…")
        hint.setProperty("role", "hint")
        hint.setWordWrap(True)
        cur.add(hint)
        draw = button("Dessiner les zones…", "main")
        show = button("Voir les zones 5 secondes")
        draw.clicked.connect(lambda: self.app.open_zone_editor())
        show.clicked.connect(self.app.show_zones)
        cur.add(hbox(draw, show))

        self.fs_warn2 = QLabel()
        self.fs_warn2.setProperty("role", "warn")
        self.fs_warn2.setWordWrap(True)
        self.fs_warn2.hide()

        how = Card("Ajouter un jeu en 3 étapes")
        self.step_labels = []
        for n in range(3):
            num = QLabel(str(n + 1))
            num.setProperty("role", "step")
            num.setFixedSize(30, 30)
            num.setAlignment(Qt.AlignmentFlag.AlignCenter)
            txt = QLabel()
            txt.setProperty("role", "steptext")
            txt.setWordWrap(True)
            line = QWidget()
            lay = QHBoxLayout(line)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(14)
            lay.addWidget(num, 0, Qt.AlignmentFlag.AlignTop)
            lay.addWidget(txt, 1)
            how.add(line)
            self.step_labels.append(txt)
        self.step_labels[1].setText("Reviens ici : la capture s'ouvre toute seule. Dessine à la souris un rectangle "
                                    "sur chaque endroit à protéger.")
        self.step_labels[2].setText("Clique sur « Enregistrer ». C'est appliqué tout de suite, sans relancer le jeu.")

        tip = Card("Le jeu cache les paroles ?")
        t = QLabel("Mets tes jeux en « fenêtré sans bordure » dans leurs options vidéo. En plein écran exclusif, "
                   "Windows n'affiche aucune fenêtre par-dessus le jeu.")
        t.setProperty("role", "hint")
        t.setWordWrap(True)
        tip.add(t)
        return [cur, self.fs_warn2, how, tip]

    # ---- page Raccourcis -----------------------------------------------------------------
    def build_keys(self):
        card = Card("Tes raccourcis", "Clique sur un raccourci, puis appuie sur la nouvelle combinaison "
                    "(avec Ctrl ou Alt, ou une touche F1 à F24). Échap annule, Suppr retire le raccourci.")
        self.key_buttons = {}
        for name, label, _default in hotkeys.ACTIONS:
            b = HotkeyButton()
            b.started.connect(self.app.hotkeys.pause)
            b.ended.connect(self.app.hotkeys.resume)
            b.captured.connect(lambda combo, n=name: self.on_key_captured(n, combo))
            card.add_row(label, b)
            self.key_buttons[name] = b
        self.key_msg = QLabel()
        self.key_msg.setProperty("role", "warn")
        self.key_msg.setWordWrap(True)
        self.key_msg.hide()
        reset = button("Remettre les raccourcis d'origine")
        reset.clicked.connect(self.on_keys_reset)
        return [card, self.key_msg, hbox(reset)]

    def on_key_captured(self, name, combo):
        stolen = self.app.set_hotkey(name, combo)
        self._key_note = (f"« {hotkeys.LABELS[stolen]} » utilisait déjà {hotkeys.pretty(combo)} : "
                          "ce raccourci lui a été retiré.") if stolen else ""
        self.hotkeys_changed()

    def on_keys_reset(self):
        self._key_note = ""
        self.app.reset_hotkeys()
        self.hotkeys_changed()

    def hotkeys_changed(self):
        """Les raccourcis ont change (ou Windows vient de dire lesquels il refuse)."""
        keys = self.app.cfg["hotkeys"]
        failed = [n for n in getattr(self.app, "hotkeys_failed", []) if keys.get(n)]
        for name, b in self.key_buttons.items():
            b.set_combo(keys.get(name, ""), name in failed)
        notes = [self._key_note] if self._key_note else []
        if failed:
            notes.append("Windows refuse " + ", ".join(hotkeys.pretty(keys[n]) for n in failed) +
                         " : cette combinaison est déjà prise par une autre appli. Choisis-en une autre.")
        self.key_msg.setText("\n".join(notes))
        self.key_msg.setVisible(bool(notes))
        capture = keys.get("capture", "")
        self.step_labels[0].setText(
            f"Dans le jeu, appuie sur {hotkeys.pretty(capture)} : une capture est prise, sans les paroles."
            if capture else "Donne d'abord un raccourci à « Capturer le jeu » dans la page Raccourcis.")
        up, down = keys.get("earlier", ""), keys.get("later", "")
        tip = "Paroles en retard : appuie sur +. En avance : appuie sur −."
        if up and down:
            tip += f"\nEn jeu : {hotkeys.pretty(up)} et {hotkeys.pretty(down)}."
        self.offset_row.hint_label.setText(tip)

    # ---- page General ----------------------------------------------------------------------
    def build_general(self):
        start = Card("Démarrage")
        self.autostart = Toggle()
        self.autostart.setChecked(autostart_enabled())
        self.autostart.toggled.connect(lambda v: None if self._building else set_autostart(bool(v)))
        start.add_row("Lancer avec Windows", self.autostart,
                      "Démarre tout seul à l'allumage du PC, discrètement près de l'heure.")

        cards = [start]
        if self._can_glass:
            look = Card("Apparence")
            self.glass = Toggle()
            self.glass.setChecked(bool(self.app.cfg.get("glass", True)))
            self.glass.toggled.connect(lambda v: None if self._building else self.set("glass", bool(v)))
            look.add_row("Panneau en verre", self.glass,
                         "Laisse voir, flouté, ce qu'il y a derrière cette fenêtre.")
            cards.append(look)
        if FROZEN:
            import install
            setup = Card("Installation")
            if install.running_installed():
                b = button("Désinstaller")
                b.clicked.connect(self.app.uninstall)
                setup.add_row("Installée sur ce PC", b, "L'appli est dans le menu Démarrer et dans les "
                              "applications installées de Windows.")
            else:
                b = button("Installer")
                b.clicked.connect(lambda: self.app.install_here())
                setup.add_row("Installer sur ce PC", b, "Range l'appli à sa place avec une icône dans le menu "
                              "Démarrer. Tu pourras ensuite jeter le fichier téléchargé.")
            cards.append(setup)

        upd = Card("Mises à jour")
        self.check_btn = button("Rechercher une mise à jour")
        self.check_btn.clicked.connect(self.on_check_click)
        row = upd.add_row(f"Version {self.version}", self.check_btn,
                          "L'appli vérifie toute seule de temps en temps et te prévient ici.")
        self.check_lbl = row.hint_label

        about = Card("À propos")
        site = button("Ouvrir le site")
        site.clicked.connect(lambda: os.startfile(SITE_URL))
        about.add_row("FollowTheLyrics", site, "Les paroles de ta musique, par-dessus tes jeux. Gratuit et libre.")
        return cards + [upd, about]

    # ---- polices -----------------------------------------------------------
    def populate_fonts(self):
        skip = ("MDL2", "Fluent Icons", "Wingdings", "Webdings", "Marlett", "Symbol", "Emoji", "HoloLens",
                "Segoe Fluent", "Bookshelf", "MT Extra")
        fams = []
        for f in QFontDatabase.families():
            if QFontDatabase.isPrivateFamily(f) or any(s in f for s in skip):
                continue
            if QFontDatabase.WritingSystem.Latin not in QFontDatabase.writingSystems(f):
                continue
            fams.append(f)
        rec = [f for f in RECOMMENDED_FONTS if f in fams]
        rest = sorted((f for f in fams if f not in rec), key=str.lower)
        self._font_items = []

        def header(text):
            it = QListWidgetItem(text)
            it.setFlags(Qt.ItemFlag.NoItemFlags)
            it.setFont(ui_font(10, QFont.Weight.Bold))
            it.setForeground(QColor(DIM))
            it.setData(Qt.ItemDataRole.UserRole + 1, "header")
            self.font_list.addItem(it)

        header("RECOMMANDÉES")
        for f in rec:
            self._add_font_item(f)
        header("TOUTES LES POLICES")
        for f in rest:
            self._add_font_item(f)

    def _add_font_item(self, fam):
        it = QListWidgetItem(fam)
        f = QFont(fam)
        f.setPixelSize(17)
        it.setFont(f)
        it.setData(Qt.ItemDataRole.UserRole, fam)
        it.setSizeHint(QSize(0, 38))
        self.font_list.addItem(it)
        self._font_items.append(it)

    def filter_fonts(self, text):
        q = text.strip().lower()
        for i in range(self.font_list.count()):
            it = self.font_list.item(i)
            if it.data(Qt.ItemDataRole.UserRole + 1) == "header":
                it.setHidden(bool(q))
            else:
                it.setHidden(bool(q) and q not in it.text().lower())

    def on_font(self, cur, _prev):
        if self._building or cur is None:
            return
        fam = cur.data(Qt.ItemDataRole.UserRole)
        if fam:
            self.set("font", fam)

    def on_size(self, v):
        self.size_lbl.setText(f"{v} %")
        if not self.size.isSliderDown() and not self._building:
            self.set("scale", v / 100)

    # ---- reglages ----------------------------------------------------------
    def set(self, key, value):
        if self._building:
            return
        if self.app.cfg.get(key) == value:
            return
        self.app.set_cfg(key, value)
        self.sync_from_cfg()
        if key == "glass":
            self.update()

    def sync_from_cfg(self):
        cfg = self.app.cfg
        self._building = True
        try:
            self.mode_cards[cfg["mode"]].setChecked(True)
            self.position.set_value(cfg["position"])
            column = cfg["mode"] in ("classic", "typewriter")
            self.position.setEnabled(column)
            self.position_row.setEnabled(column)
            self.color_cards[cfg["color"]].setChecked(True)
            self.style.set_value(cfg["style"])
            self.title_drop.set_value(cfg.get("title_drop", "always"))
            self.style_row.setEnabled(cfg["mode"] != "typewriter")
            self.style.setEnabled(cfg["mode"] != "typewriter")
            self.size.setValue(int(round(cfg["scale"] * 100)))
            self.size_lbl.setText(f"{self.size.value()} %")
            for k, t in self.opt.items():
                t.setChecked(bool(cfg.get(k, True)))
            self.demo.setChecked(self.app.demo)
            self.autostart.setChecked(autostart_enabled())
            self.master.setChecked(not self.app.overlay.user_hidden)
            self.master_state.setText("Affichées" if self.master.isChecked() else "Masquées")
            self.offset_lbl.setText(f"{cfg['offset']:+.1f} s")
            fam = cfg.get("font")
            for it in self._font_items:
                if it.data(Qt.ItemDataRole.UserRole) == fam:
                    self.font_list.setCurrentItem(it)
                    break
        finally:
            self._building = False
        mode = MODES[cfg["mode"]][0]
        self.tile_display.set_value(f"{mode} · {POSITIONS[cfg['position']]}" if column else mode)
        self.tile_style.set_value(f"{'Album' if cfg['color'] == 'album' else 'Blanc'} · {STYLES[cfg['style']]}")
        self.preview.update()
        for c in list(self.mode_cards.values()) + list(self.color_cards.values()):
            c.update()

    # ---- musique en cours ---------------------------------------------------
    def refresh(self):
        if not self.isVisible():
            return
        o = self.app.overlay
        self.refresh_sources()
        t = o.track
        if t is not None:
            self.np_title.setText(t.title)
            self.np_artist.setText(t.artist or "")
            dur = t.duration if 0 < (t.duration or 0) < 4 * 3600 else 0
            self.progress.set_values(o.raw_position(), dur)
            self.state_lbl.setText("EN COURS" if o.playing else "EN PAUSE")
            self.mini.set_track(t.title, t.artist or "", o.cover_img)
        else:
            self.np_title.setText("Aucune musique")
            self.np_artist.setText("Lance un morceau sur Spotify, YouTube Music, Deezer… les paroles arrivent toutes seules.")
            self.progress.set_values(0, 0)
            self.state_lbl.setText("EN ATTENTE")
            self.mini.set_track("Aucune musique", "En attente…", None)
        playing = bool(t is not None and o.playing)
        if playing != self.eq.playing:
            self.eq.playing = playing
            self.eq.update()
        if o.cover_img is not self._cover_src:
            self._cover_src = o.cover_img
            self.cover.set_image(o.cover_img)
        badge = o.card_badge() if t is not None else ""
        kind = "word" if (o.state == "ok" and o.word_sync) else "line"
        if badge != self.badge.text() or kind != self.badge.property("kind"):
            self.badge.setText(badge)
            self.badge.setProperty("kind", kind)
            self.badge.style().unpolish(self.badge)
            self.badge.style().polish(self.badge)
        self.badge.setVisible(bool(badge))
        txt = o.current_text()
        if o.state == "ok":
            self.lyric.setText(txt or "♪  …")
            line = o.lines[o.cur["idx"]] if (o.cur and o.lines) else None
            self.lyric_tr.setText(line.translation if (line and line.translation and o.cfg.get("translation")) else "")
        elif o.state == "loading":
            self.lyric.setText("Recherche des paroles…")
            self.lyric_tr.setText("")
        elif o.state == "missing":
            self.lyric.setText("Pas de paroles synchronisées pour ce titre.")
            self.lyric_tr.setText("")
        else:
            self.lyric.setText("—")
            self.lyric_tr.setText("")
        self.lyric_tr.setVisible(bool(self.lyric_tr.text()))
        game = o.profile.get("nom", o.profile_key) or "Bureau"
        self.profile_lbl.setText(game)
        self.tile_game.set_value(game)
        if getattr(self.app, "exclusive", False):
            msg = ("⚠  Plein écran exclusif détecté : les paroles ne peuvent pas passer "
                   "par-dessus le jeu. " + (self.app.exclusive_tip or ""))
            for w in (self.fs_warn, self.fs_warn2):
                w.setText(msg)
                w.show()
        else:
            self.fs_warn.hide()
            self.fs_warn2.hide()
        accent = QColor(o.accent[0]) if o.cover_img is not None else DEFAULT_ACCENT
        if accent.name() != self._accent_name:
            self.apply_style(accent)
            self.preview.update()
        aura = [QColor(c) for c in (o.accent[:3] if o.cover_img is not None and len(o.accent) >= 3 else BRAND)]
        if [c.name() for c in aura] != [c.name() for c in self._aura_to]:
            self._aura_from, self._aura_to = list(self._aura), aura  # fondu vers les nouvelles couleurs
            run_anim(self._aura_anim, 0.0, 1.0)

    def _aura_step(self, v):
        self._aura = [mix(a, b, v) for a, b in zip(self._aura_from, self._aura_to)]
        self.update()

    def glass_on(self):
        """Vrai si le fond laisse voir, floute, ce qu'il y a derriere la fenetre."""
        return self._glass_ok and bool(self.app.cfg.get("glass", True))

    # ---- style ---------------------------------------------------------------
    def apply_style(self, accent: QColor):
        self._accent_name = accent.name()
        UI["accent"] = QColor(accent)
        a = accent.name()
        r, g, b = accent.red(), accent.green(), accent.blue()
        ft = '"Segoe UI Variable Text"'
        # verre : plus clair en haut a gauche, comme eclaire de la
        glass = ("qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(255,255,255,0.105), "
                 "stop:0.45 rgba(255,255,255,0.055), stop:1 rgba(255,255,255,0.03))")
        edge, field = qss(CARD_BORDER), qss(FIELD)
        fd = '"Segoe UI Variable Display"'
        self.setStyleSheet(f"""
            QWidget#Panel {{ background: transparent; }}
            QFrame#Side {{ background: rgba(255,255,255,0.035); border: none; border-right: 1px solid rgba(255,255,255,0.10); }}
            QWidget#Content {{ background: transparent; }}
            QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; }}
            QStackedWidget {{ background: transparent; }}
            QLabel {{ color: {TEXT}; background: transparent; }}
            QFrame[role="card"] {{ background: {glass}; border: 1px solid {edge}; border-radius: 22px; }}
            QFrame[role="power"] {{ background: {glass}; border: 1px solid {edge}; border-radius: 15px; }}
            QFrame[role="sep"] {{ background: rgba(255,255,255,0.09); border: none; }}
            QLabel[role="brand"] {{ font: 800 17px {fd}; }}
            QLabel[role="pagetitle"] {{ font: 800 30px {fd}; }}
            QLabel[role="pagehint"] {{ color: {DIM}; font: 14px {ft}; }}
            QLabel[role="cardtitle"] {{ font: 700 17px {fd}; }}
            QLabel[role="section"] {{ color: {DIM}; font: 700 11px {ft}; letter-spacing: 1.6px; }}
            QLabel[role="rowtitle"] {{ color: {TEXT}; font: 600 14px {ft}; }}
            QLabel[role="rowtitle"]:disabled {{ color: #5a5f6e; }}
            QLabel[role="hint"] {{ color: {DIM}; font: 12px {ft}; }}
            QLabel[role="hint"]:disabled {{ color: #4b5060; }}
            QLabel[role="empty"] {{ color: {DIM}; font: 13px {ft}; padding: 10px 0; }}
            QLabel[role="value"] {{ color: {TEXT}; font: 600 13px {ft}; }}
            QLabel[role="bigvalue"] {{ color: {TEXT}; font: 700 16px {fd}; }}
            QLabel[role="nptitle"] {{ font: 800 27px {fd}; }}
            QLabel[role="npartist"] {{ color: {DIM}; font: 15px {ft}; }}
            QLabel[role="lyric"] {{ font: 700 21px {fd}; color: {a}; }}
            QLabel[role="steptext"] {{ color: {TEXT}; font: 14px {ft}; padding-top: 5px; }}
            QLabel[role="step"] {{ color: {BG}; background: {a}; border-radius: 15px; font: 800 14px {fd}; }}
            QLabel[role="badge"] {{ font: 700 10px {ft}; padding: 3px 9px; border-radius: 9px;
                                    color: #b9bdc9; background: rgba(185,189,201,0.12); border: 1px solid rgba(185,189,201,0.35); }}
            QLabel[role="badge"][kind="word"] {{ color: {a}; background: rgba({r},{g},{b},0.14); border: 1px solid rgba({r},{g},{b},0.6); }}
            QPushButton[role="ghost"] {{ background: {field}; color: {TEXT}; border: 1px solid {edge};
                                         padding: 9px 16px; border-radius: 12px; font: 600 13px {ft}; }}
            QPushButton[role="ghost"]:hover {{ border-color: {a}; background: rgba(255,255,255,0.15); }}
            QPushButton[role="ghost"]:pressed {{ background: rgba({r},{g},{b},0.2); }}
            QPushButton[role="ghost"]:disabled {{ color: #5a5f6e; }}
            QPushButton[role="round"] {{ background: {field}; color: {TEXT}; border: 1px solid {edge};
                                         min-width: 38px; max-width: 38px; min-height: 38px; max-height: 38px;
                                         border-radius: 19px; font: 700 18px {fd}; padding: 0 0 3px 0; }}
            QPushButton[role="round"]:hover {{ border-color: {a}; color: {a}; }}
            QPushButton[role="round"]:pressed {{ background: rgba({r},{g},{b},0.25); }}
            QPushButton[role="link"] {{ background: transparent; color: {DIM}; border: none; padding: 6px 8px;
                                        font: 600 12px {ft}; }}
            QPushButton[role="link"]:hover {{ color: {a}; }}
            QPushButton[role="main"] {{ background: {a}; color: {BG}; border: none; padding: 10px 20px;
                                        border-radius: 12px; font: 800 13px {ft}; }}
            QPushButton[role="main"]:hover {{ background: rgba({r},{g},{b},0.86); }}
            QPushButton[role="main"]:disabled {{ background: rgba({r},{g},{b},0.3); color: #c7cbd6; }}
            QFrame[role="update"] {{ background: rgba({r},{g},{b},0.13); border: 1px solid rgba({r},{g},{b},0.6);
                                     border-radius: 14px; }}
            QLineEdit {{ background: rgba(0,0,0,0.26); color: {TEXT}; border: 1px solid {edge}; border-radius: 12px;
                         padding: 9px 12px; font: 14px {ft}; selection-background-color: {a}; }}
            QLineEdit:focus {{ border-color: {a}; }}
            QListWidget {{ background: rgba(0,0,0,0.24); color: {TEXT}; border: 1px solid {edge}; border-radius: 14px;
                           padding: 6px; outline: none; }}
            QListWidget::item {{ padding: 4px 10px; border-radius: 8px; }}
            QListWidget::item:hover {{ background: rgba(255,255,255,0.08); }}
            QListWidget::item:selected {{ background: rgba({r},{g},{b},0.22); color: white; }}
            QSlider::groove:horizontal {{ height: 6px; background: rgba(255,255,255,0.15); border-radius: 3px; }}
            QSlider::sub-page:horizontal {{ background: {a}; border-radius: 3px; }}
            QSlider::handle:horizontal {{ background: white; width: 18px; height: 18px; margin: -6px 0; border-radius: 9px; }}
            QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
            QScrollBar::handle:vertical {{ background: rgba(255,255,255,0.16); border-radius: 4px; min-height: 30px; }}
            QScrollBar::handle:vertical:hover {{ background: rgba(255,255,255,0.30); }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
            QLabel[role="warn"] {{ color: #ffcf7a; background: rgba(255,170,60,0.10); border: 1px solid rgba(255,170,60,0.45);
                                   border-radius: 12px; padding: 11px 14px; font: 600 13px {ft}; }}
        """)
        for w in self.findChildren(QWidget):
            w.update()
        self.update()

    def paintEvent(self, _):
        """Le fond : une teinte sombre (a moitie transparente quand le verre de Windows est la),
        puis trois lueurs aux couleurs de la pochette. Les cartes de verre se posent dessus."""
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        glass = self.glass_on()
        if self._can_glass:
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            p.fillRect(self.rect(), QColor(9, 10, 16, 138 if glass else 255))
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        else:
            p.fillRect(self.rect(), QColor(BG))
        w, h = self.width(), self.height()
        for (cx, cy, radius, strength), col in zip(((0.06, 0.0, 0.66, 92), (1.0, 0.16, 0.56, 66),
                                                    (0.56, 1.08, 0.62, 58)), self._aura):
            g = QRadialGradient(QPointF(w * cx, h * cy), w * radius)
            g.setColorAt(0, alpha(col, strength))
            g.setColorAt(1, alpha(col, 0))
            p.fillRect(self.rect(), QBrush(g))

    def showEvent(self, e):
        super().showEvent(e)
        try:  # barre de titre sombre (Windows 10/11)
            val = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(int(self.winId()), 20, ctypes.byref(val), ctypes.sizeof(val))
        except Exception:
            pass
        if self._can_glass and not self._glass_ok:
            self._glass_ok = enable_backdrop(self.winId())
        dark_caption(self.winId())
        self.refresh()

    def closeEvent(self, e):
        """Fermer le panneau ne quitte pas : les paroles continuent (icone pres de l'heure pour le rouvrir)."""
        if getattr(self.app, "quitting", False):
            e.accept()
            return
        e.ignore()
        self.hide()
        try:
            self.app.tray.showMessage("FollowTheLyrics", "Toujours actif. Clique sur l'icône près de l'heure pour rouvrir le panneau.",
                                      make_icon(), 2500)
        except Exception:
            pass
