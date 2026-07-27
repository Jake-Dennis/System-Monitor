"""Base card widget for the panel.

Each metric card exposes `update(snapshot_slice)` and renders a title,
primary value, and a colored progress bar. Subclasses customize the
mapping from snapshot to display values.

Cards support drag-and-drop reordering via the `card_dropped` signal.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QMimeData, Qt, Signal
from PySide6.QtGui import QDrag, QEnterEvent, QMouseEvent, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from .. import styles


class _Card(QFrame):
    """Base card widget. Draggable for reordering."""

    card_dropped = Signal(str, str)  # dragged_card_title, target_card_title

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._card_title = title
        self.setObjectName("Card")
        self.setProperty("hovered", False)
        self.setMinimumHeight(60)
        self.setAcceptDrops(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(8)

        self._title = QLabel(title)
        self._title.setObjectName("CardTitle")

        self._value = QLabel("--")
        self._value.setObjectName("Value")
        self._value.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self._secondary = QLabel("")
        self._secondary.setObjectName("Secondary")

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(6)

        outer.addWidget(self._title)
        outer.addWidget(self._value)
        outer.addWidget(self._bar)
        outer.addWidget(self._secondary)

    # ----- drag source -----

    def mousePressEvent(self, event: QMouseEvent | None) -> None:  # type: ignore[override]
        if event is not None:
            self._drag_start = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent | None) -> None:  # type: ignore[override]
        if event is not None and hasattr(self, "_drag_start"):
            if (event.position().toPoint() - self._drag_start).manhattanLength() < 10:
                super().mouseMoveEvent(event)
                return
            drag = QDrag(self)
            mime = QMimeData()
            mime.setText(self._card_title)
            drag.setMimeData(mime)
            # Create a semi-transparent drag pixmap
            pix = self.grab()
            pix = pix.scaled(pix.width(), pix.height(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            drag.setPixmap(pix)
            drag.setHotSpot(event.position().toPoint())
            drag.exec(Qt.DropAction.MoveAction)
        super().mouseMoveEvent(event)

    # ----- drop target -----

    def dragEnterEvent(self, event) -> None:  # type: ignore[override]
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:  # type: ignore[override]
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # type: ignore[override]
        dragged = event.mimeData().text()
        if dragged and dragged != self._card_title:
            self.card_dropped.emit(dragged, self._card_title)
        event.acceptProposedAction()

    # ----- hover -----

    def enterEvent(self, event: QEnterEvent) -> None:  # type: ignore[override]
        self.setProperty("hovered", True)
        self.style().unpolish(self)
        self.style().polish(self)

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        self.setProperty("hovered", False)
        self.style().unpolish(self)
        self.style().polish(self)

    # ----- public setters used by subclasses -----

    def _set_value(self, text: str) -> None:
        self._value.setText(text)

    def _set_secondary(self, text: str) -> None:
        self._secondary.setText(text)

    def _set_bar(self, percent: float, color: str) -> None:
        self._bar.setValue(int(max(0.0, min(100.0, percent))))
        self._bar.setStyleSheet(
            f"QProgressBar::chunk {{ background: {color}; border-radius: 3px; }}"
        )

    def update(self, snapshot: Any) -> None:  # pragma: no cover - abstract
        raise NotImplementedError


def _h_split(value: float, used: float, total: float) -> str:
    return f"{value:.1f} · {used:.1f}/{total:.1f} GB"


def make_section_header(title: str) -> QWidget:
    """Small uppercase section header used between widget groups."""
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(4, 8, 4, 4)
    lbl = QLabel(title)
    lbl.setObjectName("CardTitle")
    h.addWidget(lbl)
    h.addStretch(1)
    return w
