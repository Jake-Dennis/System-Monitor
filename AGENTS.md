# AGENTS.md

Repo-specific guidance for OpenCode sessions. Read this before touching the
codebase; the non-obvious facts below took research to surface.

## Stack at a glance

- **Language:** Python 3.13 (use the `py` launcher on Windows; the bare
  `python` command resolves to the Microsoft Store stub)
- **GUI:** PySide6 (Qt 6) — frameless window, dark QSS theme, look comes from
  OS compositor blending + `rgba()` QSS backgrounds (not Qt translucency —
  `WA_TranslucentBackground` is `False`)
- **Threading:** plain `threading.Thread` driven by a `threading.Event` that
  marshals snapshots to the Qt main thread via `Signal`
- **Config:** JSON in `%APPDATA%\SystemMonitor\config.json` (override with
  `SYSTEM_MONITOR_HOME`)
- **Deps:** auto-installed by `run.py` via `depcheck.ensure()` — two tiers:
  required (PySide6, psutil) and optional (nvidia-ml-py, wmi, requests)

## Install + run (without thinking)

```powershell
.\run.bat                          # auto-creates .venv + installs deps + launches
```

For a one-shot smoke test of the data layer (no display needed):
```powershell
py -3.13 -c "from system_monitor.data.collector import Collector; c=Collector(); c.on_snapshot=lambda s: print(s); c.start(); import time; time.sleep(3); c.stop()"
```

## Layout

| Path                                                    | Role                                                            |
|---------------------------------------------------------|-----------------------------------------------------------------|
| `run.py`                                                | Entry point. Adds `src/` to `sys.path`, runs `depcheck.ensure()`, then `app.main()` |
| `src/system_monitor/depcheck.py`                        | Auto-installs required (PySide6, psutil) + optional deps before heavy imports |
| `src/system_monitor/app.py`                             | QApplication + `_Bridge` QObject that emits snapshots to Qt. 10 Hz repaint timer |
| `src/system_monitor/config.py`                          | `load()` / `save()` JSON config with `deepcopy(DEFAULTS)` + `_deep_merge` |
| `src/system_monitor/data/collector.py`                  | Background thread, calls every sensor, emits a snapshot dict. Keeps `_prev_disk`/`_prev_net` for rate computation |
| `src/system_monitor/data/cpu.py` / `memory.py` / `disk.py` / `network.py` | psutil wrappers, plain dicts out |
| `src/system_monitor/data/gpu.py`                        | Merges NVML, LHM HTTP, and DXGI. Enrichment order: NVML fills, then LHM fills gaps without overwriting non-zero values |
| `src/system_monitor/data/lhm_gpu.py`                    | Walks LHM JSON tree for any vendor GPU sensors |
| `src/system_monitor/data/dxgi.py`                       | Adapter enumeration via WMI `Win32_VideoController` |
| `src/system_monitor/ui/styles.py`                       | QSS theme + `color_for_percent` helper. All style in one file |
| `src/system_monitor/ui/main_window.py`                  | Frameless window, drag-to-move header, context menu, shortcuts. Min size 380×720 |
| `src/system_monitor/ui/widgets/_base.py`                | `_Card` QFrame base. Hover styling via `setProperty("hovered", bool)` + `unpolish()`/`polish()` |
| `src/system_monitor/ui/widgets/{cpu,ram,disk,net,gpu}_widget.py` | One card per metric. Each receives the full app snapshot in `update()` and extracts what it needs |

## Architecture facts agents get wrong

- **Snapshots are emitted from a non-Qt thread.** The collector thread calls
  `_Bridge.post()`, which uses `Signal.emit()` to bounce into the Qt main
  thread. Never touch widgets directly from the collector.
- **Repaint is decoupled from sample rate.** `app.py` runs a 10 Hz `QTimer`
  that calls `window.apply_snapshot(bridge.latest)`. The collector can run
  at any interval without overdriving the UI.
- **`psutil.cpu_percent(interval=None)` returns 0 on the very first call.**
  The collector primes it inside `_run()` before entering the loop. Don't
  remove the prime call.
