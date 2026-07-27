"""GPU adapter enumeration via WMI `Win32_VideoController`.

Returns name + vendor + VRAM for every discrete + integrated GPU. No new
dependencies: WMI is already in the install list. Works on all Windows
versions; safe no-op if the `wmi` module is missing.
"""
from __future__ import annotations

from typing import Any


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

    Uses WMI as a portable stand-in for DXGI: same data, no extra
    dependencies. `AdapterRAM` is in bytes; for cards reporting > 4 GB
    this can be slightly off, but it is enough to populate the card.
    Virtual display adapters (Remote Desktop, Parsec, VMware, etc.)
    are filtered out.
    """
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
            out.append(
                {
                    "name": name,
                    "vendor": _classify_vendor(name),
                    "vram_mb": vram_mb,
                }
            )
    except Exception:
        return []
    return out
