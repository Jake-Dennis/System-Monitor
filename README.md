# System Monitor

A small, Rainmeter-style desktop widget for Windows that shows live CPU, GPU,
RAM, disk, and network load in a frameless, translucent, always-on-top panel.

## Features

- **CPU** total + per-core strip, current frequency, model name
- **GPU** utilization, VRAM, power, fan speed — NVIDIA via NVML out of the box; AMD / Intel need LibreHardwareMonitor running
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
| `Esc`     | Close                                 |

## LibreHardwareMonitor (AMD / Intel GPU sensors)

The panel works out of the box for NVIDIA. For AMD or Intel GPUs, util / VRAM
/ fan / power readings need LibreHardwareMonitor running:

1. Download from <https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases>
   or `winget install LibreHardwareMonitor.LibreHardwareMonitor`
2. Launch once **as Administrator** (so its kernel driver can read sensors)
3. Open **Options → Remote Web Server → Run** (default port `8085`)
4. Leave LHM running in the system tray; the app polls `http://localhost:8085/data.json`

The GPU card will then show full sensor data for any vendor. Without LHM,
AMD/Intel adapters still appear by name + total VRAM (via DXGI) but live
numbers are blank.

## Configuration

Persisted to `%APPDATA%\SystemMonitor\config.json`. The file is created on
first run; you can hand-edit it.

```json
{
  "window": { "x": 1500, "y": 48, "width": 360, "height": 640, "always_on_top": true, "opacity": 0.92 },
  "ui":     { "show_gpu": true, "show_disk_io": true, "show_network": true, "show_swap": true },
  "collector": { "interval_seconds": 1.0 }
}
```

Set the `SYSTEM_MONITOR_HOME` environment variable to relocate the config
directory.

## Project layout

```
run.py                     # entry point — wires src/ to sys.path
requirements.txt
src/system_monitor/
  app.py                   # QApplication + bridge
  config.py                # JSON config in %APPDATA%
  data/
    collector.py           # background sampling thread
    cpu.py  memory.py  disk.py  network.py  gpu.py  lhm_gpu.py  dxgi.py
  ui/
    styles.py              # QSS theme + color helpers
    main_window.py         # frameless, draggable, translucent
    widgets/               # one card per metric
```

## License

MIT (or whatever you choose — pick one before publishing).