- **GPU collection is layered.** `GpuCollector.snapshot()` always returns one
  entry per adapter the system reports (via DXGI), even when no sensor source
  is available. Enrichment: NVML fills values first, then LHM fills remaining
  gaps — never overwrites a non-zero/non-None value with zero from LHM. The
  `source` field is `nvml`, `lhm`, `nvml+lhm`, `dxgi`, or `unavailable`.
- **Disk IO rates are derived from cumulative `psutil.disk_io_counters`.**
  The collector keeps `prev["counters"]` between calls; deleting that state
  will silently break the read/write MB/s readout.
- **LHM is the only path for AMD / Intel GPU utilization, memory, fan,
  and power.** NVML is NVIDIA-only. Without LHM running as Administrator,
  AMD and Intel adapters will show name + total VRAM only (via DXGI).
- **`depcheck.ensure()` runs before `system_monitor` is imported** — it uses
  only stdlib so it can install missing packages (PySide6, psutil) before they
  are imported. Optional deps (nvidia-ml-py, wmi, requests) get a one-line
  note and the app continues without them.
- **The PySide6 import errors you see in the LSP before installing deps are
  expected.** They resolve after `pip install -r requirements.txt` or running
  `.\run.bat`.
- **`_Card` hover effect** is implemented by setting a Qt dynamic property
  (`hovered` = true/false) and calling `style().unpolish()` / `style().polish()`
  to re-evaluate the QSS `[hovered="true"]` selector. Not a CSS `:hover` —
  unique to Qt's property system.

## Coding conventions

- **Pure data, plain dicts.** The data layer returns `dict[str, Any]`, not
  dataclasses. UI code uses `snapshot.get("cpu", {})` access. This keeps the
  boundary fuzz-free and means JSON serialization "just works".
- **Never raise out of a sensor function.** Wrap each psutil/NVML/WMI call in
  `try/except` and degrade to `None` or `0.0`. The UI assumes missing data is
  normal.
- **Style decisions live in `ui/styles.py`.** New colors, accent states, or QSS
  rules go there — not inline. Use `color_for_percent` for thresholds (default
  `hot_at=70`, `crit_at=90`).
- **Widget card convention:** every card subclasses `_Card`, implements
  `update(snapshot)` where `snapshot` is the full app-level dict, and never
  touches state outside its own widgets.
- **Relative imports only.** `from . import styles` inside the package, `from ..`
  from a widget, `from .ui` from `app.py`. No absolute `from system_monitor…`
  imports anywhere.

## Config

Persisted to `%APPDATA%\SystemMonitor\config.json`. Actual defaults (from
`config.py` — these are the source of truth):

```json
{
  "window": { "x": null, "y": null, "width": 480, "height": 980,
              "always_on_top": true, "opacity": 1.0, "locked": false },
  "ui":     { "theme": "dark", "accent": "#00D4FF",
              "show_gpu": true, "show_disk_io": true,
              "show_network": true, "show_swap": true },
  "collector": { "interval_seconds": 1.0 }
}
```

## Verification

No test suite. Narrowest credible checks are the headless smoke test (see
above) and launching `python run.py` / `.\run.bat`. Success criteria:
- Panel appears in the top-right of the primary monitor.
- CPU%, memory%, disk%, net% bars move within 2 seconds.
- Right-click menu toggles cards, `L` toggles drag-lock, `T` toggles
  always-on-top, `Ctrl+Q` quits and persists window position.

## Common pitfalls

- **`pip install pynvml` is the wrong package.** Use `pip install nvidia-ml-py`.
- **Window invisible after windowFlags change** — `setWindowFlags()` resets
  other flags. Always use `MainWindow.apply_always_on_top()` which rebuilds
  from `self.windowFlags()` and calls `show()` after.
- **AMD/Intel GPU shows only name + VRAM** — LHM is not running, or was not
  run as Administrator.
- **Position resets on every launch** — config save is wired to
  `aboutToQuit`. Task Manager kill won't persist it.
- **Black background, not translucent** — do not toggle
  `WA_TranslucentBackground` on. The look comes from QSS `rgba()` background
  and the OS window composer's blur.
- **Config defaults in README may be stale** — verify against
  `config.DEFAULTS` in `src/system_monitor/config.py`.
