"""CPU temperature via WMI MSAcpi_ThermalZoneTemperature.

Requires Administrator rights to read ACPI thermal zones. Returns
gracefully when not available (returns None).

Temperature readings from WMI are in tenths of Kelvin.
"""
from __future__ import annotations

import logging
import time
from typing import Any

log = logging.getLogger(__name__)


def _read_temps() -> dict[str, Any] | None:
    """Read ACPI thermal zones. Returns dict with `cpu_temp_c`, `temps`,
    or None on failure.

    `cpu_temp_c` is the max temperature found (CPU package is usually the
    highest temp), `temps` is a dict of zone-name -> celsius.
    """
    try:
        import wmi  # type: ignore
    except Exception:
        return None

    try:
        c = wmi.WMI(namespace="root\\wmi")
        zones = list(c.MSAcpi_ThermalZoneTemperature())
    except Exception:
        log.debug("MSAcpi thermal zone read failed (admin required?)", exc_info=True)
        return None

    if not zones:
        return None

    temps: dict[str, float] = {}
    max_temp_c: float | None = None
    for z in zones:
        try:
            raw = z.CurrentTemperature
            if raw is None:
                continue
            # WMI gives tenths of Kelvin
            celsius = raw / 10.0 - 273.15
            name = z.InstanceName or "?"
            temps[name] = round(celsius, 1)
            if max_temp_c is None or celsius > max_temp_c:
                max_temp_c = celsius
        except Exception:
            continue

    if max_temp_c is None:
        return None
    return {"cpu_temp_c": round(max_temp_c, 1), "temps": temps}


class CpuTempReader:
    """Cached CPU temperature reader.

    ACPI thermal zones are read once per call to `read()`. The result
    is cached briefly (default 5 seconds) to avoid hammering WMI.
    """

    def __init__(self, cache_seconds: float = 5.0) -> None:
        self._cache_seconds = cache_seconds
        self._last_value: dict[str, Any] | None = None
        self._last_time: float = 0.0

    def read(self) -> dict[str, Any] | None:
        now = time.time()
        if self._last_value is not None and (now - self._last_time) < self._cache_seconds:
            return self._last_value
        value = _read_temps()
        self._last_value = value
        self._last_time = now
        return value

    def available(self) -> bool:
        return self.read() is not None
