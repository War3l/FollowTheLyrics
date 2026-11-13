import logging

from PyQt6.QtCore import QRectF
from PyQt6.QtCore import Qt
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QBrush
from PyQt6.QtGui import QColor
from PyQt6.QtGui import QFont
from PyQt6.QtGui import QLinearGradient
from PyQt6.QtGui import QPainter
from PyQt6.QtGui import QPainterPath
from PyQt6.QtGui import QPen
from PyQt6.QtWidgets import QHBoxLayout
from PyQt6.QtWidgets import QLabel
from PyQt6.QtWidgets import QPushButton
from PyQt6.QtWidgets import QVBoxLayout
from PyQt6.QtWidgets import QWidget

from followthelyrics import i18n
from followthelyrics.config import settings
from followthelyrics.ui import widgets

logger = logging.getLogger(__name__)

STEPS = (
    (
        "Lance ta musique",
        "Spotify, YouTube Music, Deezer, Apple Music… Les paroles arrivent "
        "toutes seules, sans compte à connecter.",
    ),
    (
        "Joue en « fenêtré sans bordure »",
        "C'est le mode d'affichage qui laisse les paroles passer par-dessus "
        "le jeu. Il se règle dans les options vidéo du jeu.",
    ),
    (
        "Ctrl + Alt + L pour masquer",
        "Le raccourci marche en pleine partie. L'icône près de l'heure rouvre "
        "les réglages à tout moment.",
    ),
)


class Badge(QWidget):
    def __init__(self, n):
        super().__init__()
        self.n = n
        self.setFixedSize(38, 38)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(255, 255, 255, 80), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(0.5, 0.5, 37, 37))
        p.setPen(QColor(widgets.TEXT))
        p.setFont(widgets.ui_font(16, QFont.Weight.Normal))
        p.drawText(
            QRectF(0, 0, 38, 37), Qt.AlignmentFlag.AlignCenter, str(self.n)
        )


