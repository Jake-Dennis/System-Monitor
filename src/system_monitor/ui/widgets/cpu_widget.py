"""CPU usage card with per-core strip and timeline."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from .. import styles
from ._base import _Card
from ._timeline import Timeline


class CpuCard(_Card):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("CPU", parent)
        self._name = QLabel("")
        self._name.setObjectName("Caption")
        self._name.setWordWrap(True)
        self.layout().addWidget(self._name)  # type: ignore[arg-type]
        self._strip = _PerCoreStrip()
        self._timeline = Timeline()
        self.layout().addWidget(self._timeline)  # type: ignore[arg-type]

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        if self._strip.parent() is None:
            self.layout().addWidget(self._strip)  # type: ignore[arg-type]

    def update(self, snapshot: dict[str, Any]) -> None:
        cpu = snapshot.get("cpu", {})
        pct = float(cpu.get("percent", 0.0))
        color = styles.color_for_percent(pct)
        self._set_value(f"{pct:.0f} %")
        self._set_bar(pct, color)
        cores = cpu.get("logical_cores", 0) or 0
        freq = cpu.get("freq_mhz")
        secondary = f"{cores} threads"
        if freq:
            secondary += f" · {freq/1000:.2f} GHz"
        power = cpu.get("power_w")
        if power is not None:
            secondary += f" · {float(power):.0f} W"
        self._set_secondary(secondary)
        self._name.setText(cpu.get("name", "")[:80])
        self._strip.set_values(cpu.get("per_core", []), color)
        self._timeline.set_color(color)
        self._timeline.add_point(pct)


class _PerCoreStrip(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._values: list[float] = []
        self._color = styles.ACCENT
        self.setMinimumHeight(28)
        self.setMaximumHeight(36)

    def set_values(self, values: list[float], color: str) -> None:
        self._values = list(values)
        self._color = color
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        super().paintEvent(event)
        if not self._values:
            return
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            w = self.width()
            h = self.height()
            n = len(self._values)
            gap = 2
            col_w = max(2, (w - gap * (n - 1)) / n)
            color = QColor(self._color)
            for i, v in enumerate(self._values):
                x = i * (col_w + gap)
                bar_h = max(2.0, (float(v) / 100.0) * (h - 4))
                y = h - 2 - bar_h
                painter.fillRect(
                    int(x),
                    int(y),
                    int(col_w),
                    int(bar_h),
                    color,
                )
        finally:
            painter.end()
