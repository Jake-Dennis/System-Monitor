"""Main panel window: frameless, draggable, always-on-top.

This class is the orchestrator. Everything that used to live here as a large
blob now sits in a focused module:

- ``ui/cards.py``     — card registry (names, config keys, ordering)
- ``ui/menus.py``     — context + settings menu construction
- ``ui/appbar.py``    — Windows AppBar edge reservation (ctypes)
- ``ui/autostart.py`` — run-at-startup shortcut
- ``ui/chrome.py``    — header, detached window, drag indicator
- ``ui/styles.py``    — QSS theme, accent color

What stays here is the thing that genuinely needs to be one object: the
widget tree, Qt event handling, and the state that ties cards to config.
"""
from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QCloseEvent,
    QContextMenuEvent,
    QMouseEvent,
    QMoveEvent,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QProgressBar,
    QSizeGrip,
    QVBoxLayout,
    QWidget,
)

# Windows API types for nativeEvent
try:
    from ctypes.wintypes import UINT, WPARAM
except ImportError:  # pragma: no cover - non-Windows
    UINT = WPARAM = None

from . import autostart, cards, menus, styles
from .appbar import AppBarController
from .chrome import DetachedWindow, DropIndicator, PanelHeader
from .widgets._base import _Card
from .widgets.cpu_widget import CpuCard
from .widgets.disk_widget import SingleDiskCard
from .widgets.gpu_widget import GpuCard
from .widgets.media_widget import MediaCard
from .widgets.net_widget import NetCard
from .widgets.ram_widget import RamCard
from .taskbar_media import THBN_CLICKED, TaskbarMediaController

log = logging.getLogger(__name__)

# Sampling interval bounds, seconds. Below 0.25 the collector spins and the
# panel costs more CPU than it reports; above 60 the timeline is useless.
MIN_INTERVAL = 0.25
MAX_INTERVAL = 60.0


