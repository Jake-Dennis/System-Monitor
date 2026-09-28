"""History recording: keeps a small ring buffer of snapshots and writes
them to a CSV file when the app exits (or every N seconds).

The collector thread pushes snapshots into a bounded queue; a background
writer thread drains them into a CSV. We keep CSV files under
%APPDATA%/SystemMonitor/history/.
"""
from __future__ import annotations

import csv
import json
import logging
import os
import queue
import threading
import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Keep a small in-memory buffer so we don't lose recent data on crash.
_BUFFER_SIZE = 600  # ~10 minutes at 1 Hz
_FLUSH_INTERVAL = 30  # seconds


def history_dir() -> Path:
    """Directory the CSVs are written to."""
    return Path(os.environ.get("APPDATA", str(Path.home()))) / "SystemMonitor" / "history"


def reveal_history() -> bool:
    """Open the history folder in the shell, creating it if needed.

    The recorder has always written CSVs that nothing in the UI could reach.
    Returns False if the folder could not be opened.
    """
    path = history_dir()
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        log.warning("could not create history dir %s", path, exc_info=True)
        return False
    try:
        os.startfile(str(path))  # noqa: S606 - Windows shell open is the point
    except (OSError, AttributeError):
        log.warning("could not open history dir %s", path, exc_info=True)
        return False
    return True


class HistoryRecorder:
    """Background-thread CSV recorder for snapshots."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir or history_dir()
        self._queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=_BUFFER_SIZE)
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="history-recorder"
        )
        self._last_flush = time.time()
        self._thread.start()

    def record(self, snapshot: dict[str, Any]) -> None:
        """Enqueue a snapshot. Drops silently if the queue is full."""
        try:
            self._queue.put_nowait(snapshot)
        except queue.Full:
            pass

    def stop(self) -> None:
        """Signal the writer thread to drain and exit."""
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.is_set() or not self._queue.empty():
            try:
                snap = self._queue.get(timeout=1.0)
            except queue.Empty:
                if self._stop.is_set():
                    break
                continue
            self._write_one(snap)
            if time.time() - self._last_flush > _FLUSH_INTERVAL:
                self._flush_all()
                self._last_flush = time.time()

    def _csv_path(self, date: time.struct_time) -> Path:
        name = time.strftime("%Y-%m-%d.csv", date)
        return self._base_dir / name

    def _row(self, snap: dict[str, Any]) -> dict[str, Any]:
        """Flatten a snapshot into a single CSV row."""
        cpu = snap.get("cpu", {})
        mem = snap.get("memory", {})
        net = snap.get("network", {})
        disk = snap.get("disks", {})
        gpus = snap.get("gpus", []) or []
        row = {
            "timestamp": time.strftime(
                "%Y-%m-%dT%H:%M:%S", time.localtime(snap.get("timestamp", time.time()))
            ),
            "cpu_percent": cpu.get("percent", 0),
            "cpu_freq_mhz": cpu.get("freq_mhz", 0),
            "cpu_power_w": cpu.get("power_w", ""),
            "mem_percent": mem.get("percent", 0),
            "mem_used_gb": mem.get("used_gb", 0),
            "net_up_kb_s": net.get("up_kb_s", 0),
            "net_down_kb_s": net.get("down_kb_s", 0),
            "disk_percent": disk.get("percent", 0),
            "disk_read_mb_s": disk.get("read_mb_s", 0),
            "disk_write_mb_s": disk.get("write_mb_s", 0),
            "gpu_count": len(gpus),
            "gpu_util_max": max((g.get("util_percent", 0) for g in gpus), default=0),
            "gpu_mem_used_mb_max": max((g.get("mem_used_mb", 0) or 0 for g in gpus), default=0),
        }
        return row

    def _write_one(self, snap: dict[str, Any]) -> None:
        try:
            ts = time.localtime(snap.get("timestamp", time.time()))
            path = self._csv_path(ts)
            path.parent.mkdir(parents=True, exist_ok=True)
            new_file = not path.exists()
            with path.open("a", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(self._row(snap).keys()))
                if new_file:
                    w.writeheader()
                w.writerow(self._row(snap))
        except Exception:
            log.debug("history write failed", exc_info=True)

    def _flush_all(self) -> None:
        # Files are already flushed via file.flush(); nothing extra needed
        # at the OS level on Windows without fsync. We just log stats.
        try:
            files = list(self._base_dir.glob("*.csv"))
            if files:
                total_rows = 0
                for f in files:
                    try:
                        with f.open("r", encoding="utf-8") as fh:
                            total_rows += sum(1 for _ in fh) - 1
                    except OSError:
                        pass
                log.debug("history: %d files, %d rows", len(files), total_rows)
        except OSError:
            pass
