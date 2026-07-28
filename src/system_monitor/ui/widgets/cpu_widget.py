"""CPU usage card with info line, per-core strip, and usage timeline."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from .. import styles
from ._base import _Card
from ._timeline import Timeline


class CpuCard(_Card):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("CPU", parent)
        layout = self.layout()  # type: ignore[arg-type]

        # Hide the default value and secondary labels — info goes in _cpu_info
        self._value.hide()
        self._secondary.hide()

        # CPU info line
        self._cpu_info = QLabel("")
        self._cpu_info.setObjectName("Caption")
        self._cpu_info.setWordWrap(True)
        layout.addWidget(self._cpu_info)

        # Bar with percentage under the info line
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
        layout.addWidget(bar_wrap)

        self._strip = _PerCoreStrip()
        self._timeline = Timeline()
        layout.addWidget(self._strip)
        layout.addWidget(self._timeline)

    def update(self, snapshot: dict[str, Any]) -> None:
        cpu = snapshot.get("cpu", {})
        pct = float(cpu.get("percent", 0.0))
        color = styles.color_for_percent(pct)
        self._set_value(f"{pct:.0f} %")
        self._set_bar(pct, color)
        self._bar_pct.setText(f"{pct:.0f}%")

        # Info line: CPU: (Model) (C/T) - GHz
        name = cpu.get("name", "").strip()
        cores = cpu.get("physical_cores", 0) or 0
        threads = cpu.get("logical_cores", 0) or 0
        freq = cpu.get("freq_mhz")
        parts = []
        if name:
            name_short = name.split("@")[0].strip()
            parts.append(name_short)
        if cores and threads:
            parts.append(f"({cores}C/{threads}T)")
        elif threads:
            parts.append(f"({threads}T)")
        if freq:
            parts.append(f"{freq/1000:.2f} GHz")
        self._cpu_info.setText("CPU: " + " ".join(parts))

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
                    int(x), int(y), int(col_w), int(bar_h), color
                )
        finally:
            painter.end()