class MainWindow(QMainWindow):
    """The always-on-top metrics panel."""

    # Emitted when the user picks a different sample interval, so app.py can
    # retune the live collector without a restart.
    interval_changed = Signal(float)

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__()
        self._config = config
        self._scale = 1.0
        self._detached_windows: dict[str, DetachedWindow] = {}
        self._disk_cards: dict[str, SingleDiskCard] = {}
        self._taskbar_media: TaskbarMediaController | None = None

        # Apply the configured accent before any widget is styled.
        styles.set_accent(self._config.get("ui", {}).get("accent", styles.ACCENT))

        # Do NOT force appbar on here. The old code did
        # `config["window"]["appbar"] = True` unconditionally, which silently
        # re-enabled the appbar for anyone who had turned it off.
        self._config.setdefault("window", {}).setdefault("appbar", False)
        self._appbar = AppBarController(self, self._config)
        self._appbar.active = bool(self._config["window"].get("appbar", False))

        self.setWindowTitle("System Monitor")
        self.setObjectName("PanelRoot")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self._apply_size()
        self._build_ui()
        self._install_shortcuts()

        from .drag_manager import CardDragManager

        self._drag_mgr = CardDragManager()
        self._drag_mgr.card_dropped.connect(self._on_card_dropped)
        self._drag_mgr.set_locked(bool(self._config.get("window", {}).get("locked", False)))
        # Position and dock are applied after show() via timer — move()
        # before show() gets overridden by the window manager.
        QTimer.singleShot(0, self._init_position)

    # ----- snapshot fan-out -----

    def apply_snapshot(self, snap: dict[str, Any]) -> None:
        """Hand a new system snapshot to every card."""
        if not snap:
            return
        self._cpu.update(snap)
        self._ram.update(snap)
        self._reconcile_disk_cards(snap)
        self._net.update(snap)
        self._media.update(snap)
        if self._config.get("ui", {}).get("show_gpu", True):
            self._gpu.update(snap)
        self._update_detached_cards(snap)
        self._update_health_subtitle(snap.get("health"))

    def _update_health_subtitle(self, health: dict[str, str] | None) -> None:
        """Show which sensors are failing, so a broken reading is not
        mistaken for an idle one. Clears as soon as everything recovers."""
        if not health or not hasattr(self, "_header"):
            return
        failed = sorted(name for name, state in health.items() if state != "ok")
        self._header.set_subtitle(f"⚠ {', '.join(failed)}" if failed else "")

    def _update_detached_cards(self, snap: dict[str, Any]) -> None:
        """Detached cards live in their own windows, so they miss fan-out.

        A detached disk card has to be fed from the snapshot's per-disk entry
        by label. The previous version read `_io_percent` off the
        DetachedWindow, which does not define it, so detaching a drive raised
        AttributeError on every repaint.
        """
        per_disk = {
            d.get("label"): d
            for d in (snap.get("disks", {}).get("per_disk") or [])
            if d.get("label")
        }
        for name in list(self._detached_windows):
            disk_card = self._disk_cards.get(name)
            if disk_card is not None:
                d = per_disk.get(name) or {}
                disk_card.set_disk(
                    io_percent=float(d.get("io_percent", 0.0)),
                    read_mb_s=float(d.get("read_mb_s", 0.0)),
                    write_mb_s=float(d.get("write_mb_s", 0.0)),
                )
                continue
            card = getattr(self, cards.card_attr(name), None)
            if card is not None:
                card.update(snap)

    def _card_for_name(self, name: str) -> QWidget | None:
        """Look up a card widget by display name — handles both static
        registry cards and dynamic disk cards."""
        attr = cards.card_attr(name)
        if attr:
            return getattr(self, attr, None)
        return self._disk_cards.get(name)

    def _reconcile_disk_cards(self, snap: dict[str, Any]) -> None:
        """Create/remove SingleDiskCard widgets as drives change."""
        disk = snap.get("disks", {})
        per_disk: list[dict] = disk.get("per_disk", []) or []
        current_labels = {d.get("label", "") for d in per_disk if d.get("label")}
        outer = self.centralWidget().layout()
        if outer is None:
            return

        order = cards.resolve_order(self._config, list(self._disk_cards))
        self._config.setdefault("ui", {})["card_order"] = order

        # Remove cards for drives that no longer exist
        for label in list(self._disk_cards):
            if label not in current_labels:
                card = self._disk_cards.pop(label)
                outer.removeWidget(card)
                card.hide()
                card.deleteLater()
                if label in order:
                    order.remove(label)

        show_io = bool(self._config.get("ui", {}).get("show_disk_io", True))
        for d in per_disk:
            label = d.get("label", "")
            if not label:
                continue
            if label not in self._disk_cards:
                card = SingleDiskCard(label)
                self._disk_cards[label] = card
                card.setVisible(show_io and self._drive_visible(label))
                if label in order:
                    layout_idx = 1  # after header
                    for name in order[: order.index(label)]:
                        if name in self._disk_cards or cards.card_attr(name):
                            layout_idx += 1
                    outer.insertWidget(layout_idx, card, 1)
                else:
                    order.append(label)
                    media_card = self._card_for_name("Now Playing")
                    if media_card is not None:
                        outer.insertWidget(outer.indexOf(media_card), card, 1)
                    else:
                        outer.addWidget(card, 1)
            else:
                card = self._disk_cards[label]
                card.set_disk(
                    io_percent=float(d.get("io_percent", 0.0)),
                    read_mb_s=float(d.get("read_mb_s", 0.0)),
                    write_mb_s=float(d.get("write_mb_s", 0.0)),
                )

    # ----- Qt events -----

    def closeEvent(self, event: QCloseEvent) -> None:  # type: ignore[override]
        self._save_detached_state()
        self._save_position()
        if self._taskbar_media is not None:
            self._taskbar_media.cleanup()
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            app.quit()

    def resizeEvent(self, event: QResizeEvent) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._apply_scale()
        self._save_position()

    def moveEvent(self, event: QMoveEvent) -> None:  # type: ignore[override]
        super().moveEvent(event)
        self._save_position()

    def nativeEvent(self, event_type, message):  # type: ignore[override]
        """Handle Windows messages for taskbar thumbnail button clicks."""
        try:
            if event_type in (b"windows_generic_MSG", b"windows_generic_MSG"):
                msg_ptr = int(message)
                msg_id = UINT.from_address(msg_ptr + 8).value if UINT is not None else 0
                if msg_id == 0x0111:  # WM_COMMAND
                    wparam = WPARAM.from_address(msg_ptr + 12).value if WPARAM is not None else 0
                    if (wparam >> 16) == THBN_CLICKED:
                        if self._taskbar_media is not None:
                            self._taskbar_media.handle_click(wparam & 0xFFFF)
                        return True, 0
        except Exception:
            log.debug("nativeEvent handling failed", exc_info=True)
        return super().nativeEvent(event_type, message)

    def _apply_scale(self) -> None:
        """Re-scale fonts and fixed widget sizes to match window width."""
        if not hasattr(self, "_header"):
            return  # UI not built yet

        from PySide6.QtWidgets import QApplication

        new_scale = max(0.6, min(2.0, self.width() / 480.0))
        if abs(new_scale - self._scale) < 0.01:
            return
        old_scale = self._scale
        self._scale = new_scale
        scale = new_scale

        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(
                styles.qss(
                    scale,
                    theme=self._config.get("ui", {}).get("theme", "dark"),
                    accent=styles.current_accent(),
                )
            )

        self._header.setFixedHeight(round(34 * scale))

        for child in self.findChildren(QProgressBar):
            base_h = round(child.height() / old_scale)
            child.setFixedHeight(max(3, round(base_h * scale)))

        for child in self.findChildren(QLabel):
            if child.objectName() in ("CardTitle", "ValueSmall"):
                base_w = max(20, round(child.width() / old_scale))
                child.setFixedWidth(round(base_w * scale))

        from .widgets._timeline import Timeline

        for child in self.findChildren(Timeline):
            child.set_scale(scale)

        outer = self.centralWidget().layout()
        if outer:
            outer.setSpacing(max(4, round(10 * scale)))
            outer.setContentsMargins(*[round(m * scale) for m in (12, 12, 12, 12)])

    # ----- build -----

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("PanelRoot")
        root.setAcceptDrops(True)
        root.dragEnterEvent = self._container_drag_enter  # type: ignore[assignment]
        root.dragMoveEvent = self._container_drag_move  # type: ignore[assignment]
        root.dragLeaveEvent = self._container_drag_leave  # type: ignore[assignment]
        root.dropEvent = self._container_drop  # type: ignore[assignment]
        outer = QVBoxLayout(root)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        self._header = PanelHeader()
        self._header.toggle_lock_clicked.connect(self._toggle_lock)
        self._header.close_clicked.connect(self.close)
        self._header.settings_clicked.connect(self._open_settings_menu)
        self._header.set_locked(
            bool(self._config.get("window", {}).get("locked", False))
        )
        outer.addWidget(self._header)

        self._cpu = CpuCard()
        self._ram = RamCard()
        self._net = NetCard()
        self._gpu = GpuCard()
        self._media = MediaCard()

        for name in cards.resolve_order(self._config):
            card = self._card_for_name(name)
            if card is not None:
                outer.addWidget(card, 1)

        # Restore visibility from config for all cards.
        ui = self._config.get("ui", {})
        for name, attr, cfg_key in cards.CARD_DEFS:
            if not ui.get(cfg_key, True):
                card = getattr(self, attr, None)
                if card is not None:
                    card.hide()

        self._ram.set_show_swap(bool(ui.get("show_swap", True)))

        try:
            self._taskbar_media = TaskbarMediaController(int(self.winId()))
            self._taskbar_media.setup()
        except Exception:
            log.debug("taskbar media unavailable", exc_info=True)
            self._taskbar_media = None

        self._drop_indicator = DropIndicator()
        outer.addWidget(self._drop_indicator)

        self.setCentralWidget(root)
        self._apply_scale()
        self.setMinimumSize(QSize(380, 600))

        grip = QSizeGrip(root)
        grip.setStyleSheet(
            "QSizeGrip { width: 12px; height: 12px; "
            "background: rgba(255,255,255,30); "
            "border-radius: 4px; margin: 0px; }"
        )
        grip.setToolTip("Drag to resize")
        outer.addWidget(grip, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)

        self._restore_detached_state()

    def _init_position(self) -> None:
        """Restore last position and optionally dock. Runs via QTimer after
        show() so the window manager doesn't override move()."""
        from PySide6.QtWidgets import QApplication

        win = self._config.get("window", {})
        x = win.get("x")
        y = win.get("y")
        if x is not None and y is not None:
            self.move(int(x), int(y))
        else:
            screen = QApplication.primaryScreen()
            if screen is not None:
                geo = screen.availableGeometry()
                self.move(geo.right() - self.width() - 24, geo.top() + 48)
        dock_side = win.get("dock_side")
        if dock_side:
            QTimer.singleShot(
                100, lambda: self._dock_to_side(dock_side, register_appbar=True)
            )

    def _save_position(self) -> None:
        geo = self.frameGeometry()
        cfg = self._config.setdefault("window", {})
        cfg["x"] = int(geo.x())
        cfg["y"] = int(geo.y())
        cfg["width"] = int(geo.width())
        cfg["height"] = int(geo.height())
        from ..config import save as save_config

        save_config(self._config)

    def _apply_size(self) -> None:
        win = self._config.get("window", {})
        self.resize(int(win.get("width", 480)), int(win.get("height", 980)))

    def apply_opacity(self, opacity: float) -> None:
        self.setWindowOpacity(max(0.3, min(1.0, float(opacity))))

    def _reset_position(self) -> None:
        from PySide6.QtWidgets import QApplication

        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        self.move(geo.right() - self.width() - 24, geo.top() + 48)
        self._save_position()

    def _install_shortcuts(self) -> None:
        from PySide6.QtGui import QKeySequence, QShortcut

        sc = QShortcut(QKeySequence("Ctrl+Q"), self)
        sc.activated.connect(self.close)

    # ----- detach / reattach -----

    def _detach_card(self, name: str, geometry: tuple[int, int, int, int] | None = None) -> None:
        """Pop a card out into its own floating window."""
        if name in self._detached_windows:
            return
        attr = cards.card_attr(name)
        if not attr:
            return
        card = getattr(self, attr, None)
        if card is None:
            return
        layout = self.centralWidget().layout()
        if layout is None:
            return
        layout.removeWidget(card)
        card.setParent(None)
        card.setVisible(False)

        dw = DetachedWindow(card, name)
        dw.reattach.connect(lambda n=name: self._reattach_card(n))
        if geometry:
            dw.setGeometry(*geometry)
        else:
            dw.setGeometry(self.x() + 40, self.y() + 40, 420, 500)
        dw.show()
        self._detached_windows[name] = dw

    def _reattach_card(self, name: str) -> None:
        """Bring a detached card back into the main panel."""
        dw = self._detached_windows.pop(name, None)
        if dw is not None:
            dw.deleteLater()
        attr = cards.card_attr(name)
        if not attr:
            return
        card = getattr(self, attr, None)
        if card is None:
            return
        layout = self.centralWidget().layout()
        if layout is None:
            return
        idx = 1  # after the header (index 0)
        for n, a, _ in cards.CARD_DEFS:
            if n == name:
                break
            c = getattr(self, a, None)
            if c is not None and c.isVisible() and n not in self._detached_windows:
                idx += 1
        layout.insertWidget(idx, card, 1)
        card.setVisible(True)

    def _save_detached_state(self) -> None:
        """Save which cards are detached and their positions."""
        detached: dict[str, dict[str, int]] = {}
        for name, dw in self._detached_windows.items():
            geo = dw.frameGeometry()
            detached[name] = {
                "x": int(geo.x()),
                "y": int(geo.y()),
                "width": int(geo.width()),
                "height": int(geo.height()),
            }
        self._config["detached"] = detached

    def _restore_detached_state(self) -> None:
        """Recreate detached windows from saved config."""
        for name, geo in (self._config.get("detached") or {}).items():
            if not cards.card_attr(name):
                continue
            self._detach_card(
                name, geometry=(geo["x"], geo["y"], geo["width"], geo["height"])
            )

    # ----- settings: visibility -----

    def _set_card_visible(self, name: str, visible: bool) -> None:
        """Show/hide a card and persist it immediately."""
        key = cards.card_config_key(name)
        if not key:
            return
        self._config.setdefault("ui", {})[key] = bool(visible)
        card = self._card_for_name(name)
        if card is not None:
            card.setVisible(bool(visible))
        self._save_position()

    def _drive_visible(self, label: str) -> bool:
        """Per-drive visibility, honoring the master disk I/O switch."""
        if not bool(self._config.get("ui", {}).get("show_disk_io", True)):
            return False
        hidden = self._config.get("ui", {}).get("hidden_drives") or []
        return label not in hidden

    def _set_drive_visible(self, label: str, visible: bool) -> None:
        ui = self._config.setdefault("ui", {})
        hidden = [d for d in (ui.get("hidden_drives") or []) if d != label]
        if not visible:
            hidden.append(label)
        ui["hidden_drives"] = hidden
        card = self._disk_cards.get(label)
        if card is not None:
            card.setVisible(
                bool(visible) and bool(ui.get("show_disk_io", True))
            )
        self._save_position()

    def _toggle_disk_io(self) -> None:
        ui = self._config.setdefault("ui", {})
        on = not bool(ui.get("show_disk_io", True))
        ui["show_disk_io"] = on
        for label, card in self._disk_cards.items():
            card.setVisible(on and label not in (ui.get("hidden_drives") or []))
        self._save_position()

    def _toggle_show_gpu(self) -> None:
        current = bool(self._config.get("ui", {}).get("show_gpu", True))
        self._set_card_visible("GPU", not current)

    def _toggle_show_network(self) -> None:
        cfg = self._config.setdefault("ui", {})
        cfg["show_network"] = not bool(cfg.get("show_network", True))
        self._net.setVisible(bool(cfg["show_network"]))
        self._save_position()

    def _toggle_show_swap(self) -> None:
        cfg = self._config.setdefault("ui", {})
        cfg["show_swap"] = not bool(cfg.get("show_swap", True))
        self._ram.set_show_swap(bool(cfg["show_swap"]))
        self._save_position()

    def _toggle_lock(self) -> None:
        win = self._config.setdefault("window", {})
        win["locked"] = not bool(win.get("locked", False))
        self._header.set_locked(bool(win["locked"]))
        self._drag_mgr.set_locked(bool(win["locked"]))
        self._save_position()

    # ----- settings: appearance -----

    def _set_accent(self, value: str) -> None:
        """Set the accent color, persist it, and restyle live."""
        applied = styles.set_accent(value)
        self._config.setdefault("ui", {})["accent"] = applied
        self._restyle()
        self._save_position()

    def _toggle_theme(self) -> None:
        ui = self._config.setdefault("ui", {})
        ui["theme"] = "light" if ui.get("theme", "dark") == "dark" else "dark"
        self._restyle()
        self._save_position()

    def _restyle(self) -> None:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(
                styles.qss(
                    self._scale,
                    theme=self._config.get("ui", {}).get("theme", "dark"),
                    accent=styles.current_accent(),
                )
            )
        self._drop_indicator.update()

    def _set_interval(self, seconds: float) -> None:
        """Change the sample interval, clamped to a sane range."""
        value = max(MIN_INTERVAL, min(MAX_INTERVAL, float(seconds)))
        self._config.setdefault("collector", {})["interval_seconds"] = value
        self._save_position()
        self.interval_changed.emit(value)

    def _toggle_autostart(self) -> None:
        on = not bool(self._config.get("window", {}).get("autostart", False))
        achieved = autostart.set_enabled(on)
        self._config.setdefault("window", {})["autostart"] = achieved
        self._save_position()
        if achieved != on:
            log.warning("autostart toggle did not take effect (wanted %s)", on)

    def _open_history(self) -> None:
        from ..history import reveal_history

        reveal_history()

    def _set_screen(self, name: str) -> None:
        self._config.setdefault("window", {})["dock_screen"] = name
        dock_side = self._config.get("window", {}).get("dock_side", "")
        if dock_side:
            self._dock_to_side(dock_side, register_appbar=True)
        else:
            self._save_position()

    # ----- dock / appbar -----

    def _dock_to_side(self, side: str, register_appbar: bool = False) -> None:
        self._appbar.dock_to_side(side, register_appbar=register_appbar)
        self._save_position()

    def _toggle_appbar(self) -> None:
        self._appbar.toggle()
        self._save_position()

    @property
    def _appbar_active(self) -> bool:
        return self._appbar.active

    # ----- menus -----

    def _open_settings_menu(self) -> None:
        btn = self.sender()
        if btn is None:
            return
        menus.build_settings_menu(self, btn)

    def _open_settings_menu_at_center(self) -> None:
        """Open the settings menu from the context menu (no button anchor)."""
        menus.build_settings_menu(self, self._header)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:  # type: ignore[override]
        menus.build_context_menu(self, event.globalPos())

    # ----- drag and drop -----

    def _on_card_dropped(self, dragged_name: str, target_name: str, target_idx: int) -> None:
        """Handle a card drag-and-drop: move dragged to target position."""
        ui = self._config.setdefault("ui", {})
        order = cards.resolve_order(self._config, list(self._disk_cards))
        if dragged_name not in order:
            return
        order.remove(dragged_name)
        new_idx = order.index(target_name) if target_name in order else len(order)
        order.insert(new_idx, dragged_name)
        ui["card_order"] = order

        outer = self.centralWidget().layout()
        if outer is not None:
            dragged_card = self._card_for_name(dragged_name)
            if dragged_card is not None:
                outer.insertWidget(target_idx, dragged_card)
        self._save_position()

    def _move_card(self, name: str, direction: int) -> None:
        """Move a card up (-1) or down (+1) via context menu."""
        ui = self._config.setdefault("ui", {})
        order = cards.resolve_order(self._config, list(self._disk_cards))
        if name not in order:
            return
        new_idx = order.index(name) + direction
        if new_idx < 0 or new_idx >= len(order):
            return
        order.insert(new_idx, order.pop(order.index(name)))
        ui["card_order"] = order

        outer = self.centralWidget().layout()
        if outer is not None:
            card = self._card_for_name(name)
            if card is not None:
                outer.insertWidget(new_idx, card)
        self._save_position()

    def _container_drag_enter(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()
            self._show_drop_indicator(event)

    def _container_drag_move(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()
            self._move_drop_indicator(event)

    def _container_drag_leave(self, event):
        self._hide_drop_indicator()

    def _container_drop(self, event):
        self._hide_drop_indicator()
        outer = self.centralWidget().layout()
        if outer is None:
            return
        target_idx = self._find_drop_index(event.position().toPoint())
        self._drag_mgr.card_dropped.emit(
            event.mimeData().text(), self._name_at_layout_index(target_idx) or "", target_idx
        )
        event.acceptProposedAction()

    def _find_drop_index(self, pos: QPoint) -> int:
        outer = self.centralWidget().layout()
        if outer is None:
            return 0
        for i in range(outer.count()):
            item = outer.itemAt(i)
            w = item.widget() if item is not None else None
            if w is None or w is self._drop_indicator or not w.isVisible():
                continue
            if pos.y() < w.y() + w.height() // 2:
                return i
        return outer.count()

    def _name_at_layout_index(self, idx: int) -> str | None:
        outer = self.centralWidget().layout()
        if outer is None:
            return None
        item = outer.itemAt(idx)
        w = item.widget() if item is not None else None
        if isinstance(w, _Card):
            return w.card_title()
        return None

    def _show_drop_indicator(self, event):
        self._move_drop_indicator(event)
        self._drop_indicator.show()

    def _move_drop_indicator(self, event):
        outer = self.centralWidget().layout()
        if outer is not None:
            outer.insertWidget(self._find_drop_index(event.position().toPoint()), self._drop_indicator)

    def _hide_drop_indicator(self):
        self._drop_indicator.hide()
