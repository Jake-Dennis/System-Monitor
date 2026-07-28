"""Application-level event filter for card drag-and-drop.

Installed on QApplication to intercept mouse events before they reach
child widgets (QPushButton, etc.), so dragging works from any point on a card.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QMimeData, QObject, Qt, Signal
from PySide6.QtGui import QDrag, QMouseEvent
from PySide6.QtWidgets import QApplication, QWidget

from .widgets._base import _Card


class CardDragManager(QObject):
    """Installed on QApplication to intercept mouse events for card dragging.

    Catches mouse events before they reach child widgets so that drag can
    be initiated from any point on a card, including QPushButton areas.
    """

    card_dropped = Signal(str, str, int)  # dragged_name, target_name, target_idx

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._press_pos = None
        self._source_card: _Card | None = None
        self._locked = False

        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def set_locked(self, locked: bool) -> None:
        """When locked, card dragging is disabled."""
        self._locked = locked

    # ------------------------------------------------------------------
    # Event filter
    # ------------------------------------------------------------------

    def eventFilter(self, obj: QObject | None, event: QEvent | None) -> bool:
        if event is None or not isinstance(obj, QWidget):
            return super().eventFilter(obj, event)

        card = self._find_card(obj)
        if card is None:
            return super().eventFilter(obj, event)

        if event.type() == QEvent.Type.MouseButtonPress:
            me = _as_mouse_event(event)
            if me is not None and me.button() == Qt.MouseButton.LeftButton and not self._locked:
                self._press_pos = me.globalPosition().toPoint()
                self._source_card = card
            return False  # Let child widgets see the event

        elif event.type() == QEvent.Type.MouseMove:
            if self._source_card is not None and self._press_pos is not None:
                me = _as_mouse_event(event)
                if me is not None and me.buttons() & Qt.MouseButton.LeftButton:
                    dist = (me.globalPosition().toPoint() - self._press_pos).manhattanLength()
                    if dist >= QApplication.startDragDistance():
                        self._start_drag(me.globalPosition().toPoint())
                        self._press_pos = None
                        return True  # Consume — drag modal loop owns input
            return False

        elif event.type() == QEvent.Type.MouseButtonRelease:
            self._press_pos = None
            self._source_card = None
            return False

        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _find_card(self, widget: QWidget | None) -> _Card | None:
        while widget is not None:
            if isinstance(widget, _Card):
                return widget
            widget = widget.parentWidget()
        return None

    def _start_drag(self, global_pos) -> None:
        card = self._source_card
        if card is None:
            return

        drag = QDrag(card)
        mime = QMimeData()
        mime.setText(card.card_title())
        drag.setMimeData(mime)

        pix = card.grab()
        drag.setPixmap(pix)
        card_origin = card.mapToGlobal(card.rect().topLeft())
        drag.setHotSpot(global_pos - card_origin)

        drag.exec(Qt.DropAction.MoveAction)

        # Reset child widgets that may be stuck in pressed state
        for child in card.findChildren(QWidget):
            child.setAttribute(Qt.WidgetAttribute.WA_UnderMouse, False)
            child.update()

        self._source_card = None
        self._press_pos = None


def _as_mouse_event(event: QEvent) -> QMouseEvent | None:
    if event.type() in (
        QEvent.Type.MouseButtonPress,
        QEvent.Type.MouseMove,
        QEvent.Type.MouseButtonRelease,
    ):
        return event  # type: ignore[return-value]
    return None
