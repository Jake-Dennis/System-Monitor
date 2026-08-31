"""Network up/down card with compact layout and per-NIC breakdown."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

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
        for _ in range(2):
            for i in range(layout.count() - 1, -1, -1):
                item = layout.itemAt(i)
                w = item.widget() if item is not None else None
                if w is not None and w is not self._title:
                    layout.removeWidget(w)
                    w.hide()
                    w.deleteLater()

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

        # Per-NIC container (built dynamically)
        self._nic_container = QWidget()
        self._nic_layout = QVBoxLayout(self._nic_container)
        self._nic_layout.setContentsMargins(0, 4, 0, 0)
        self._nic_layout.setSpacing(2)
        body.addWidget(self._nic_container)

        # Totals line
        self._total_label = QLabel("")
        self._total_label.setObjectName("Secondary")
        body.addWidget(self._total_label)

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

        # Card alert based on aggregate utilization
        util = float(net.get("util_percent", 0.0))
        self._set_alert(util, warn=60.0, crit=85.0)

        # Per-NIC rows: show active NICs only
        self._update_nic_rows(net.get("pernic", {}))

    def _update_nic_rows(self, pernic: dict[str, dict[str, Any]]) -> None:
        # Clear existing rows
        for i in range(self._nic_layout.count() - 1, -1, -1):
            item = self._nic_layout.itemAt(i)
            w = item.widget() if item is not None else None
            if w is not None:
                self._nic_layout.removeWidget(w)
                w.deleteLater()

        active_count = 0
        for name, info in pernic.items():
            is_up = info.get("is_up", False)
            speed = info.get("speed_mbps", 0)
            down_kbs = float(info.get("down_kb_s", 0.0))
            up_kbs = float(info.get("up_kb_s", 0.0))
            util = float(info.get("util_percent", 0.0))
            # Show only NICs that are up with a known speed AND have any
            # traffic, OR are simply up and connected.
            if not is_up or speed <= 0:
                continue
            active_count += 1
            row = _NicRow(name, speed, down_kbs, up_kbs, util)
            self._nic_layout.addWidget(row)

        if active_count == 0:
            hide_label = QLabel("(no active interfaces)")
            hide_label.setObjectName("Secondary")
            self._nic_layout.addWidget(hide_label)


class _NicRow(QFrame):
    """Single NIC summary line: name | speed | down/up rates."""

    def __init__(self, name: str, speed_mbps: int, down_kbs: float,
                 up_kbs: float, util_percent: float, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")  # Reuse card-style background

        outer = QHBoxLayout(self)
        outer.setContentsMargins(8, 3, 8, 3)
        outer.setSpacing(6)

        # Interface name (truncate to keep card compact)
        display_name = name
        if len(display_name) > 14:
            display_name = display_name[:13] + "..."
        name_lbl = QLabel(display_name)
        name_lbl.setObjectName("Caption")
        name_lbl.setFixedWidth(110)
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        outer.addWidget(name_lbl)

        # Link speed (Mbps or Gbps)
        if speed_mbps >= 1000:
            speed_str = f"{speed_mbps / 1000:.0f} Gbps"
        else:
            speed_str = f"{speed_mbps} Mbps" if speed_mbps > 0 else "?"
        speed_lbl = QLabel(speed_str)
        speed_lbl.setObjectName("Secondary")
        speed_lbl.setFixedWidth(70)
        speed_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        outer.addWidget(speed_lbl)

        # Rates
        dv, du = _fmt_rate(down_kbs)
        uv, uu = _fmt_rate(up_kbs)
        rates_lbl = QLabel(
            chr(8595) + " " + dv + du + "   " + chr(8593) + " " + uv + uu
        )
        rates_lbl.setObjectName("Secondary")
        rates_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        outer.addWidget(rates_lbl, 1)
