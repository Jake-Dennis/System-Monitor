"""Media control card — play/pause, next, prev, track info."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from ...data.media import next_track, now_playing, play_pause, prev_track
from ._base import _Card


def _std_icon(standard: QStyle.StandardPixmap) -> QIcon:
    app = QApplication.instance()
    if app is not None:
        return app.style().standardIcon(standard)
    return QIcon()


class MediaCard(_Card):
    def __init__(self, parent=None) -> None:
        super().__init__("Now Playing", parent)
        layout = self.layout()  # type: ignore[arg-type]

        # Remove the default value label and bar — we replace them.
        for i in range(layout.count() - 1, -1, -1):
            item = layout.itemAt(i)
            w = item.widget() if item is not None else None
            if w is not None and w.objectName() in ("Value", ""):
                layout.removeWidget(w)
                w.hide()
                w.deleteLater()

        # Track info
        self._track = QLabel("No media detected")
        self._track.setObjectName("Value")
        self._track.setWordWrap(True)
        self._track.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        layout.insertWidget(1, self._track)

        self._artist = QLabel("")
        self._artist.setObjectName("Secondary")
        self._artist.setWordWrap(True)
        layout.insertWidget(2, self._artist)

        # Control buttons with OS theme icons
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 4, 0, 0)
        btn_row.setSpacing(8)

        self._prev_btn = QPushButton()
        self._prev_btn.setIcon(_std_icon(QStyle.StandardPixmap.SP_MediaSkipBackward))
        self._prev_btn.setObjectName("IconButton")
        self._prev_btn.setToolTip("Previous track")
        self._prev_btn.clicked.connect(prev_track)

        self._play_btn = QPushButton()
        self._play_btn.setIcon(_std_icon(QStyle.StandardPixmap.SP_MediaPlay))
        self._play_btn.setObjectName("IconButton")
        self._play_btn.setToolTip("Play / Pause")
        self._play_btn.clicked.connect(play_pause)

        self._next_btn = QPushButton()
        self._next_btn.setIcon(_std_icon(QStyle.StandardPixmap.SP_MediaSkipForward))
        self._next_btn.setObjectName("IconButton")
        self._next_btn.setToolTip("Next track")
        self._next_btn.clicked.connect(next_track)

        btn_row.addStretch(1)
        btn_row.addWidget(self._prev_btn)
        btn_row.addWidget(self._play_btn)
        btn_row.addWidget(self._next_btn)
        btn_row.addStretch(1)

        btn_wrap = QWidget()
        btn_wrap.setLayout(btn_row)
        layout.insertWidget(3, btn_wrap)

        # Hide the default secondary text.
        for i in range(layout.count() - 1, -1, -1):
            item = layout.itemAt(i)
            w = item.widget() if item is not None else None
            if w is not None and w.objectName() == "Secondary" and w is not self._artist:
                w.hide()
                w.deleteLater()

    def update(self, snapshot: dict[str, Any]) -> None:
        media = now_playing()
        if media.get("is_active"):
            title = media.get("title", "")
            artist = media.get("artist", "")
            app = media.get("app", "")
            if title:
                self._track.setText(title[:80])
            else:
                self._track.setText("Playing...")
            if artist:
                self._artist.setText(f"{artist}  \u00b7  {app}" if app else artist)
            else:
                self._artist.setText(f"via {app}" if app else "")
        else:
            self._track.setText("No media detected")
            self._artist.setText("")
