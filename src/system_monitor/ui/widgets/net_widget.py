"""Network up/down card with compact layout — built from scratch."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget

from .. import styles
from ._base import _Card
from ._timeline import Timeline


def _fmt_rate(kbps: float) -> tuple[str, str]:
    if kbps >= 1024:
        return f"{kbps / 1024:.2f}", "MB/s"
    return f"{kbps:.0f}", "KB/s"


class NetCard(_Card):
    def __init__(self, parent=None) -> None:
        super().__init__("Network", parent)
        layout = self.layout()  # type: ignore[arg-type]

        # Strip the default _Card body (value, bar, secondary) — keep only title.
        for i in range(layout.count() - 1, -1, -1):
            item = layout.itemAt(i)
            w = item.widget() if item is not None else None
            if w is not None and w is not self._title:
                layout.removeWidget(w)
                w.hide()
                w.deleteLater()

        # Remove the bar too (it has no objectName, so the loop above may have
        # caught it — but be safe and remove anything left).
        for i in range(layout.count() - 1, -1, -1):
            item = layout.itemAt(i)
            w = item.widget() if item is not None else None
            if w is not None and w is not self._title:
                layout.removeWidget(w)
                w.hide()
                w.deleteLater()

        # Tighten card spacing
        layout.setSpacing(0)
        layout.setContentsMargins(18, 8, 18, 6)

        # -- content built from scratch --
        body = QVBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(2)

        # Row: down rate ↔ up rate
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)

        self._down_label = QLabel(chr(8595) + "  --  KB/s")
        self._down_label.setObjectName("ValueSmall")
        self._up_label = QLabel(chr(8593) + "  --  KB/s")
        self._up_label.setObjectName("ValueSmall")

        row.addWidget(self._down_label)
        row.addStretch(1)
        row.addWidget(self._up_label)
        body.addLayout(row)

        # Row: two timelines side by side
        tl_row = QHBoxLayout()
        tl_row.setContentsMargins(0, 0, 0, 0)
        tl_row.setSpacing(6)

        self._down_timeline = Timeline()
        self._down_timeline.set_color(styles.ACCENT)
        self._down_timeline.setFixedHeight(28)
        tl_row.addWidget(self._down_timeline, 1)

        self._up_timeline = Timeline()
        self._up_timeline.set_color(styles.WARN)
        self._up_timeline.setFixedHeight(28)
        tl_row.addWidget(self._up_timeline, 1)

        body.addLayout(tl_row)

        # Totals line
        self._total_label = QLabel("")
        self._total_label.setObjectName("Secondary")
        body.addWidget(self._total_label)

        # Insert everything after the title
        body_wrap = QWidget()
        body_wrap.setLayout(body)
        layout.addWidget(body_wrap)

    def update(self, snapshot: dict[str, Any]) -> None:
        net = snapshot.get("network", {})
        up = float(net.get("up_kb_s", 0.0))
        down = float(net.get("down_kb_s", 0.0))

        dv, du = _fmt_rate(down)
        uv, uu = _fmt_rate(up)
        self._down_label.setText(chr(8595) + "  " + dv + " " + du)
        self._up_label.setText(chr(8593) + "  " + uv + " " + uu)

        self._down_timeline.add_point(down / 1024)  # MB/s for timeline range
        self._up_timeline.add_point(up / 1024)      # MB/s for timeline range

        sent = float(net.get("total_sent_gb", 0.0))
        recv = float(net.get("total_recv_gb", 0.0))
        self._total_label.setText(
            "total  " + chr(8593) + " " + f"{sent:.2f}" + " GB  " + chr(183) + "  "
            + chr(8595) + " " + f"{recv:.2f}" + " GB"
        )
