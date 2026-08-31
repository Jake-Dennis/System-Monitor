r"""GPU stats: NVML for NVIDIA, DXGI for name + VRAM, Windows PDH for
fallback util/VRAM usage.

Adapter list comes from DXGI (Win32_VideoController) so the card always
knows the GPU's name, vendor, and total VRAM — even on systems where
NVML is missing.

Per-sensor enrichment order, applied per adapter:
  1. NVML (NVIDIA only, fastest, most complete)
  2. Windows PDH (any vendor, no external deps — provides util/VRAM used
     via `\GPU Engine(*)\Utilization Percentage` and
     `\GPU Adapter Memory(*)\Dedicated Usage`)
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
        self._pdh_query = None
        self._pdh_primed = False
        self._pdh_util_counter = None
        self._pdh_vram_counter = None
        self._init_sources()
        self._init_pdh()

    # ----- public surface -----

    @property
    def available(self) -> bool:
        return bool(self._adapters)

    def snapshot(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for idx, adapter in enumerate(self._adapters):
            entry = _empty_entry(idx, adapter["name"], adapter["vendor"])
            vram = float(adapter.get("vram_mb") or 0.0)
            if vram > 0:
                entry["mem_total_mb"] = vram

            # 1. NVML (NVIDIA only — fast path, most complete)
            if adapter.get("_nvml_handle") is not None and pynvml is not None:
                self._enrich_nvml(entry, adapter["_nvml_handle"])

            # 2. Windows PDH (any vendor — no external deps, always available)
            if self._pdh_query is not None:
                self._enrich_pdh(entry, idx)

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

        # Match NVML handles to DXGI adapters by vendor (NVIDIA only).
        nvml_cursor = 0
        for a in adapters:
            entry = {
                "name": a["name"],
                "vendor": a["vendor"],                "vram_mb": float(a.get("vram_mb") or 0.0),
                "_nvml_handle": None,
            }
            if a["vendor"] == "nvidia" and nvml_cursor < len(nvml_handles) and pynvml is not None:
                entry["_nvml_handle"] = nvml_handles[nvml_cursor]
                nvml_cursor += 1
            self._adapters.append(entry)

    # ----- PDH setup -----

    def _init_pdh(self) -> None:
        """Open Windows Performance Counter queries for GPU util/VRAM.

        No external deps needed — uses pywin32's win32pdh which is already
        a required dep. Provides a fallback for systems where NVML isn't
        installed but we still want GPU utilization data.

        PDH counters need two samples with a delay between them to
        compute rates. We prime both samples during init so the first
        snapshot returns real data immediately.
        """
        try:
            import win32pdh  # type: ignore
            self._pdh_query = win32pdh.OpenQuery()
            self._pdh_util_counter = win32pdh.AddCounter(
                self._pdh_query, r"\GPU Engine(*)\Utilization Percentage"
            )
            self._pdh_vram_counter = win32pdh.AddCounter(
                self._pdh_query, r"\GPU Adapter Memory(*)\Dedicated Usage"
            )
            # Prime: first collect is raw, second collect (after delay)
            # produces rate-based values.
            win32pdh.CollectQueryData(self._pdh_query)
            import time as _time
            _time.sleep(0.3)
            win32pdh.CollectQueryData(self._pdh_query)
            self._pdh_primed = True
        except Exception:
            log.debug("PDH GPU counters unavailable", exc_info=True)
            self._pdh_query = None
            self._pdh_primed = False

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

    def _enrich_pdh(self, entry: dict[str, Any], adapter_idx: int) -> None:
        """Fill util_percent and mem_used_mb from Windows PDH GPU counters.

        Works on any GPU vendor (Intel, AMD, NVIDIA) without any external
        software. Uses the GPU Engine utilization counter aggregated by
        physical adapter index, and the GPU Adapter Memory counter for
        VRAM used.

        PDH rate counters need two samples. We collect a fresh sample
        at every snapshot (async-friendly: no sleep). The next snapshot
        gets the new rate based on (current - previous) / interval.
        """
        import re
        try:
            import win32pdh  # type: ignore
            # Trigger a fresh collect (returns immediately, no sleep).
            # The next call to GetFormattedCounterArray computes the
            # rate between this sample and the previous one.
            win32pdh.CollectQueryData(self._pdh_query)
        except Exception:
            return

        # Aggregate GPU Engine utilization per physical adapter
        try:
            util_data = win32pdh.GetFormattedCounterArray(
                self._pdh_util_counter, win32pdh.PDH_FMT_DOUBLE
            )
            util_per_adapter: dict[int, float] = {}
            for name, val in util_data.items():
                m = re.search(r"phys_(\d+)_", name)
                if m:
                    idx = int(m.group(1))
                    # Use max since multiple engines could be active
                    util_per_adapter[idx] = max(util_per_adapter.get(idx, 0.0), val)
            if adapter_idx in util_per_adapter:
                entry["util_percent"] = round(util_per_adapter[adapter_idx], 1)
        except Exception:
            log.debug("PDH GPU util read failed", exc_info=True)

        # Read VRAM usage
        try:
            vram_data = win32pdh.GetFormattedCounterArray(
                self._pdh_vram_counter, win32pdh.PDH_FMT_LARGE
            )
            for name, val in vram_data.items():
                if f"phys_{adapter_idx}" in name:
                    entry["mem_used_mb"] = round(val / 1024**2, 1)
                    break
        except Exception:
            log.debug("PDH GPU VRAM read failed", exc_info=True)

        # Recompute mem percent and tag source
        if entry["mem_used_mb"] and entry["mem_total_mb"]:
            entry["mem_percent"] = round(
                100.0 * entry["mem_used_mb"] / entry["mem_total_mb"], 1
            )
        if entry["source"] == "none":
            entry["source"] = "pdh"
        elif "pdh" not in entry["source"]:
            entry["source"] = f"{entry['source']}+pdh"
