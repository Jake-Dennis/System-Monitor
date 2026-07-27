"""GPU stats: NVML for NVIDIA, LHM for everything (AMD/NVIDIA/Intel),
DXGI for name + VRAM. Graceful fallback when only some sources respond.

Adapter list comes from DXGI (Win32_VideoController) so the card always
knows the GPU's name, vendor, and total VRAM — even on systems where
NVML is missing and LHM is not running.

Per-sensor enrichment order, applied per adapter:
  1. NVML (NVIDIA only, fastest, most complete)
  2. LHM (any vendor, fills gaps when NVML is absent or for AMD/Intel)
  3. DXGI name + VRAM only if nothing else responds
"""
from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    import pynvml  # type: ignore
else:
    pynvml: Any | None = None
    try:
        import pynvml as _pynvml  # type: ignore
        pynvml = _pynvml
    except Exception:
        pynvml = None

from . import dxgi
from .lhm_gpu import LhmGpuReader


log = logging.getLogger(__name__)


def _empty_entry(idx: int, name: str, vendor: str) -> dict[str, Any]:
    return {
        "index": idx,
        "name": name,
        "vendor": vendor,
        "util_percent": 0.0,
        "mem_used_mb": 0.0,
        "mem_total_mb": 0.0,
        "mem_percent": 0.0,
        "power_w": None,
        "fan_percent": None,
        "source": "none",
    }


class GpuCollector:
    def __init__(self) -> None:
        self._adapters: list[dict[str, Any]] = []  # private metadata
        self._lhm: LhmGpuReader | None = None
        self._init_sources()

    # ----- public surface -----

    @property
    def available(self) -> bool:
        return bool(self._adapters)

    def read_cpu_power_w(self) -> float | None:
        """Return CPU package power in watts from LHM, or None."""
        if self._lhm is not None:
            return self._lhm.read_cpu_power_w()
        return None

    def snapshot(self) -> list[dict[str, Any]]:
        # Read LHM once for all adapters (single HTTP fetch).
        lhm_by_vendor: dict[str, list[dict[str, Any]]] = {}
        if self._lhm is not None and self._lhm.available:
            try:
                for gpu in self._lhm.snapshot():
                    v = gpu.get("vendor", "unknown")
                    lhm_by_vendor.setdefault(v, []).append(gpu)
            except Exception:
                log.exception("LHM GPU snapshot failed")

        out: list[dict[str, Any]] = []
        for idx, adapter in enumerate(self._adapters):
            entry = _empty_entry(idx, adapter["name"], adapter["vendor"])
            vram = float(adapter.get("vram_mb") or 0.0)
            if vram > 0:
                entry["mem_total_mb"] = vram

            # 1. NVML (NVIDIA only — fast path, most complete)
            if adapter.get("_nvml_handle") is not None and pynvml is not None:
                self._enrich_nvml(entry, adapter["_nvml_handle"])

            # 2. LHM (any vendor — fills gaps; the only source for AMD/Intel)
            vendor = adapter["vendor"]
            lhm_list = lhm_by_vendor.get(vendor, [])
            if lhm_list:
                self._enrich_lhm(entry, lhm_list.pop(0))

            if entry["source"] == "none":
                entry["source"] = "dxgi" if vram > 0 else "unavailable"
            out.append(entry)
        return out

    # ----- source init -----

    def _init_sources(self) -> None:
        nvml_handles: list = []
        if pynvml is not None:
            try:
                pynvml.nvmlInit()
                count = pynvml.nvmlDeviceGetCount()
                nvml_handles = [pynvml.nvmlDeviceGetHandleByIndex(i) for i in range(count)]
            except Exception:
                nvml_handles = []

        adapters = dxgi.enumerate_adapters()
        if not adapters and nvml_handles and pynvml is not None:
            # DXGI / WMI unavailable — fall back to NVML for the name only.
            adapters = []
            for i, h in enumerate(nvml_handles):
                try:
                    name = pynvml.nvmlDeviceGetName(h).decode("utf-8", errors="ignore")
                except Exception:
                    name = f"NVIDIA GPU {i}"
                adapters.append({"name": name, "vendor": "nvidia", "vram_mb": 0.0})

        try:
            self._lhm = LhmGpuReader()
        except Exception:
            self._lhm = None

        # Match NVML handles to DXGI adapters by vendor (NVIDIA only).
        nvml_cursor = 0
        for a in adapters:
            entry = {
                "name": a["name"],
                "vendor": a["vendor"],
                "vram_mb": float(a.get("vram_mb") or 0.0),
                "_nvml_handle": None,
            }
            if a["vendor"] == "nvidia" and nvml_cursor < len(nvml_handles) and pynvml is not None:
                entry["_nvml_handle"] = nvml_handles[nvml_cursor]
                nvml_cursor += 1
            self._adapters.append(entry)

    # ----- enrichers -----

    def _enrich_nvml(self, entry: dict[str, Any], h) -> None:
        assert pynvml is not None
        try:
            rates = pynvml.nvmlDeviceGetUtilizationRates(h)
            entry["util_percent"] = float(rates.gpu)
        except Exception:
            pass
        try:
            info = pynvml.nvmlDeviceGetMemoryInfo(h)
            entry["mem_used_mb"] = round(info.used / 1024**2, 1)
            entry["mem_total_mb"] = round(info.total / 1024**2, 1)
            if info.total:
                entry["mem_percent"] = round(100.0 * info.used / info.total, 1)
        except Exception:
            pass
        try:
            mw = pynvml.nvmlDeviceGetPowerUsage(h)
            entry["power_w"] = round(mw / 1000.0, 1)
        except Exception:
            pass
        try:
            entry["fan_percent"] = float(pynvml.nvmlDeviceGetFanSpeed(h))
        except Exception:
            pass
        entry["source"] = "nvml"

    @staticmethod
    def _enrich_lhm(entry: dict[str, Any], lhm_gpu: dict[str, Any]) -> None:
        """Fill gaps in `entry` from an LHM GPU snapshot. Never overwrites
        a real (non-zero, non-None) value with zero/None."""
        for key in ("util_percent", "mem_used_mb", "mem_total_mb",
                    "fan_percent", "power_w"):
            new = lhm_gpu.get(key)
            if new is None:
                continue
            current = entry.get(key)
            if current in (None, 0, 0.0):
                entry[key] = new
        # Recompute mem percent after potentially filling mem fields.
        if entry["mem_used_mb"] and entry["mem_total_mb"]:
            entry["mem_percent"] = round(
                100.0 * entry["mem_used_mb"] / entry["mem_total_mb"], 1
            )
        if entry["source"] == "none":
            entry["source"] = "lhm"
        else:
            entry["source"] = f"{entry['source']}+lhm"
