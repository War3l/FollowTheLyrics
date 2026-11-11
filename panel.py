"""Panneau de controle : musique en cours + tous les reglages, en direct."""
import ctypes
import math

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QFontDatabase, QFontMetricsF, QIcon, QImage, QLinearGradient,
    QPainter, QPainterPath, QPen, QPixmap, QRadialGradient,
)
from PyQt6.QtWidgets import (
    QAbstractButton, QButtonGroup, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QScrollArea, QSizePolicy, QSlider,
    QVBoxLayout, QWidget,
)

from settings import (COLORS, MODES, POSITIONS, RECOMMENDED_FONTS, STYLES, TITLE_DROP, app_label,
                      autostart_enabled, set_autostart)

DEFAULT_ACCENT = QColor("#8B7CFF")
UI = {"accent": QColor(DEFAULT_ACCENT)}  # couleur d'accent du panneau (celle de la pochette)

BG = "#0c0d12"
CARD = "#14161e"
CARD_BORDER = "#20232e"
FIELD = "#1b1e28"
TEXT = "#eceef4"
DIM = "#8b91a3"


def icon_pixmap(size=64):
    """Le logo : carre arrondi en degrade, trois lignes de paroles dont une « chantee »."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = size / 64.0
    p.scale(s, s)
    body = QRectF(2, 2, 60, 60)
    g = QLinearGradient(QPointF(4, 2), QPointF(60, 62))
    g.setColorAt(0.0, QColor("#5EE7FF"))
    g.setColorAt(0.5, QColor("#8B7CFF"))
    g.setColorAt(1.0, QColor("#FF6FB5"))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(g))
    p.drawRoundedRect(body, 15, 15)
    shine = QRadialGradient(QPointF(16, 8), 44)
    shine.setColorAt(0, QColor(255, 255, 255, 90))
    shine.setColorAt(1, QColor(255, 255, 255, 0))
    p.setBrush(QBrush(shine))
    p.drawRoundedRect(body, 15, 15)
    # trois lignes de paroles : celle du milieu est en train d'etre chantee
    dark = QColor(14, 12, 28)
    p.setBrush(QColor(dark.red(), dark.green(), dark.blue(), 95))
    p.drawRoundedRect(QRectF(13, 16, 26, 7), 3.5, 3.5)
    p.drawRoundedRect(QRectF(13, 41, 32, 7), 3.5, 3.5)
    p.setBrush(QColor(dark.red(), dark.green(), dark.blue(), 110))
    p.drawRoundedRect(QRectF(13, 27, 38, 10), 5, 5)
    p.setBrush(QColor("white"))
    p.drawRoundedRect(QRectF(13, 27, 25, 10), 5, 5)
    p.end()
    return pm


def make_icon():
    ic = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(icon_pixmap(size))
    return ic


def fmt_time(t):
    t = max(0, int(t))
    return f"{t // 60}:{t % 60:02d}"


def ui_font(px, weight=QFont.Weight.Normal, family="Segoe UI Variable Text"):
    f = QFont(family)
    f.setPixelSize(px)
    f.setWeight(weight)
    return f


# --------------------------------------------------------------------------
# Petits composants dessines a la main
# --------------------------------------------------------------------------
class Toggle(QAbstractButton):
    """Interrupteur on/off."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(46, 26)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        on = self.isChecked()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(UI["accent"] if on else QColor("#2a2e3b"))
        p.drawRoundedRect(QRectF(0, 0, 46, 26), 13, 13)
        p.setBrush(QColor("#0c0d12") if on else QColor("#cfd3de"))
        p.drawEllipse(QRectF(23 if on else 3, 3, 20, 20))


