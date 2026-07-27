# Architecture

System Monitor is a Rainmeter-style desktop widget for Windows that displays
live CPU, GPU, RAM, disk, and network load in a frameless, always-on-top
panel. Written in Python 3.13 with PySide6 (Qt 6).

## Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                      System Monitor                               │
│  ┌──────────┐  ┌──────────────────┐  ┌────────────────────────┐  │
│  │  run.py   │──▶ depcheck.py      │──▶  app.main()             │  │
│  │ (entry)   │  │ (auto-install)   │  │ (wire + launch)         │  │
│  └──────────┘  └──────────────────┘  └──────┬─────────────────┘  │
│                                             │                     │
│              ┌──────────────────────────────┘                     │
│              ▼                                                    │
│  ┌──────────────────────┐   ┌─────────────────────────────────┐   │
│  │  _Bridge (QObject)   │   │  Collector (background thread)   │   │
│  │  Signal.emit(snap)   │◀──│  _run() loop every ~1s          │   │
│  │  latest cache        │   │  cpu/memory/disk/network/gpu    │   │
│  └──────────┬───────────┘   └─────────────────────────────────┘   │
│             │                                                     │
│             ▼                                                     │
│  ┌──────────────────────────────────────────────────┐             │
│  │            MainWindow (QMainWindow)               │             │
│  │  apply_snapshot(snap)  → each card.update(snap)   │             │
│  │  ┌──────────────────────────────────────────────┐ │             │
│  │  │ PanelHeader  (drag-to-move, lock, close)      │ │             │
│  │  │ CpuCard     + _PerCoreStrip + Timeline        │ │             │
│  │  │ RamCard     + swap toggle + Timeline           │ │             │
│  │  │ GpuCard     + _GpuRow[] + VRAM bar + Timeline │ │             │
│  │  │ NetCard     + down/up + timelines              │ │             │
│  │  │ DiskCard    + _DiskRow[] + timelines           │ │             │
│  │  │ MediaCard   + play/pause/next/prev + track     │ │             │
│  │  └──────────────────────────────────────────────┘ │             │
│  │  QSystemTrayIcon  (play/pause/next/prev)          │             │
│  │  TaskbarMediaController  (thumbnail buttons)     │ │             │
│  └──────────────────────────────────────────────────┘             │
│                                                                   │
│  Config: %APPDATA%\SystemMonitor\config.json (JSON deep-merge)     │
│  Theme:  styles.py · qss(scale) · rgba() + OS compositor blur     │
└───────────────────────────────────────────────────────────────────┘
```

## Functional Areas

The codebase is organized into six horizontal layers. Each layer has a
single responsibility and communicates with adjacent layers through plain
dicts or Qt signals — never through shared mutable state.

### 1. Entry & Dependency Management

- **`run.py`**: Adds `src/` to `sys.path`, runs `depcheck.ensure()`, then
  calls `app.main()`. Pure-stdlib preamble ensures deps are available before
  any heavy import.
- **`depcheck.py`**: Checks two tiers:
  - **Required** (PySide6, psutil) — auto-`pip install`s if missing; exits
    with a readable message on failure.
  - **Optional** (nvidia-ml-py, wmi, requests) — prints a one-line note and
    continues. The app degrades gracefully without them.

### 2. Application Core

- **`app.py`**: `main()` loads config, creates `QApplication` with the QSS
  theme, instantiates `MainWindow`, `_Bridge`, and `Collector`. Wires the
  collector's snapshot callback to `_Bridge.post()` and starts a 10 Hz
  `QTimer` that repaints from `bridge.latest`.
- **`_Bridge`**: A `QObject` with a `Signal(dict)` and a `latest` property.
  The collector thread calls `post()` which stores the snapshot and emits
  the signal — the only thread-safe path into Qt.
- **`config.py`**: JSON config persisted to
  `%APPDATA%\SystemMonitor\config.json`. `load()` deep-merges user values
  over `DEFAULTS`. `save()` writes atomically via a `.tmp` rename. Override
  with `SYSTEM_MONITOR_HOME`.

### 3. Data Collection Layer

All sensor modules degrade gracefully — every psutil/NVML/WMI call is wrapped
in `try/except` and returns `None` or `0.0` on failure.

- **`collector.py`**: Runs a `threading.Thread` that samples every
  `interval_seconds`. Primes `psutil.cpu_percent()` (first call returns 0
  otherwise), then loops calling `_collect_once()` which assembles a flat
  dict from every sensor and calls the registered callback. Keeps
  `_prev_disk`/`_prev_net` across ticks for rate computation.
- **`cpu.py`**: Wraps `psutil.cpu_percent()`, `cpu_freq()`, `cpu_count()`.
  Returns percent, per-core list, frequency, model name (from WMI
  `Win32_Processor.Name` with fallback to `platform.processor()`).
- **`memory.py`**: Wraps `psutil.virtual_memory()` and `swap_memory()`.
  Returns used/total/percent for RAM and swap.
- **`disk.py`**: Per-disk IO rates and activity percentage. Maps partitions
  to physical drives via WMI (`Win32_DiskDrive → Win32_DiskPartition →
  Win32_LogicalDisk`). Activity % is a heuristic using max of throughput
  ratio (combined MB/s / 80 MB/s cap) and IOPS ratio (combined ops/s /
  500 IOPS cap), since `read_time`/`write_time` are not reliably populated
  on Windows.
- **`network.py`**: Wraps `psutil.net_io_counters()`. Derives up/down KB/s
  from cumulative counters stored in `prev`.
- **`gpu.py`**: Layered enrichment per adapter:
  1. **NVML** (`nvidia-ml-py`) — fills util, VRAM, power, fan. NVIDIA only.
  2. **LHM** (LibreHardwareMonitor HTTP) — fills any gaps. Works on any
     vendor. Never overwrites a non-zero value from NVML.
  3. **DXGI** (WMI `Win32_VideoController`) — name + VRAM only, always
     available baseline. Virtual display adapters are filtered out via
     `_is_virtual()`.
  Returns one entry per adapter even when no sensor source responds. The
  `source` field tracks which layers contributed.
- **`lhm_gpu.py`**: Fetches `http://localhost:8085/data.json` and walks the
  recursive JSON tree for `/gpu-{vendor}/{idx}/` subtrees. Also exposes CPU
  package power via `read_cpu_power_w()`.
