"""GPU adapter enumeration via WMI `Win32_VideoController`.

Returns name + vendor + VRAM for every discrete + integrated GPU. Uses
the `wmi` module if available, otherwise falls back to `wmic.exe` (built
into Windows). Safe no-op when neither works.
"""
from __future__ import annotations

import logging
import re
import subprocess
from typing import Any

log = logging.getLogger(__name__)


_VENDOR_HINTS: list[tuple[str, tuple[str, ...]]] = [
    ("nvidia", ("nvidia", "geforce", "rtx", "gtx", "quadro", "tesla")),
    ("amd",    ("amd", "radeon", "ati ", "rx ", "vega", "navi", "rdna")),
    ("intel",  ("intel", "arc ", "iris", "uhd", "hd graphics")),
]

_VIRTUAL_KEYWORDS: tuple[str, ...] = (
    "virtual", "microsoft basic", "parsec", "citrix", "vmware",
    "hyper-v", "remote", "indirect", "display adapter", "ldci",
    "rdp", "spice", "parallels", "virtualbox",
)


def _classify_vendor(name: str) -> str:
    nl = (name or "").lower()
    for vendor, hints in _VENDOR_HINTS:
        for hint in hints:
            if hint in nl:
                return vendor
    return "unknown"


def _is_virtual(name: str) -> bool:
    nl = (name or "").lower()
    return any(kw in nl for kw in _VIRTUAL_KEYWORDS)


def enumerate_adapters() -> list[dict[str, Any]]:
    """Return a list of `{name, vendor, vram_mb}` dicts for every real GPU.

    Tries WMI module first, then wmic.exe, then reads the Windows registry.
    Virtual display adapters are filtered out.
    """
    out = _enumerate_wmi()
    if not out:
        out = _enumerate_wmic()
    if not out:
        out = _enumerate_registry()
    return out


def _enumerate_wmi() -> list[dict[str, Any]]:
    """WMI-based GPU enumeration via the `wmi` package."""
    try:
        import wmi  # type: ignore
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    try:
        c = wmi.WMI()
        for ctrl in c.Win32_VideoController():
            name = (ctrl.Name or "").strip() or "GPU"
            if _is_virtual(name):
                continue
            vram = 0
            try:
                vram = int(ctrl.AdapterRAM or 0)
            except Exception:
                vram = 0
            vram_mb = round(vram / 1024 / 1024, 0) if vram > 0 else 0.0
            out.append({"name": name, "vendor": _classify_vendor(name), "vram_mb": vram_mb})
    except Exception:
        return []
    return out


def _enumerate_wmic() -> list[dict[str, Any]]:
    """Fallback GPU enumeration via `wmic.exe` (built into Windows)."""
    out: list[dict[str, Any]] = []
    try:
        result = subprocess.run(
            ["wmic", "path", "Win32_VideoController", "get", "Name", "AdapterRAM", "/format:csv"],
            capture_output=True, text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except Exception:
        return []
    if result.returncode != 0 or not result.stdout.strip():
        return []
    # Parse CSV output: header first, then data rows
    lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]
    if len(lines) < 2:
        return []
    for line in lines[1:]:
        parts = line.split(",")
        if len(parts) < 3:
            continue
        name = (parts[1] or "").strip()
        if not name or _is_virtual(name):
            continue
        vram_str = (parts[2] or "").strip()
        vram = 0
        try:
            vram = abs(int(vram_str))
        except (ValueError, TypeError):
            vram = 0
        vram_mb = round(vram / 1024 / 1024, 0) if vram > 0 else 0.0
        out.append({"name": name, "vendor": _classify_vendor(name), "vram_mb": vram_mb})
    return out


def _enumerate_registry() -> list[dict[str, Any]]:
    """Fallback GPU enumeration via Windows registry (no deps needed).

    Reads display adapter names from the Device Manager registry key.
    """
    out: list[dict[str, Any]] = []
    try:
        import winreg
    except Exception:
        return []
    key_path = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as base:
            i = 0
            while True:
                try:
                    sub_name = winreg.EnumKey(base, i)
                    i += 1
                except OSError:
                    break
                sub_path = f"{key_path}\\{sub_name}"
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, sub_path) as sub_key:
                        try:
                            name, _ = winreg.QueryValueEx(sub_key, "DriverDesc")
                        except OSError:
                            continue
                        name = (name or "").strip()
                        if not name or _is_virtual(name):
                            continue
                        out.append({
                            "name": name,
                            "vendor": _classify_vendor(name),
                            "vram_mb": 0.0,
                        })
                except OSError:
                    continue
    except OSError:
        pass
    return out
