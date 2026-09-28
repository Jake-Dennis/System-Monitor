"""Headless smoke tests for System Monitor.

Run: .venv/Scripts/python.exe tests/test_smoke.py

Tests that don't need a display or window manager, covering:
- Data layer (CPU/memory/disk/network/GPU collectors)
- Config persistence
- SMTC media (with graceful fallback)
- Appbar registration math

Failures here indicate regressions in the data pipeline or config
that would otherwise only show up at runtime.
"""
import json
import os
import subprocess
import sys
import time
import tempfile
import unittest
from pathlib import Path

# Headless mode for Qt (must be set before any Qt import)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestConfig(unittest.TestCase):
    """Config load/save/merge behavior."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self._old_env = os.environ.get("SYSTEM_MONITOR_HOME")
        os.environ["SYSTEM_MONITOR_HOME"] = self.tmpdir

    def tearDown(self):
        if self._old_env is None:
            del os.environ["SYSTEM_MONITOR_HOME"]
        else:
            os.environ["SYSTEM_MONITOR_HOME"] = self._old_env

    def test_defaults_round_trip(self):
        from system_monitor import config as config_mod

        cfg = config_mod.load()
        self.assertEqual(cfg["window"]["width"], 380)
        self.assertEqual(cfg["window"]["height"], 980)
        self.assertTrue(cfg["ui"]["show_gpu"])

        # Save and reload
        cfg["window"]["x"] = 1234
        cfg["ui"]["theme"] = "light"
        config_mod.save(cfg)
        cfg2 = config_mod.load()
        self.assertEqual(cfg2["window"]["x"], 1234)
        self.assertEqual(cfg2["ui"]["theme"], "light")

    def test_deep_merge_preserves_keys(self):
        from system_monitor import config as config_mod

        # Write a partial config
        cfg_path = config_mod.config_path()
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text('{"ui": {"theme": "dark"}}')

        cfg = config_mod.load()
        # DEFAULTS preserved for keys not in user file
        self.assertIn("show_gpu", cfg["ui"])
        # User override preserved
        self.assertEqual(cfg["ui"]["theme"], "dark")


class TestMedia(unittest.TestCase):
    """SMTC media functions with graceful fallback."""

    def test_now_playing_returns_dict(self):
        from system_monitor.data.media import now_playing

        result = now_playing()
        self.assertIn("title", result)
        self.assertIn("artist", result)
        self.assertIn("status", result)
        self.assertIn("is_active", result)
        self.assertIsInstance(result["is_active"], bool)

    def test_control_calls_dont_raise(self):
        from system_monitor.data.media import play_pause, next_track, prev_track

        # Should not raise even when no media session is active
        for fn in (play_pause, next_track, prev_track):
            try:
                fn()
            except Exception as e:
                self.fail(f"{fn.__name__} raised: {e}")

    def test_dispatch_handles_every_command_id(self):
        """The taskbar toolbar dispatches by id; unknown ids must be ignored."""
        from system_monitor.data import media as media_mod

        for cmd_id in (media_mod.CMD_PREV, media_mod.CMD_PLAY, media_mod.CMD_NEXT):
            media_mod.dispatch(cmd_id)  # must not raise
        media_mod.dispatch(9999)  # unknown id, must be a no-op


class TestMediaSnapshotFlow(unittest.TestCase):
    """Media is sampled by the collector, not polled by the repaint timer.

    now_playing() blocks on the SMTC async call (3s timeout). MediaCard.update
    used to call it directly at 10Hz, and the tray did the same.
    """

    def setUp(self):
        from PySide6.QtWidgets import QApplication

        self.app = QApplication.instance() or QApplication([])

    def test_collector_includes_media_in_snapshot(self):
        from system_monitor.data.collector import Collector

        snap = Collector(interval=1.0)._collect_once()
        self.assertIn("media", snap)
        self.assertIn("is_active", snap["media"])
        self.assertIn("media", snap["health"])

    def test_media_card_reads_snapshot_not_live_api(self):
        from system_monitor.ui.widgets.media_widget import MediaCard

        card = MediaCard()
        card.update(
            {
                "media": {
                    "title": "Test Track",
                    "artist": "Test Artist",
                    "app_name": "Spotify",
                    "status": "playing",
                    "is_active": True,
                    "can_next": True,
                    "can_prev": True,
                    "can_play_pause": True,
                }
            }
        )
        self.assertEqual(card._track.text(), "Test Track")
        # Source line tells you which app the buttons are steering.
        self.assertIn("Spotify", card._source.text())
        self.assertIn("Test Artist", card._source.text())

    def test_media_card_tolerates_missing_media_key(self):
        from system_monitor.ui.widgets.media_widget import MediaCard

        card = MediaCard()
        card.update({})  # must not raise
        self.assertEqual(card._track.text(), "No media detected")

    def test_unsupported_skip_buttons_are_disabled(self):
        """A browser playing YouTube has no skip. The buttons must reflect
        that instead of silently doing nothing."""
        from system_monitor.ui.widgets.media_widget import MediaCard

        card = MediaCard()
        card.update(
            {
                "media": {
                    "title": "A Video",
                    "app_name": "Brave",
                    "status": "playing",
                    "is_active": True,
                    "can_next": False,
                    "can_prev": False,
                    "can_play_pause": True,
                }
            }
        )
        self.assertFalse(card._next_btn.isEnabled())
        self.assertFalse(card._prev_btn.isEnabled())
        self.assertTrue(card._play_btn.isEnabled())

    def test_supported_skip_buttons_stay_enabled(self):
        from system_monitor.ui.widgets.media_widget import MediaCard

        card = MediaCard()
        card.update(
            {
                "media": {
                    "title": "A Song",
                    "app_name": "Spotify",
                    "status": "playing",
                    "is_active": True,
                    "can_next": True,
                    "can_prev": True,
                    "can_play_pause": True,
                }
            }
        )
        self.assertTrue(card._next_btn.isEnabled())
        self.assertTrue(card._prev_btn.isEnabled())

    def test_no_media_disables_all_buttons(self):
        from system_monitor.ui.widgets.media_widget import MediaCard

        card = MediaCard()
        card.update({"media": {"is_active": False}})
        self.assertFalse(card._play_btn.isEnabled())
        self.assertFalse(card._next_btn.isEnabled())
        self.assertFalse(card._prev_btn.isEnabled())


class TestMediaSessionTargeting(unittest.TestCase):
    """Windows exposes one 'current' SMTC session, so the app must be able to
    choose which one it steers."""

    def test_friendly_app_names(self):
        from system_monitor.data.media import friendly_app

        self.assertEqual(friendly_app("Spotify.exe"), "Spotify")
        self.assertEqual(friendly_app("chrome.exe"), "Chrome")
        self.assertEqual(friendly_app("Brave"), "Brave")
        self.assertEqual(friendly_app("Microsoft.MSEdge_8wekyb3d8bbwe"), "Edge")
        self.assertEqual(friendly_app("C:\\apps\\firefox.exe"), "Firefox")
        self.assertEqual(friendly_app(""), "")

    def test_browsers_are_not_media_players(self):
        """Browsers publish SMTC sessions for any page with <video>, but they
        have no skip support and aren't media players."""
        from system_monitor.data.media import is_media_player

        for browser in (
            "chrome.exe",
            "Microsoft.MSEdge_8wekyb3d8bbwe",
            "firefox.exe",
            "Brave",
            "opera.exe",
            "vivaldi.exe",
            "msedgewebview2.exe",
        ):
            self.assertFalse(is_media_player(browser), f"{browser} should be excluded")

    def test_dedicated_players_are_media_players(self):
        from system_monitor.data.media import is_media_player

        for player in (
            "Spotify.exe",
            "vlc.exe",
            "C:\\Program Files\\foobar2000\\foobar2000.exe",
            "AIMP.exe",
            "MusicBee.exe",
            "wmplayer.exe",
        ):
            self.assertTrue(is_media_player(player), f"{player} should be included")

    def test_normalize_app_strips_wrappers(self):
        from system_monitor.data.media import normalize_app

        self.assertEqual(normalize_app("Spotify.exe"), "spotify")
        self.assertEqual(normalize_app("Microsoft.MSEdge_8wekyb3d8bbwe"), "msedge")
        self.assertEqual(normalize_app("C:\\x\\VLC.exe"), "vlc")
        self.assertEqual(normalize_app(""), "")

    def test_session_list_contains_no_browsers(self):
        """Whatever is actually running, browsers must not surface."""
        from system_monitor.data.media import is_media_player, sessions

        for entry in sessions():
            self.assertTrue(
                is_media_player(entry.get("app", "")),
                f"browser leaked into session list: {entry.get('app')}",
            )

    def test_now_playing_never_reports_a_browser(self):
        from system_monitor.data.media import is_media_player, now_playing

        result = now_playing()
        if result.get("is_active"):
            self.assertTrue(is_media_player(result.get("app", "")))

    def test_status_str_handles_enum_and_ordinal(self):
        from system_monitor.data.media import _status_str

        import enum

        class Fake(enum.Enum):
            PLAYING = "playing"

        self.assertEqual(_status_str(Fake.PLAYING), "playing")
        # Windows ordinals: 4 = PAUSED, 5 = PLAYING
        self.assertEqual(_status_str(4), "paused")
        self.assertEqual(_status_str(5), "playing")
        self.assertEqual(_status_str(None), "unknown")
        self.assertEqual(_status_str(999), "unknown")

    def test_set_target_and_clear(self):
        from system_monitor.data import media as media_mod

        # No-op-tolerant: works whether or not an SMTC session exists.
        media_mod.set_target("Spotify.exe")
        media_mod.set_target(None)
        self.assertIsNone(media_mod.target() or None)

    def test_sessions_returns_list_of_dicts(self):
        from system_monitor.data.media import sessions

        result = sessions()
        self.assertIsInstance(result, list)
        for entry in result:
            for key in ("app", "app_name", "title", "status",
                        "can_next", "can_prev", "can_play_pause"):
                self.assertIn(key, entry)

    def test_smtc_dependencies_are_declared(self):
        """Regression: requirements listed only winrt-Windows.Media.Control,
        but PyRT packages are per-contract, so a clean install raised
        ModuleNotFoundError: winrt.windows.foundation at first use."""
        req = (Path(__file__).parent.parent / "requirements.txt").read_text(
            encoding="utf-8"
        )
        for dist in (
            "winrt-Windows.Media.Control",
            "winrt-Windows.Foundation",
            "winrt-Windows.Foundation.Collections",
        ):
            self.assertIn(dist, req, f"{dist} missing from requirements.txt")


