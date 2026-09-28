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
  required (PySide6, psutil) and optional (nvidia-ml-py, wmi)

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
| `src/system_monitor/data/collector.py`                  | Background thread, calls every sensor, emits a snapshot dict. Keeps `_prev_disk`/`_prev_net` for rate computation. Probes each sensor and reports `snapshot["health"]` |
| `src/system_monitor/data/cpu.py` / `memory.py` / `disk.py` / `network.py` | psutil wrappers, plain dicts out |
| `src/system_monitor/data/gpu.py`                        | Merges NVML, Windows PDH, and DXGI. Enrichment order: NVML fills, then PDH fills gaps for any vendor |
| `src/system_monitor/data/dxgi.py`                       | Adapter enumeration via WMI `Win32_VideoController` |
| `src/system_monitor/data/media.py`                      | Owns all media state: winrt SMTC session on a daemon thread, `now_playing()` + `dispatch(cmd_id)`. Sampled by the collector, not by the UI |
| `src/system_monitor/history.py`                         | Background CSV recorder (`%APPDATA%\SystemMonitor\history\`) + `reveal_history()` |
| `src/system_monitor/ui/styles.py`                       | QSS theme, `color_for_percent`, and the runtime accent (`set_accent`/`normalize_accent`) |
| `src/system_monitor/ui/main_window.py`                  | Orchestrator: frameless window, widget tree, Qt events, drag-drop. Min size 380×600 |
| `src/system_monitor/ui/cards.py`                        | The single card registry — display name, widget attr, config key, `resolve_order()` |
| `src/system_monitor/ui/menus.py`                        | Context + settings menu construction; actions call `MainWindow` intent methods |
| `src/system_monitor/ui/appbar.py`                       | `AppBarController` — Windows AppBar edge reservation (one `APPBARDATA` struct, one implementation) |
| `src/system_monitor/ui/autostart.py`                     | Startup-shortcut create/remove, no Qt dependency |
| `src/system_monitor/ui/taskbar_media.py`                | Taskbar thumbnail media buttons; forwards clicks to `media.dispatch()` |
| `src/system_monitor/ui/widgets/_base.py`                | `_Card` QFrame base. Hover styling via `setProperty("hovered", bool)` + `unpolish()`/`polish()` |
| `src/system_monitor/ui/widgets/{cpu,ram,disk,net,gpu,media}_widget.py` | One card per metric. Each receives the full app snapshot in `update()` and extracts what it needs |
| `tests/test_smoke.py`                                    | Headless suite (31 tests). Run: `py -3.13 tests\test_smoke.py` |

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
  is available. Enrichment: NVML fills values first, then Windows PDH fills
  remaining gaps for any vendor. The `source` field is `nvml`, `pdh`,
  `nvml+pdh`, `dxgi`, or `unavailable`.
- **Disk IO rates are derived from cumulative `psutil.disk_io_counters`.**
  The collector keeps `prev["counters"]` between calls; deleting that state
  will silently break the read/write MB/s readout.
- **AMD / Intel GPU utilization and VRAM come from Windows PDH.** NVML is
  NVIDIA-only. PDH works for any vendor with no external software, so AMD and
  Intel adapters still get live util/VRAM out of the box.
- **`depcheck.ensure()` runs before `system_monitor` is imported** — it uses
  only stdlib so it can install missing packages (PySide6, psutil) before they
  are imported. Optional deps (nvidia-ml-py, wmi) get a one-line
  note and the app continues without them.
- **The PySide6 import errors you see in the LSP before installing deps are
  expected.** They resolve after `pip install -r requirements.txt` or running
  `.\run.bat`.
- **`_Card` hover effect** is implemented by setting a Qt dynamic property
  (`hovered` = true/false) and calling `style().unpolish()` / `style().polish()`
  to re-evaluate the QSS `[hovered="true"]` selector. Not a CSS `:hover` —
  unique to Qt's property system.
- **Never call a blocking API from a card's `update()`.** `update(snapshot)`
  runs on the 10 Hz repaint timer. `MediaCard` used to call `now_playing()`
  there, which blocks on the SMTC async call for up to 3s. Media is sampled by
  the collector and arrives as `snapshot["media"]`. The same applies to the
  tray, which reads `bridge.latest["media"]`.
- **`data/media.py` owns all media state.** Command ids (`CMD_PREV`/`CMD_PLAY`/
  `CMD_NEXT`) live there, and `ui/taskbar_media.py` forwards clicks to
  `media.dispatch()`. Do not add media logic to the UI layer. Session selection
  (`set_target`/`sessions`) and capability flags (`can_next`/`can_prev`/
  `can_play_pause`) are also its job — the UI must not assume a session
  supports skip. **Web browsers are excluded** by `is_media_player()`: they
  publish SMTC sessions for any page with a `<video>` and never support skip,
  so only dedicated players (Spotify, VLC, foobar, AIMP, …) are surfaced.
- **The `winrt-*` packages are per-API-contract and don't depend on each
  other.** Adding only `winrt-Windows.Media.Control` installs fine and then
  throws `ModuleNotFoundError: winrt.windows.foundation` at first use. Any new
  winrt import needs its sibling contract added to `requirements.txt` *and*
  `depcheck.OPTIONAL`, and should be verified by awaiting it, not importing it.
- **Settings writes must go through a `MainWindow` method that calls
  `_save_position()`.** Toggles used to write config inside menu lambdas and
  rely on a later save in the same tuple; per-drive visibility was never
  persisted because of it. `snapshot["health"]` is how sensor failures become
  visible — a card showing 0.0 is otherwise indistinguishable from a broken
  sensor.
- **`styles.ACCENT` is the compiled-in default, not the active color.** The
  runtime accent lives in `styles._current_accent`; set it with
  `styles.set_accent()`. `color_for_percent()` reads it, which is why cards
  don't need the accent passed in. `normalize_accent()` drops invalid values
  back to the default so a hand-edited config can't produce an unstyled panel.

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
              "always_on_top": true, "opacity": 1.0, "locked": false,
              "appbar": false, "dock_side": "" },
  "ui":     { "theme": "dark", "accent": "#00D4FF",
              "show_cpu": true, "show_gpu": true, "show_memory": true,
              "show_network": true, "show_now_playing": true,
              "show_disk_io": true, "show_swap": true,
              "hidden_drives": [] },
  "collector": { "interval_seconds": 1.0 }
}
```

`ui.card_order`, `ui.dock_screen`, `window.appbar_edge`, `window.autostart`,
`window._pre_appbar` and the top-level `detached` block are written at runtime
and merged on load. Do not hand-set `_pre_appbar`.

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
- **Position resets on every launch** — config save is wired to
  `aboutToQuit`. Task Manager kill won't persist it.
- **Black background, not translucent** — do not toggle
  `WA_TranslucentBackground` on. The look comes from QSS `rgba()` background
  and the OS window composer's blur.
- **Config defaults in README may be stale** — verify against
  `config.DEFAULTS` in `src/system_monitor/config.py`.

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **System-Monitor** (473 symbols, 991 relationships, 36 execution flows).

> Index stale? Run `node .gitnexus/run.cjs analyze --index-only` from the project root — it auto-selects an available runner. No `.gitnexus/run.cjs` yet? Bootstrap with `npx`, `bunx`, or `pnpm dlx` — e.g. `bunx gitnexus@latest analyze` (npm 11 npx crash; #1939).

## Always Do

- **MUST run impact before editing.** Use `impact({target: "symbolName", direction: "upstream"})` or `node .gitnexus/run.cjs impact "symbolName" --direction upstream --repo .`; report callers, processes, and risk. Never substitute grep for graph analysis.
- **MUST analyze graph changes before committing.** Use `detect_changes({scope: "all"})` (MCP) or `node .gitnexus/run.cjs detect-changes --scope all --repo .` (CLI fallback). `partial: true` or `truncated: true` is not a clean check — a zero means unseen, not unaffected; re-run it. For regression review: `detect_changes({scope: "compare", base_ref: "main"})` or `node .gitnexus/run.cjs detect-changes --scope compare --base-ref "main" --repo .`.
- MUST warn on HIGH/CRITICAL `risk` pre-edit; never use `riskSharedAxes` to waive a HIGH/CRITICAL `risk` warning. Compare File/symbol: MCP File omits axes; Graph-RAG expands File.
- **MUST treat `risk: UNKNOWN` as unresolved, not as low.** An empty caller set is not evidence the symbol is unused — it can also mean the callers are not resolvable by the index (plain-object property access, dynamic dispatch, cross-language calls). `impact` pairs `UNKNOWN` with a `riskNote` saying so. Confirm with a text search before treating the symbol as safe to change or delete; do not proceed on the strength of a zero.
- **MUST use `query({search_query: "concept"})` for concepts/flows, `context({name: "symbolName"})` for a named symbol, or `impact` for blast radius, on read-only callers, dependencies, imports, or execution flow.** Graph first; text search only for empty/`UNKNOWN`/literals.
- For security review, `explain({target: "fileOrSymbol"})` lists taint findings (source→sink flows; needs `analyze --pdg`).

## Never Do

- NEVER edit a function, class, or method before MCP/CLI impact analysis.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis, and never read `UNKNOWN` as an all-clear — it means the walk could not answer, which is the one verdict that requires confirming by other means.
- NEVER rename symbols with find-and-replace — use `rename` which understands the call graph.
- NEVER commit before MCP/CLI graph change analysis.

## Resources

| Resource | Use for |
| --- | --- |
| `gitnexus://repo/System-Monitor/context` | Codebase overview, check index freshness |
| `gitnexus://repo/System-Monitor/clusters` | All functional areas |
| `gitnexus://repo/System-Monitor/processes` | All execution flows |
| `gitnexus://repo/System-Monitor/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
| --- | --- |
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
