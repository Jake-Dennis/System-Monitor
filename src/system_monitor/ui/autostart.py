"""Run-at-startup shortcut management.

Lives apart from MainWindow because it is pure filesystem/COM work with no
Qt dependency — and because the old inline version swallowed every failure,
so a user who ticked the box and got no shortcut had no way to tell why.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

log = logging.getLogger(__name__)

LINK_NAME = "System Monitor.lnk"


def startup_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return base / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def link_path() -> Path:
    return startup_dir() / LINK_NAME


def is_enabled() -> bool:
    """True if the startup shortcut currently exists on disk."""
    return link_path().exists()


def set_enabled(on: bool, script: Path | None = None) -> bool:
    """Create or remove the startup shortcut. Returns the state achieved.

    `script` defaults to ./run.py next to the current working directory,
    which is how run.bat launches the app.
    """
    link = link_path()
    if not on:
        try:
            link.unlink(missing_ok=True)
        except OSError:
            log.warning("could not remove startup shortcut %s", link, exc_info=True)
            return link.exists()
        return False

    target = Path(sys.executable).resolve()
    args = script or (Path.cwd() / "run.py")
    try:
        import pythoncom
        from win32com.client import Dispatch

        pythoncom.CoInitialize()
        shell = Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(str(link))
        shortcut.TargetPath = str(target)
        shortcut.Arguments = f'"{args}"'
        shortcut.WorkingDirectory = str(Path.cwd())
        shortcut.IconLocation = str(target)
        shortcut.Save()
    except Exception:
        # pywin32 is optional (depcheck installs it as such), and the Startup
        # folder may be redirected or unwritable.
        log.warning("could not create startup shortcut %s", link, exc_info=True)
        return False
    return link.exists()
