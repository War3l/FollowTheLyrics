import logging

from PyQt6.QtCore import QPointF
from PyQt6.QtCore import QRectF
from PyQt6.QtCore import Qt
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtGui import QFont
from PyQt6.QtGui import QImage
from PyQt6.QtGui import QPainter
from PyQt6.QtGui import QPen
from PyQt6.QtWidgets import QComboBox
from PyQt6.QtWidgets import QHBoxLayout
from PyQt6.QtWidgets import QLabel
from PyQt6.QtWidgets import QLineEdit
from PyQt6.QtWidgets import QPushButton
from PyQt6.QtWidgets import QVBoxLayout
from PyQt6.QtWidgets import QWidget

from followthelyrics.config import games
from followthelyrics.ui import widgets

logger = logging.getLogger(__name__)

ACCENT = "#8B7CFF"
HANDLE = 9
MIN_SIZE = 0.015
UPPER = 0.5


class Canvas(QWidget):
    changed = pyqtSignal()
    selected = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(640, 360)
        self.image = None
        self.zones = []
        self.sel = -1
        self._drag = None

    def view(self):
        ratio = (
            (self.image.width() / self.image.height())
            if self.image is not None
            else 16 / 9
        )
        w, h = self.width(), self.height()
        vw = min(w, h * ratio)
        vh = vw / ratio
        return QRectF((w - vw) / 2, (h - vh) / 2, vw, vh)

    def to_frac(self, pos):
        v = self.view()
        return (
            min(1.0, max(0.0, (pos.x() - v.left()) / v.width())),
            min(1.0, max(0.0, (pos.y() - v.top()) / v.height())),
        )

    def rect_of(self, z):
        v = self.view()
        return QRectF(
            v.left() + z["x"] * v.width(),
            v.top() + z["y"] * v.height(),
            z["l"] * v.width(),
            z["h"] * v.height(),
        )

    def handles(self, z):
        r = self.rect_of(z)
        return {
            "tl": r.topLeft(),
            "tr": r.topRight(),
            "bl": r.bottomLeft(),
            "br": r.bottomRight(),
        }

    def hit(self, pos):
        order = ([self.sel] if 0 <= self.sel < len(self.zones) else []) + [
            i for i in reversed(range(len(self.zones))) if i != self.sel
        ]
        for i in order:
            for name, pt in self.handles(self.zones[i]).items():
                if (
                    abs(pos.x() - pt.x()) <= HANDLE + 2
                    and abs(pos.y() - pt.y()) <= HANDLE + 2
                ):
                    return name, i
        for i in order:
            if self.rect_of(self.zones[i]).contains(pos):
                return "move", i
        return "new", -1

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            return
        self.setFocus()
        pos = e.position()
        mode, i = self.hit(pos)
        fx, fy = self.to_frac(pos)
        if mode == "new":
            if not self.view().contains(pos):
                return
            self.zones.append(
                {
                    "nom": f"Zone {len(self.zones) + 1}",
                    "x": fx,
                    "y": fy,
                    "l": 0.0,
                    "h": 0.0,
                }
            )
            i = len(self.zones) - 1
            mode = "br"
        self.select(i)
        self._drag = (mode, i, (fx, fy), dict(self.zones[i]))
        self.update()

    def mouseMoveEvent(self, e):
        pos = e.position()
        if self._drag is None:
            mode, _ = self.hit(pos)
            self.setCursor(
                {
                    "move": Qt.CursorShape.SizeAllCursor,
                    "new": Qt.CursorShape.CrossCursor,
                    "tl": Qt.CursorShape.SizeFDiagCursor,
                    "br": Qt.CursorShape.SizeFDiagCursor,
                    "tr": Qt.CursorShape.SizeBDiagCursor,
                    "bl": Qt.CursorShape.SizeBDiagCursor,
                }[mode]
            )
            return
        mode, i, (sx, sy), z0 = self._drag
        fx, fy = self.to_frac(pos)
        z = self.zones[i]
        if mode == "move":
            z["x"] = min(1.0 - z0["l"], max(0.0, z0["x"] + fx - sx))
            z["y"] = min(1.0 - z0["h"], max(0.0, z0["y"] + fy - sy))
        else:
            ax = z0["x"] + z0["l"] if "l" in mode else z0["x"]
            ay = z0["y"] + z0["h"] if "t" in mode else z0["y"]
            z["x"], z["l"] = min(ax, fx), abs(fx - ax)
            z["y"], z["h"] = min(ay, fy), abs(fy - ay)
        self.changed.emit()
        self.update()

    def mouseReleaseEvent(self, _):
        if self._drag is None:
            return
        _, i, _, _ = self._drag
        self._drag = None
        z = self.zones[i]
        if z["l"] < MIN_SIZE or z["h"] < MIN_SIZE:
            del self.zones[i]
            self.select(-1)
        for z in self.zones:
            for k in ("x", "y", "l", "h"):
                z[k] = round(z[k], 4)
        self.changed.emit()
        self.update()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_selected()
        else:
            super().keyPressEvent(e)

    def select(self, i):
        self.sel = i
        self.selected.emit(i)
        self.update()

    def delete_selected(self):
        if 0 <= self.sel < len(self.zones):
            del self.zones[self.sel]
            self.select(-1)
            self.changed.emit()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.fillRect(self.rect(), QColor("#06070a"))
        v = self.view()
        if self.image is not None:
            p.drawImage(v, self.image)
            p.fillRect(v, QColor(0, 0, 0, 70))
        else:
            p.fillRect(v, QColor("#12151d"))
            p.setPen(QPen(QColor(255, 255, 255, 14), 1))
            for k in range(1, 16):
                p.drawLine(
                    QPointF(v.left() + v.width() * k / 16, v.top()),
                    QPointF(v.left() + v.width() * k / 16, v.bottom()),
                )
            for k in range(1, 9):
                p.drawLine(
                    QPointF(v.left(), v.top() + v.height() * k / 9),
                    QPointF(v.right(), v.top() + v.height() * k / 9),
                )
            p.setPen(QColor(widgets.DIM))
            p.setFont(widgets.ui_font(16))
            p.drawText(
                QRectF(v.left(), v.top() + v.height() * 0.55, v.width(), 60),
                Qt.AlignmentFlag.AlignCenter,
                "Pas encore de capture de ce jeu.\nEn jeu, appuie sur Ctrl + "
                "Alt + E : elle s'affichera ici.",
            )
        p.setPen(QPen(QColor(120, 200, 255, 190), 1.5, Qt.PenStyle.DashLine))
        y = v.top() + v.height() * UPPER
        p.drawLine(QPointF(v.left(), y), QPointF(v.right(), y))
        p.setFont(widgets.ui_font(11, family="Segoe UI Variable Text"))
        p.setPen(QColor(150, 215, 255, 230))
        p.drawText(
            QRectF(v.left() + 8, y - 20, 400, 18),
            Qt.AlignmentFlag.AlignLeft,
            "Les paroles s'affichent au-dessus de cette ligne",
        )
        for i, z in enumerate(self.zones):
            r = self.rect_of(z)
            on = i == self.sel
            p.setPen(
                QPen(
                    QColor(255, 255, 255) if on else QColor(255, 80, 80, 230), 2
                )
            )
            p.setBrush(QColor(255, 50, 50, 95 if on else 60))
            p.drawRect(r)
            if r.width() > 50 and r.height() > 22:
                p.setPen(QColor(255, 255, 255, 240))
                p.setFont(widgets.ui_font(12, QFont.Weight.DemiBold))
                p.drawText(
                    r.adjusted(7, 5, -7, -5),
                    Qt.AlignmentFlag.AlignLeft
                    | Qt.AlignmentFlag.AlignTop
                    | Qt.TextFlag.TextWordWrap,
                    z.get("nom", ""),
                )
            if on:
                p.setPen(QPen(QColor("#0c0d12"), 1.5))
                p.setBrush(QColor("white"))
                for pt in self.handles(z).values():
                    p.drawRect(
                        QRectF(
                            pt.x() - HANDLE / 2,
                            pt.y() - HANDLE / 2,
                            HANDLE,
                            HANDLE,
                        )
                    )