class TestCollectors(unittest.TestCase):
    """Data collectors produce valid snapshots."""

    def test_collector_produces_snapshot(self):
        from system_monitor.data.collector import Collector

        c = Collector(interval=1.0)
        # Prime - first call may be slow due to WMI init
        c._collect_once()
        # Second call should be fast and produce real data
        t0 = time.time()
        snap = c._collect_once()
        dt = time.time() - t0

        # Required keys
        self.assertIn("timestamp", snap)
        self.assertIn("cpu", snap)
        self.assertIn("memory", snap)
        self.assertIn("disks", snap)
        self.assertIn("network", snap)
        self.assertIn("gpus", snap)

        # CPU shape
        self.assertIn("percent", snap["cpu"])
        self.assertIn("per_core", snap["cpu"])

        # Network shape. net_widget iterates pernic with .items(), so a list
        # here would crash the card on the first repaint.
        self.assertIsInstance(snap["network"]["pernic"], dict)

        # Performance: should be fast
        self.assertLess(dt, 0.5, f"Snapshot took {dt*1000:.0f}ms")

    def test_disk_per_disk_data(self):
        from system_monitor.data.collector import Collector

        c = Collector(interval=1.0)
        snap = c._collect_once()
        per_disk = snap["disks"].get("per_disk", [])
        self.assertIsInstance(per_disk, list)
        for disk in per_disk:
            self.assertIn("label", disk)
            self.assertIn("io_percent", disk)
            self.assertIn("read_mb_s", disk)
            self.assertIn("write_mb_s", disk)


