"""Entry point. Checks dependencies first, then launches the desktop app.

The dep check is pure stdlib so it runs even if PySide6 / psutil are not
yet installed — it can install them itself on the first run.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make the src/ layout importable when running as `python run.py`.
ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if SRC.exists() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Check + install missing deps BEFORE importing system_monitor (which pulls
# in PySide6 etc.). The check module is stdlib-only.
from system_monitor import depcheck  # noqa: E402

depcheck.ensure()

# Now safe to import the heavy stuff.
from system_monitor.app import main  # noqa: E402


if __name__ == "__main__":
    sys.exit(main())