class ModeCard(QAbstractButton):
    """Carte de choix du mode avec une mini illustration de l'ecran."""

    def __init__(self, key, title, desc, parent=None):
        super().__init__(parent)
        self.key, self.title, self.desc = key, title, desc
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(170, 176)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        acc = UI["accent"]
        on = self.isChecked()
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        bg = QColor(FIELD)
        if on:
            bg = QColor(int(bg.red() * 0.8 + acc.red() * 0.2), int(bg.green() * 0.8 + acc.green() * 0.2),
                        int(bg.blue() * 0.8 + acc.blue() * 0.2))
        p.setPen(QPen(acc if on else QColor(CARD_BORDER), 2 if on else 1))
        p.setBrush(bg)
        p.drawRoundedRect(r, 14, 14)

        # mini ecran
        scr = QRectF(r.left() + 12, r.top() + 12, r.width() - 24, 86)
        p.setPen(QPen(QColor("#2b2f3c"), 1))
        p.setBrush(QColor("#0a0b0f"))
        p.drawRoundedRect(scr, 8, 8)
        p.setPen(QPen(QColor(120, 200, 255, 70), 1, Qt.PenStyle.DashLine))
        p.drawLine(QPointF(scr.left() + 4, scr.center().y()), QPointF(scr.right() - 4, scr.center().y()))
        p.setPen(Qt.PenStyle.NoPen)
        dim = QColor(255, 255, 255, 70)
        w = scr.width()

        def bar(x, y, length, col, h=6, rot=0):
            p.save()
            p.translate(scr.left() + x, scr.top() + y)
            p.rotate(rot)
            p.setBrush(col)
            p.drawRoundedRect(QRectF(0, -h / 2, length, h), h / 2, h / 2)
            p.restore()

        if self.key == "classic":
            bar(10, 14, w * 0.30, dim, 5)
            bar(10, 26, w * 0.48, acc, 7)
        elif self.key == "edit":
            bar(10, 16, w * 0.32, acc, 7, -4)
            bar(w * 0.58, 12, w * 0.30, dim, 5, 3)
            bar(w * 0.40, 34, w * 0.26, dim, 5, -2)
        else:
            bar(w * 0.25, 14, w * 0.40, dim, 5)
            bar(w * 0.25, 27, w * 0.30, acc, 7)
            p.setBrush(acc)
            p.drawRoundedRect(QRectF(scr.left() + w * 0.25 + w * 0.30 + 4, scr.top() + 21, 3, 12), 1, 1)

        p.setPen(QColor(TEXT))
        p.setFont(ui_font(14, QFont.Weight.Bold, "Segoe UI Variable Display"))
        p.drawText(QRectF(r.left() + 14, scr.bottom() + 10, r.width() - 28, 20),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.title)
        p.setPen(QColor(DIM))
        p.setFont(ui_font(11))
        p.drawText(QRectF(r.left() + 14, scr.bottom() + 32, r.width() - 28, 36),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap, self.desc)