class TestGPU(unittest.TestCase):
    """GPU detection doesn't crash and produces valid output."""

    def test_gpu_snapshot(self):
        from system_monitor.data.gpu import GpuCollector

        g = GpuCollector()
        snap = g.snapshot()
        self.assertIsInstance(snap, list)
        # Each entry has required keys
        for gpu in snap:
            self.assertIn("name", gpu)
            self.assertIn("vendor", gpu)
            self.assertIn("util_percent", gpu)
            self.assertIn("mem_total_mb", gpu)

    def test_gpu_dxgi_enumerate(self):
        from system_monitor.data import dxgi

        adapters = dxgi.enumerate_adapters()
        self.assertIsInstance(adapters, list)
        for a in adapters:
            self.assertIn("name", a)
            self.assertIn("vendor", a)
            self.assertIn("vram_mb", a)

    def test_gpu_widget_update_does_not_crash(self):
        """Regression: set_gpu() previously called self._set_alert() which
        doesn't exist on _GpuRow (it's on _Card). The exception silently
        killed the update, leaving the GPU card empty/stale."""
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])

        from system_monitor.ui.widgets.gpu_widget import GpuCard
        card = GpuCard()
        snap = {"gpus": [{
            "name": "Test GPU", "vendor": "nvidia",
            "util_percent": 25.0, "mem_used_mb": 1000, "mem_total_mb": 8000,
            "mem_percent": 12.5, "power_w": 50.0, "fan_percent": 30.0,
            "source": "test",
        }]}
        # Should not raise
        card.update(snap)
        # VRAM bar should reflect the snapshot
        if card._rows:
            self.assertEqual(card._rows[0]._vram_bar.value(), 12)
            self.assertEqual(card._rows[0]._vram_pct.text(), "12%")


