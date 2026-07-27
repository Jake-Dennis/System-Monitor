"""Compact sparkline timeline widget for usage history."""
from __future__ import annotations

from collections import deque

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from .. import styles


class Timeline(QWidget):
    """Sparkline chart showing value history (like Task Manager)."""

    def __init__(self, max_points: int = 300, parent=None) -> None:
        super().__init__(parent)
        self._data: deque[float] = deque(maxlen=max_points)
        self._max_points = max_points
        self._color: str = styles.ACCENT
        self._show_fill = True
        self._base_height = 40
        self.setMinimumHeight(self._base_height)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.setMinimumWidth(80)

    def add_point(self, value: float) -> None:
        self._data.append(float(value))
        self.update()

    def set_color(self, color: str) -> None:
        self._color = color

    def clear(self) -> None:
        self._data.clear()
        self.update()

    def set_scale(self, scale: float) -> None:
        self.setMinimumHeight(max(20, round(self._base_height * scale)))

    @property
    def point_count(self) -> int:
        return len(self._data)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        super().paintEvent(event)
        if not self._data:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        w = self.width()
        h = self.height()
        n = len(self._data)
        margin = 2

        plot_w = w - margin * 2
        plot_h = h - margin * 2
        plot_x = margin
        plot_y = margin

        # Background
        painter.fillRect(
            QRect(plot_x, plot_y, plot_w, plot_h),
            QColor(0, 0, 0, 30),
        )

        # Compute min/max from data
        lo = min(self._data)
        hi = max(self._data)
        if hi - lo < 1.0:
            # Expand the range so tiny variations still show as a visible line.
            mid = (lo + hi) / 2.0
            lo = max(0.0, mid - 1.0)
            hi = min(100.0, mid + 1.0)
        if hi - lo < 0.1:
            hi = lo + 0.1
        if lo == hi:
            return

        points: list[tuple[float, float]] = []
        for i, val in enumerate(self._data):
            x = plot_x + (i / (n - 1)) * plot_w if n > 1 else plot_x + plot_w / 2
            y = plot_y + plot_h - ((val - lo) / (hi - lo)) * plot_h
            points.append((x, y))

        # Draw fill under the line
        if self._show_fill:
            base_y = plot_y + plot_h
            color = QColor(self._color)
            gradient = QLinearGradient(0, plot_y, 0, plot_y + plot_h)
            gradient.setColorAt(0.0, QColor(color.red(), color.green(), color.blue(), 60))
            gradient.setColorAt(1.0, QColor(color.red(), color.green(), color.blue(), 10))
            path = []
            for px, py in points:
                path.append(px)
                path.append(py)
            # Close the fill polygon
            path.append(points[-1][0])
            path.append(base_y)
            path.append(points[0][0])
            path.append(base_y)

            fill_pen = QPen(Qt.PenStyle.NoPen)
            painter.setPen(fill_pen)
            painter.setBrush(gradient)

            poly = []
            for i in range(0, len(path), 2):
                poly.append((path[i], path[i + 1]))
            # Use drawPolygon
            from PySide6.QtCore import QPointF
            qpoints = [QPointF(x, y) for x, y in poly]
            painter.drawPolygon(qpoints)

        # Draw the line
        line_pen = QPen(QColor(self._color), 1.5)
        painter.setPen(line_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for i in range(len(points) - 1):
            x1, y1 = points[i]
            x2, y2 = points[i + 1]
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))

        # Grid lines (horizontal 25%, 50%, 75%)
        grid_pen = QPen(QColor(255, 255, 255, 15), 1)
        painter.setPen(grid_pen)
        for frac in (0.25, 0.5, 0.75):
            gy = plot_y + plot_h * (1.0 - frac)
            painter.drawLine(plot_x, int(gy), plot_x + plot_w, int(gy))

        painter.end()
