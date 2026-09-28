# System Monitor

A small, Rainmeter-style desktop widget for Windows that shows live CPU, GPU,
RAM, disk, and network load in a frameless, translucent, always-on-top panel.

## Features

- **CPU** total + per-core strip, current frequency, model name
- **GPU** utilization, VRAM, power, fan speed — NVIDIA via NVML; all vendors via built-in Windows Performance Counters
- **Memory** used/total + swap
- **Disk** all physical volumes with read/write MB/s
- **Network** up/down rates + lifetime totals

## Quick start

```powershell
# from the repo root
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

The panel appears in the top-right of your primary monitor. Drag the header
to move it.

## Keyboard shortcuts

| Key       | Action                                |
|-----------|---------------------------------------|
| `L`       | Toggle drag-lock                      |
| `T`       | Toggle always-on-top                  |
| `Ctrl+Q`  | Quit                                  |
| Right-click | Open context menu (toggle cards, reset position) |
| Gear (⚙)   | Settings: per-card visibility/detach/reorder, drives, theme, accent, sample interval, dock, screen, history folder |
| `Esc`     | Close                                 |

## Configuration

Persisted to `%APPDATA%\SystemMonitor\config.json`. The file is created on
first run; you can hand-edit it.

```json
{
  "window": { "x": 1500, "y": 48, "width": 360, "height": 640,
              "always_on_top": true, "opacity": 0.92,
              "locked": false, "appbar": false, "dock_side": "" },
  "ui":     { "theme": "dark", "accent": "#00D4FF",
              "show_cpu": true, "show_gpu": true, "show_memory": true,
              "show_network": true, "show_now_playing": true,
              "show_disk_io": true, "show_swap": true,
              "hidden_drives": [] },
  "collector": { "interval_seconds": 1.0 }
}
```

Every key above is reachable from the gear menu except `x`/`y`/`width`/
`height`, which track the window itself. Unknown keys are preserved, and a
hand-edited value that fails validation falls back to the default rather than
producing an unstyled panel — `ui.accent` must be `#RGB` or `#RRGGBB`.

Set the `SYSTEM_MONITOR_HOME` environment variable to relocate the config
directory.

## Project layout

```
run.py                     # entry point — wires src/ to sys.path
requirements.txt
tests/test_smoke.py        # headless suite: .venv/Scripts/python tests/test_smoke.py
src/system_monitor/
  app.py                   # QApplication, snapshot bridge, single-instance lock
  config.py                # JSON config in %APPDATA%
  depcheck.py              # two-tier dependency install
  history.py               # background CSV recorder
  data/                    # plain dicts, never raises
    collector.py           # background sampling thread + per-sensor health
    cpu.py  memory.py  disk.py  network.py  gpu.py  dxgi.py  media.py
  ui/
    styles.py              # QSS theme, accent color, color_for_percent
    main_window.py         # orchestrator: widget tree + Qt events
    cards.py               # card registry (names, config keys, ordering)
    menus.py               # context + settings menu construction
    appbar.py              # Windows AppBar edge reservation (ctypes)
    autostart.py           # run-at-startup shortcut
    taskbar_media.py       # taskbar thumbnail media buttons
    drag_manager.py        # app-level card drag-and-drop
    widgets/               # one card per metric
```

## License

MIT (or whatever you choose — pick one before publishing).