- **`dxgi.py`**: Enumerates adapters via WMI `Win32_VideoController`. Filters
  out virtual adapters (`_is_virtual()`). Returns name, vendor classification,
  and VRAM.

### 4. Media Detection & Control

- **`media.py`**: Sends media keys (play/pause/next/prev) via
  `ctypes.windll.user32.keybd_event`. Detects currently playing media by
  scanning window titles of known players (Spotify, Chrome, VLC, etc.)
  via `win32gui.EnumWindows`. Parses "Artist – Title" patterns from window
  titles. Returns title, artist, app name.

### 5. UI Theme & Styles

- **`styles.py`**: Single-file QSS theme with dark palette constants
  (`ACCENT`, `WARN`, `HOT`, `CRIT`, background/text colors). Exports
  `qss(scale)` function that generates stylesheet with font sizes and widget
  heights scaled proportionally. Default thresholds: `hot_at=70`, `crit_at=90`.

### 6. UI Window & Widgets

- **`main_window.py`**:
  - **`MainWindow`** (QMainWindow): Frameless (`FramelessWindowHint`),
    always-on-top via `WindowStaysOnTopHint`. Minimum size 380×600. Accepts
    the full snapshot dict in `apply_snapshot()` and fans it out to every
    card. Persists position, size, detached state in `closeEvent()`. Responds
    to `L` (drag-lock), `T` (always-on-top), `Ctrl+Q` (quit). Gear menu opens
    settings with visibility/detach/dock/screen toggles. `resizeEvent` calls
    `_apply_scale()` to rescale fonts and widget dimensions based on window
    width.
  - **`PanelHeader`** (QFrame): Title, lock/unlock button, gear button,
    close button. Implements drag-to-move. Signals for lock, close, settings.
  - **`DetachedWindow`** (QMainWindow): Frameless, always-on-top window that
    hosts a single detached card. Drag-to-move via mouse events. Reattach
    button (⤵) sends the card back to the main panel. Position and state
    saved/restored across sessions.
