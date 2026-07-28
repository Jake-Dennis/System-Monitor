"""Persistent config (JSON in %APPDATA%/SystemMonitor/config.json)."""
from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any


DEFAULTS: dict[str, Any] = {
    "window": {
        "x": None,
        "y": None,
        "width": 380,
        "height": 980,
        "always_on_top": True,
        "opacity": 1.0,
        "locked": False,
        "appbar": False,
        "dock_side": "",
    },
    "ui": {
        "theme": "dark",
        "accent": "#00D4FF",
        "show_gpu": True,
        "show_disk_io": True,
        "show_network": True,
        "show_swap": True,
    },
    "collector": {
        "interval_seconds": 1.0,
    },
}


def config_dir() -> Path:
    base = os.environ.get("SYSTEM_MONITOR_HOME")
    if base:
        return Path(base)
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "SystemMonitor"
    return Path.home() / ".system_monitor"


def config_path() -> Path:
    return config_dir() / "config.json"


def load() -> dict[str, Any]:
    path = config_path()
    cfg = deepcopy(DEFAULTS)
    if not path.exists():
        return cfg
    try:
        with path.open("r", encoding="utf-8") as f:
            user = json.load(f)
    except (OSError, json.JSONDecodeError):
        return cfg
    _deep_merge(cfg, user)
    return cfg


def save(cfg: dict[str, Any]) -> None:
    path = config_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, sort_keys=True)
        os.replace(tmp, path)
    except OSError:
        # Config persistence is best-effort.
        pass


def _deep_merge(base: dict, overlay: dict) -> None:
    for k, v in overlay.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