class ZoneEditor(QWidget):
    def __init__(self, app, key=None):
        super().__init__()
        self.app = app
        self.key = None
        self.dirty = False
        self._loading = False
        self.setWindowTitle("FollowTheLyrics — zones à éviter")
        self.setWindowIcon(widgets.make_icon())
        self.resize(1280, 820)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        top = QHBoxLayout()
        top.setSpacing(10)
        title = QLabel("Zones à éviter")
        title.setProperty("role", "title")
        top.addWidget(title)
        self.game = QComboBox()
        self.game.setMinimumWidth(240)
        self.game.currentIndexChanged.connect(self.on_game)
        top.addWidget(self.game)
        top.addStretch(1)
        self.name = QLineEdit()
        self.name.setPlaceholderText("Nom de la zone (minimap, chat…)")
        self.name.setFixedWidth(250)
        self.name.textEdited.connect(self.on_name)
        top.addWidget(self.name)
        self.btn_del = self.button("Supprimer la zone", self.delete_zone)
        top.addWidget(self.btn_del)
        root.addLayout(top)

        self.canvas = Canvas()
        self.canvas.changed.connect(self.on_changed)
        self.canvas.selected.connect(self.on_selected)
        root.addWidget(self.canvas, 1)

        bottom = QHBoxLayout()
        bottom.setSpacing(10)
        self.hint = QLabel(
            "Clique et glisse pour dessiner une zone. Glisse une zone pour la "
            "déplacer, "
            "ses coins pour la redimensionner. Suppr l'efface."
        )
        self.hint.setProperty("role", "hint")
        self.hint.setWordWrap(True)
        bottom.addWidget(self.hint, 1)
        bottom.addWidget(self.button("Zones d'origine", self.restore_defaults))
        bottom.addWidget(self.button("Tout effacer", self.clear_all))
        bottom.addWidget(self.button("Fermer", self.close))
        self.btn_save = self.button("Enregistrer", self.save, main=True)
        self.btn_save.setMinimumWidth(140)
        bottom.addWidget(self.btn_save)
        root.addLayout(bottom)

        self.setStyleSheet(f"""
            ZoneEditor {{
                background: {widgets.BG};
            }}
            QLabel {{
                color: {widgets.TEXT};
                background: transparent;
            }}
            QLabel[role="title"] {{
                font: 800 20px "Segoe UI Variable Display";
            }}
            QLabel[role="hint"] {{
                color: {widgets.DIM};
                font: 13px "Segoe UI Variable Text";
            }}
            QPushButton {{
                background: {widgets.SOLID_FIELD};
                color: {widgets.TEXT};
                border: 1px solid {widgets.SOLID_BORDER};
                padding: 9px 16px;
                border-radius: 10px;
                font: 600 13px "Segoe UI Variable Text";
            }}
            QPushButton:hover {{
                border-color: {ACCENT};
            }}
            QPushButton:disabled {{
                color: #565b6b;
            }}
            QPushButton[main="true"] {{
                background: {ACCENT};
                color: {widgets.BG};
                border-color: {ACCENT};
                font-weight: 800;
            }}
            QPushButton[main="true"]:disabled {{
                background: #2a2740;
                color: #6b7080;
                border-color: #2a2740;
            }}
            QLineEdit, QComboBox {{
                background: {widgets.SOLID_FIELD};
                color: {widgets.TEXT};
                border: 1px solid {widgets.SOLID_BORDER};
                border-radius: 10px;
                padding: 8px 12px;
                font: 14px "Segoe UI Variable Text";
            }}
            QLineEdit:focus, QComboBox:focus {{
                border-color: {ACCENT};
            }}
            QLineEdit:disabled {{
                color: #565b6b;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 26px;
            }}
            QComboBox QAbstractItemView {{
                background: {widgets.SOLID_CARD};
                color: {widgets.TEXT};
                border: 1px solid {widgets.SOLID_BORDER};
                selection-background-color: {ACCENT};
                selection-color: {widgets.BG};
                outline: none;
            }}
        """)
        self.fill_games(key)

    def button(self, text, slot, main=False):
        b = QPushButton(text)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        if main:
            b.setProperty("main", "true")
        b.clicked.connect(slot)
        return b

    def fill_games(self, key=None):
        self._loading = True
        self.game.clear()
        profiles = self.app.profiles
        for exe, prof in profiles.get("jeux", {}).items():
            self.game.addItem(prof.get("nom", exe), exe)
        for exe in games.captured_games():
            if exe not in profiles.get("jeux", {}) and exe != "jeu_inconnu":
                self.game.addItem(f"{games.pretty_name(exe)} (nouveau)", exe)
        self.game.addItem("Autres jeux en plein écran", "jeu_inconnu")
        self._loading = False
        idx = max(0, self.game.findData(key)) if key else 0
        self.game.setCurrentIndex(idx)
        self.load(self.game.itemData(idx))

    def on_game(self, idx):
        if self._loading or idx < 0:
            return
        self.load(self.game.itemData(idx))

    def load(self, key):
        self.key = key
        profiles = self.app.profiles
        prof = profiles.get("jeux", {}).get(key) or profiles.get(
            "jeu_inconnu", {}
        )
        self.canvas.zones = [dict(z) for z in prof.get("zones_interdites", [])]
        img = QImage(games.capture_path(key))
        self.canvas.image = None if img.isNull() else img
        self.canvas.select(-1)
        self.set_dirty(False)

    def show_game(self, key):
        self.fill_games(key)

    def set_dirty(self, on):
        self.dirty = on
        self.btn_save.setEnabled(on)
        self.btn_save.setText("Enregistrer" if on else "Enregistré")

    def on_changed(self):
        self.set_dirty(True)

    def on_selected(self, i):
        ok = 0 <= i < len(self.canvas.zones)
        self.name.setEnabled(ok)
        self.btn_del.setEnabled(ok)
        self.name.setText(self.canvas.zones[i].get("nom", "") if ok else "")

    def on_name(self, text):
        i = self.canvas.sel
        if 0 <= i < len(self.canvas.zones):
            self.canvas.zones[i]["nom"] = text
            self.canvas.update()
            self.set_dirty(True)

    def delete_zone(self):
        self.canvas.delete_selected()

    def clear_all(self):
        self.canvas.zones = []
        self.canvas.select(-1)
        self.set_dirty(True)

    def restore_defaults(self):
        base = (
            games.DEFAULT_PROFILES["jeux"].get(self.key)
            or games.DEFAULT_PROFILES["jeu_inconnu"]
        )
        self.canvas.zones = [dict(z) for z in base.get("zones_interdites", [])]
        self.canvas.select(-1)
        self.set_dirty(True)

    def save(self):
        zones = [
            {
                "nom": z.get("nom", "").strip() or f"Zone {n + 1}",
                "x": z["x"],
                "y": z["y"],
                "l": z["l"],
                "h": z["h"],
            }
            for n, z in enumerate(self.canvas.zones)
        ]
        if games.save_zones(self.key, zones):
            self.app.reload_profiles()
            self.set_dirty(False)
            self.hint.setText(
                "Enregistré. Les paroles éviteront ces zones dès maintenant "
                "(Ctrl + Alt + Z en jeu pour les revoir)."
            )
            self.fill_games(self.key)
        else:
            self.hint.setText(
                "Impossible d'enregistrer le fichier des profils."
            )

    def showEvent(self, e):
        super().showEvent(e)
        self.app.desktop.windowing.dark_title_bar(int(self.winId()))
