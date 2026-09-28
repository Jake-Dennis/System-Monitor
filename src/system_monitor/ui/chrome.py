"""Window chrome: the draggable header, the detached-card window, and the
drag indicator line.

These are plain widgets with no config, no card-registry and no AppBar
knowledge — they were ~150 lines of MainWindow purely by proximity. Keeping
them here lets main_window.py be only the orchestrator.
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizeGrip,
    QVBoxLayout,
    QWidget,
)

from . import styles


class DropIndicator(QWidget):
    """Thin colored line shown between cards during drag to show insert position."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(3)
        self.hide()

    def paintEvent(self, event: QPaintEvent) -> None:  # type: ignore[override]
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(styles.current_accent()))


class DetachedWindow(QMainWindow):
    """A small frameless window hosting one detached card."""

    reattach = Signal(object)  # emits the card widget to reattach

    def __init__(self, card: QWidget, title: str) -> None:
        super().__init__()
        self._card = card
        self._drag_pos: QPoint | None = None
        self.setWindowTitle(title)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setMinimumSize(QSize(360, 200))

        root = QWidget()
        root.setObjectName("PanelRoot")
        outer = QVBoxLayout(root)
        outer.setContentsMargins(12, 8, 12, 12)
        outer.setSpacing(6)

        # Draggable header with title and reattach button
        self._header = QWidget()
        self._header.setObjectName("PanelHeader")
        self._header.setFixedHeight(34)
        hdr = QHBoxLayout(self._header)
        hdr.setContentsMargins(12, 0, 8, 0)
        lbl = QLabel(title)
        lbl.setObjectName("HeaderTitle")
        hdr.addWidget(lbl)
        hdr.addStretch(1)
        attach_btn = QPushButton("⤵")
        attach_btn.setObjectName("IconButton")
        attach_btn.setToolTip("Reattach to main panel")
        attach_btn.clicked.connect(lambda: self._do_reattach())
        hdr.addWidget(attach_btn)
        outer.addWidget(self._header)
        outer.addWidget(card, 1)
        card.setVisible(True)

        grip = QSizeGrip(self)
        grip.setStyleSheet(
            "QSizeGrip { width: 12px; height: 12px; "
            "background: rgba(255,255,255,30); border-radius: 4px; }"
        )
        outer.addWidget(grip, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)

        self.setCentralWidget(root)
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            self.setStyleSheet(app.styleSheet())

    def _do_reattach(self) -> None:
        self.reattach.emit(self._card)
        self.close()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.reattach.emit(self._card)
        super().closeEvent(event)

    def mousePressEvent(self, e: QMouseEvent) -> None:  # type: ignore[override]
        if e.button() == Qt.MouseButton.LeftButton and e.position().y() <= self._header.height():
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            e.accept()

    def mouseMoveEvent(self, e: QMouseEvent) -> None:  # type: ignore[override]
        if self._drag_pos is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_pos)
            e.accept()

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:  # type: ignore[override]
        self._drag_pos = None


class PanelHeader(QFrame):
    """The draggable header strip with title, lock, and close buttons."""

    toggle_lock_clicked = Signal()
    close_clicked = Signal()
    settings_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Header")
        self.setFixedHeight(34)
        h = QHBoxLayout(self)
        h.setContentsMargins(12, 0, 8, 0)
        h.setSpacing(6)

        self._title = QLabel("SYSTEM MONITOR")
        self._title.setObjectName("HeaderTitle")
        h.addWidget(self._title)

        self._subtitle = QLabel("")
        self._subtitle.setObjectName("HeaderSub")
        h.addSpacing(8)
        h.addWidget(self._subtitle)
        h.addStretch(1)

        self._lock = QPushButton("\U0001F513")
        self._lock.setObjectName("IconButton")
        self._lock.setToolTip("Toggle drag-lock (L)")
        self._lock.clicked.connect(self.toggle_lock_clicked)
        h.addWidget(self._lock)

        self._settings = QPushButton("⚙")
        self._settings.setObjectName("IconButton")
        self._settings.setToolTip("Settings")
        self._settings.clicked.connect(self.settings_clicked)
        h.addWidget(self._settings)

        self._close = QPushButton("✕")
        self._close.setObjectName("IconButton")
        self._close.setToolTip("Close (Esc)")
        self._close.clicked.connect(self.close_clicked)
        h.addWidget(self._close)

        self._drag_pos: QPoint | None = None
        self._locked = False
        self.set_locked(False)

    def set_subtitle(self, text: str) -> None:
        self._subtitle.setText(text)

    def set_locked(self, locked: bool) -> None:
        self._locked = bool(locked)
        self._lock.setText("\U0001F512" if self._locked else "\U0001F513")

    def mousePressEvent(self, e: QMouseEvent) -> None:  # type: ignore[override]
        if self._locked:
            return
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
            e.accept()

    def mouseMoveEvent(self, e: QMouseEvent) -> None:  # type: ignore[override]
        if self._drag_pos is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self.window().move(e.globalPosition().toPoint() - self._drag_pos)
            e.accept()

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:  # type: ignore[override]
        self._drag_pos = None
