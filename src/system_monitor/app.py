"""QApplication entry point. Wires the collector to the main window."""
from __future__ import annotations

import logging
import sys
from typing import Any

from PySide6.QtCore import QLockFile, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import config as config_mod
from .data.collector import Collector
from .data.media import next_track, play_pause, prev_track
from .ui import styles
from .ui.main_window import MainWindow


log = logging.getLogger(__name__)


def _acquire_instance_lock(config_dir, timeout_ms: int = 100):
    """Try to take the single-instance lock in `config_dir`.

    Returns the QLockFile on success, or None if another live instance holds
    it. The config dir is created first: on a clean machine it doesn't exist
    yet, and QLockFile would fail with an opaque OSError.

    Default stale-lock time (30s) lets a crashed instance's lock be reclaimed;
    a live holder PID keeps the lock indefinitely.
    """
    from pathlib import Path

    path = Path(config_dir)
    path.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(path / "app.lock"))
    if not lock.tryLock(timeout_ms):
        return None
    return lock


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

    # Single-instance guard: two instances writing config.json would clobber
    # each other's settings (the last one to close wins with stale data).
    lock = _acquire_instance_lock(config_mod.config_dir(), 100)
    if lock is None:
        print("System Monitor is already running.", file=sys.stderr)
        return 0

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(argv)
    accent = styles.set_accent(cfg.get("ui", {}).get("accent", styles.ACCENT))
    app.setStyleSheet(styles.qss(1.0, theme=cfg.get("ui", {}).get("theme", "dark"), accent=accent))
    app.setQuitOnLastWindowClosed(True)

    window = MainWindow(cfg)
    window.show()
    window.apply_opacity(float(cfg.get("window", {}).get("opacity", 0.92)))

    bridge = _Bridge()
    bridge.snapshot.connect(window.apply_snapshot)

    interval = float(cfg.get("collector", {}).get("interval_seconds", 1.0))
    collector = Collector(interval=interval)
    # The collector re-reads self.interval each loop, so a settings change
    # takes effect on the next tick without restarting the thread.
    window.interval_changed.connect(lambda secs: setattr(collector, "interval", secs))

    # History recorder: writes snapshots to daily CSVs under %APPDATA%.
    from .history import HistoryRecorder
    history = HistoryRecorder()

    def _on_snap(snap: dict[str, Any]) -> None:
        bridge.post(snap)
        history.record(snap)

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
    painter.setBrush(QColor(accent))
    painter.setPen(Qt.PenStyle.NoPen)
    # Draw a small filled circle
    painter.drawEllipse(2, 2, 12, 12)
    painter.end()
    tray = QSystemTrayIcon(QIcon(tray_pix), app)
    tray.setToolTip("System Monitor")

    tray_menu = QMenu()
    tray_menu.setStyleSheet(styles.qss(1.0, accent=styles.current_accent()))

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
    # Read from the latest snapshot rather than calling now_playing(): that
    # blocks on the SMTC async call, and this timer fires 10x a second.
    def _update_tray() -> None:
        media = (bridge.latest or {}).get("media") or {}
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
        history.stop()  # drains queue and exits writer thread
        config_mod.save(cfg)
        tray.hide()

    app.aboutToQuit.connect(_on_exit)
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
