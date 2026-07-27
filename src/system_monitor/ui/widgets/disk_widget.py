"""Disk IO card. Per-disk bar + rates, single aggregate timeline."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget

from .. import styles
from ._base import _Card
from ._timeline import Timeline


class _DiskRow(QWidget):
    """One disk volume: `C  [====bar====]  73%   R 5.9  |  W 0.2` with compact timeline."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(2)

        # Row: label | bar | io_pct | R | W
        h = QHBoxLayout()
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)

        self._label = QLabel("--")
        self._label.setObjectName("CardTitle")
        self._label.setFixedWidth(46)
        self._label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(8)

        self._pct = QLabel("--")
        self._pct.setObjectName("ValueSmall")
        self._pct.setFixedWidth(50)
        self._pct.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        self._read_label = QLabel("")
        self._read_label.setObjectName("Secondary")
        self._write_label = QLabel("")
        self._write_label.setObjectName("Secondary")

        h.addWidget(self._label)
        h.addWidget(self._bar, 1)
        h.addWidget(self._pct)
        h.addSpacing(4)
        h.addWidget(self._read_label)
        h.addSpacing(2)
        h.addWidget(self._write_label)
        root.addLayout(h)

        # Compact per-disk timeline
        self._timeline = Timeline()
        self._timeline.set_color(styles.ACCENT)
        self._timeline.setFixedHeight(30)
        root.addWidget(self._timeline)

    def set_disk(
        self, label: str, io_percent: float, read_mb_s: float, write_mb_s: float
    ) -> None:
        self._label.setText(label or "--")

        pct = float(max(0.0, min(100.0, io_percent)))
        self._bar.setValue(int(pct))
        color = styles.color_for_percent(pct)
        self._bar.setStyleSheet(
            "QProgressBar { background: rgba(0,0,0,80); border: none; "
            "height: 8px; border-radius: 4px; }"
            f"QProgressBar::chunk {{ background: {color}; border-radius: 4px; }}"
        )
        self._pct.setText(f"{pct:.0f}%")

        self._read_label.setText(f"R {read_mb_s:.1f}")
        self._write_label.setText(f"W {write_mb_s:.1f}")

        self._timeline.set_color(color)
        self._timeline.add_point(pct)


class DiskCard(_Card):
    def __init__(self, parent=None) -> None:
        super().__init__("Disk", parent)
        self._rows: list[_DiskRow] = []
        self._rows_host: QWidget | None = None
        self.hidden_disks: set[str] = set()
        self.visible_disk_list: list[str] = []

        layout = self.layout()  # type: ignore[arg-type]
        # Remove default value label and bar from _Card.
        for i in range(layout.count() - 1, -1, -1):
            item = layout.itemAt(i)
            w = item.widget() if item is not None else None
            if w is not None and w.objectName() in ("Value", ""):
                layout.removeWidget(w)
                w.hide()
                w.deleteLater()

        # Container for disk rows (inserted right after the title).
        self._rows_host = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_host)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(6)
        layout.insertWidget(1, self._rows_host)

    def update(self, snapshot: dict[str, Any]) -> None:
        disk = snapshot.get("disks", {})
        per_disk: list[dict] = disk.get("per_disk", []) or []

        self.visible_disk_list = [d.get("label", "?") for d in per_disk]
        hidden = self.hidden_disks
        per_disk = [d for d in per_disk if d.get("label", "") not in hidden]

        # Reconcile row count with disk count.
        while len(self._rows) < len(per_disk):
            row = _DiskRow()
            self._rows.append(row)
            self._rows_layout.addWidget(row)
        while len(self._rows) > len(per_disk):
            row = self._rows.pop()
            self._rows_layout.removeWidget(row)
            row.hide()
            row.deleteLater()

        if not per_disk:
            placeholder = QLabel("No physical disks found")
            placeholder.setObjectName("Secondary")
            self._rows_layout.addWidget(placeholder)
        else:
            peak = 0.0
            for row, d in zip(self._rows, per_disk):
                io_pct = float(d.get("io_percent", 0.0))
                peak = max(peak, io_pct)
                row.set_disk(
                    label=d.get("label", "") or "--",
                    io_percent=io_pct,
                    read_mb_s=float(d.get("read_mb_s", 0.0)),
                    write_mb_s=float(d.get("write_mb_s", 0.0)),
                )
                row.show()