- **`widgets/_base.py`**: **`_Card`** — base class for all metric cards.
  Provides title (`QLabel`), progress bar (`QProgressBar`, fixed 6px height),
  and secondary text. **Hover effect** via `setProperty("hovered", bool)` +
  `unpolish()`/`polish()` — not CSS `:hover`.
- **`widgets/_timeline.py`**: **`Timeline`** — sparkline chart widget showing
  60-second value history. Auto-scales to data range, colored fill gradient
  under the line, 1.5px line stroke, 25%/50%/75% grid lines. 300-point ring
  buffer (5 minutes at 1 Hz). Uses `QSizePolicy.Expanding` to fill available
  card space.
- **`widgets/cpu_widget.py`**: **`CpuCard`** — shows total %, per-core strip
  (`_PerCoreStrip`, custom-painted vertical bars), model name, thread count,
  frequency, CPU package power (from LHM). Timeline of total %.
- **`widgets/ram_widget.py`**: **`RamCard`** — shows RAM %, used/total GB,
  optional swap %. Timeline of RAM %.
- **`widgets/gpu_widget.py`**: **`GpuCard`** — one `_GpuRow` per adapter.
  Each row shows: vendor·name, util bar + %, VRAM bar + %, power W, fan %,
  and a util timeline. Per-adapter visibility toggle. Footer show adapter
  count, source breakdown, combined CPU+GPU power.
- **`widgets/disk_widget.py`**: **`DiskCard`** — one `_DiskRow` per drive.
  Each row shows: drive label, IO activity bar + %, R/W rates, and a compact
  timeline. Per-disk visibility toggle.
- **`widgets/net_widget.py`**: **`NetCard`** — down arrow + rate, up arrow +
  rate on one line. Two side-by-side timelines (30px fixed) for down and up.
  Total sent/recv in footer.
- **`widgets/media_widget.py`**: **`MediaCard`** — shows current track title,
  artist, source app. Three buttons: previous, play/pause, next. Updated on
  every tick via `now_playing()`.

### 7. Windows Integration

- **`taskbar_media.py`**: Adds media control buttons to the Windows taskbar
  thumbnail preview via `ITaskbarList3::ThumbBarAddButtons` (COM interface
  via `ctypes`). Icons created via `win32gui` geometric drawing. Button
  clicks dispatched via `WM_COMMAND` / `THBN_CLICKED` in `nativeEvent`.
- **System tray icon** (in `app.py`): `QSystemTrayIcon` with context menu:
  Previous, Play/Pause, Next, track info, Quit. Updates every 100ms.
  Dispatches media key commands.

### 8. Config Persistence

- **`config.py`**: JSON in `%APPDATA%\SystemMonitor\config.json`. `load()`
  deep-copies `DEFAULTS` then deep-merges saved values. `save()` uses
  atomic `.tmp` + `os.replace()` pattern.

Default config:
```json
{
  "window": { "x": null, "y": null, "width": 480, "height": 980,
              "always_on_top": true, "opacity": 1.0, "locked": false,
              "appbar": false, "dock_side": "" },
  "ui":     { "theme": "dark", "accent": "#00D4FF",
              "show_gpu": true, "show_disk_io": true,
              "show_network": true, "show_swap": true },
  "collector": { "interval_seconds": 1.0 }
}
```

## Key Execution Flows

### Flow 1: Startup — Dependency Auto-Install

