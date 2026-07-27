"""CPU stats via psutil."""
from __future__ import annotations

from typing import Any

import psutil


class CpuInfo:
    name: str
    physical_cores: int
    logical_cores: int
    arch: str

    def __init__(self) -> None:
        self.name = _read_cpu_name()
        self.physical_cores = psutil.cpu_count(logical=False) or 1
        self.logical_cores = psutil.cpu_count(logical=True) or 1
        self.arch = _read_arch()

    def snapshot(self) -> dict[str, Any]:
        """Return a fresh CPU stats dict. `psutil.cpu_percent(interval=None)`
        needs to have been called at least once before; the collector primes
        it at start, so subsequent calls return real values.
        """
        per_core = psutil.cpu_percent(interval=None, percpu=True)
        total = psutil.cpu_percent(interval=None)
        freq = psutil.cpu_freq()
        return {
            "percent": float(total),
            "per_core": [float(p) for p in per_core],
            "freq_mhz": float(freq.current) if freq else None,
            "name": self.name,
            "physical_cores": self.physical_cores,
            "logical_cores": self.logical_cores,
        }


def _read_cpu_name() -> str:
    # WMI gives actual model name (e.g. "AMD Ryzen 7 5700X 8-Core Processor").
    try:
        import wmi  # type: ignore

        c = wmi.WMI()
        for cpu in c.Win32_Processor():
            if cpu.Name and cpu.Name.strip():
                return cpu.Name.strip()
    except Exception:
        pass
    # Fallback to platform.processor() (raw CPUID string).
    try:
        import platform

        processor = platform.processor() or ""
        if processor.strip():
            return processor.strip()
    except Exception:
        pass
    return "CPU"


def _read_arch() -> str:
    import platform

    return platform.machine() or "unknown"
