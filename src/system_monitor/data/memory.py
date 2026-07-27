"""Memory stats via psutil."""
from __future__ import annotations

import psutil


def snapshot() -> dict:
    vm = psutil.virtual_memory()
    sw = psutil.swap_memory()
    return {
        "used_gb": round(vm.used / 1024**3, 2),
        "total_gb": round(vm.total / 1024**3, 2),
        "percent": float(vm.percent),
        "available_gb": round(vm.available / 1024**3, 2),
        "swap_used_gb": round(sw.used / 1024**3, 2),
        "swap_total_gb": round(sw.total / 1024**3, 2),
        "swap_percent": float(sw.percent),
    }
