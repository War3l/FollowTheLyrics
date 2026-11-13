"""Ecran de bienvenue affiche au tout premier lancement."""
import ctypes

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from panel import BG, CARD_BORDER, DIM, FIELD, TEXT, Toggle, icon_pixmap, make_icon, ui_font
import install
from settings import FROZEN, autostart_enabled

ACCENT = QColor("#8B7CFF")

STEPS = (
    ("Lance ta musique",
     "Spotify, YouTube Music, Deezer, Apple Music… Les paroles arrivent toutes seules, sans compte à connecter."),
    ("Joue en « fenêtré sans bordure »",
     "C'est le mode d'affichage qui laisse les paroles passer par-dessus le jeu. Il se règle dans les options vidéo du jeu."),
    ("Ctrl + Alt + L pour masquer",
     "Le raccourci marche en pleine partie. L'icône près de l'heure rouvre les réglages à tout moment."),
)


class Badge(QWidget):
    """Pastille numerotee en degrade."""

    def __init__(self, n):
        super().__init__()
        self.n = n
        self.setFixedSize(38, 38)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        g = QLinearGradient(0, 0, 38, 38)
        g.setColorAt(0, QColor("#5EE7FF"))
        g.setColorAt(0.5, QColor("#8B7CFF"))
        g.setColorAt(1, QColor("#FF6FB5"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawRoundedRect(QRectF(0, 0, 38, 38), 12, 12)
        p.setPen(QColor(14, 12, 28))
        p.setFont(ui_font(17, QFont.Weight.Black, "Segoe UI Variable Display"))
        p.drawText(QRectF(0, 0, 38, 37), Qt.AlignmentFlag.AlignCenter, str(self.n))


class Welcome(QWidget):
    """Fenetre sans bordure, centree : 3 etapes, quelques options, 1 bouton."""
    finished = pyqtSignal(bool, bool, bool)  # (lancer avec Windows, raccourci bureau, installer)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bienvenue dans FollowTheLyrics")
        self.setWindowIcon(make_icon())
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.can_install = FROZEN and not install.running_installed()
        self.setFixedSize(660, 640 + (60 if FROZEN else 0) + (72 if self.can_install else 0))
        self._drag = None
        self._done = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(44, 40, 44, 34)
        lay.setSpacing(0)

        logo = QLabel()
        logo.setPixmap(icon_pixmap(144))
        logo.setScaledContents(True)
        logo.setFixedSize(72, 72)
        lay.addWidget(logo, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(18)
        title = QLabel("Bienvenue dans FollowTheLyrics")
        title.setProperty("role", "title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)
        lay.addSpacing(6)
        sub = QLabel("Les paroles de ta musique, par-dessus tes jeux.")
        sub.setProperty("role", "sub")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(sub)
        lay.addSpacing(26)

        for i, (head, text) in enumerate(STEPS, 1):
            line = QHBoxLayout()
            line.setSpacing(16)
            line.addWidget(Badge(i), 0, Qt.AlignmentFlag.AlignTop)
            box = QVBoxLayout()
            box.setSpacing(3)
            h = QLabel(head)
            h.setProperty("role", "head")
            t = QLabel(text)
            t.setProperty("role", "text")
            t.setWordWrap(True)
            box.addWidget(h)
            box.addWidget(t)
            line.addLayout(box, 1)
            lay.addLayout(line)
            lay.addSpacing(16)

        lay.addSpacing(16)
        self.autostart = Toggle()
        self.autostart.setChecked(autostart_enabled())
        lay.addLayout(self._option("Lancer avec Windows", self.autostart))
        self.shortcut = Toggle()
        self.shortcut.setChecked(FROZEN)
        if FROZEN:
            lay.addSpacing(28)
            lay.addLayout(self._option("Créer un raccourci sur le bureau", self.shortcut))
        self.setup = Toggle()
        self.setup.setChecked(self.can_install)
        if self.can_install:
            lay.addSpacing(28)
            lay.addLayout(self._option("Installer sur ce PC (icône dans le menu Démarrer)", self.setup))
        lay.addStretch(1)

        go = QPushButton("C'est parti")
        go.setProperty("role", "go")
        go.setCursor(Qt.CursorShape.PointingHandCursor)
        go.setFixedHeight(50)
        go.setDefault(True)
        go.clicked.connect(self.accept)
        lay.addWidget(go)

        a = ACCENT.name()
        self.setStyleSheet(f"""
            QLabel {{ color: {TEXT}; background: transparent; }}
            QLabel[role="title"] {{ font: 800 27px "Segoe UI Variable Display"; }}
            QLabel[role="sub"] {{ color: {DIM}; font: 15px "Segoe UI Variable Text"; }}
            QLabel[role="head"] {{ font: 700 15px "Segoe UI Variable Text"; }}
            QLabel[role="text"] {{ color: {DIM}; font: 13px "Segoe UI Variable Text"; }}
            QLabel[role="opt"] {{ font: 600 14px "Segoe UI Variable Text"; }}
            QPushButton[role="go"] {{ color: #0e0c1c; border: none; border-radius: 14px;
                font: 800 16px "Segoe UI Variable Display";
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #5EE7FF, stop:0.5 {a}, stop:1 #FF6FB5); }}
            QPushButton[role="go"]:hover {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #8ff0ff, stop:0.5 #a99dff, stop:1 #ff94c8); }}
            QPushButton[role="go"]:pressed {{ padding-top: 2px; }}
        """)

    def _option(self, label, toggle):
        line = QHBoxLayout()
        line.setContentsMargins(16, 0, 14, 0)
        lbl = QLabel(label)
        lbl.setProperty("role", "opt")
        line.addWidget(lbl, 1)
        line.addWidget(toggle)
        return line

    # ---- dessin / deplacement -------------------------------------------------
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(r, 26, 26)
        p.fillPath(path, QColor(BG))
        p.setClipPath(path)
        for cx, cy, col, alpha in ((0.1, 0.0, "#5EE7FF", 60), (0.95, 0.05, "#FF6FB5", 46), (0.5, 1.05, "#8B7CFF", 40)):
            c = QColor(col)
            g = QRadialGradient(QPointF(r.width() * cx, r.height() * cy), r.width() * 0.62)
            g.setColorAt(0, QColor(c.red(), c.green(), c.blue(), alpha))
            g.setColorAt(1, QColor(c.red(), c.green(), c.blue(), 0))
            p.fillRect(r, QBrush(g))
        # fonds des deux lignes d'options
        p.setPen(QPen(QColor(CARD_BORDER), 1))
        p.setBrush(QColor(FIELD))
        for t in (self.autostart, self.shortcut, self.setup):
            if t.isVisible():
                y = t.geometry().center().y()
                p.drawRoundedRect(QRectF(44, y - 22, r.width() - 86, 44), 12, 12)
        p.setClipping(False)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 34), 1))
        p.drawPath(path)

    def showEvent(self, e):
        super().showEvent(e)
        scr = self.screen().availableGeometry()
        self.move(scr.center().x() - self.width() // 2, scr.center().y() - self.height() // 2)
        try:  # coins arrondis + ombre Windows 11
            val = ctypes.c_int(2)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(int(self.winId()), 33, ctypes.byref(val), ctypes.sizeof(val))
        except Exception:
            pass

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, _):
        self._drag = None

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.accept()
        elif e.key() == Qt.Key.Key_Escape:
            self.close()  # passer : rien n'est cree ni modifie

    def accept(self):
        if self._done:
            return
        self._done = True
        self.finished.emit(self.autostart.isChecked(), FROZEN and self.shortcut.isChecked(),
                           self.can_install and self.setup.isChecked())
        self.close()

    def closeEvent(self, e):
        if not self._done:  # fermee autrement (Alt+F4) : on ne change rien, mais on continue
            self._done = True
            self.finished.emit(autostart_enabled(), False, False)
        e.accept()
