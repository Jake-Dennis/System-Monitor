"""LHM-based GPU sensor reader.

Pulls util / VRAM / fan / power for any GPU vendor that
LibreHardwareMonitor exposes (AMD, NVIDIA, Intel). Walks the recursive
LHM JSON tree defensively so it tolerates differences across LHM
versions and driver revisions.

Requires LibreHardwareMonitor running locally with the Remote Web
Server enabled (default port 8085). The Python reader is read-only and
does not need elevation; LHM itself must be launched as Administrator
for AMD/NVIDIA driver-level sensors to populate.
"""
from __future__ import annotations

import json
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


LHM_URL = "http://localhost:8085/data.json"
_LHM_TIMEOUT = 1.5  # seconds


class LhmGpuReader:
    """Walks the LHM sensor tree and returns one dict per detected GPU.

    Each returned dict has: `vendor`, `name`, and any of
    `util_percent`, `mem_used_mb`, `mem_total_mb`,
    `fan_percent`, `power_w` that LHM exposed for that GPU.

    Also exposes CPU package power via `read_cpu_power_w()`.
    """

    def __init__(self) -> None:
        self._ok = self._probe()

    @property
    def available(self) -> bool:
        return self._ok

    def snapshot(self) -> list[dict[str, Any]]:
        if not self._ok:
            return []
        data = self._fetch_tree()
        if data is None:
            return []
        out: list[dict[str, Any]] = []
        # LHM groups GPUs under /gpu-{vendor}/{idx}/ subtrees. We try each
        # known vendor prefix; sensors will only populate for what the
        # current hardware/driver combo actually exposes.
        for vendor in ("amd", "nvidia", "intel"):
            for idx in range(8):
                gpu = self._read_gpu(data, vendor, idx)
                if gpu is not None:
                    out.append(gpu)
        return out

    def read_cpu_power_w(self) -> float | None:
        """Return CPU package power in watts, or None if unavailable."""
        if not self._ok:
            return None
        data = self._fetch_tree()
        if data is None:
            return None
        # LHM typically exposes CPU package power under /cpu/{idx}/ package,
        # or on some systems under /main/power or /cpu/{idx}/clocks/power.
        # Try a broad sweep: find any Power sensor in /cpu/ subtrees.
        for idx in range(8):
            prefix = f"/cpu/{idx}/"
            node = self._find_node(data, prefix)
            if node is None:
                continue
            # Depth-first search for Power sensors under this CPU node.
            out: dict[str, Any] = {}
            self._collect(node, prefix + "xxx", out)
            # Fall back: if the node itself isn't matched by collect's startswith
            # (which expects the prefix to match SensorId's full path), redo with
            # a simpler descent that looks for Type == "Power".
            result = self._find_power(node, prefix)
            if result is not None:
                return result
        return None

    @staticmethod
    def _find_power(node: dict, prefix: str) -> float | None:
        """Deep search under `node` for the first Power sensor."""
        sid = node.get("SensorId", "") or ""
        stype = node.get("Type", "") or ""
        if sid.startswith(prefix) and stype == "Power":
            value = node.get("Value")
            if value is not None:
                num = _parse_number(value, suffix_strip="wW")
                if num is not None:
                    return num
        for child in node.get("Children", []) or []:
            result = LhmGpuReader._find_power(child, prefix)
            if result is not None:
                return result
        return None

    # ----- HTTP -----

    def _probe(self) -> bool:
        try:
            req = Request(LHM_URL, headers={"User-Agent": "system-monitor"})
            with urlopen(req, timeout=_LHM_TIMEOUT) as r:
                return r.status == 200
        except (URLError, OSError, ValueError):
            return False

    def _fetch_tree(self) -> dict | None:
        try:
            req = Request(LHM_URL, headers={"User-Agent": "system-monitor"})
            with urlopen(req, timeout=_LHM_TIMEOUT) as r:
                return json.loads(r.read().decode("utf-8", errors="ignore"))
        except (URLError, OSError, ValueError):
            return None

    # ----- tree walking -----

    def _read_gpu(self, root: dict, vendor: str, idx: int) -> dict[str, Any] | None:
        prefix = f"/gpu-{vendor}/{idx}/"
        node = self._find_node(root, prefix)
        if node is None:
            return None
        out: dict[str, Any] = {"vendor": vendor, "name": vendor.upper() + f" #{idx}"}
        self._collect(node, prefix, out)
        # Drop the entry if LHM gave us nothing actionable.
        if not any(k in out for k in ("util_percent", "mem_used_mb", "fan_percent", "power_w")):
            return None
        return out

    @staticmethod
    def _find_node(node: dict, target_prefix: str) -> dict | None:
        """Find the node whose SensorId equals `target_prefix` (no trailing slash)."""
        sid = node.get("SensorId", "") or ""
        if sid == target_prefix.rstrip("/"):
            return node
        for child in node.get("Children", []) or []:
            hit = LhmGpuReader._find_node(child, target_prefix)
            if hit is not None:
                return hit
        return None

    def _collect(self, node: dict, prefix: str, out: dict[str, Any]) -> None:
        sid = node.get("SensorId", "") or ""
        if sid.startswith(prefix):
            self._absorb(sid[len(prefix):], node, out)
        for child in node.get("Children", []) or []:
            self._collect(child, prefix, out)

    @staticmethod
    def _absorb(sensor_path: str, node: dict, out: dict[str, Any]) -> None:
        value = node.get("Value")
        if value is None:
            return
        stype = node.get("Type", "") or ""
        text = (node.get("Text") or "").lower()
        pl = sensor_path.lower()

        # Load: utilization. Prefer the "Core" sensor when LHM exposes several.
        if stype == "Load" and "util_percent" not in out:
            if "core" in text or "gpu" in text or "util" in text:
                num = _parse_number(value, suffix_strip="%")
                if num is not None:
                    out["util_percent"] = num
            return

        # Memory: data sensors under memory or smali namespaces.
        if stype in ("Data", "SmallData"):
            num = _parse_number(value, suffix_strip="mbgb")
            if num is None:
                return
            mb = LhmGpuReader._normalize_mem(num, value)
            if "used" in pl and "mem_used_mb" not in out:
                out["mem_used_mb"] = mb
            elif "total" in pl and "mem_total_mb" not in out:
                out["mem_total_mb"] = mb
            return

        # Fan: control sensors.
        if stype == "Control" and "fan_percent" not in out:
            num = _parse_number(value, suffix_strip="%")
            if num is not None:
                out["fan_percent"] = num
            return

        # Power.
        if stype == "Power" and "power_w" not in out:
            num = _parse_number(value, suffix_strip="wW")
            if num is not None:
                out["power_w"] = num
            return

    @staticmethod
    def _normalize_mem(num: float, raw: Any) -> float:
        """LHM may report memory in bytes or in MB/GB. Normalize to MB."""
        s = str(raw).lower()
        if "gb" in s:
            return round(num * 1024.0, 1)
        if "mb" in s:
            return round(num, 1)
        # No unit suffix: assume bytes if the value is huge.
        if num > 10 * 1024 * 1024:
            return round(num / 1024 / 1024, 1)
        return round(num, 1)


def _parse_number(value: Any, *, suffix_strip: str = "") -> float | None:
    """Parse a sensor value, tolerating unit suffixes (°C, %, MB, W, …)."""
    s = str(value).strip()
    if not s:
        return None
    # strip every character in suffix_strip (case-insensitively)
    keep = []
    sl = s.lower()
    for i, ch in enumerate(s):
        if sl[i] in suffix_strip.lower():
            continue
        keep.append(ch)
    cleaned = "".join(keep).strip()
    cleaned = cleaned.replace(",", "")
    try:
        return float(cleaned)
    except (TypeError, ValueError):
        return None
