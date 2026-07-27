"""Network IO rates and utilization via psutil.

Measures throughput per active network interface and computes utilization
as a percentage of the adapter's link speed — same approach as Task Manager.
"""
from __future__ import annotations

import time
from typing import Any

import psutil


def snapshot(prev: dict | None) -> dict:
    try:
        counters_pernic: dict[str, Any] = psutil.net_io_counters(pernic=True) or {}
    except Exception:
        counters_pernic = {}
    stats: dict[str, Any] = {}
    try:
        stats = psutil.net_if_stats() or {}
    except Exception:
        stats = {}
    now = time.time()

    up_kb_s = down_kb_s = 0.0
    util_pct = 0.0

    for iface, cur in counters_pernic.items():
        iface_stat = stats.get(iface)
        if iface_stat is None or not iface_stat.isup:
            continue
        link_speed_mbps = iface_stat.speed  # 0 if unknown
        if link_speed_mbps <= 0:
            continue

        if (prev is not None
                and prev.get("pernic")
                and iface in prev["pernic"]
                and prev["pernic"][iface].get("io") is not None):
            prev_io = prev["pernic"][iface]["io"]
            dt = max(now - prev.get("t", now), 0.001)
            du = max(0.0, (cur.bytes_sent - prev_io.bytes_sent) / dt / 1024)
            dd = max(0.0, (cur.bytes_recv - prev_io.bytes_recv) / dt / 1024)
            up_kb_s += du
            down_kb_s += dd
            # Utilization: (throughput) / (link speed) * 100
            total_mbps = (du + dd) / 125  # KB/s to Mbps
            iface_util = min(100.0, total_mbps / link_speed_mbps * 100.0)
            util_pct = max(util_pct, iface_util)

    # Aggregate totals (for total_sent_gb / total_recv_gb)
    total_sent = total_recv = 0
    for iface, cur in counters_pernic.items():
        total_sent += cur.bytes_sent
        total_recv += cur.bytes_recv

    return {
        "up_kb_s": round(up_kb_s, 1),
        "down_kb_s": round(down_kb_s, 1),
        "util_percent": round(util_pct, 1),
        "total_sent_gb": round(total_sent / 1024**3, 2),
        "total_recv_gb": round(total_recv / 1024**3, 2),
        "pernic": {name: {"io": io} for name, io in counters_pernic.items()},
        "t": now,
    }