class TestDragDrop(unittest.TestCase):
    """Drag-and-drop wiring exists and doesn't crash."""

    def test_card_dropped_signal_exists(self):
        from PySide6.QtWidgets import QApplication
        from system_monitor.ui.widgets._base import _Card

        app = QApplication.instance() or QApplication([])
        c = _Card("Test")
        # card_title() is the public accessor for drag MIME
        self.assertEqual(c.card_title(), "Test")


class _QtTestCase(unittest.TestCase):
    """Base for tests that need a live QApplication and an isolated config."""

    def setUp(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        self.app = QApplication.instance() or QApplication([])
        self.tmpdir = tempfile.mkdtemp()
        self._old_env = os.environ.get("SYSTEM_MONITOR_HOME")
        os.environ["SYSTEM_MONITOR_HOME"] = self.tmpdir

    def tearDown(self):
        if self._old_env is None:
            del os.environ["SYSTEM_MONITOR_HOME"]
        else:
            os.environ["SYSTEM_MONITOR_HOME"] = self._old_env

    def _write_config(self, data: dict) -> None:
        from system_monitor import config as config_mod

        path = config_mod.config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")

    def _build_window(self, overrides: dict | None = None):
        """Construct a MainWindow over an isolated config."""
        from system_monitor import config as config_mod
        from system_monitor.ui.main_window import MainWindow

        cfg = config_mod.load()
        for section, values in (overrides or {}).items():
            cfg.setdefault(section, {}).update(values)
        return MainWindow(cfg), cfg


class TestSettingsPersistence(_QtTestCase):
    """Regression cover for settings that were silently lost across restarts.

    Commit 3bb97b2 fixed exactly these: toggles only wrote config on quit, so
    killing the app (or a crash) discarded them, and show_swap was never read
    back at startup.
    """

    def test_show_swap_toggle_saves_immediately(self):
        window, cfg = self._build_window()
        self.assertTrue(cfg["ui"]["show_swap"])

        window._toggle_show_swap()

        from system_monitor import config as config_mod

        reloaded = config_mod.load()
        self.assertFalse(
            reloaded["ui"]["show_swap"],
            "show_swap toggle must hit disk immediately, not only on quit",
        )

    def test_show_swap_restored_at_startup(self):
        self._write_config({"ui": {"show_swap": False}})
        window, _cfg = self._build_window()
        self.assertFalse(
            window._ram._show_swap,
            "show_swap=False in config must be applied to the RAM card on startup",
        )

    def test_show_gpu_toggle_saves_immediately(self):
        window, cfg = self._build_window()
        self.assertTrue(cfg["ui"]["show_gpu"])

        window._toggle_show_gpu()

        from system_monitor import config as config_mod

        self.assertFalse(config_mod.load()["ui"]["show_gpu"])
        self.assertTrue(window._gpu.isHidden(), "GPU card must be hidden, not just unshown")

    def test_card_visibility_toggle_saves_immediately(self):
        """The per-card 'Visible' action in the settings menu writes config."""
        window, _cfg = self._build_window()
        window._set_card_visible("CPU", False)

        from system_monitor import config as config_mod

        self.assertFalse(config_mod.load()["ui"]["show_cpu"])
        self.assertTrue(window._cpu.isHidden())

    def test_appbar_flag_is_not_forced_on(self):
        """Regression: __init__ used to hard-set window.appbar = True, which
        silently re-enabled the appbar for users who had turned it off."""
        window, cfg = self._build_window({"window": {"appbar": False}})
        self.assertFalse(
            cfg["window"]["appbar"],
            "loading a window with appbar disabled must not flip it back on",
        )

    def test_window_position_persisted_on_move(self):
        window, _cfg = self._build_window()
        # A window that was never shown does not emit moveEvent, so show it
        # first â€” otherwise this asserts nothing about the real app.
        window.show()
        self.app.processEvents()
        window.move(321, 234)
        self.app.processEvents()

        from system_monitor import config as config_mod

        reloaded = config_mod.load()
        self.assertEqual(reloaded["window"]["x"], 321)
        self.assertEqual(reloaded["window"]["y"], 234)


class TestAccentConfig(_QtTestCase):
    """ui.accent is a documented config key and must reach the stylesheet."""

    def test_accent_reaches_qss(self):
        from system_monitor.ui import styles

        sheet = styles.qss(1.0, theme="dark", accent="#FF00AA")
        self.assertIn("#FF00AA", sheet)
        self.assertNotIn(styles.ACCENT, sheet)

    def test_color_for_percent_uses_custom_accent(self):
        from system_monitor.ui import styles

        self.assertEqual(
            styles.color_for_percent(10.0, accent="#FF00AA"), "#FF00AA"
        )
        # Thresholds keep their own colors.
        self.assertEqual(styles.color_for_percent(95.0, accent="#FF00AA"), styles.CRIT)

    def test_toggle_accent_persists(self):
        window, _cfg = self._build_window()
        window._set_accent("#12AB34")

        from system_monitor import config as config_mod

        self.assertEqual(config_mod.load()["ui"]["accent"], "#12AB34")


class TestSingleInstance(_QtTestCase):
    """Two instances would clobber each other's config.json on exit."""

    _HOLDER = (
        "import sys, time\n"
        "from PySide6.QtCore import QLockFile\n"
        "lock = QLockFile(sys.argv[1])\n"
        "assert lock.tryLock(10000), 'holder could not acquire lock'\n"
        "print('locked', flush=True)\n"
        "time.sleep(60)\n"
    )

    def _spawn_holder(self, lock_path: Path):
        proc = subprocess.Popen(
            [sys.executable, "-c", self._HOLDER, str(lock_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        line = proc.stdout.readline().strip()
        self.assertEqual(line, "locked", "lock holder did not start")
        return proc

    def test_second_instance_exits_cleanly(self):
        from system_monitor import config as config_mod

        lock_path = config_mod.config_dir() / "app.lock"
        holder = self._spawn_holder(lock_path)
        try:
            env = dict(os.environ)
            env["SYSTEM_MONITOR_HOME"] = self.tmpdir
            env["QT_QPA_PLATFORM"] = "offscreen"
            src = str(Path(__file__).parent.parent / "src")
            proc = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "import sys; sys.path.insert(0, %r);"
                    "from system_monitor import app;"
                    "sys.exit(app.main(['test']))" % src,
                ],
                capture_output=True,
                text=True,
                timeout=60,
                env=env,
            )
        finally:
            holder.terminate()
            holder.wait(timeout=15)

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("already running", proc.stderr.lower())

    def test_lock_file_created_in_config_dir(self):
        """The guard must mkdir the config dir before locking, or first run
        on a clean machine fails with an unhelpful OSError."""
        from system_monitor.app import _acquire_instance_lock

        config_dir = Path(self.tmpdir) / "nested" / "fresh"
        self.assertFalse(config_dir.exists())
        lock = _acquire_instance_lock(config_dir, timeout_ms=0)
        self.assertIsNotNone(lock)
        self.assertTrue((config_dir / "app.lock").exists())


class TestIntervalConfig(_QtTestCase):
    """collector.interval_seconds is a documented key and must be settable."""

    def test_interval_clamped_to_sane_range(self):
        window, _cfg = self._build_window()
        window._set_interval(0.05)
        from system_monitor import config as config_mod

        self.assertGreaterEqual(config_mod.load()["collector"]["interval_seconds"], 0.25)

        window._set_interval(999.0)
        self.assertLessEqual(config_mod.load()["collector"]["interval_seconds"], 60.0)


class TestDiskIoVisibility(_QtTestCase):
    """ui.show_disk_io exists in DEFAULTS and must actually control the cards."""

    def test_disk_io_cards_hidden_when_disabled(self):
        window, _cfg = self._build_window({"ui": {"show_disk_io": False}})
        snap = {
            "disks": {
                "per_disk": [
                    {"label": "C:", "io_percent": 10.0, "read_mb_s": 1.0, "write_mb_s": 2.0}
                ]
            }
        }
        window._reconcile_disk_cards(snap)
        self.assertIn("C:", window._disk_cards)
        self.assertTrue(window._disk_cards["C:"].isHidden())

    def test_disk_io_cards_visible_when_enabled(self):
        window, _cfg = self._build_window({"ui": {"show_disk_io": True}})
        snap = {
            "disks": {
                "per_disk": [
                    {"label": "D:", "io_percent": 10.0, "read_mb_s": 1.0, "write_mb_s": 2.0}
                ]
            }
        }
        window._reconcile_disk_cards(snap)
        self.assertFalse(window._disk_cards["D:"].isHidden())


class TestSensorHealth(_QtTestCase):
    """A broken sensor must be visible, not silently read as zero."""

    def test_health_reports_ok_for_all_sensors(self):
        from system_monitor.data.collector import Collector

        snap = Collector(interval=1.0)._collect_once()
        self.assertIn("health", snap)
        for name in ("cpu", "memory", "disk", "network", "gpu"):
            self.assertEqual(snap["health"][name], "ok", f"{name} should be ok")

    def test_failing_sensor_degrades_only_its_own_section(self):
        from system_monitor.data.collector import Collector

        c = Collector(interval=1.0)

        def boom():
            raise RuntimeError("sensor exploded")

        c._cpu.snapshot = boom
        snap = c._collect_once()

        self.assertEqual(snap["health"]["cpu"], "error")
        self.assertEqual(snap["health"]["memory"], "ok")
        # Other sections still carry real data.
        self.assertIn("percent", snap["memory"])
        self.assertIn("pernic", snap["network"])

    def test_panel_subtitle_flags_failing_sensor(self):
        window, _cfg = self._build_window()
        window._header.set_subtitle("")

        window.apply_snapshot(
            {
                "timestamp": 0.0, "cpu": {}, "memory": {}, "disks": {"per_disk": []},
                "network": {"pernic": {}}, "gpus": [],
                "health": {"cpu": "error", "memory": "ok"},
            }
        )
        self.assertIn("cpu", window._header._subtitle.text())

        window.apply_snapshot(
            {
                "timestamp": 0.0, "cpu": {}, "memory": {}, "disks": {"per_disk": []},
                "network": {"pernic": {}}, "gpus": [],
                "health": {"cpu": "ok", "memory": "ok"},
            }
        )
        self.assertEqual(window._header._subtitle.text(), "")


class TestDockingGeometry(_QtTestCase):
    """Docking must be flush to the edge, with no gap and no taskbar overlap.

    Regression: register() derived the final position from the rect returned
    by ABM_QUERYPOS, which adjusts the cross-axis. For a left/right bar that is
    the vertical axis, so the panel kept whatever y it was dragged to (a gap
    above) and its bottom could land in the taskbar strip.
    """

    def _dock(self, side: str):
        from system_monitor.ui.appbar import AppBarController

        window, cfg = self._build_window()
        window.show()
        self.app.processEvents()
        ctl = AppBarController(window, cfg)
        # Deliberately park the window off-edge first: docking must ignore
        # where it was, not snap to it.
        window.move(120, 150)
        self.app.processEvents()
        self.assertTrue(ctl.dock_to_side(side, register_appbar=False))
        self.app.processEvents()
        return window, ctl

    def test_dock_left_is_flush_top_left(self):
        window, _ = self._dock("left")
        screen = self.app.primaryScreen()
        self.assertEqual(window.x(), screen.geometry().left())
        self.assertEqual(window.y(), screen.availableGeometry().top())

    def test_dock_right_is_flush_right_and_top(self):
        window, _ = self._dock("right")
        screen = self.app.primaryScreen()
        g = window.geometry()
        self.assertEqual(g.right(), screen.geometry().right())
        self.assertEqual(g.y(), screen.availableGeometry().top())

    def test_dock_top_is_flush_top_left(self):
        window, _ = self._dock("top")
        screen = self.app.primaryScreen()
        self.assertEqual(window.y(), screen.geometry().top())
        self.assertEqual(window.x(), screen.availableGeometry().left())

    def test_dock_bottom_stays_inside_work_area(self):
        window, _ = self._dock("bottom")
        screen = self.app.primaryScreen()
        g = window.geometry()
        self.assertEqual(g.bottom(), screen.availableGeometry().bottom())
        self.assertLessEqual(g.bottom(), screen.geometry().bottom())

    def test_docked_panel_never_exceeds_work_area(self):
        """A panel taller than the usable area must be clamped, not overflow
        into the taskbar."""
        from system_monitor.ui.appbar import AppBarController

        window, cfg = self._build_window({"window": {"height": 5000}})
        window.show()
        self.app.processEvents()
        AppBarController(window, cfg).dock_to_side("right", register_appbar=False)
        self.app.processEvents()
        self.assertLessEqual(window.height(), self.app.primaryScreen().availableGeometry().height())

    def test_unknown_side_is_rejected(self):
        from system_monitor.ui.appbar import AppBarController

        window, cfg = self._build_window()
        ctl = AppBarController(window, cfg)
        self.assertFalse(ctl.dock_to_side("diagonal", register_appbar=False))
        self.assertEqual(cfg["window"].get("dock_side", ""), "")

    def test_appbar_data_accepts_a_rect(self):
        """Regression: the APPBARDATA.rc field was declared as a c_long array
        while _Rect structs were assigned to it, so every registration raised
        TypeError and the edge was never actually reserved."""
        from system_monitor.ui.appbar import ABE_TOP, AppBarController, _Rect

        window, cfg = self._build_window()
        window.show()
        self.app.processEvents()
        ctl = AppBarController(window, cfg)
        abd, _byref = ctl._abd(ABE_TOP, _Rect(0, 0, 100, 200))
        self.assertEqual((abd.rc.left, abd.rc.top, abd.rc.right, abd.rc.bottom), (0, 0, 100, 200))
        # Named-field writes are what register() relies on after QUERYPOS.
        abd.rc.right = 640
        self.assertEqual(abd.rc.right, 640)

    def test_register_does_not_raise(self):
        """The whole point of register() is that it swallows shell errors —
        but a struct mismatch used to be swallowed too, silently."""
        from system_monitor.ui.appbar import ABE_RIGHT, AppBarController, _Rect

        window, cfg = self._build_window()
        window.show()
        self.app.processEvents()
        ctl = AppBarController(window, cfg)
        try:
            result = ctl.register(edge=ABE_RIGHT)
        except TypeError as exc:  # pragma: no cover - the regression itself
            self.fail(f"appbar registration raised a struct error: {exc}")
        self.assertIn(result, (True, False))
        ctl.unregister()


if __name__ == "__main__":
    unittest.main(verbosity=2)
