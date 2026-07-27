"""Startup dependency check. Pure stdlib so it runs before PySide6 or psutil
are imported — it can install them.

Split into two tiers:

- **Required** — the app cannot start without these (PySide6, psutil). If
  any are missing, we attempt a `pip install` automatically, then re-check.
  On hard failure (no network, no permissions, broken venv) we print a
  clear error and exit so the user gets a readable message instead of a
  stack trace.
- **Optional** — the app degrades gracefully without these
  (`nvidia-ml-py` → no NVIDIA GPU stats; `wmi` / `pywin32` → no DXGI
  adapter names). We just print a one-line note and continue.

The check runs in the *currently active* Python, which is whichever
interpreter launched `run.py` / `run.bat`. As long as the user goes
through `run.bat`, that is the venv's Python and installs land in
`.venv\\Lib\\site-packages`.
"""
from __future__ import annotations

import importlib
import subprocess
import sys
from typing import Iterable


# Module name (what we `import` in code) → pip distribution name.
REQUIRED: dict[str, str] = {
    "psutil": "psutil",
    "PySide6": "PySide6",
}

OPTIONAL: dict[str, str] = {
    "pynvml": "nvidia-ml-py",   # NVIDIA GPU
    "wmi": "wmi",               # DXGI adapter enumeration, AMD/Intel
    "requests": "requests",     # LHM HTTP (AMD/Intel GPU)
}


def missing(modules: Iterable[str]) -> list[str]:
    """Return the modules that aren't importable in this Python."""
    out: list[str] = []
    for name in modules:
        try:
            importlib.import_module(name)
        except Exception:
            out.append(name)
    return out


def install(packages: list[str]) -> tuple[int, str]:
    """Run `python -m pip install <packages>` and return (returncode, stdout+stderr)."""
    if not packages:
        return 0, ""
    cmd = [sys.executable, "-m", "pip", "install", "--quiet", *packages]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def ensure(allow_optional_install: bool = True) -> None:
    """Check deps, install what's missing, print status.

    Exits the process if a required dep cannot be installed.
    """
    missing_req = missing(REQUIRED.keys())
    if missing_req:
        print(f"[deps] missing required: {', '.join(missing_req)}")
        pip_names = [REQUIRED[m] for m in missing_req]
        print(f"[deps] installing: {' '.join(pip_names)}")
        rc, out = install(pip_names)
        if rc != 0 or missing(REQUIRED.keys()):
            sys.stderr.write(
                "[deps] automatic install failed. Run install.bat or:\n"
                f"    {sys.executable} -m pip install {' '.join(pip_names)}\n"
            )
            if out:
                sys.stderr.write(out + "\n")
            sys.exit(1)
        print("[deps] required deps installed")

    missing_opt = missing(OPTIONAL.keys())
    if missing_opt and allow_optional_install:
        print(
            f"[deps] optional not installed (app will still work): "
            f"{', '.join(missing_opt)}"
        )
