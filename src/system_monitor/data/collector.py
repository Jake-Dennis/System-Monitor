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
from . import media as media_mod
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
        # Each sensor is isolated: one raising subsystem degrades its own
        # section to an empty reading and is reported in "health", instead of
        # taking down the whole snapshot.
        health: dict[str, str] = {}

        def probe(name: str, fn, *args, fallback):
            try:
                return fn(*args), "ok"
            except Exception:
                log.warning("sensor %s failed", name, exc_info=True)
                health[name] = "error"
                return fallback, "error"

        cpu_stats, cpu_health = probe("cpu", self._cpu.snapshot, fallback={})
        gpus, gpu_health = probe("gpu", self._gpu.snapshot, fallback=[])
        health["cpu"] = cpu_health
        health["gpu"] = gpu_health

        disk_stats, disk_health = probe(
            "disk", disk_mod.snapshot, self._prev_disk, fallback={"per_disk": []}
        )
        self._prev_disk = disk_stats
        health["disk"] = disk_health

        net_stats, net_health = probe(
            "network", net_mod.snapshot, self._prev_net, fallback={"pernic": {}}
        )
        self._prev_net = net_stats
        health["network"] = net_health

        mem_stats, mem_health = probe("memory", mem_mod.snapshot, fallback={})
        health["memory"] = mem_health

        # Media is sampled here, on the collector thread, rather than in the
        # card: now_playing() blocks on the SMTC async call (3s timeout), and
        # the card used to call it on every 10 Hz repaint.
        media_stats, media_health = probe("media", media_mod.now_playing, fallback={})
        health["media"] = media_health

        return {
            "timestamp": time.time(),
            "cpu": cpu_stats,
            "memory": mem_stats,
            "disks": disk_stats,
            "network": net_stats,
            "gpus": gpus,
            "media": media_stats,
            # Per-subsystem status so the UI can tell "idle" from "broken".
            "health": health,
        }