```
run.py
  └─ sys.path.insert(0, "src/")
  └─ depcheck.ensure()
       ├─ importlib.import_module("PySide6")  → missing?
       │    └─ pip install PySide6 --quiet
       ├─ importlib.import_module("psutil")    → missing?
       │    └─ pip install psutil --quiet
       ├─ importlib.import_module("pynvml")    → missing?
       │    └─ print "optional not installed" (continue)
       ├─ importlib.import_module("wmi")       → missing?
       │    └─ print "optional not installed" (continue)
       └─ importlib.import_module("requests")  → missing?
            └─ print "optional not installed" (continue)
  └─ app.main() → QApplication + MainWindow + Collector + QTimer
```

### Flow 2: Snapshot Collection (Background Thread)

```
Collector._run()  [daemon thread: "system-monitor-collector"]
  ├─ PRIME: psutil.cpu_percent(interval=None, percpu=True)
  │          (first call returns 0.0 — this avoids a blank reading)
  └─ LOOP (every interval_seconds, ~1.0s):
       ├─ t0 = time.time()
       ├─ _collect_once() → dict:
       │    ├─ "cpu":     CpuInfo.snapshot()        [psutil + WMI name]
       │    ├─ "memory":  mem_mod.snapshot()        [psutil]
       │    ├─ "disks":   disk_mod.snapshot(prev)   [psutil + WMI drive map]
       │    │              updates self._prev_disk
       │    ├─ "network": net_mod.snapshot(prev)    [psutil]
       │    │              updates self._prev_net
       │    ├─ "gpus":    GpuCollector.snapshot()   [NVML → LHM → DXGI]
       │    └─ append cpu_power_w if LHM available
       ├─ self._on_snapshot(snap)
       └─ sleep(max(0.05, interval - (time.time() - t0)))
```

### Flow 3: Snapshot Delivery to Qt Main Thread

```
Collector._run() → callback(snap)
  └─ app.py closure: _Bridge.post(snap)
       ├─ self._latest = snap
       └─ self.snapshot.emit(snap)  →  Signal(dict)  →  Qt::QueuedConnection
                                                               │
      [background thread]              [Qt event loop (main)]  │
                                                                ▼
                                                  MainWindow.apply_snapshot(snap)
                                                    ├─ CpuCard.update(snap)
                                                    ├─ RamCard.update(snap)
                                                    ├─ DiskCard.update(snap)
                                                    ├─ NetCard.update(snap)
                                                    ├─ GpuCard.update(snap)
                                                    ├─ MediaCard.update(snap)
                                                    └─ detached cards → update(snap)
```

### Flow 4: UI Repaint (Decoupled from Sample Rate)

```
app.py: QTimer(interval=100ms)
  └─ timeout → window.apply_snapshot(bridge.latest or {})
       └─ fans out to all cards (same as Flow 3, but from
            the cached latest snapshot, not a fresh emission)
```

The collector can run at any rate (default 1 Hz). The UI always repaints at
10 Hz, picking up the most recent snapshot.

### Flow 5: GPU Sensor Enrichment (Per-Adapter Pipeline)

```
GpuCollector.snapshot()
  │
  ├─ Fetch LHM tree once (single HTTP GET to http://localhost:8085/data.json)
  │    → vendor buckets: {"nvidia": [nv_gpu], "intel": [intel_gpu], ...}
  │
  ├─ For each adapter (from DXGI, filtered for virtual):
  │   ├─ _empty_entry(idx, name, vendor)  ← baseline with 0s
  │   ├─ [1] NVML enrich (if NVIDIA + pynvml available)
  │   │    util_percent, mem_*, power_w, fan_percent
  │   ├─ [2] LHM enrich (if matching vendor found in tree)
  │   │    Fills any None/0 fields. NEVER overwrites non-zero from NVML.
  │   └─ source = "nvml" | "lhm" | "nvml+lhm" | "dxgi" | "unavailable"
  │
  └─ Returns list[dict], one entry per adapter
```

