"""Per-disk IO rates and active time via psutil + WMI drive mapping."""
from __future__ import annotations

import time
from typing import Any

import psutil


def _read_partitions(only_physical: bool = True) -> list:
    parts = psutil.disk_partitions(all=False)
    out = []
    for p in parts:
        if only_physical and p.opts and "cdrom" in p.opts:
            continue
        if only_physical and p.fstype == "":
            continue
        out.append(p)
    return out


# Cache the drive-mount mapping so we don't hit WMI every tick.
_drive_map: dict[str, int] | None = None


def _build_drive_map() -> dict[str, int]:
    """Build {drive_letter: physical_drive_index} via WMI.

    Walks Win32_DiskDrive → Win32_DiskPartition → Win32_LogicalDisk
    to map each logical volume to the physical drive hosting it.
    """
    mapping: dict[str, int] = {}
    try:
        import wmi  # type: ignore

        c = wmi.WMI()
        for pd in c.Win32_DiskDrive():
            try:
                drive_idx = int(pd.Index)
            except Exception:
                continue
            for part in pd.associators(wmi_result_class="Win32_DiskPartition"):
                for ld in part.associators(wmi_result_class="Win32_LogicalDisk"):
                    letter = (ld.Name or "").rstrip(":").upper()
                    if letter:
                        mapping[letter] = drive_idx
    except Exception:
        pass
    return mapping


def _drive_index_for(label: str) -> int | None:
    global _drive_map
    if _drive_map is None:
        _drive_map = _build_drive_map()
    return _drive_map.get(label.upper())


def snapshot(prev: dict | None) -> dict:
    """Return per-disk IO rates and activity percentage.

    `prev` is the previous disk_stats dict (or None on first call). It is
    needed to compute read/write MB/s and disk activity % per disk.

    Activity % is a heuristic using max of two metrics:
    - throughput ratio (combined MB/s / 80 MB/s cap)
    - IOPS ratio (combined ops/s / 500 IOPS cap)
    read_time/write_time are not reliably populated on Windows, so
    throughput + IOPS serve as the proxy for disk busyness.
    """
    counters_all: Any = None
    try:
        counters_all = psutil.disk_io_counters()
    except Exception:
        pass
    counters_perdisk: dict = {}
    try:
        counters_perdisk = psutil.disk_io_counters(perdisk=True) or {}
    except Exception:
        pass
    now = time.time()
    per_disk: list[dict] = []

    for part in _read_partitions(only_physical=True):
        label = _label_for(part)
        drive_idx = _drive_index_for(label)

        cur_io = None
        if drive_idx is not None:
            key = f"PhysicalDrive{drive_idx}"
            cur_io = counters_perdisk.get(key)

        read_mb_s = write_mb_s = io_pct = 0.0
        read_iops = write_iops = 0.0

        if prev is not None and label in (prev.get("per_disk_keys") or {}):
            prev_disk = prev["per_disk_keys"][label]
            dt = max(now - prev.get("t", now), 0.001)
            if cur_io is not None and prev_disk.get("io") is not None:
                prev_io = prev_disk["io"]
                drb = cur_io.read_bytes - prev_io.read_bytes
                dwb = cur_io.write_bytes - prev_io.write_bytes
                drc = cur_io.read_count - prev_io.read_count
                dwc = cur_io.write_count - prev_io.write_count
                read_mb_s = max(0.0, drb / dt / 1024 / 1024)
                write_mb_s = max(0.0, dwb / dt / 1024 / 1024)
                read_iops = max(0.0, drc / dt)
                write_iops = max(0.0, dwc / dt)

                # Activity % uses max of two heuristics:
                # 1. Throughput-based: combined MB/s as % of 80 MB/s cap
                # 2. IOPS-based: combined ops/s as % of 500 IOPS cap
                # This catches both large transfers (via bytes) and tiny
                # random IO (via ops) that Windows caching masks from bytes.
                pct_via_bytes = (read_mb_s + write_mb_s) / 80.0 * 100.0
                pct_via_ops = (read_iops + write_iops) / 500.0 * 100.0
                io_pct = min(100.0, max(pct_via_bytes, pct_via_ops))

        per_disk.append({
            "label": label,
            "io_percent": round(io_pct, 1),
            "read_mb_s": round(read_mb_s, 1),
            "write_mb_s": round(write_mb_s, 1),
            "_io": cur_io,
        })

    # Build per_disk_keys for next tick
    per_disk_keys = {}
    for d in per_disk:
        per_disk_keys[d["label"]] = {"io": d.pop("_io")}

    return {
        "per_disk": per_disk,
        "per_disk_keys": per_disk_keys,
        "counters": counters_all,
        "t": now,
    }


def _label_for(part) -> str:
    label = part.mountpoint.rstrip(":\\").rstrip("/")
    if not label:
        label = part.device
    return label
