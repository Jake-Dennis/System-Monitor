"""Media control card — now playing + playback buttons."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget

from ...data.media import next_track, now_playing, play_pause, prev_track
from ._base import _Card

# Material Symbols – outlined style, fill matches TXT_M (#8A95AD)
_FILL = "#8A95AD"
_SKIP_BACK_SVG = f"""<svg viewBox="0 -960 960 960"><path d="M280-240v-480h60v480h-60Zm0-240 346-240v480Z" fill="{_FILL}"/></svg>"""
_PLAY_SVG = f"""<svg viewBox="0 -960 960 960"><path d="M320-203v-560l440 280-440 280Z" fill="{_FILL}"/></svg>"""
_PAUSE_SVG = f"""<svg viewBox="0 -960 960 960"><path d="M525-200v-560h235v560H525Zm-325 0v-560h235v560H200Z" fill="{_FILL}"/></svg>"""
_SKIP_FWD_SVG = f"""<svg viewBox="0 -960 960 960"><path d="M680-240v-480h60v480h-60Zm0-240-346-240v480Z" fill="{_FILL}"/></svg>"""


def _svg_to_icon(svg: str, size: int = 22) -> QIcon:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    painter = QPainter(pix)
    renderer.render(painter)
    painter.end()
    return QIcon(pix)


_ICONS: dict[str, QIcon] | None = None


def _get_icons() -> dict[str, QIcon]:
    """Lazy-init icons — needs QApplication to exist."""
    global _ICONS
    if _ICONS is None:
        _ICONS = {
            "prev": _svg_to_icon(_SKIP_BACK_SVG),
            "play": _svg_to_icon(_PLAY_SVG),
            "pause": _svg_to_icon(_PAUSE_SVG),
            "next": _svg_to_icon(_SKIP_FWD_SVG),
        }
    return _ICONS


class MediaCard(_Card):
    def __init__(self, parent=None) -> None:
        super().__init__("Media")
        self.setMinimumHeight(0)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout = self.layout()

        # Strip everything built by _Card EXCEPT the title (used as drag handle)
        for i in range(layout.count() - 1, -1, -1):
            item = layout.itemAt(i)
            w = item.widget() if item is not None else None
            if w is not None and w is not self._title:
                layout.removeWidget(w)
                w.hide()
                w.deleteLater()

        layout.setSpacing(2)
        layout.setContentsMargins(18, 6, 18, 6)

        # "Now Playing: Song"
        self._track = QLabel("No media detected")
        self._track.setObjectName("ValueSmall")
        self._track.setWordWrap(True)
        layout.addWidget(self._track)

        # Centered media buttons
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(8)

        self._prev_btn = QPushButton()
        self._prev_btn.setIcon(_get_icons()["prev"])
        self._prev_btn.setIconSize(QSize(22, 22))
        self._prev_btn.setObjectName("IconButton")
        self._prev_btn.setToolTip("Previous")
        self._prev_btn.clicked.connect(prev_track)

        self._play_btn = QPushButton()
        self._play_btn.setIcon(_get_icons()["play"])
        self._play_btn.setIconSize(QSize(22, 22))
        self._play_btn.setObjectName("IconButton")
        self._play_btn.setToolTip("Play / Pause")
        self._play_btn.clicked.connect(play_pause)

        self._next_btn = QPushButton()
        self._next_btn.setIcon(_get_icons()["next"])
        self._next_btn.setIconSize(QSize(22, 22))
        self._next_btn.setObjectName("IconButton")
        self._next_btn.setToolTip("Next")
        self._next_btn.clicked.connect(next_track)

        btn_row.addStretch()
        btn_row.addWidget(self._prev_btn)
        btn_row.addWidget(self._play_btn)
        btn_row.addWidget(self._next_btn)
        btn_row.addStretch()

        btn_wrap = QWidget()
        btn_wrap.setLayout(btn_row)
        layout.addWidget(btn_wrap)

    def update(self, snapshot: dict[str, Any]) -> None:
        media = now_playing()
        if media.get("is_active"):
            title = media.get("title", "")
            self._track.setText(title[:80] if title else "Playing...")
            if media.get("status") == "playing":
                self._play_btn.setIcon(_get_icons()["pause"])
            else:
                self._play_btn.setIcon(_get_icons()["play"])
        else:
            self._track.setText("No media detected")
            self._play_btn.setIcon(_get_icons()["play"])