### Flow 6: Window Close & Config Persistence

```
User closes (Ctrl+Q / close button / Alt+F4)
  └─ MainWindow.closeEvent()
       ├─ _save_detached_state()    → saves detached window names + positions
       ├─ _save_position()           → saves x, y, width, height
       │    └─ save_config(self._config)  → atomic write to config.json
       ├─ taskbar_media.cleanup()
       └─ super().closeEvent()
  └─ QApplication.aboutToQuit
       └─ _on_exit()
            ├─ collector.stop()     → threading.Event.set() + join(timeout=2)
            ├─ config_mod.save(cfg) → backup save
            └─ tray.hide()
```

### Flow 7: Dynamic Window Scaling

```
MainWindow.resizeEvent(event)
  └─ _apply_scale()
       ├─ scale = clamp(width / 480, 0.6, 2.0)
       ├─ app.setStyleSheet(styles.qss(scale))  ← regenerates QSS with scaled fonts
       ├─ header height = round(34 * scale)
       ├─ QProgressBars: height *= scale
       ├─ QLabels (CardTitle, ValueSmall): width *= scale
       └─ Timelines: set_scale(scale)
```

## Data Contract

All cross-layer communication uses `dict[str, Any]`. The snapshot shape:

```python
{
    "timestamp": float,
    "cpu": {
        "percent": float,          # overall CPU %
        "per_core": [float],       # per-logical-core %
        "logical_cores": int,
        "freq_mhz": float | None,
        "name": str,               # WMI Win32_Processor.Name
        "arch": str,
        "power_w": float | None,   # from LHM if available
    },
    "memory": {
        "percent": float,
        "used_gb": float, "total_gb": float,
        "swap_percent": float | None,
        "swap_used_gb": float | None, "swap_total_gb": float | None,
    },
    "disks": {
        "per_disk": [{
            "label": str,          # drive letter
            "io_percent": float,   # activity % (throughput + IOPS heuristic)
            "read_mb_s": float,
            "write_mb_s": float,
        }],
        "t": float,
    },
    "network": {
        "up_kb_s": float,
        "down_kb_s": float,
        "total_sent_gb": float,
        "total_recv_gb": float,
    },
    "gpus": [{
        "index": int,
        "name": str,
        "vendor": str,             # "nvidia" | "amd" | "intel" | "unknown"
        "util_percent": float,
        "mem_used_mb": float,
        "mem_total_mb": float,
        "mem_percent": float,
        "power_w": float | None,
        "fan_percent": float | None,
        "source": str,             # "nvml" | "lhm" | "nvml+lhm" | "dxgi" | "unavailable"
    }],
}
```

Every sensor function degrades to `None` or `0.0` on failure. The UI never
assumes a field is present — cards access via `snapshot.get("key", {})` or
`snapshot.get("gpus", [])`.

## Design Constraints

- **No Qt translucency**: `WA_TranslucentBackground` is `False`. The visual
  effect comes from `rgba()` QSS backgrounds + the OS window composer's
  blur. Do not toggle translucency on.
- **No dataclasses**: Data layer returns plain dicts. This keeps the
  collector↔UI boundary serialization-free and JSON-compatible.
- **Never raise from a sensor**: Every psutil/NVML/WMI call is wrapped in
  `try/except`. Missing data is normal — `None` and `0.0` are valid values.
- **Relative imports only**: `from . import` inside the package, `from ..`
  from widgets, `from .ui` from `app.py`. No absolute `from system_monitor.*`.
- **Style in one file**: All QSS, color constants, and `color_for_percent`
  live in `ui/styles.py`. Cards reference `styles.COLOR`, not inline values.
- **Thread safety**: `_Bridge` is the only object the collector thread
  touches from the Qt side. Widgets are never touched directly from the
  collector — all updates go through `Signal.emit()`.