class Welcome(QWidget):
    finished = pyqtSignal(bool, bool, bool)

    def __init__(self, desktop_startup, installation, desktop):
        super().__init__()
        self.startup = desktop_startup
        self.windowing = desktop.windowing
        self.setWindowTitle(i18n.tr("Bienvenue dans FollowTheLyrics"))
        self.setWindowIcon(widgets.make_icon())
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.can_install = (
            settings.FROZEN
            and installation is not None
            and not installation.running_installed()
        )
        self.offers_shortcut = (
            settings.FROZEN and desktop_startup.supports_shortcuts
        )
        self.offers_autostart = desktop_startup.supports_autostart
        self.setFixedSize(
            660,
            592
            + (48 if self.offers_autostart else 0)
            + (60 if self.offers_shortcut else 0)
            + (72 if self.can_install else 0),
        )
        self._drag = None
        self._done = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(44, 40, 44, 34)
        lay.setSpacing(0)

        logo = QLabel()
        logo.setPixmap(widgets.icon_pixmap(144))
        logo.setScaledContents(True)
        logo.setFixedSize(72, 72)
        lay.addWidget(logo, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(18)
        title = QLabel(i18n.tr("Bienvenue dans FollowTheLyrics"))
        title.setProperty("role", "title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)
        lay.addSpacing(6)
        sub = QLabel(i18n.tr("Les paroles de ta musique, par-dessus tes jeux."))
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
            h = QLabel(i18n.tr(head))
            h.setProperty("role", "head")
            t = QLabel(i18n.tr(text))
            t.setProperty("role", "text")
            t.setWordWrap(True)
            box.addWidget(h)
            box.addWidget(t)
            line.addLayout(box, 1)
            lay.addLayout(line)
            lay.addSpacing(16)

        lay.addSpacing(16)
        self.autostart = widgets.Toggle()
        self.autostart.setChecked(desktop_startup.enabled())
        if self.offers_autostart:
            lay.addLayout(
                self._option(
                    i18n.tr("Lancer avec {}").format(desktop.name),
                    self.autostart,
                )
            )
        self.shortcut = widgets.Toggle()
        self.shortcut.setChecked(self.offers_shortcut)
        if self.offers_shortcut:
            lay.addSpacing(28)
            lay.addLayout(
                self._option(
                    i18n.tr("Créer un raccourci sur le bureau"), self.shortcut
                )
            )
        self.setup = widgets.Toggle()
        self.setup.setChecked(self.can_install)
        if self.can_install:
            lay.addSpacing(28)
            lay.addLayout(
                self._option(
                    i18n.tr(
                        "Installer sur ce PC (icône dans le menu Démarrer)"
                    ),
                    self.setup,
                )
            )
        lay.addStretch(1)

        go = QPushButton(i18n.tr("C'est parti"))
        go.setProperty("role", "go")
        go.setCursor(Qt.CursorShape.PointingHandCursor)
        go.setFixedHeight(50)
        go.setDefault(True)
        go.clicked.connect(self.accept)
        lay.addWidget(go)

        a = widgets.DEFAULT_ACCENT.name()
        self.setStyleSheet(f"""
            QLabel {{
                color: {widgets.TEXT};
                background: transparent;
            }}
            QLabel[role="title"] {{
                font: 400 30px "{widgets.font_family()}";
            }}
            QLabel[role="sub"] {{
                color: {widgets.DIM};
                font: 15px "{widgets.font_family()}";
            }}
            QLabel[role="head"] {{
                font: 600 15px "{widgets.font_family()}";
            }}
            QLabel[role="text"] {{
                color: {widgets.DIM};
                font: 13px "{widgets.font_family()}";
            }}
            QLabel[role="opt"] {{
                font: 500 14px "{widgets.font_family()}";
            }}
            QPushButton[role="go"] {{
                color: {widgets.ink_for(widgets.DEFAULT_ACCENT).name()};
                border: none;
                border-radius: 24px;
                font: 600 15px "{widgets.font_family()}";
                background: {a};
            }}
            QPushButton[role="go"]:hover {{
                background: #ffffff;
            }}
            QPushButton[role="go"]:pressed {{
                padding-top: 2px;
            }}
        """)

    def _option(self, label, toggle):
        line = QHBoxLayout()
        line.setContentsMargins(16, 0, 14, 0)
        lbl = QLabel(label)
        lbl.setProperty("role", "opt")
        line.addWidget(lbl, 1)
        line.addWidget(toggle)
        return line

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(r, 30, 30)
        p.fillPath(path, QColor(widgets.BG))
        p.setClipPath(path)
        sheen = QLinearGradient(0, 0, 0, r.height())
        sheen.setColorAt(0, QColor(255, 255, 255, 26))
        sheen.setColorAt(0.6, QColor(255, 255, 255, 0))
        p.fillRect(r, QBrush(sheen))
        p.setPen(QPen(QColor(widgets.CARD_BORDER), 1))
        p.setBrush(QColor(widgets.FIELD))
        for t in (self.autostart, self.shortcut, self.setup):
            if t.isVisible():
                y = t.geometry().center().y()
                p.drawRoundedRect(
                    QRectF(44, y - 22, r.width() - 86, 44), 22, 22
                )
        p.setClipping(False)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 34), 1))
        p.drawPath(path)

    def showEvent(self, e):
        super().showEvent(e)
        screen = self.screen()
        if screen is None:
            return
        scr = screen.availableGeometry()
        self.move(
            scr.center().x() - self.width() // 2,
            scr.center().y() - self.height() // 2,
        )
        self.windowing.round_corners(int(self.winId()))

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = (
                e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )

    def mouseMoveEvent(self, e):
        if self._drag is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, _):
        self._drag = None

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.accept()
        elif e.key() == Qt.Key.Key_Escape:
            self.close()

    def accept(self):
        if self._done:
            return
        self._done = True
        self.finished.emit(
            self.autostart.isChecked(),
            self.offers_shortcut and self.shortcut.isChecked(),
            self.can_install and self.setup.isChecked(),
        )
        self.close()

    def closeEvent(self, e):
        if not self._done:
            self._done = True
            self.finished.emit(self.startup.enabled(), False, False)
        e.accept()
