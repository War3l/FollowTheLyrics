import logging

from PyQt6.QtCore import QPointF
from PyQt6.QtCore import QRectF
from PyQt6.QtCore import QSize
from PyQt6.QtCore import Qt
from PyQt6.QtCore import QTimer
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QBrush
from PyQt6.QtGui import QColor
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtGui import QFont
from PyQt6.QtGui import QFontDatabase
from PyQt6.QtGui import QFontMetricsF
from PyQt6.QtGui import QPainter
from PyQt6.QtGui import QPen
from PyQt6.QtGui import QPixmap
from PyQt6.QtGui import QRadialGradient
from PyQt6.QtWidgets import QButtonGroup
from PyQt6.QtWidgets import QFrame
from PyQt6.QtWidgets import QGraphicsDropShadowEffect
from PyQt6.QtWidgets import QGraphicsOpacityEffect
from PyQt6.QtWidgets import QGridLayout
from PyQt6.QtWidgets import QHBoxLayout
from PyQt6.QtWidgets import QLabel
from PyQt6.QtWidgets import QLineEdit
from PyQt6.QtWidgets import QListWidget
from PyQt6.QtWidgets import QListWidgetItem
from PyQt6.QtWidgets import QPushButton
from PyQt6.QtWidgets import QScrollArea
from PyQt6.QtWidgets import QSlider
from PyQt6.QtWidgets import QStackedWidget
from PyQt6.QtWidgets import QVBoxLayout
from PyQt6.QtWidgets import QWidget

from followthelyrics import i18n
from followthelyrics import version
from followthelyrics.config import settings
from followthelyrics.desktop import ports
from followthelyrics.playback import sites
from followthelyrics.system import hotkeys
from followthelyrics.ui import logos
from followthelyrics.ui import widgets

logger = logging.getLogger(__name__)

TITLE_BAR = ports.TitleBarColors(
    caption="#0a0a0c", border="#2a2a2e", text="#f6f6f4"
)

SITE_URL = "https://war3l.github.io/FollowTheLyrics/"
AUTHOR_URL = "https://github.com/War3l"

IDLE_AURA = ("#3c3c42", "#26262a", "#303036")

PAGES = [
    (
        "home",
        "Accueil",
        "home",
        "Accueil",
        "Ce qui joue, et l'essentiel à portée de main.",
    ),
    (
        "display",
        "Affichage",
        "screen",
        "Affichage",
        "Où et comment les paroles s'affichent.",
    ),
    (
        "style",
        "Style",
        "style",
        "Style",
        "Couleurs, animation et police.",
    ),
    (
        "music",
        "Musique",
        "music",
        "Musique",
        "Sources, traduction et calage.",
    ),
    (
        "games",
        "Jeux",
        "game",
        "Jeux",
        "Les zones que les paroles évitent.",
    ),
    (
        "keys",
        "Raccourcis",
        "keys",
        "Raccourcis",
        "Ils marchent même en pleine partie.",
    ),
    (
        "general",
        "Général",
        "sliders",
        "Général",
        "Démarrage, mises à jour, à propos.",
    ),
]


class FontPreview(QWidget):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.setFixedHeight(104)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(widgets.CARD_BORDER), 1))
        p.setBrush(QColor(widgets.WELL))
        p.drawRoundedRect(r, 26, 26)
        p.setPen(QColor(widgets.DIM))
        p.setFont(widgets.ui_font(12))
        p.drawText(
            r.adjusted(20, 12, 0, 0),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
            i18n.tr("Aperçu"),
        )
        cfg = self.app.cfg
        o = self.app.overlay
        f = QFont(cfg.get("font", "Segoe UI"))
        f.setPixelSize(34)
        f.setWeight(QFont.Weight.Black)
        text = i18n.tr("Les paroles prennent vie")
        fm = QFontMetricsF(f)
        tw = fm.horizontalAdvance(text)
        if tw > r.width() - 40:
            f.setPixelSize(int(34 * (r.width() - 40) / tw))
            fm = QFontMetricsF(f)
            tw = fm.horizontalAdvance(text)
        x = r.center().x() - tw / 2
        y = r.center().y() + fm.ascent() / 2 - 2
        o.draw_text_fx(
            p, text, f, x, y, o.fill_brush(x, tw, False), o.base_glow()
        )


class SettingRow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.title_label: QLabel | None = None
        self.hint_label: QLabel | None = None


class Card(QFrame):
    def __init__(self, title=None, hint=None):
        super().__init__()
        self.setProperty("role", "card")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(24, 22, 24, 22)
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
        if self.rows:
            sep = QFrame()
            sep.setFixedHeight(1)
            sep.setProperty("role", "sep")
            self.lay.addWidget(sep)
        self.rows += 1
        w = SettingRow()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(16)
        box = QVBoxLayout()
        box.setSpacing(2)
        l1 = QLabel(label)
        l1.setProperty("role", "rowtitle")
        box.addWidget(l1)
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