- **GPU enrichment order**: NVML writes first (NVIDIA only, most complete),
  then LHM fills gaps without overwriting non-zero values, then DXGI is the
  always-available fallback for name + VRAM.
- **`psutil.cpu_percent(interval=None)` returns 0 on first call**. The
  collector primes it before the main loop. Never remove the prime.
- **Disk/net rates are derived from cumulative counters**. The collector
  stores `_prev_disk`/`_prev_net` between ticks. Deleting this state breaks
  read/write MB/s.
- **Virtual GPUs are filtered**: Adapters whose names match virtual keywords
  (Parsec, Citrix, VMware, Hyper-V, etc.) are excluded at the DXGI level.

## Dependency Graph

```mermaid
graph TB
    subgraph "Entry"
        run["run.py"] --> depcheck["depcheck.py"]
        depcheck --> app["app.py"]
    end

    subgraph "App Core"
        app --> config["config.py<br/>JSON in %APPDATA%"]
        app --> bridge["_Bridge<br/>Signal + latest cache"]
        app --> timer["QTimer 100ms"]
        app --> tray["QSystemTrayIcon<br/>media controls"]
        app --> window["MainWindow"]
    end

    subgraph "Data Layer"
        collector["Collector (thread)"] --> cpu["cpu.py<br/>psutil + WMI"]
        collector --> mem["memory.py<br/>psutil"]
        collector --> disk["disk.py<br/>psutil + WMI drive map"]
        collector --> net["network.py<br/>psutil"]
        subgraph "GPU Pipeline"
            gpu["gpu.py<br/>GpuCollector"]
            nvml["pynvml<br/>NVIDIA only"]
            lhm["lhm_gpu.py<br/>LHM HTTP"]
            dxgi["dxgi.py<br/>WMI Win32_Controller"]
            dxgi -->|adapter[0]| gpu
            dxgi -->|adapter[N]| gpu
            gpu --> nvml
            gpu --> lhm
        end
    end

    subgraph "Media"
        media["media.py<br/>window title scan<br/>+ media keys"]
    end

    subgraph "UI Theme"
        styles["styles.py<br/>qss(scale) + colors"]
    end

    subgraph "UI Widgets"
        _card["_Card base<br/>hover: property + unpolish/polish"]
        timeline["Timeline<br/>sparkline 5min history"]
        cpu_card["CpuCard + PerCoreStrip"]
        ram_card["RamCard"]
        disk_card["DiskCard + DiskRow[]"]
        net_card["NetCard + dual timelines"]
        gpu_card["GpuCard + GpuRow[]"]
        media_card["MediaCard<br/>now playing + controls"]
        header["PanelHeader<br/>drag-to-move"]
    end

    subgraph "Windows Integration"
        taskbar["taskbar_media.py<br/>thumbnail toolbar"]
    end

    collector -- "callback" --> bridge
    bridge -- "Signal.emit()" --> window
    timer -- "bridge.latest" --> window
    window --> header
    window --> _card
    window --> timeline
    _card --> cpu_card
    _card --> ram_card
    _card --> disk_card
    _card --> net_card
    _card --> gpu_card
    _card --> media_card
    window --> taskbar
    app --> styles
    window --> styles
    tray --> media

    classDef entry fill:#1a1a2e,stroke:#e94560,color:#eee
    classDef core fill:#16213e,stroke:#0f3460,color:#eee
    classDef data fill:#0f3460,stroke:#00b4d8,color:#eee
    classDef ui fill:#1b4332,stroke:#52b788,color:#eee
    classDef theme fill:#4a1942,stroke:#c77dff,color:#eee
    classDef win fill:#3d0c11,stroke:#e94560,color:#eee
    class run,depcheck entry
    class app,config,bridge,timer,tray core
    class collector,cpu,mem,disk,net,gpu,nvml,lhm,dxgi data
    class _card,timeline,cpu_card,ram_card,disk_card,net_card,gpu_card,media_card,header ui
    class styles theme
    class taskbar win
```
