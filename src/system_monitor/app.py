"""QApplication entry point. Wires the collector to the main window."""
from __future__ import annotations

import logging
import sys
from typing import Any

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import config as config_mod
from .data.collector import Collector
from .data.media import play_pause, next_track, prev_track, now_playing
from .ui import styles
from .ui.main_window import MainWindow


log = logging.getLogger(__name__)


class _Bridge(QObject):
    """Thread-safe snapshot emitter: collector thread → Qt main thread."""

    snapshot = Signal(dict)

    def __init__(self) -> None:
        super().__init__()
        self._latest: dict[str, Any] | None = None

    def post(self, snap: dict[str, Any]) -> None:
        self._latest = snap
        self.snapshot.emit(snap)

    @property
    def latest(self) -> dict[str, Any] | None:
        return self._latest


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if argv is None:
        argv = sys.argv

    cfg = config_mod.load()

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(argv)
    app.setStyleSheet(styles.qss(1.0, theme=cfg.get("ui", {}).get("theme", "dark")))
    app.setQuitOnLastWindowClosed(True)

    window = MainWindow(cfg)
    window.show()
    window.apply_opacity(float(cfg.get("window", {}).get("opacity", 0.92)))

    bridge = _Bridge()
    bridge.snapshot.connect(window.apply_snapshot)

    interval = float(cfg.get("collector", {}).get("interval_seconds", 1.0))
    collector = Collector(interval=interval)

    def _on_snap(snap: dict[str, Any]) -> None:
        bridge.post(snap)

    collector.on_snapshot(_on_snap)
    collector.start()

    # Coalesce UI repaints to a steady 10 Hz even if the collector ticks faster
    repaint_timer = QTimer()
    repaint_timer.setInterval(100)
    repaint_timer.timeout.connect(lambda: window.apply_snapshot(bridge.latest or {}))
    repaint_timer.start()

    # System tray icon with media controls
    tray_pix = QPixmap(16, 16)
    tray_pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(tray_pix)
    painter.setBrush(styles.ACCENT)
    painter.setPen(Qt.PenStyle.NoPen)
    # Draw a small filled circle
    painter.drawEllipse(2, 2, 12, 12)
    painter.end()
    tray = QSystemTrayIcon(QIcon(tray_pix), app)
    tray.setToolTip("System Monitor")

    tray_menu = QMenu()
    tray_menu.setStyleSheet(styles.qss(1.0))

    tray_prev = QAction("⏮  Previous", tray_menu)
    tray_prev.triggered.connect(prev_track)
    tray_menu.addAction(tray_prev)

    tray_play = QAction("⏯  Play / Pause", tray_menu)
    tray_play.triggered.connect(play_pause)
    tray_menu.addAction(tray_play)

    tray_next = QAction("⏭  Next", tray_menu)
    tray_next.triggered.connect(next_track)
    tray_menu.addAction(tray_next)

    tray_menu.addSeparator()

    tray_show = QAction("Show System Monitor", tray_menu)
    tray_show.triggered.connect(window.show)
    tray_menu.addAction(tray_show)

    tray_menu.addSeparator()

    tray_track = QAction("No media detected", tray_menu)
    tray_track.setEnabled(False)
    tray_menu.addAction(tray_track)

    tray_menu.addSeparator()

    tray_quit = QAction("Quit", tray_menu)
    tray_quit.triggered.connect(app.quit)
    tray_menu.addAction(tray_quit)

    tray.setContextMenu(tray_menu)
    tray.show()

    # Update the tray tooltip and track info on each repaint timer tick.
    def _update_tray() -> None:
        media = now_playing()
        if media.get("is_active"):
            title = media.get("title", "")
            artist = media.get("artist", "")
            parts = [title, artist] if artist else [title]
            tray_track.setText("  ·  ".join(parts) if parts else "Playing")
            tray.setToolTip(f"Playing: {title}" if title else "System Monitor")
        else:
            tray_track.setText("No media detected")
            tray.setToolTip("System Monitor")

    repaint_timer.timeout.connect(_update_tray)

    def _on_exit() -> None:
        collector.stop()
        config_mod.save(cfg)
        tray.hide()

    app.aboutToQuit.connect(_on_exit)
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
