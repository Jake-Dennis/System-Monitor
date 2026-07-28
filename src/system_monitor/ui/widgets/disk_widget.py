"""Per-disk IO card — one instance per physical drive."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QSizePolicy, QVBoxLayout, QWidget

from .. import styles
from ._base import _Card
from ._timeline import Timeline


class SingleDiskCard(_Card):
    """A single disk drive shown as an independent card."""

    def __init__(self, label: str, parent=None) -> None:
        super().__init__(label, parent)
        self.setMinimumHeight(0)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout = self.layout()  # type: ignore[arg-type]

        # Strip default _Card body, keep only title
        for i in range(layout.count() - 1, -1, -1):
            item = layout.itemAt(i)
            w = item.widget() if item is not None else None
            if w is not None and w is not self._title:
                layout.removeWidget(w)
                w.hide()
                w.deleteLater()

        layout.setSpacing(4)
        layout.setContentsMargins(18, 10, 18, 10)

        # R/W rates on the header line
        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 0, 0, 0)
        self._read_label = QLabel("")
        self._read_label.setObjectName("Secondary")
        self._write_label = QLabel("")
        self._write_label.setObjectName("Secondary")
        hdr.addStretch()
        hdr.addWidget(self._read_label)
        hdr.addSpacing(4)
        hdr.addWidget(self._write_label)
        layout.addLayout(hdr)

        # Bar row: percentage | bar
        bar_row = QHBoxLayout()
        bar_row.setContentsMargins(0, 0, 0, 0)
        bar_row.setSpacing(6)

        self._pct = QLabel("0%")
        self._pct.setObjectName("ValueSmall")
        self._pct.setFixedWidth(48)
        self._pct.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(10)

        bar_row.addWidget(self._pct)
        bar_row.addWidget(self._bar, 1)
        layout.addLayout(bar_row)

        # Timeline
        self._timeline = Timeline()
        self._timeline.set_color(styles.ACCENT)
        self._timeline.setFixedHeight(30)
        layout.addWidget(self._timeline)

    def set_disk(self, io_percent: float, read_mb_s: float, write_mb_s: float) -> None:
        pct = float(max(0.0, min(100.0, io_percent)))
        self._bar.setValue(int(pct))
        color = styles.color_for_percent(pct)
        self._bar.setStyleSheet(
            "QProgressBar { background: rgba(0,0,0,80); border: none; "
            "height: 10px; border-radius: 4px; }"
            f"QProgressBar::chunk {{ background: {color}; border-radius: 4px; }}"
        )
        self._pct.setText(f"{pct:.0f}%")
        self._read_label.setText(f"R {read_mb_s:.1f}")
        self._write_label.setText(f"W {write_mb_s:.1f}")
        self._timeline.set_color(color)
        self._timeline.add_point(pct)

    def update(self, snapshot: dict[str, Any]) -> None:
        pass  # updated via set_disk
