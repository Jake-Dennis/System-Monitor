"""RAM + swap card with timeline."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from ._base import _Card
from ._timeline import Timeline


class RamCard(_Card):
    def __init__(self, parent=None) -> None:
        super().__init__("Memory", parent)
        self._show_swap = True
        self._value.hide()

        # Percentage label left of bar — insert right after title
        self._bar_pct = QLabel("0%")
        self._bar_pct.setObjectName("ValueSmall")
        self._bar_pct.setFixedWidth(48)
        self._bar_pct.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(14)
        bar_wrap = QWidget()
        bar_row = QHBoxLayout(bar_wrap)
        bar_row.setContentsMargins(0, 0, 0, 0)
        bar_row.setSpacing(6)
        bar_row.addWidget(self._bar_pct)
        bar_row.addWidget(self._bar, 1)
        self.layout().insertWidget(1, bar_wrap)

        # Timeline goes at the very end
        self._timeline = Timeline()
        self.layout().addWidget(self._timeline)

    def set_show_swap(self, show: bool) -> None:
        self._show_swap = bool(show)

    def update(self, snapshot: dict[str, Any]) -> None:
        from .. import styles

        mem = snapshot.get("memory", {})
        pct = float(mem.get("percent", 0.0))
        color = styles.color_for_percent(pct, hot_at=75.0, crit_at=92.0)
        self._set_value(f"{pct:.0f} %")
        self._set_bar(pct, color)
        self._bar_pct.setText(f"{pct:.0f}%")
        used = float(mem.get("used_gb", 0.0))
        total = float(mem.get("total_gb", 0.0))
        secondary = f"{used:.1f} / {total:.1f} GB"
        if self._show_swap:
            su = float(mem.get("swap_used_gb", 0.0))
            st = float(mem.get("swap_total_gb", 0.0))
            sp = float(mem.get("swap_percent", 0.0))
            if st > 0:
                secondary += f"   ·   swap {sp:.0f}% ({su:.1f}/{st:.1f} GB)"
        self._set_secondary(secondary)
        self._timeline.set_color(color)
        self._timeline.add_point(pct)
