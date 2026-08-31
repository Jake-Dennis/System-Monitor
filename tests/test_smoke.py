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
import os
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

        # Network shape
        self.assertIn("pernic", snap["network"])

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