def logo_label(key, name):
    size = 22
    label = QLabel()
    label.setFixedSize(size, size)
    pm = QPixmap(size * 2, size * 2)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    logo = logos.pixmap(key)
    if logo is not None:
        p.drawPixmap(
            QRectF(0, 0, size * 2, size * 2), logo, QRectF(logo.rect())
        )
    else:
        p.setPen(QPen(QColor(255, 255, 255, 90), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(1, 1, size * 2 - 2, size * 2 - 2))
        p.setPen(QColor(widgets.TEXT))
        p.setFont(widgets.ui_font(22, QFont.Weight.Bold))
        p.drawText(
            QRectF(0, 0, size * 2, size * 2),
            Qt.AlignmentFlag.AlignCenter,
            name[:1].upper(),
        )
    p.end()
    pm.setDevicePixelRatio(2.0)
    label.setPixmap(pm)
    return label


def translated(options):
    return {key: i18n.tr(label) for key, label in options.items()}


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


class Panel(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setObjectName("Panel")
        self.setWindowTitle("FollowTheLyrics")
        self.setWindowIcon(widgets.make_icon())
        self.resize(1160, 770)
        self.setMinimumSize(1020, 660)
        self._accent_name = None
        self._cover_src = None
        self._windowing = app.desktop.windowing
        self._can_glass = self._windowing.supports_backdrop()
        self._glass_ok = False
        if self._can_glass:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._aura = [QColor(c) for c in IDLE_AURA]
        self._aura_from = list(self._aura)
        self._aura_to = list(self._aura)
        self._aura_anim = widgets.make_anim(self, self._aura_step, 1100)
        self._building = True
        self._key_note = ""

        main = QVBoxLayout(self)
        main.setContentsMargins(36, 20, 22, 0)
        main.setSpacing(18)
        main.addWidget(self.build_topbar())
        main.addSpacing(6)
        self.page_title = QLabel()
        self.page_title.setProperty("role", "pagetitle")
        self._title_glow = QGraphicsDropShadowEffect(self.page_title)
        self._title_glow.setOffset(0, 0)
        self._title_glow.setBlurRadius(34)
        self.page_title.setGraphicsEffect(self._title_glow)
        self.page_hint = QLabel()
        self.page_hint.setProperty("role", "pagehint")
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 16, 0)
        head.setSpacing(18)
        head.addWidget(self.page_title)
        head.addWidget(self.page_hint, 1, Qt.AlignmentFlag.AlignBottom)
        main.addLayout(head)
        ub = QHBoxLayout()
        ub.setContentsMargins(0, 0, 14, 0)
        ub.addWidget(self.build_update_bar())
        main.addLayout(ub)
        self.stack = QStackedWidget()
        self.pages = {}
        for key, builder in (
            ("home", self.build_home),
            ("display", self.build_display),
            ("style", self.build_style),
            ("music", self.build_music),
            ("games", self.build_games),
            ("keys", self.build_keys),
            ("general", self.build_general),
        ):
            self.pages[key] = self.make_page(builder())
            self.stack.addWidget(self.pages[key])
        main.addWidget(self.stack, 1)

        self._fade_fx = None
        self._fade_anim = widgets.make_anim(self, self._fade_step, 240)
        self._fade_anim.finished.connect(self._fade_done)
        self._building = False
        self.apply_style(widgets.DEFAULT_ACCENT)
        self.go("home", animate=False)
        self.sync_from_cfg()
        self.hotkeys_changed()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(200)
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self.tick)
        self.anim_timer.start(33)
        self.refresh()

    def build_topbar(self):
        bar = QWidget()
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(0, 0, 14, 0)
        lay.setSpacing(12)
        mark = QPixmap(92, 92)
        mark.fill(Qt.GlobalColor.transparent)
        painter = QPainter(mark)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        widgets.draw_logo_glow(painter, QRectF(14, 14, 64, 64))
        painter.end()
        mark.setDevicePixelRatio(2.0)
        logo = QLabel()
        logo.setPixmap(mark)
        logo.setFixedSize(46, 46)
        logo.setToolTip(f"FollowTheLyrics {version.current()}")
        lay.addWidget(logo)
        self.version = version.current()
        lay.addStretch(1)
        self.nav = widgets.TopNav(
            [(k, i18n.tr(label), icon) for k, label, icon, _t, _h in PAGES]
        )
        self.nav.changed.connect(self.go)
        lay.addWidget(self.nav)
        lay.addStretch(1)
        self.mini = widgets.MiniPlayer()
        self.mini.clicked.connect(lambda: self.nav.select("home"))
        lay.addWidget(self.mini)
        self.master_state = QLabel(bar)
        self.master_state.hide()
        self.master = widgets.Toggle()
        self.master.toggled.connect(self.on_master)
        lay.addWidget(self.master)
        return bar

    def on_master(self, on):
        self.master_state.setText(
            i18n.tr("Affichées") if on else i18n.tr("Masquées")
        )
        self.master.setToolTip(
            i18n.tr("Paroles affichées") if on else i18n.tr("Paroles masquées")
        )
        if not self._building:
            self.app.set_visible(on)

    def make_page(self, widgets):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        content = QWidget()
        content.setObjectName("Content")
        lay = QVBoxLayout(content)
        lay.setContentsMargins(0, 0, 14, 24)
        lay.setSpacing(14)
        for w in widgets:
            lay.addWidget(w)
        lay.addStretch(1)
        scroll.setWidget(content)
        return scroll

    def go(self, key, animate=True):
        info = next(p for p in PAGES if p[0] == key)
        self.nav.select(key, emit=False)
        self.page_title.setText(i18n.tr(info[3]))
        self.page_hint.setText(i18n.tr(info[4]))
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
            widgets.run_anim(self._fade_anim, 0.0, 1.0)

    def _fade_step(self, v):
        page = self.stack.currentWidget()
        if self._fade_fx is not None and page is not None:
            self._fade_fx.setOpacity(v)
            page.move(0, round(16 * (1.0 - v)))

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
        self.update_btn = button(i18n.tr("Mettre à jour"), "main")
        self.update_btn.clicked.connect(self.on_update_click)
        lay.addWidget(self.update_btn)
        bar.hide()
        self.update_bar = bar
        return bar

    def show_update(self, info):
        self.update_lbl.setText(
            i18n.tr(
                "La version {} est disponible. La mise à jour se fait "
                "toute seule, en gardant tes réglages."
            ).format(info["version"])
        )
        self.update_btn.setText(i18n.tr("Mettre à jour"))
        self.update_btn.setEnabled(True)
        self.update_bar.show()
        self.nav.set_badge("general", True)
        self.check_lbl.setText(
            i18n.tr("La version {} est disponible (bandeau en haut).").format(
                info["version"]
            )
        )
        self.check_btn.setEnabled(True)

    def on_update_click(self):
        self.update_btn.setEnabled(False)
        self.update_btn.setText(i18n.tr("Téléchargement…"))
        self.app.install_update()

    def update_progress(self, frac):
        self.update_btn.setText(
            i18n.tr("Téléchargement {} %").format(int(frac * 100))
        )
        if frac >= 1.0:
            self.update_lbl.setText(
                i18n.tr("Installation… l'appli va redémarrer toute seule.")
            )

    def update_failed(self, message):
        self.update_lbl.setText(message)
        self.update_btn.setText(i18n.tr("Réessayer"))
        self.update_btn.setEnabled(True)

    def on_check_click(self):
        self.check_btn.setEnabled(False)
        self.check_lbl.setText(i18n.tr("Recherche…"))
        self.app.check_update(manual=True)

    def update_none(self, error):
        self.check_btn.setEnabled(True)
        self.check_lbl.setText(
            i18n.tr("Impossible de joindre GitHub. Vérifie ta connexion.")
            if error
            else i18n.tr("Tu as déjà la dernière version.")
        )

    def build_home(self):
        hero = Card()
        hero.lay.setSpacing(16)
        top = QHBoxLayout()
        top.setSpacing(22)
        self.cover = widgets.CoverView(148, 24)
        top.addWidget(self.cover, 0, Qt.AlignmentFlag.AlignTop)
        box = QVBoxLayout()
        box.setSpacing(4)
        state = QHBoxLayout()
        state.setSpacing(9)
        self.eq = widgets.Equalizer()
        state.addWidget(self.eq)
        self.state_lbl = QLabel(i18n.tr("En cours"))
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
        self.progress = widgets.ProgressView()
        box.addWidget(self.progress)
        top.addLayout(box, 1)
        hero.lay.addLayout(top)
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setProperty("role", "sep")
        hero.add(sep)
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

        self.tile_display = widgets.NavTile("screen", i18n.tr("Affichage"))
        self.tile_style = widgets.NavTile("style", i18n.tr("Style"))
        self.tile_game = widgets.NavTile("game", i18n.tr("Jeu détecté"))
        self.tile_display.clicked.connect(lambda: self.nav.select("display"))
        self.tile_style.clicked.connect(lambda: self.nav.select("style"))
        self.tile_game.clicked.connect(lambda: self.nav.select("games"))
        tiles = hbox(
            self.tile_display,
            self.tile_style,
            self.tile_game,
            spacing=14,
            stretch=False,
        )

        demo = Card()
        self.quick_mode = widgets.Segmented(
            {k: i18n.tr(title) for k, (title, _d) in settings.MODES.items()}
        )
        self.quick_mode.changed.connect(lambda k: self.set("mode", k))
        demo.add_row(i18n.tr("Mode d'affichage"), self.quick_mode)
        self.demo = widgets.Toggle()
        self.demo.toggled.connect(
            lambda v: None if self._building else self.app.set_demo(v)
        )
        demo.add_row(
            i18n.tr("Essayer sans musique"),
            self.demo,
            i18n.tr("Des paroles de démonstration, pour régler le style."),
        )
        return [hero, self.fs_warn, tiles, demo]

    def build_display(self):
        modes = Card(
            i18n.tr("Mode"),
            i18n.tr(
                "Passe la souris sur une carte pour voir le mode en action."
            ),
        )
        cards = QHBoxLayout()
        cards.setSpacing(12)
        self.mode_group = QButtonGroup(self)
        self.mode_cards = {}
        for key, (raw_title, raw_desc) in settings.MODES.items():
            title, desc = i18n.tr(raw_title), i18n.tr(raw_desc)
            c = widgets.ModeCard(key, title, desc)
            self.mode_group.addButton(c)
            c.clicked.connect(lambda _=False, k=key: self.set("mode", k))
            cards.addWidget(c)
            self.mode_cards[key] = c
        modes.lay.addLayout(cards)

        place = Card(i18n.tr("Placement et taille"))
        self.position = widgets.Segmented(translated(settings.POSITIONS))
        self.position.changed.connect(lambda k: self.set("position", k))
        self.position_row = place.add_row(
            i18n.tr("Position"),
            self.position,
            i18n.tr("En haut de l'écran : à gauche, au centre ou à droite."),
        )
        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setRange(70, 160)
        self.size_slider.setSingleStep(5)
        self.size_slider.setFixedWidth(240)
        self.size_lbl = QLabel()
        self.size_lbl.setProperty("role", "value")
        self.size_lbl.setFixedWidth(52)
        self.size_lbl.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.size_slider.valueChanged.connect(self.on_size)
        self.size_slider.sliderReleased.connect(
            lambda: self.set("scale", self.size_slider.value() / 100)
        )
        place.add_row(
            i18n.tr("Taille du texte"),
            hbox(self.size_slider, self.size_lbl, stretch=False),
        )

        extra = Card(i18n.tr("Moments forts"))
        self.opt = {}
        self.title_drop = widgets.Segmented(translated(settings.TITLE_DROP))
        self.title_drop.changed.connect(lambda k: self.set("title_drop", k))
        extra.add_row(
            i18n.tr("Titre en géant"),
            self.title_drop,
            i18n.tr(
                "Quand le chanteur dit le titre du morceau, il s'affiche en très "
                "grand "
                "(en jeu : dans un espace libre, jamais sur l'action)."
            ),
        )
        self.opt["card"] = widgets.Toggle()
        extra.add_row(
            i18n.tr("Carte de la pochette"),
            self.opt["card"],
            i18n.tr(
                "Pochette, titre et artiste quelques secondes au début du morceau."
            ),
        )
        return [modes, place, extra]

    def build_style(self):
        self.preview = FontPreview(self.app)

        colors = Card(i18n.tr("Couleurs du texte"))
        row = QHBoxLayout()
        row.setSpacing(12)
        self.color_group = QButtonGroup(self)
        self.color_cards = {
            "album": widgets.ColorCard(
                "album",
                i18n.tr("Couleurs de l'album"),
                i18n.tr("Tirées de la pochette du morceau."),
                lambda: self.app.overlay.accent[:3],
            ),
            "white": widgets.ColorCard(
                "white",
                i18n.tr("Blanc lumineux"),
                i18n.tr("Blanc avec un léger halo."),
                lambda: [QColor("#ffffff")],
            ),
        }
        for key, c in self.color_cards.items():
            self.color_group.addButton(c)
            c.clicked.connect(lambda _=False, k=key: self.set("color", k))
            row.addWidget(c)
        colors.lay.addLayout(row)

        motion = Card(i18n.tr("Animation"))
        self.style_picker = widgets.Segmented(translated(settings.STYLES))
        self.style_picker.changed.connect(lambda k: self.set("style", k))
        self.style_row = motion.add_row(
            i18n.tr("Arrivée des mots"),
            self.style_picker,
            i18n.tr("Pour les modes Classique et Edit."),
        )
        self.opt["beat"] = widgets.Toggle()
        motion.add_row(
            i18n.tr("Pulsation sur le beat"),
            self.opt["beat"],
            i18n.tr("Le texte grossit légèrement sur la grosse caisse."),
        )
        self.opt["particles"] = widgets.Toggle()
        motion.add_row(
            i18n.tr("Particules sur les mots tenus"),
            self.opt["particles"],
            i18n.tr("De petites étincelles quand le chanteur tient une note."),
        )
        self.opt["stack"] = widgets.Toggle()
        self.stack_row = motion.add_row(
            i18n.tr("Mots empilés"),
            self.opt["stack"],
            i18n.tr(
                "En mode Edit, des rangées de tailles différentes, la plus forte "
                "en couleur."
            ),
        )
        self.opt["tilt"] = widgets.Toggle()
        self.tilt_row = motion.add_row(
            i18n.tr("Effet 3D sur les côtés"),
            self.opt["tilt"],
            i18n.tr(
                "En mode Edit, les lignes à gauche et à droite partent en "
                "perspective."
            ),
        )
        self.opt["easter"] = widgets.Toggle()
        motion.add_row(
            i18n.tr("Easter eggs"),
            self.opt["easter"],
            i18n.tr(
                "Quelques morceaux cachent un spectacle spécial. À toi de les "
                "trouver."
            ),
        )

        fonts = Card(i18n.tr("Police"))
        self.font_search = QLineEdit()
        self.font_search.setPlaceholderText(i18n.tr("Rechercher une police…"))
        self.font_search.setClearButtonEnabled(True)
        self.font_search.textChanged.connect(self.filter_fonts)
        fonts.add(self.font_search)
        self.font_list = QListWidget()
        self.font_list.setFixedHeight(264)
        self.font_list.setVerticalScrollMode(
            QListWidget.ScrollMode.ScrollPerPixel
        )
        self.populate_fonts()
        self.font_list.currentItemChanged.connect(self.on_font)
        fonts.add(self.font_list)
        return [self.preview, colors, motion, fonts]

    def build_music(self):
        src = Card(
            i18n.tr("Applis écoutées"),
            i18n.tr(
                "Décoche celles qui ne servent pas à la musique. Les médias de "
                "plus de 20 minutes sont "
                "toujours ignorés."
            ),
        )
        self.sources_box = QVBoxLayout()
        self.sources_box.setSpacing(12)
        src.lay.addLayout(self.sources_box)
        self._sources_shown = None

        web = Card(
            i18n.tr("Sites de musique dans le navigateur"),
            i18n.tr(
                "Quand le son vient de Chrome, Opera, Brave, Edge, Firefox… seuls "
                "ces sites affichent des "
                "paroles. Netflix, Twitch et les autres vidéos sont ignorés."
            ),
        )
        self.web_state = QLabel()
        self.web_state.setProperty("role", "hint")
        self.web_state.setWordWrap(True)
        self.web_state.hide()
        web.add(self.web_state)
        grid = QGridLayout()
        grid.setHorizontalSpacing(34)
        grid.setVerticalSpacing(12)
        off = set(self.app.cfg.get("sites_off", []))
        self.site_toggles = {}
        for i, (sid, label, _rx) in enumerate(sites.SITES):
            t = widgets.Toggle()
            t.setChecked(sid not in off)
            t.toggled.connect(
                lambda v, s=sid: self.app.set_site_enabled(s, bool(v))
            )
            self.site_toggles[sid] = t
            name = QLabel(label)
            name.setProperty("role", "rowtitle")
            cell = QHBoxLayout()
            cell.setContentsMargins(0, 0, 0, 0)
            cell.setSpacing(12)
            cell.addWidget(logo_label(sid, label))
            cell.addWidget(name, 1)
            cell.addWidget(t)
            grid.addLayout(cell, i // 2, i % 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        web.lay.addLayout(grid)
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setProperty("role", "sep")
        web.add(sep)
        other = widgets.Toggle()
        other.setChecked(bool(self.app.cfg.get("sites_other", False)))
        other.toggled.connect(
            lambda v: self.app.set_site_enabled(sites.OTHER, bool(v))
        )
        self.site_toggles[sites.OTHER] = other
        web.add_row(
            i18n.tr("Tous les autres sites"),
            other,
            i18n.tr(
                "À activer seulement si ta musique vient d'un site absent de la "
                "liste : les vidéos "
                "seront de nouveau suivies."
            ),
        )
        self._web_shown = None

        lyr = Card(i18n.tr("Paroles"))
        self.opt["translation"] = widgets.Toggle()
        lyr.add_row(
            i18n.tr("Traduction en français"),
            self.opt["translation"],
            i18n.tr(
                "Sous la ligne, pour les chansons qui ne sont pas en français."
            ),
        )
        self.opt["liriqo"] = widgets.Toggle()
        lyr.add_row(
            i18n.tr("Plus de mot à mot (LiriQo)"),
            self.opt["liriqo"],
            i18n.tr(
                "Quand un morceau n'a pas de mot à mot, demande à LiriQo, un "
                "service tiers qui regroupe d'autres sources. Le titre et "
                "l'artiste lui sont envoyés."
            ),
        )
        later = button("−", "round")
        earlier = button("+", "round")
        reset = button(i18n.tr("Remettre à zéro"), "link")
        self.offset_lbl = QLabel()
        self.offset_lbl.setProperty("role", "bigvalue")
        self.offset_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.offset_lbl.setFixedWidth(78)
        later.clicked.connect(
            lambda: self.set("offset", round(self.app.cfg["offset"] - 0.1, 2))
        )
        earlier.clicked.connect(
            lambda: self.set("offset", round(self.app.cfg["offset"] + 0.1, 2))
        )
        reset.clicked.connect(lambda: self.set("offset", 0.0))
        self.offset_row = lyr.add_row(
            i18n.tr("Calage des paroles"),
            hbox(reset, later, self.offset_lbl, earlier, stretch=False),
            " ",
        )
        for key, t in self.opt.items():
            t.toggled.connect(lambda v, k=key: self.set(k, bool(v)))
        return [src, web, lyr]

    def refresh_web(self):
        seen = tuple(sorted(getattr(self.app, "browsers", {}).items()))
        if seen == self._web_shown:
            return
        self._web_shown = seen
        lines = []
        for app_id, (sid, ok) in seen:
            who = settings.app_label(app_id)
            if sid == sites.OTHER:
                lines.append(
                    i18n.tr("{} : site non reconnu, ").format(who)
                    + (i18n.tr("suivi quand même") if ok else i18n.tr("ignoré"))
                )
            else:
                lines.append(
                    f"{who} : {sites.SITE_NAMES.get(sid, sid)}"
                    + ("" if ok else i18n.tr(", ignoré"))
                )
        self.web_state.setText(i18n.tr("En ce moment — ") + " · ".join(lines))
        self.web_state.setVisible(bool(lines))

    def refresh_sources(self):
        blocked = list(self.app.cfg.get("sources_blocked", []))
        ids = list(
            dict.fromkeys(list(getattr(self.app, "sources", [])) + blocked)
        )
        state = (tuple(ids), tuple(blocked))
        if state == self._sources_shown:
            return
        self._sources_shown = state
        while self.sources_box.count():
            item = self.sources_box.takeAt(0)
            w = item.widget() if item else None
            if w:
                w.deleteLater()
        if not ids:
            lbl = QLabel(
                i18n.tr(
                    "Aucune appli détectée pour l'instant. Lance une musique."
                )
            )
            lbl.setProperty("role", "empty")
            self.sources_box.addWidget(lbl)
            return
        for app_id in ids:
            t = widgets.Toggle()
            t.setChecked(app_id not in blocked)
            t.toggled.connect(
                lambda v, a=app_id: self.app.set_source_enabled(a, v)
            )
            line = QWidget()
            lay = QHBoxLayout(line)
            lay.setContentsMargins(0, 0, 0, 0)
            name = QLabel(settings.app_label(app_id))
            name.setProperty("role", "rowtitle")
            lay.setSpacing(12)
            lay.addWidget(
                logo_label(logos.app_key(app_id), settings.app_label(app_id))
            )
            lay.addWidget(name, 1)
            lay.addWidget(t)
            self.sources_box.addWidget(line)

    def build_games(self):
        cur = Card()
        cap = QLabel(i18n.tr("Jeu détecté"))
        cap.setProperty("role", "section")
        cur.add(cap)
        self.profile_lbl = QLabel(i18n.tr("Bureau"))
        self.profile_lbl.setProperty("role", "nptitle")
        self.game_logo = QLabel()
        self.game_logo.setFixedSize(36, 36)
        self.game_logo.setScaledContents(True)
        self.game_logo.hide()
        cur.add(hbox(self.game_logo, self.profile_lbl, spacing=14))
        hint = QLabel(
            i18n.tr(
                "Les paroles contournent les zones importantes du jeu : vie, "
                "minimap, score, sorts…"
            )
        )
        hint.setProperty("role", "hint")
        hint.setWordWrap(True)
        cur.add(hint)
        draw = button(i18n.tr("Dessiner les zones…"), "main")
        show = button(i18n.tr("Voir les zones 5 secondes"))
        draw.clicked.connect(self.app.open_zone_editor)
        show.clicked.connect(self.app.show_zones)
        cur.add(hbox(draw, show))

        self.fs_warn2 = QLabel()
        self.fs_warn2.setProperty("role", "warn")
        self.fs_warn2.setWordWrap(True)
        self.fs_warn2.hide()

        how = Card(i18n.tr("Ajouter un jeu en 3 étapes"))
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
        self.step_labels[1].setText(
            i18n.tr(
                "Reviens ici : la capture s'ouvre toute seule. Dessine à la "
                "souris un rectangle "
                "sur chaque endroit à protéger."
            )
        )
        self.step_labels[2].setText(
            i18n.tr(
                "Clique sur « Enregistrer ». C'est appliqué tout de suite, sans "
                "relancer le jeu."
            )
        )

        tip = Card(i18n.tr("Le jeu cache les paroles ?"))
        t = QLabel(
            i18n.tr(
                "Mets tes jeux en « fenêtré sans bordure » dans leurs "
                "options vidéo. En plein écran exclusif, {} n'affiche "
                "aucune fenêtre par-dessus le jeu."
            ).format(self.app.desktop.name)
        )
        t.setProperty("role", "hint")
        t.setWordWrap(True)
        tip.add(t)
        return [cur, self.fs_warn2, how, tip]

    def build_keys(self):
        card = Card(
            i18n.tr("Tes raccourcis"),
            i18n.tr(
                "Clique sur un raccourci, puis appuie sur la nouvelle combinaison "
                "(avec Ctrl ou Alt, ou une touche F1 à F24). Échap annule, Suppr "
                "retire le raccourci."
            ),
        )
        self.key_buttons = {}
        for name, raw_label, _default in hotkeys.ACTIONS:
            label = i18n.tr(raw_label)
            b = widgets.HotkeyButton(self.app.hotkeys)
            b.started.connect(self.app.hotkeys.pause)
            b.ended.connect(self.app.hotkeys.resume)
            b.captured.connect(
                lambda combo, n=name: self.on_key_captured(n, combo)
            )
            card.add_row(label, b)
            self.key_buttons[name] = b
        self.key_msg = QLabel()
        self.key_msg.setProperty("role", "warn")
        self.key_msg.setWordWrap(True)
        self.key_msg.hide()
        reset = button(i18n.tr("Remettre les raccourcis d'origine"))
        reset.clicked.connect(self.on_keys_reset)
        if not self.app.hotkeys.available:
            unsupported = QLabel(
                i18n.tr(
                    "Les raccourcis clavier globaux ne sont pas encore "
                    "disponibles sur {}."
                ).format(self.app.desktop.name)
            )
            unsupported.setProperty("role", "hint")
            unsupported.setWordWrap(True)
            card.add(unsupported)
        return [card, self.key_msg, hbox(reset)]

    def on_key_captured(self, name, combo):
        stolen = self.app.set_hotkey(name, combo)
        self._key_note = (
            (
                i18n.tr(
                    "« {} » utilisait déjà {} : ce raccourci lui a été retiré."
                ).format(
                    i18n.tr(hotkeys.LABELS[stolen]),
                    self.app.hotkeys.pretty(combo),
                )
            )
            if stolen
            else ""
        )
        self.hotkeys_changed()

    def on_keys_reset(self):
        self._key_note = ""
        self.app.reset_hotkeys()
        self.hotkeys_changed()

    def hotkeys_changed(self):
        keys = self.app.cfg["hotkeys"]
        failed = [
            n for n in getattr(self.app, "hotkeys_failed", []) if keys.get(n)
        ]
        for name, b in self.key_buttons.items():
            b.set_combo(keys.get(name, ""), name in failed)
        notes = [self._key_note] if self._key_note else []
        if failed:
            notes.append(
                i18n.tr("{} refuse ").format(self.app.desktop.name)
                + ", ".join(self.app.hotkeys.pretty(keys[n]) for n in failed)
                + i18n.tr(
                    " : cette combinaison est déjà prise par une autre appli. "
                    "Choisis-en une autre."
                )
            )
        self.key_msg.setText("\n".join(notes))
        self.key_msg.setVisible(bool(notes))
        pretty = self.app.hotkeys.pretty
        capture = keys.get("capture", "")
        self.step_labels[0].setText(
            i18n.tr(
                "Dans le jeu, appuie sur {} : une capture est prise, sans "
                "les paroles."
            ).format(pretty(capture))
            if capture
            else i18n.tr(
                "Donne d'abord un raccourci à « Capturer le jeu » dans la "
                "page Raccourcis."
            )
        )
        up, down = keys.get("earlier", ""), keys.get("later", "")
        tip = i18n.tr(
            "Paroles en retard : appuie sur +. En avance : appuie sur −."
        )
        if up and down:
            tip += i18n.tr("\nEn jeu : {} et {}.").format(
                pretty(up), pretty(down)
            )
        self.offset_row.hint_label.setText(tip)

    def build_general(self):
        cards = []
        self.autostart = widgets.Toggle()
        self.autostart.setChecked(self.app.startup.enabled())
        self.autostart.toggled.connect(
            lambda v: None if self._building else self.app.startup.set(bool(v))
        )
        if self.app.startup.supports_autostart:
            start = Card(i18n.tr("Démarrage"))
            start.add_row(
                i18n.tr("Lancer avec {}").format(self.app.desktop.name),
                self.autostart,
                i18n.tr(
                    "Démarre tout seul à l'allumage du PC, discrètement près de "
                    "l'heure."
                ),
            )
            cards.append(start)
        lang = Card(i18n.tr("Langue"))
        self.language = widgets.Segmented(dict(i18n.LANGUAGES))
        self.language.set_value(i18n.language())
        self.language.changed.connect(self.app.set_language)
        lang.add_row(i18n.tr("Langue de l'appli"), self.language)
        cards.append(lang)
        installation = self.app.installation
        if settings.FROZEN and installation is not None:
            setup = Card(i18n.tr("Installation"))
            if installation.running_installed():
                b = button(i18n.tr("Désinstaller"))
                b.clicked.connect(self.app.uninstall)
                setup.add_row(
                    i18n.tr("Installée sur ce PC"),
                    b,
                    i18n.tr(
                        "L'appli est dans le menu Démarrer et dans les "
                        "applications installées de {}."
                    ).format(self.app.desktop.name),
                )
            else:
                b = button(i18n.tr("Installer"))
                b.clicked.connect(self.app.install_here)
                setup.add_row(
                    i18n.tr("Installer sur ce PC"),
                    b,
                    i18n.tr(
                        "Range l'appli à sa place avec une icône dans le menu "
                        "Démarrer. Tu pourras ensuite jeter le fichier téléchargé."
                    ),
                )
            cards.append(setup)

        upd = Card(i18n.tr("Mises à jour"))
        self.check_btn = button(i18n.tr("Rechercher une mise à jour"))
        self.check_btn.clicked.connect(self.on_check_click)
        row = upd.add_row(
            i18n.tr("Version {}").format(self.version),
            self.check_btn,
            i18n.tr(
                "L'appli vérifie toute seule de temps en temps et te prévient ici."
            ),
        )
        self.check_lbl = row.hint_label

        about = Card(i18n.tr("À propos"))
        site = button(i18n.tr("Ouvrir le site"))
        site.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(SITE_URL)))
        github = button(i18n.tr("GitHub de War3l"))
        github.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(AUTHOR_URL))
        )
        about.add_row(
            "FollowTheLyrics",
            hbox(site, github, stretch=False),
            i18n.tr(
                "Les paroles de ta musique, par-dessus tes jeux. Gratuit et "
                "libre. Créé par War3l."
            ),
        )
        return [*cards, upd, about]

    def populate_fonts(self):
        skip = (
            "MDL2",
            "Fluent Icons",
            "Wingdings",
            "Webdings",
            "Marlett",
            "Symbol",
            "Emoji",
            "HoloLens",
            "Segoe Fluent",
            "Bookshelf",
            "MT Extra",
        )
        fams = []
        for f in QFontDatabase.families():
            if QFontDatabase.isPrivateFamily(f) or any(s in f for s in skip):
                continue
            if (
                QFontDatabase.WritingSystem.Latin
                not in QFontDatabase.writingSystems(f)
            ):
                continue
            fams.append(f)
        rec = [f for f in settings.RECOMMENDED_FONTS if f in fams]
        rest = sorted((f for f in fams if f not in rec), key=str.lower)
        self._font_items = []

        def header(text):
            it = QListWidgetItem(text)
            it.setFlags(Qt.ItemFlag.NoItemFlags)
            it.setFont(widgets.ui_font(10, QFont.Weight.Bold))
            it.setForeground(QColor(widgets.DIM))
            it.setData(Qt.ItemDataRole.UserRole + 1, "header")
            self.font_list.addItem(it)

        header(i18n.tr("Recommandées"))
        for f in rec:
            self._add_font_item(f)
        header(i18n.tr("Toutes les polices"))
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
            if it is None:
                continue
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
        if not self.size_slider.isSliderDown() and not self._building:
            self.set("scale", v / 100)

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
            self.quick_mode.set_value(cfg["mode"])
            self.position.set_value(cfg["position"])
            column = cfg["mode"] in ("classic", "typewriter")
            self.position.setEnabled(column)
            self.position_row.setEnabled(column)
            self.color_cards[cfg["color"]].setChecked(True)
            self.style_picker.set_value(cfg["style"])
            self.title_drop.set_value(cfg.get("title_drop", "always"))
            self.style_row.setEnabled(cfg["mode"] != "typewriter")
            self.style_picker.setEnabled(cfg["mode"] != "typewriter")
            self.size_slider.setValue(round(cfg["scale"] * 100))
            self.size_lbl.setText(f"{self.size_slider.value()} %")
            for k, t in self.opt.items():
                t.setChecked(bool(cfg.get(k, True)))
            self.demo.setChecked(self.app.demo)
            self.autostart.setChecked(self.app.startup.enabled())
            self.master.setChecked(not self.app.overlay.user_hidden)
            self.master_state.setText(
                i18n.tr("Affichées")
                if self.master.isChecked()
                else i18n.tr("Masquées")
            )
            self.offset_lbl.setText(f"{cfg['offset']:+.1f} s")
            fam = cfg.get("font")
            for it in self._font_items:
                if it.data(Qt.ItemDataRole.UserRole) == fam:
                    self.font_list.setCurrentItem(it)
                    break
        finally:
            self._building = False
        mode = i18n.tr(settings.MODES[cfg["mode"]][0])
        self.tile_display.set_value(
            f"{mode} · {i18n.tr(settings.POSITIONS[cfg['position']])}"
            if column
            else mode
        )
        self.tile_style.set_value(
            f"{'Album' if cfg['color'] == 'album' else 'Blanc'} · "
            f"{i18n.tr(settings.STYLES[cfg['style']])}"
        )
        self.preview.update()
        for c in list(self.mode_cards.values()) + list(
            self.color_cards.values()
        ):
            c.update()

    def refresh(self):
        if not self.isVisible():
            return
        o = self.app.overlay
        self.refresh_sources()
        self.refresh_web()
        t = o.track
        if t is not None:
            self.np_title.setText(t.title)
            self.np_artist.setText(t.artist or "")
            dur = t.duration if 0 < (t.duration or 0) < 4 * 3600 else 0
            self.progress.set_values(o.raw_position(), dur)
            self.state_lbl.setText(
                i18n.tr("En cours") if o.playing else i18n.tr("En pause")
            )
            self.mini.set_track(t.title, t.artist or "", o.cover_img)
        else:
            self.np_title.setText(i18n.tr("Aucune musique"))
            self.np_artist.setText(
                i18n.tr(
                    "Lance un morceau sur Spotify, YouTube Music, Deezer… les "
                    "paroles arrivent toutes seules."
                )
            )
            self.progress.set_values(0, 0)
            self.state_lbl.setText(i18n.tr("En attente"))
            self.mini.set_track(
                i18n.tr("Aucune musique"), i18n.tr("En attente…"), None
            )
        playing = bool(t is not None and o.playing)
        if playing != self.eq.playing:
            self.eq.playing = playing
            self.eq.update()
        if o.cover_img is not self._cover_src:
            self._cover_src = o.cover_img
            self.cover.set_image(o.cover_img)
        badge = o.card_badge().capitalize() if t is not None else ""
        kind = "word" if (o.state == "ok" and o.word_sync) else "line"
        if badge != self.badge.text() or kind != self.badge.property("kind"):
            self.badge.setText(badge)
            self.badge.setProperty("kind", kind)
            badge_style = self.badge.style()
            if badge_style is not None:
                badge_style.unpolish(self.badge)
                badge_style.polish(self.badge)
        self.badge.setVisible(bool(badge))
        txt = o.current_text()
        if o.state == "ok":
            self.lyric.setText(txt or "♪  …")
            line = o.lines[o.cur["idx"]] if (o.cur and o.lines) else None
            self.lyric_tr.setText(
                line.translation
                if (line and line.translation and o.cfg.get("translation"))
                else ""
            )
        elif o.state == "loading":
            self.lyric.setText(i18n.tr("Recherche des paroles…"))
            self.lyric_tr.setText("")
        elif o.state == "missing":
            self.lyric.setText(
                i18n.tr("Pas de paroles synchronisées pour ce titre.")
            )
            self.lyric_tr.setText("")
        else:
            self.lyric.setText("—")
            self.lyric_tr.setText("")
        self.lyric_tr.setVisible(bool(self.lyric_tr.text()))
        game = i18n.tr(o.profile.get("nom", o.profile_key) or "Bureau")
        self.profile_lbl.setText(game)
        self.tile_game.set_value(game)
        logo = logos.pixmap(logos.game_key(o.profile_key))
        self.tile_game.set_logo(logo)
        if logo is not None:
            self.game_logo.setPixmap(logo)
        self.game_logo.setVisible(logo is not None)
        if getattr(self.app, "exclusive", False):
            msg = i18n.tr(
                "Plein écran exclusif détecté : les paroles ne peuvent pas "
                "passer "
                "par-dessus le jeu. "
            ) + (self.app.exclusive_tip or "")
            for w in (self.fs_warn, self.fs_warn2):
                w.setText(msg)
                w.show()
        else:
            self.fs_warn.hide()
            self.fs_warn2.hide()
        themed = o.cover_img is not None and t is not None
        accent = QColor(o.accent[0]) if themed else widgets.DEFAULT_ACCENT
        if accent.name() != self._accent_name:
            self.apply_style(accent)
            self.preview.update()
        aura = [
            QColor(c)
            for c in (
                o.accent[:3] if themed and len(o.accent) >= 3 else IDLE_AURA
            )
        ]
        if [c.name() for c in aura] != [c.name() for c in self._aura_to]:
            self._aura_from, self._aura_to = list(self._aura), aura
            widgets.run_anim(self._aura_anim, 0.0, 1.0)

    def _aura_step(self, v):
        self._aura = [
            widgets.mix(a, b, v)
            for a, b in zip(self._aura_from, self._aura_to, strict=False)
        ]
        self.update()

    def glass_on(self):
        return self._glass_ok

    def apply_style(self, accent: QColor):
        self._accent_name = accent.name()
        widgets.UI["accent"] = QColor(accent)
        widgets.UI["ink"] = widgets.ink_for(accent)
        a = accent.name()
        r, g, b = accent.red(), accent.green(), accent.blue()
        ink = widgets.UI["ink"].name()
        text, dim = widgets.TEXT, widgets.DIM
        ft = fd = f'"{widgets.font_family()}"'
        self._title_glow.setColor(widgets.alpha(accent, 150))
        edge = "rgba(255,255,255,0.15)"
        line = "rgba(255,255,255,0.30)"
        self.setStyleSheet(f"""
            QWidget#Panel, QWidget#Content, QStackedWidget {{
                background: transparent;
            }}
            QScrollArea, QScrollArea > QWidget > QWidget {{
                background: transparent;
            }}
            QLabel {{
                color: {text};
                background: transparent;
            }}
            QToolTip {{
                color: {text};
                background: #1a1a1d;
                border: 1px solid #38383c;
                padding: 4px 8px;
            }}
            QFrame[role="card"] {{
                background: rgba(255,255,255,0.07);
                border: 1px solid {edge};
                border-radius: 26px;
            }}
            QFrame[role="sep"] {{
                background: rgba(255,255,255,0.08);
                border: none;
            }}
            QLabel[role="pagetitle"] {{
                font: 400 38px {fd};
            }}
            QLabel[role="pagehint"] {{
                color: {dim};
                font: 14px {ft};
                padding-bottom: 8px;
            }}
            QLabel[role="cardtitle"] {{
                font: 600 16px {fd};
            }}
            QLabel[role="section"] {{
                color: {dim};
                font: 13px {ft};
            }}
            QLabel[role="rowtitle"] {{
                color: {text};
                font: 500 14px {ft};
            }}
            QLabel[role="rowtitle"]:disabled {{
                color: #66666b;
            }}
            QLabel[role="hint"] {{
                color: {dim};
                font: 12px {ft};
            }}
            QLabel[role="hint"]:disabled {{
                color: #55555a;
            }}
            QLabel[role="empty"] {{
                color: {dim};
                font: 13px {ft};
                padding: 10px 0;
            }}
            QLabel[role="value"] {{
                color: {text};
                font: 500 13px {ft};
            }}
            QLabel[role="bigvalue"] {{
                color: {text};
                font: 400 20px {fd};
            }}
            QLabel[role="nptitle"] {{
                font: 400 32px {fd};
            }}
            QLabel[role="npartist"] {{
                color: {dim};
                font: 15px {ft};
            }}
            QLabel[role="lyric"] {{
                font: 500 20px {fd};
                color: {text};
            }}
            QLabel[role="steptext"] {{
                color: {text};
                font: 14px {ft};
                padding-top: 5px;
            }}
            QLabel[role="step"] {{
                color: {ink};
                background: {a};
                border-radius: 15px;
                font: 600 14px {fd};
            }}
            QLabel[role="badge"] {{
                font: 500 11px {ft};
                padding: 3px 11px;
                min-height: 14px;
                border-radius: 10px;
                color: {text};
                background: transparent;
                border: 1px solid {line};
            }}
            QLabel[role="badge"][kind="word"] {{
                color: {ink};
                background: {a};
                border: 1px solid {a};
            }}
            QPushButton[role="ghost"] {{
                background: transparent;
                color: {text};
                border: 1px solid {line};
                padding: 8px 18px;
                min-height: 18px;
                border-radius: 17px;
                font: 500 13px {ft};
            }}
            QPushButton[role="ghost"]:hover {{
                border-color: rgba(255,255,255,0.55);
                background: rgba(255,255,255,0.10);
            }}
            QPushButton[role="ghost"]:pressed {{
                background: rgba(255,255,255,0.18);
            }}
            QPushButton[role="ghost"]:disabled {{
                color: #66666b;
                border-color: {edge};
            }}
            QPushButton[role="round"] {{
                background: transparent;
                color: {text};
                border: 1px solid {line};
                min-width: 38px;
                max-width: 38px;
                min-height: 38px;
                max-height: 38px;
                border-radius: 19px;
                font: 400 18px {fd};
                padding: 0 0 3px 0;
            }}
            QPushButton[role="round"]:hover {{
                background: {a};
                border-color: {a};
                color: {ink};
            }}
            QPushButton[role="link"] {{
                background: transparent;
                color: {dim};
                border: none;
                padding: 6px 8px;
                font: 12px {ft};
            }}
            QPushButton[role="link"]:hover {{
                color: {text};
            }}
            QPushButton[role="main"] {{
                background: {a};
                color: {ink};
                border: none;
                padding: 9px 22px;
                min-height: 18px;
                border-radius: 17px;
                font: 600 13px {ft};
            }}
            QPushButton[role="main"]:hover {{
                background: #ffffff;
            }}
            QPushButton[role="main"]:disabled {{
                background: rgba({r},{g},{b},0.30);
                color: #8a8a90;
            }}
            QFrame[role="update"] {{
                background: rgba(255,255,255,0.10);
                border: 1px solid {line};
                border-radius: 24px;
            }}
            QLineEdit {{
                background: rgba(0,0,0,0.24);
                color: {text};
                border: 1px solid {edge};
                border-radius: 17px;
                min-height: 18px;
                padding: 8px 16px;
                font: 14px {ft};
                selection-background-color: {a};
                selection-color: {ink};
            }}
            QLineEdit:focus {{
                border-color: rgba(255,255,255,0.5);
            }}
            QListWidget {{
                background: rgba(0,0,0,0.24);
                color: {text};
                border: 1px solid {edge};
                border-radius: 20px;
                padding: 8px;
                outline: none;
            }}
            QListWidget::item {{
                padding: 4px 12px;
                border-radius: 12px;
            }}
            QListWidget::item:hover {{
                background: rgba(255,255,255,0.08);
            }}
            QListWidget::item:selected {{
                background: {a};
                color: {ink};
            }}
            QSlider::groove:horizontal {{
                height: 4px;
                background: rgba(255,255,255,0.20);
                border-radius: 2px;
            }}
            QSlider::sub-page:horizontal {{
                background: {a};
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {a};
                width: 18px;
                height: 18px;
                margin: -7px 0;
                border-radius: 9px;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 8px;
                margin: 2px;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(255,255,255,0.16);
                border-radius: 4px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: rgba(255,255,255,0.30);
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: transparent;
            }}
            QLabel[role="warn"] {{
                color: {text};
                background: rgba(255,255,255,0.08);
                border: 1px solid rgba({r},{g},{b},0.6);
                border-radius: 20px;
                padding: 12px 18px;
                font: 500 13px {ft};
            }}
        """)
        for w in self.findChildren(QWidget):
            w.update()
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        glass = self.glass_on()
        base = QColor(6, 6, 8, 150 if glass else 255)
        if self._can_glass:
            p.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_Source
            )
            p.fillRect(self.rect(), base)
            p.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_SourceOver
            )
        else:
            p.fillRect(self.rect(), QColor(widgets.BG))
        w, h = self.width(), self.height()
        for (cx, cy, radius, strength), col in zip(
            (
                (0.04, -0.05, 0.72, 120),
                (1.02, 0.18, 0.62, 92),
                (0.55, 1.12, 0.70, 84),
            ),
            self._aura,
            strict=False,
        ):
            glow = QRadialGradient(QPointF(w * cx, h * cy), w * radius)
            glow.setColorAt(0, widgets.alpha(col, strength))
            glow.setColorAt(0.55, widgets.alpha(col, strength * 0.32))
            glow.setColorAt(1, widgets.alpha(col, 0))
            p.fillRect(self.rect(), QBrush(glow))

    def showEvent(self, e):
        super().showEvent(e)
        window = int(self.winId())
        self._windowing.dark_title_bar(window)
        if self._can_glass and not self._glass_ok:
            self._glass_ok = self._windowing.enable_backdrop(window)
        self._windowing.color_title_bar(window, TITLE_BAR)
        self.refresh()

    def closeEvent(self, e):
        if getattr(self.app, "quitting", False):
            e.accept()
            return
        e.ignore()
        self.hide()
        try:
            self.app.tray.showMessage(
                "FollowTheLyrics",
                i18n.tr(
                    "Toujours actif. Clique sur l'icône près de l'heure pour "
                    "rouvrir le panneau."
                ),
                widgets.make_icon(),
                2500,
            )
        except Exception:
            logger.debug("closeEvent failed", exc_info=True)