class Segmented(QWidget):
    """Groupe de boutons dont un seul est actif."""
    changed = pyqtSignal(str)

    def __init__(self, options: dict, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.group = QButtonGroup(self)
        self.buttons = {}
        for key, label in options.items():
            b = QPushButton(label)
            b.setCheckable(True)
            b.setProperty("role", "seg")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            self.group.addButton(b)
            lay.addWidget(b)
            self.buttons[key] = b
            b.clicked.connect(lambda _=False, k=key: self.changed.emit(k))
        lay.addStretch(1)

    def set_value(self, key):
        if key in self.buttons:
            self.buttons[key].setChecked(True)

    def setEnabled(self, on):  # noqa: N802 (API Qt)
        for b in self.buttons.values():
            b.setEnabled(on)


class CoverView(QWidget):
    def __init__(self, size, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.img = None

    def set_image(self, img):
        self.img = img
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = QRectF(self.rect())
        path = QPainterPath()
        path.addRoundedRect(r, 18, 18)
        p.setClipPath(path)
        if self.img is not None and not self.img.isNull():
            p.drawImage(r, self.img)
        else:
            g = QLinearGradient(r.topLeft(), r.bottomRight())
            acc = UI["accent"]
            g.setColorAt(0, QColor(acc.red(), acc.green(), acc.blue(), 120))
            g.setColorAt(1, QColor("#16182200"))
            p.fillRect(r, QColor("#161822"))
            p.fillRect(r, QBrush(g))
            p.setPen(QColor(255, 255, 255, 170))
            p.setFont(ui_font(int(r.width() * 0.32), QFont.Weight.Bold, "Segoe UI Symbol"))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, "♪")


class ProgressView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(34)
        self.pos, self.dur = 0.0, 0.0

    def set_values(self, pos, dur):
        self.pos, self.dur = pos, dur
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        bar = QRectF(0, 6, w, 5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#272a36"))
        p.drawRoundedRect(bar, 2.5, 2.5)
        if self.dur > 0:
            frac = max(0.0, min(1.0, self.pos / self.dur))
            p.setBrush(UI["accent"])
            p.drawRoundedRect(QRectF(0, 6, w * frac, 5), 2.5, 2.5)
            p.setBrush(QColor("white"))
            p.drawEllipse(QPointF(w * frac, 8.5), 5, 5)
        p.setPen(QColor(DIM))
        p.setFont(ui_font(11))
        p.drawText(QRectF(0, 16, w / 2, 18), Qt.AlignmentFlag.AlignLeft, fmt_time(self.pos) if self.dur else "")
        p.drawText(QRectF(w / 2, 16, w / 2, 18), Qt.AlignmentFlag.AlignRight, fmt_time(self.dur) if self.dur else "")


class FontPreview(QWidget):
    """Apercu du texte avec la police et les couleurs choisies."""

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.setFixedHeight(96)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, QColor("#1d2b22"))
        g.setColorAt(1, QColor("#33424e"))
        p.setPen(QPen(QColor(CARD_BORDER), 1))
        p.setBrush(QBrush(g))
        p.drawRoundedRect(r, 12, 12)
        cfg = self.app.cfg
        o = self.app.overlay
        f = QFont(cfg.get("font", "Segoe UI"))
        f.setPixelSize(32)
        f.setWeight(QFont.Weight.Black)
        text = "Les paroles prennent vie"
        fm = QFontMetricsF(f)
        tw = fm.horizontalAdvance(text)
        if tw > r.width() - 30:
            f.setPixelSize(int(32 * (r.width() - 30) / tw))
            fm = QFontMetricsF(f)
            tw = fm.horizontalAdvance(text)
        x = r.center().x() - tw / 2
        y = r.center().y() + fm.ascent() / 2 - 4
        # meme rendu que les paroles a l'ecran (vrai glow)
        o.draw_text_fx(p, text, f, x, y, o.fill_brush(x, tw, False), o.base_glow())


def section(title):
    """Carte avec un titre en petites majuscules ; renvoie (carte, layout du contenu)."""
    card = QFrame()
    card.setProperty("role", "card")
    lay = QVBoxLayout(card)
    lay.setContentsMargins(20, 18, 20, 20)
    lay.setSpacing(14)
    lbl = QLabel(title.upper())
    lbl.setProperty("role", "section")
    lay.addWidget(lbl)
    return card, lay


def row(label, widget, hint=None):
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(14)
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
    lay.addLayout(box, 1)
    lay.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)
    w.title_label = l1
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
        self.resize(1140, 780)
        self.setMinimumSize(1000, 660)
        self._accent_name = None
        self._cover_src = None
        self._building = True

        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 22)
        root.setSpacing(18)
        root.addLayout(self.build_header())
        body = QHBoxLayout()
        body.setSpacing(18)
        body.addWidget(self.build_now_playing(), 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content.setObjectName("Content")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 0, 8, 0)
        cl.setSpacing(16)
        cl.addWidget(self.build_modes())
        cl.addWidget(self.build_look())
        cl.addWidget(self.build_options())
        cl.addWidget(self.build_sources())
        cl.addWidget(self.build_sync_games())
        cl.addWidget(self.build_shortcuts())
        cl.addStretch(1)
        scroll.setWidget(content)
        body.addWidget(scroll, 1)
        root.addLayout(body, 1)

        self._building = False
        self.apply_style(DEFAULT_ACCENT)
        self.sync_from_cfg()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(200)
        self.refresh()

    # ---- construction ----------------------------------------------------
    def build_header(self):
        lay = QHBoxLayout()
        lay.setSpacing(14)
        logo = QLabel()
        logo.setPixmap(make_icon().pixmap(40, 40))
        lay.addWidget(logo)
        box = QVBoxLayout()
        box.setSpacing(0)
        t = QLabel("FollowTheLyrics")
        t.setProperty("role", "apptitle")
        st = QLabel("Les paroles de ta musique, par-dessus tes jeux")
        st.setProperty("role", "hint")
        box.addWidget(t)
        box.addWidget(st)
        lay.addLayout(box)
        lay.addStretch(1)
        lbl = QLabel("Paroles à l'écran")
        lbl.setProperty("role", "rowtitle")
        lay.addWidget(lbl)
        self.master = Toggle()
        self.master.toggled.connect(lambda v: None if self._building else self.app.set_visible(v))
        lay.addWidget(self.master)
        return lay

    def build_now_playing(self):
        card = QFrame()
        card.setProperty("role", "card")
        card.setFixedWidth(340)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(22, 20, 22, 22)
        lay.setSpacing(10)
        lbl = QLabel("EN COURS")
        lbl.setProperty("role", "section")
        lay.addWidget(lbl)
        self.cover = CoverView(296)
        lay.addWidget(self.cover, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(6)
        self.np_title = QLabel()
        self.np_title.setProperty("role", "nptitle")
        self.np_title.setWordWrap(True)
        self.np_artist = QLabel()
        self.np_artist.setProperty("role", "npartist")
        lay.addWidget(self.np_title)
        lay.addWidget(self.np_artist)
        self.progress = ProgressView()
        lay.addWidget(self.progress)
        brow = QHBoxLayout()
        self.badge = QLabel()
        self.badge.setProperty("role", "badge")
        brow.addWidget(self.badge)
        brow.addStretch(1)
        self.state_lbl = QLabel()
        self.state_lbl.setProperty("role", "hint")
        brow.addWidget(self.state_lbl)
        lay.addLayout(brow)
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setProperty("role", "sep")
        lay.addWidget(sep)
        l2 = QLabel("PAROLES")
        l2.setProperty("role", "section")
        lay.addWidget(l2)
        self.lyric = QLabel()
        self.lyric.setProperty("role", "lyric")
        self.lyric.setWordWrap(True)
        self.lyric.setMinimumHeight(54)
        self.lyric.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(self.lyric)
        self.lyric_tr = QLabel()
        self.lyric_tr.setProperty("role", "hint")
        self.lyric_tr.setWordWrap(True)
        lay.addWidget(self.lyric_tr)
        lay.addStretch(1)
        return card

    def build_modes(self):
        card, lay = section("Mode d'affichage")
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
        lay.addLayout(cards)
        self.position = Segmented(POSITIONS)
        self.position.changed.connect(lambda k: self.set("position", k))
        self.position_row = row("Position", self.position, "En haut de l'écran, à gauche, au centre ou à droite.")
        lay.addWidget(self.position_row)
        return card

    def build_look(self):
        card, lay = section("Apparence")
        self.color = Segmented(COLORS)
        self.color.changed.connect(lambda k: self.set("color", k))
        lay.addWidget(row("Couleurs", self.color, "Les couleurs de la pochette, ou blanc avec un léger halo."))
        self.style = Segmented(STYLES)
        self.style.changed.connect(lambda k: self.set("style", k))
        self.style_row = row("Animation", self.style, "Comment les mots arrivent (modes Classique et Edit).")
        lay.addWidget(self.style_row)

        sz = QWidget()
        sl = QHBoxLayout(sz)
        sl.setContentsMargins(0, 0, 0, 0)
        self.size = QSlider(Qt.Orientation.Horizontal)
        self.size.setRange(70, 160)
        self.size.setSingleStep(5)
        self.size.setFixedWidth(260)
        self.size_lbl = QLabel()
        self.size_lbl.setProperty("role", "value")
        self.size_lbl.setFixedWidth(52)
        self.size.valueChanged.connect(self.on_size)
        self.size.sliderReleased.connect(lambda: self.set("scale", self.size.value() / 100))
        sl.addWidget(self.size)
        sl.addWidget(self.size_lbl)
        lay.addWidget(row("Taille du texte", sz))

        lbl = QLabel("Police")
        lbl.setProperty("role", "rowtitle")
        lay.addWidget(lbl)
        self.preview = FontPreview(self.app)
        lay.addWidget(self.preview)
        self.font_search = QLineEdit()
        self.font_search.setPlaceholderText("\U0001F50D  Rechercher une police…")
        self.font_search.setClearButtonEnabled(True)
        self.font_search.textChanged.connect(self.filter_fonts)
        lay.addWidget(self.font_search)
        self.font_list = QListWidget()
        self.font_list.setFixedHeight(250)
        self.font_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.populate_fonts()
        self.font_list.currentItemChanged.connect(self.on_font)
        lay.addWidget(self.font_list)
        return card

    def build_options(self):
        card, lay = section("Options")
        self.opt = {}
        for key, title, hint in (
            ("translation", "Traduction en français", "Sous la ligne, pour les chansons qui ne sont pas en français."),
            ("beat", "Pulsation sur le beat", "Le texte grossit légèrement sur la grosse caisse."),
            ("card", "Carte de la pochette", "Pochette, titre et artiste quelques secondes au début du morceau."),
            ("particles", "Particules sur les mots tenus", "Petites étincelles quand le chanteur tient une note."),
        ):
            t = Toggle()
            t.toggled.connect(lambda v, k=key: self.set(k, bool(v)))
            lay.addWidget(row(title, t, hint))
            self.opt[key] = t
        self.title_drop = Segmented(TITLE_DROP)
        self.title_drop.changed.connect(lambda k: self.set("title_drop", k))
        lay.addWidget(row("Titre en géant", self.title_drop,
                          "Quand le chanteur dit le titre du morceau, il s'affiche en très grand "
                          "(en jeu : dans un espace libre, jamais sur l'action)."))
        self.demo = Toggle()
        self.demo.toggled.connect(lambda v: None if self._building else self.app.set_demo(v))
        lay.addWidget(row("Mode démo", self.demo, "Des paroles de test en boucle, pour essayer les réglages sans musique."))
        self.autostart = Toggle()
        self.autostart.setChecked(autostart_enabled())
        self.autostart.toggled.connect(lambda v: None if self._building else set_autostart(bool(v)))
        lay.addWidget(row("Lancer avec Windows", self.autostart,
                          "Démarre tout seul à l'allumage du PC, discrètement près de l'heure."))
        return card

    def build_sources(self):
        card, lay = section("Sources de musique")
        hint = QLabel("Les applis qui diffusent du son. Décoche celles qui ne servent pas à la musique "
                      "(par exemple le navigateur où tu regardes des vidéos) : elles seront ignorées. "
                      "Les médias de plus de 20 minutes (films, lives) sont toujours ignorés.")
        hint.setProperty("role", "hint")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        self.sources_box = QVBoxLayout()
        self.sources_box.setSpacing(12)
        lay.addLayout(self.sources_box)
        self._sources_shown = None
        return card

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
            lbl.setProperty("role", "hint")
            self.sources_box.addWidget(lbl)
            return
        for app_id in ids:
            t = Toggle()
            t.setChecked(app_id not in blocked)
            t.toggled.connect(lambda v, a=app_id: self.app.set_source_enabled(a, v))
            self.sources_box.addWidget(row(app_label(app_id), t))

    def build_sync_games(self):
        card, lay = section("Synchro et jeux")
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        later = QPushButton("− 0,1 s")
        earlier = QPushButton("+ 0,1 s")
        reset = QPushButton("Réinitialiser")
        for b in (later, earlier, reset):
            b.setProperty("role", "ghost")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        self.offset_lbl = QLabel()
        self.offset_lbl.setProperty("role", "value")
        self.offset_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.offset_lbl.setFixedWidth(70)
        later.clicked.connect(lambda: self.set("offset", round(self.app.cfg["offset"] - 0.1, 2)))
        earlier.clicked.connect(lambda: self.set("offset", round(self.app.cfg["offset"] + 0.1, 2)))
        reset.clicked.connect(lambda: self.set("offset", 0.0))
        h.addWidget(later)
        h.addWidget(self.offset_lbl)
        h.addWidget(earlier)
        h.addWidget(reset)
        lay.addWidget(row("Décalage des paroles", w, "Paroles en retard : + ; en avance : −."))

        g = QWidget()
        gl = QHBoxLayout(g)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setSpacing(8)
        zones = QPushButton("Voir les zones (5 s)")
        prof = QPushButton("Modifier les profils…")
        for b in (zones, prof):
            b.setProperty("role", "ghost")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        zones.clicked.connect(self.app.show_zones)
        prof.clicked.connect(self.app.edit_profiles)
        gl.addWidget(zones)
        gl.addWidget(prof)
        self.profile_row = row("Jeu détecté : Bureau", g, "Les paroles évitent les zones importantes du jeu (vie, minimap, score…).")
        self.profile_lbl = self.profile_row.title_label
        lay.addWidget(self.profile_row)
        self.fs_warn = QLabel()
        self.fs_warn.setProperty("role", "warn")
        self.fs_warn.setWordWrap(True)
        self.fs_warn.hide()
        lay.addWidget(self.fs_warn)
        tip = QLabel("Astuce : mets tes jeux en « fenêtré sans bordure ». En plein écran exclusif, "
                     "Windows n'affiche aucune fenêtre par-dessus le jeu.")
        tip.setProperty("role", "hint")
        tip.setWordWrap(True)
        lay.addWidget(tip)
        return card

    def build_shortcuts(self):
        card, lay = section("Raccourcis (marchent en jeu)")
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)
        items = [("Ctrl+Alt+L", "Afficher / masquer"), ("Ctrl+Alt+M", "Changer de mode"),
                 ("Ctrl+Alt+T", "Couleurs album / blanc"), ("Ctrl+Alt+S", "Changer d'animation"),
                 ("Ctrl+Alt+Z", "Voir les zones du jeu"), ("Ctrl+Alt+↑ / ↓", "Paroles plus tôt / tard")]
        for i, (k, d) in enumerate(items):
            key = QLabel(k)
            key.setProperty("role", "key")
            desc = QLabel(d)
            desc.setProperty("role", "hint")
            grid.addWidget(key, i // 2, (i % 2) * 2, Qt.AlignmentFlag.AlignLeft)
            grid.addWidget(desc, i // 2, (i % 2) * 2 + 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        lay.addLayout(grid)
        return card

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

    def sync_from_cfg(self):
        cfg = self.app.cfg
        self._building = True
        try:
            self.mode_cards[cfg["mode"]].setChecked(True)
            self.position.set_value(cfg["position"])
            column = cfg["mode"] in ("classic", "typewriter")
            self.position.setEnabled(column)
            self.position_row.setEnabled(column)
            self.color.set_value(cfg["color"])
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
            self.offset_lbl.setText(f"{cfg['offset']:+.1f} s")
            fam = cfg.get("font")
            for it in self._font_items:
                if it.data(Qt.ItemDataRole.UserRole) == fam:
                    self.font_list.setCurrentItem(it)
                    break
        finally:
            self._building = False
        self.preview.update()
        for c in self.mode_cards.values():
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
            self.state_lbl.setText("" if o.playing else "En pause")
        else:
            self.np_title.setText("Aucune musique")
            self.np_artist.setText("Lance une musique sur Spotify, YouTube Music, Deezer…")
            self.progress.set_values(0, 0)
            self.state_lbl.setText("")
        if o.cover_img is not self._cover_src:
            self._cover_src = o.cover_img
            self.cover.set_image(o.cover_img)
        badge = o.card_badge() if t is not None else ""
        self.badge.setText(badge)
        self.badge.setVisible(bool(badge))
        self.badge.setProperty("kind", "word" if (o.state == "ok" and o.word_sync) else "line")
        self.badge.style().unpolish(self.badge)
        self.badge.style().polish(self.badge)
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
        self.profile_lbl.setText(f"Jeu détecté : {o.profile.get('nom', o.profile_key)}")
        if getattr(self.app, "exclusive", False):
            self.fs_warn.setText("⚠  Plein écran exclusif détecté : les paroles ne peuvent pas passer "
                                 "par-dessus le jeu. " + (self.app.exclusive_tip or ""))
            self.fs_warn.show()
        else:
            self.fs_warn.hide()
        accent = QColor(o.accent[0]) if o.cover_img is not None else DEFAULT_ACCENT
        if accent.name() != self._accent_name:
            self.apply_style(accent)
            self.preview.update()

    # ---- style ---------------------------------------------------------------
    def apply_style(self, accent: QColor):
        self._accent_name = accent.name()
        UI["accent"] = QColor(accent)
        a = accent.name()
        r, g, b = accent.red(), accent.green(), accent.blue()
        self.setStyleSheet(f"""
            QWidget#Panel {{ background: {BG}; }}
            QWidget#Content {{ background: transparent; }}
            QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; }}
            QLabel {{ color: {TEXT}; background: transparent; }}
            QFrame[role="card"] {{ background: {CARD}; border: 1px solid {CARD_BORDER}; border-radius: 18px; }}
            QFrame[role="sep"] {{ background: {CARD_BORDER}; border: none; }}
            QLabel[role="section"] {{ color: {DIM}; font: 700 11px "Segoe UI Variable Text"; letter-spacing: 1.6px; }}
            QLabel[role="apptitle"] {{ font: 800 24px "Segoe UI Variable Display"; }}
            QLabel[role="rowtitle"] {{ font: 600 14px "Segoe UI Variable Text"; }}
            QLabel[role="hint"] {{ color: {DIM}; font: 12px "Segoe UI Variable Text"; }}
            QLabel[role="value"] {{ color: {TEXT}; font: 600 13px "Segoe UI Variable Text"; }}
            QLabel[role="nptitle"] {{ font: 800 21px "Segoe UI Variable Display"; }}
            QLabel[role="npartist"] {{ color: {DIM}; font: 14px "Segoe UI Variable Text"; }}
            QLabel[role="lyric"] {{ font: 700 17px "Segoe UI Variable Display"; color: {TEXT}; }}
            QLabel[role="badge"] {{ font: 700 10px "Segoe UI Variable Text"; padding: 3px 9px; border-radius: 9px;
                                    color: #b9bdc9; background: rgba(185,189,201,0.12); border: 1px solid rgba(185,189,201,0.35); }}
            QLabel[role="badge"][kind="word"] {{ color: {a}; background: rgba({r},{g},{b},0.14); border: 1px solid rgba({r},{g},{b},0.6); }}
            QLabel[role="key"] {{ font: 700 12px "Cascadia Code", "Consolas"; color: {TEXT}; background: {FIELD};
                                  border: 1px solid {CARD_BORDER}; border-bottom: 2px solid #2c303d; border-radius: 7px; padding: 4px 9px; }}
            QPushButton[role="seg"] {{ background: {FIELD}; color: #c7cbd6; border: 1px solid {CARD_BORDER};
                                       padding: 8px 16px; border-radius: 10px; font: 600 13px "Segoe UI Variable Text"; }}
            QPushButton[role="seg"]:hover {{ border-color: rgba({r},{g},{b},0.7); }}
            QPushButton[role="seg"]:checked {{ background: {a}; color: {BG}; border-color: {a}; }}
            QPushButton[role="seg"]:disabled {{ color: #4b5060; background: #15171f; }}
            QPushButton[role="seg"]:checked:disabled {{ background: rgba({r},{g},{b},0.25); color: #6b7080; }}
            QPushButton[role="ghost"] {{ background: {FIELD}; color: {TEXT}; border: 1px solid {CARD_BORDER};
                                         padding: 8px 14px; border-radius: 10px; font: 600 13px "Segoe UI Variable Text"; }}
            QPushButton[role="ghost"]:hover {{ border-color: {a}; }}
            QPushButton[role="ghost"]:pressed {{ background: rgba({r},{g},{b},0.2); }}
            QLineEdit {{ background: {FIELD}; color: {TEXT}; border: 1px solid {CARD_BORDER}; border-radius: 10px;
                         padding: 9px 12px; font: 14px "Segoe UI Variable Text"; selection-background-color: {a}; }}
            QLineEdit:focus {{ border-color: {a}; }}
            QListWidget {{ background: #101219; color: {TEXT}; border: 1px solid {CARD_BORDER}; border-radius: 12px;
                           padding: 6px; outline: none; }}
            QListWidget::item {{ padding: 4px 10px; border-radius: 8px; }}
            QListWidget::item:hover {{ background: #1b1e29; }}
            QListWidget::item:selected {{ background: rgba({r},{g},{b},0.22); color: white; }}
            QSlider::groove:horizontal {{ height: 6px; background: #262a36; border-radius: 3px; }}
            QSlider::sub-page:horizontal {{ background: {a}; border-radius: 3px; }}
            QSlider::handle:horizontal {{ background: white; width: 18px; height: 18px; margin: -6px 0; border-radius: 9px; }}
            QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
            QScrollBar::handle:vertical {{ background: #2a2e3b; border-radius: 4px; min-height: 30px; }}
            QScrollBar::handle:vertical:hover {{ background: #3a3f50; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
            QLabel[role="rowtitle"] {{ color: {TEXT}; }}
            QLabel[role="rowtitle"]:disabled {{ color: #5a5f6e; }}
            QLabel[role="hint"]:disabled {{ color: #4b5060; }}
            QLabel[role="warn"] {{ color: #ffcf7a; background: rgba(255,170,60,0.10); border: 1px solid rgba(255,170,60,0.45);
                                   border-radius: 10px; padding: 10px 12px; font: 600 13px "Segoe UI Variable Text"; }}
        """)
        for w in self.findChildren(QWidget):
            w.update()
        self.update()

    def paintEvent(self, _):
        """Fond sombre avec une lueur aux couleurs de la pochette."""
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(BG))
        acc = UI["accent"]
        g = QRadialGradient(QPointF(self.width() * 0.12, 0), self.width() * 0.6)
        g.setColorAt(0, QColor(acc.red(), acc.green(), acc.blue(), 46))
        g.setColorAt(1, QColor(acc.red(), acc.green(), acc.blue(), 0))
        p.fillRect(self.rect(), QBrush(g))
        g2 = QRadialGradient(QPointF(self.width(), self.height()), self.width() * 0.5)
        g2.setColorAt(0, QColor(acc.red(), acc.green(), acc.blue(), 22))
        g2.setColorAt(1, QColor(acc.red(), acc.green(), acc.blue(), 0))
        p.fillRect(self.rect(), QBrush(g2))

    def showEvent(self, e):
        super().showEvent(e)
        try:  # barre de titre sombre (Windows 10/11)
            val = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(int(self.winId()), 20, ctypes.byref(val), ctypes.sizeof(val))
        except Exception:
            pass
        self.refresh()

    def closeEvent(self, e):
        """Fermer le panneau ne quitte pas : les paroles continuent (icone ♪ pour le rouvrir)."""
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
