"""Background collector: samples every `interval` seconds, emits a snapshot dict.

Designed to be driven from a QObject (see app.py) or a plain thread. The
collector never raises into its caller — all sensor failures degrade to None
or zero values so the UI keeps painting.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

from . import cpu as cpu_mod
from . import disk as disk_mod
from . import gpu as gpu_mod
from . import memory as mem_mod
from . import network as net_mod


log = logging.getLogger(__name__)


class Collector:
    def __init__(self, interval: float = 1.0) -> None:
        self.interval = float(interval)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._cpu = cpu_mod.CpuInfo()
        self._gpu = gpu_mod.GpuCollector()
        self._prev_disk: dict | None = None
        self._prev_net: dict | None = None

    # -- public lifecycle --

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="system-monitor-collector", daemon=True
        )
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    # -- info --

    @property
    def gpu_available(self) -> bool:
        return self._gpu.available

    # -- main loop --

    def _run(self) -> None:
        # Prime psutil cpu percent (first call returns 0.0 otherwise)
        try:
            import psutil

            psutil.cpu_percent(interval=None, percpu=True)
        except Exception:
            pass
        while not self._stop.is_set():
            t0 = time.time()
            try:
                snap = self._collect_once()
                if self._on_snapshot is not None:
                    try:
                        self._on_snapshot(snap)
                    except Exception:
                        log.exception("snapshot callback failed")
            except Exception:
                log.exception("collector iteration failed")
            dt = time.time() - t0
            self._stop.wait(max(0.05, self.interval - dt))

    _on_snapshot = None  # type: ignore[assignment]

    def on_snapshot(self, callback) -> None:
        """Register a callback(snapshot_dict). The callback runs on the
        collector thread; UI code must marshal to the GUI thread itself."""
        self._on_snapshot = callback

    def _collect_once(self) -> dict[str, Any]:
        cpu_stats = self._cpu.snapshot()
        gpus = self._gpu.snapshot()

        cpu_power_w = self._gpu.read_cpu_power_w()
        if cpu_power_w is not None:
            cpu_stats["power_w"] = round(cpu_power_w, 1)

        disk_stats = disk_mod.snapshot(self._prev_disk)
        self._prev_disk = disk_stats
        net_stats = net_mod.snapshot(self._prev_net)
        self._prev_net = net_stats

        return {
            "timestamp": time.time(),
            "cpu": cpu_stats,
            "memory": mem_mod.snapshot(),
            "disks": disk_stats,
            "network": net_stats,
            "gpus": gpus,
        }
