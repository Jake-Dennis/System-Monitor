"""Main panel window: frameless, translucent, draggable, always-on-top."""
from __future__ import annotations

import ctypes
import logging
import os
import sys
from pathlib import Path
from typing import Any
from PySide6.QtCore import QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QCloseEvent, QContextMenuEvent, QIcon, QMouseEvent, QMoveEvent, QResizeEvent

# Windows API types for nativeEvent
try:
    from ctypes.wintypes import MSG, UINT, WPARAM
except ImportError:
    MSG = UINT = WPARAM = None

from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QProgressBar,
    QPushButton,
    QSizeGrip,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from . import styles
from .widgets.cpu_widget import CpuCard
from .widgets.disk_widget import DiskCard
from .widgets.gpu_widget import GpuCard
from .widgets.media_widget import MediaCard
from .widgets.net_widget import NetCard
from .widgets.ram_widget import RamCard
from .taskbar_media import ID_NEXT, ID_PLAY, ID_PREV, THBN_CLICKED, TaskbarMediaController


# Ordered list of (name, attr, config_key) for card management
_CARD_DEFS = [
    ("CPU", "_cpu", "show_cpu"),
    ("Memory", "_ram", "show_memory"),
    ("GPU", "_gpu", "show_gpu"),
    ("Network", "_net", "show_network"),
    ("Disk", "_disk", "show_disk"),
    ("Now Playing", "_media", "show_now_playing"),
]


class DetachedWindow(QMainWindow):
    """A small frameless window hosting one detached card."""

    reattach = Signal(object)  # emits the card widget to reattach

    def __init__(self, card: QWidget, title: str) -> None:
        super().__init__()
        self._card = card
        self._drag_pos: QPoint | None = None
        self.setWindowTitle(title)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setMinimumSize(QSize(360, 200))

        root = QWidget()
        root.setObjectName("PanelRoot")
        outer = QVBoxLayout(root)
        outer.setContentsMargins(12, 8, 12, 12)
        outer.setSpacing(6)

        # Draggable header with title and reattach button
        self._header = QWidget()
        self._header.setObjectName("PanelHeader")
        self._header.setFixedHeight(34)
        hdr = QHBoxLayout(self._header)
        hdr.setContentsMargins(12, 0, 8, 0)
        lbl = QLabel(title)
        lbl.setObjectName("HeaderTitle")
        hdr.addWidget(lbl)
        hdr.addStretch(1)
        attach_btn = QPushButton("\u2935")  # ⤵
        attach_btn.setObjectName("IconButton")
        attach_btn.setToolTip("Reattach to main panel")
        attach_btn.clicked.connect(lambda: self._do_reattach())
        hdr.addWidget(attach_btn)
        outer.addWidget(self._header)
        outer.addWidget(card, 1)
        card.setVisible(True)

        # Size grip
        grip = QSizeGrip(self)
        grip.setStyleSheet(
            "QSizeGrip { width: 12px; height: 12px; "
            "background: rgba(255,255,255,30); border-radius: 4px; }"
        )
        outer.addWidget(grip, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)

        self.setCentralWidget(root)
        # Apply the same dark styles
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            self.setStyleSheet(app.styleSheet())

    def _do_reattach(self) -> None:
        self.reattach.emit(self._card)
        self.close()

    def closeEvent(self, event: QCloseEvent) -> None:  # type: ignore[override]
        self.reattach.emit(self._card)
        super().closeEvent(event)

    # drag-to-move
    def mousePressEvent(self, e: QMouseEvent) -> None:  # type: ignore[override]
        if e.button() == Qt.MouseButton.LeftButton and e.position().y() <= self._header.height():
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            e.accept()

    def mouseMoveEvent(self, e: QMouseEvent) -> None:  # type: ignore[override]
        if self._drag_pos is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_pos)
            e.accept()

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:  # type: ignore[override]
        self._drag_pos = None


log = logging.getLogger(__name__)


def _card_attr(name: str) -> str:
    """Return the attribute name for a card by display name."""
    for n, attr, _ in _CARD_DEFS:
        if n == name:
            return attr
    return ""


class PanelHeader(QFrame):
    """The draggable header strip with title, lock, and close buttons."""

    toggle_lock_clicked = Signal()
    close_clicked = Signal()
    settings_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Header")
        self.setFixedHeight(34)
        h = QHBoxLayout(self)
        h.setContentsMargins(12, 0, 8, 0)
        h.setSpacing(6)

        self._title = QLabel("SYSTEM MONITOR")
        self._title.setObjectName("HeaderTitle")
        h.addWidget(self._title)

        self._subtitle = QLabel("")
        self._subtitle.setObjectName("HeaderSub")
        h.addSpacing(8)
        h.addWidget(self._subtitle)
        h.addStretch(1)

        self._lock = QPushButton("\U0001F513")
        self._lock.setObjectName("IconButton")
        self._lock.setToolTip("Toggle drag-lock (L)")
        self._lock.clicked.connect(self.toggle_lock_clicked)
        h.addWidget(self._lock)

        self._settings = QPushButton("\u2699")
        self._settings.setObjectName("IconButton")
        self._settings.setToolTip("Settings")
        self._settings.clicked.connect(self.settings_clicked)
        h.addWidget(self._settings)

        self._close = QPushButton("\u2715")
        self._close.setObjectName("IconButton")
        self._close.setToolTip("Close (Esc)")
        self._close.clicked.connect(self.close_clicked)
        h.addWidget(self._close)

        self._drag_pos: QPoint | None = None
        self._locked = False
        self.set_locked(False)

    def set_subtitle(self, text: str) -> None:
        self._subtitle.setText(text)

    def set_locked(self, locked: bool) -> None:
        self._locked = bool(locked)
        self._lock.setText("\U0001F512" if self._locked else "\U0001F513")

    # drag-to-move
    def mousePressEvent(self, e: QMouseEvent) -> None:  # type: ignore[override]
        if self._locked:
            return
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
            e.accept()

    def mouseMoveEvent(self, e: QMouseEvent) -> None:  # type: ignore[override]
        if self._drag_pos is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self.window().move(e.globalPosition().toPoint() - self._drag_pos)
            e.accept()

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:  # type: ignore[override]
        self._drag_pos = None


class MainWindow(QMainWindow):
    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__()
        self._config = config
        self._scale = 1.0
        self._detached_windows: dict[str, DetachedWindow] = {}
        self.setWindowTitle("System Monitor")
        self.setObjectName("PanelRoot")
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if self._config.get("window", {}).get("always_on_top", True):
            flags = flags | Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self._apply_size()
        self._build_ui()
        self._restore_position()
        self._install_shortcuts()
        if self._config.get("window", {}).get("dock_side"):
            QTimer.singleShot(200, lambda: self._dock_to_side(
                self._config["window"]["dock_side"], register_appbar=True
            ))

    # ----- public API -----

    def apply_snapshot(self, snap: dict[str, Any]) -> None:
        """Hand a new system snapshot to every card. Cheap enough to call
        from the Qt main thread at the collector's tick rate."""
        if not snap:
            return
        self._cpu.update(snap)
        self._ram.update(snap)
        self._disk.update(snap)
        self._net.update(snap)
        self._media.update(snap)
        if self._config.get("ui", {}).get("show_gpu", True):
            self._gpu.update(snap)
        # Update detached cards too
        for name, dw in list(self._detached_windows.items()):
            card = getattr(self, _card_attr(name), None)
            if card is not None:
                card.update(snap)

    def closeEvent(self, event: QCloseEvent) -> None:  # type: ignore[override]
        self._save_detached_state()
        self._save_position()
        if self._taskbar_media is not None:
            self._taskbar_media.cleanup()
        # Minimize to tray instead of closing
        self.hide()
        event.ignore()

    def resizeEvent(self, event: QResizeEvent) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._apply_scale()

    # ----- scaling -----

    def nativeEvent(self, event_type, message):  # type: ignore[override]
        """Handle Windows messages for taskbar thumbnail button clicks."""
        try:
            if event_type in (b"windows_generic_MSG", "windows_generic_MSG"):
                # message may be an int (address) or a ctypes struct
                msg_ptr = int(message)
                msg_id = UINT.from_address(msg_ptr + 8).value if UINT is not None else 0
                if msg_id == 0x0111:  # WM_COMMAND
                    wparam = WPARAM.from_address(msg_ptr + 12).value if WPARAM is not None else 0
                    if (wparam >> 16) == THBN_CLICKED:
                        cmd_id = wparam & 0xFFFF
                        if self._taskbar_media is not None:
                            self._taskbar_media.handle_click(cmd_id)
                        return True, 0
        except Exception:
            pass
        return super().nativeEvent(event_type, message)

    def _apply_scale(self) -> None:
        """Re-scale fonts and fixed widget sizes to match window width."""
        # Guard: UI must be built before we can scale it.
        if not hasattr(self, "_header"):
            return

        from PySide6.QtWidgets import QApplication

        new_scale = max(0.6, min(2.0, self.width() / 480.0))
        if abs(new_scale - self._scale) < 0.01:
            return
        old_scale = self._scale
        self._scale = new_scale
        scale = new_scale

        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(styles.qss(scale))

        self._header.setFixedHeight(round(34 * scale))

        for child in self.findChildren(QProgressBar):
            base_h = round(child.height() / old_scale)
            child.setFixedHeight(max(3, round(base_h * scale)))

        for child in self.findChildren(QLabel):
            obj = child.objectName()
            if obj == "CardTitle":
                base_w = max(20, round(child.width() / old_scale))
                child.setFixedWidth(round(base_w * scale))
            elif obj == "ValueSmall":
                base_w = max(20, round(child.width() / old_scale))
                child.setFixedWidth(round(base_w * scale))

        from .widgets._timeline import Timeline
        for child in self.findChildren(Timeline):
            child.set_scale(scale)

        outer = self.centralWidget().layout()
        if outer:
            outer.setSpacing(max(4, round(10 * scale)))
            outer.setContentsMargins(*[round(m * scale) for m in (12, 12, 12, 12)])

        from .widgets._timeline import Timeline
        for child in self.findChildren(Timeline):
            child.set_scale(scale)

    # ----- detach / reattach -----

    def _detach_card(self, name: str, geometry: tuple[int, int, int, int] | None = None) -> None:
        """Pop a card out into its own floating window."""
        if name in self._detached_windows:
            return
        attr = _card_attr(name)
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

        if geometry:
            dw = DetachedWindow(card, name)
            dw.reattach.connect(lambda n=name: self._reattach_card(n))
            dw.setGeometry(*geometry)
            dw.show()
        else:
            dw = DetachedWindow(card, name)
            dw.reattach.connect(lambda n=name: self._reattach_card(n))
            dw.setGeometry(self.x() + 40, self.y() + 40, 420, 500)
            dw.show()
        self._detached_windows[name] = dw

    def _reattach_card(self, name: str) -> None:
        """Bring a detached card back into the main panel."""
        dw = self._detached_windows.pop(name, None)
        if dw is not None:
            dw.deleteLater()
        attr = _card_attr(name)
        if not attr:
            return
        card = getattr(self, attr, None)
        if card is None:
            return

        layout = self.centralWidget().layout()
        if layout is None:
            return
        # Find insertion index: after header, before the grip
        idx = 1  # after the header (index 0)
        for n, a, _ in _CARD_DEFS:
            if n == name:
                break
            c = getattr(self, a, None)
            if c is not None and c.isVisible() and n not in self._detached_windows:
                idx += 1
        layout.insertWidget(idx, card, 1)
        card.setVisible(True)

    def _save_detached_state(self) -> None:
        """Save which cards are detached and their positions."""
        detached_cfg = {}
        for name, dw in self._detached_windows.items():
            geo = dw.frameGeometry()
            detached_cfg[name] = {
                "x": int(geo.x()),
                "y": int(geo.y()),
                "width": int(geo.width()),
                "height": int(geo.height()),
            }
        self._config["detached"] = detached_cfg

    def _restore_detached_state(self) -> None:
        """Recreate detached windows from saved config."""
        detached_cfg = self._config.get("detached", {})
        if not detached_cfg:
            return
        for name, geo in detached_cfg.items():
            g = (geo["x"], geo["y"], geo["width"], geo["height"])
            self._detach_card(name, geometry=g)

    # ----- settings menu -----

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("PanelRoot")
        outer = QVBoxLayout(root)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        self._header = PanelHeader()
        self._header.toggle_lock_clicked.connect(self._toggle_lock)
        self._header.close_clicked.connect(self.close)
        self._header.settings_clicked.connect(self._open_settings_menu)
        # Sync initial lock state from config.
        self._header.set_locked(
            bool(self._config.get("window", {}).get("locked", False))
        )
        outer.addWidget(self._header)

        self._cpu = CpuCard()
        self._ram = RamCard()
        self._disk = DiskCard()
        self._net = NetCard()
        self._gpu = GpuCard()
        self._media = MediaCard()

        # Wire drag-and-drop reordering
        for name, attr, _ in _CARD_DEFS:
            card = getattr(self, attr, None)
            if card is not None:
                card.card_dropped.connect(self._on_card_dropped)

        # Apply saved card order, falling back to _CARD_DEFS order.
        order = self._config.get("ui", {}).get("card_order")
        if not order:
            order = [n for n, _, _ in _CARD_DEFS]
        for name in order:
            card = getattr(self, _card_attr(name), None)
            if card is not None:
                outer.addWidget(card, 1)

        # Restore visibility from config for all cards.
        for name, attr, cfg_key in _CARD_DEFS:
            if not self._config.get("ui", {}).get(cfg_key, True):
                card = getattr(self, attr, None)
                if card is not None:
                    card.hide()

        # Taskbar thumbnail toolbar (Windows media controls).
        try:
            self._taskbar_media = TaskbarMediaController(int(self.winId()))
            self._taskbar_media.setup()
        except Exception:
            self._taskbar_media = None

        # Resize grip at bottom-right
        grip = QSizeGrip(self)
        grip.setStyleSheet(
            "QSizeGrip { width: 12px; height: 12px; "
            "background: rgba(255,255,255,30); "
            "border-radius: 4px; margin: 0px; }"
        )
        grip.setToolTip("Drag to resize")
        outer.addWidget(grip, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)

        self.setCentralWidget(root)

        # Scale to match the initial window size.
        self._apply_scale()
        self.setMinimumSize(QSize(380, 600))

        # Restore any detached windows from last session.
        self._restore_detached_state()

    def _restore_position(self) -> None:
        win = self._config.get("window", {})
        x = win.get("x")
        y = win.get("y")
        if x is not None and y is not None:
            self.move(int(x), int(y))
        else:
            from PySide6.QtWidgets import QApplication

            screen = QApplication.primaryScreen()
            if screen is not None:
                geo = screen.availableGeometry()
                self.move(geo.right() - self.width() - 24, geo.top() + 48)

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
        w = int(win.get("width", 480))
        h = int(win.get("height", 980))
        self.resize(w, h)

    def apply_always_on_top(self, on_top: bool) -> None:
        flags = self.windowFlags()
        if on_top:
            flags = flags | Qt.WindowType.WindowStaysOnTopHint
        else:
            flags = flags & ~Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()

    def apply_opacity(self, opacity: float) -> None:
        self.setWindowOpacity(max(0.3, min(1.0, float(opacity))))

    def _toggle_lock(self) -> None:
        win = self._config.setdefault("window", {})
        win["locked"] = not bool(win.get("locked", False))
        self._header.set_locked(bool(win["locked"]))

    def _install_shortcuts(self) -> None:
        from PySide6.QtGui import QKeySequence, QShortcut

        sc = QShortcut(QKeySequence("L"), self)
        sc.activated.connect(self._toggle_lock)
        sc = QShortcut(QKeySequence("T"), self)
        sc.activated.connect(self._toggle_always_on_top)
        sc = QShortcut(QKeySequence("Ctrl+Q"), self)
        sc.activated.connect(self.close)

    def _toggle_always_on_top(self) -> None:
        win = self._config.setdefault("window", {})
        win["always_on_top"] = not bool(win.get("always_on_top", True))
        self.apply_always_on_top(bool(win["always_on_top"]))

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:  # type: ignore[override]
        menu = QMenu(self)
        aot = QAction("Always on top", self, checkable=True)
        aot.setChecked(bool(self._config.get("window", {}).get("always_on_top", True)))
        aot.triggered.connect(self._toggle_always_on_top)
        menu.addAction(aot)

        show_gpu = QAction("Show GPU", self, checkable=True)
        show_gpu.setChecked(bool(self._config.get("ui", {}).get("show_gpu", True)))
        show_gpu.triggered.connect(self._toggle_show_gpu)
        menu.addAction(show_gpu)

        show_net = QAction("Show network", self, checkable=True)
        show_net.setChecked(bool(self._config.get("ui", {}).get("show_network", True)))
        show_net.triggered.connect(self._toggle_show_network)
        menu.addAction(show_net)

        show_swap = QAction("Show swap", self, checkable=True)
        show_swap.setChecked(bool(self._config.get("ui", {}).get("show_swap", True)))
        show_swap.triggered.connect(self._toggle_show_swap)
        menu.addAction(show_swap)

        menu.addSeparator()
        reset = QAction("Reset position", self)
        reset.triggered.connect(self._reset_position)
        menu.addAction(reset)

        quit_act = QAction("Quit", self)
        quit_act.triggered.connect(self.close)
        menu.addAction(quit_act)

        menu.exec(event.globalPos())

    def _reset_position(self) -> None:
        from PySide6.QtWidgets import QApplication

        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        self.move(geo.right() - self.width() - 24, geo.top() + 48)
        self._config.setdefault("window", {})["x"] = self.x()
        self._config.setdefault("window", {})["y"] = self.y()

    def _dock_to_side(self, side: str, register_appbar: bool = False) -> None:
        """Snap window to a screen edge. Optionally register as appbar."""
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtCore import QPoint

        screens = QGuiApplication.screens()
        preferred = self._config.get("window", {}).get("dock_screen", "")
        geo = screens[0].geometry()
        if preferred:
            for s in screens:
                if s.name() == preferred:
                    geo = s.geometry()
                    break
        else:
            center = self.mapToGlobal(QPoint(self.width() // 2, self.height() // 2))
            for s in screens:
                sg = s.geometry()
                if sg.contains(center):
                    geo = sg
                    break

        w = self.width()
        if side == "left":
            self.setGeometry(geo.left(), geo.top(), w, geo.height())
        elif side == "right":
            self.setGeometry(geo.right() - w, geo.top(), w, geo.height())
        elif side == "top":
            self.setGeometry(geo.left(), geo.top(), geo.width(), self.height())
        elif side == "bottom":
            self.setGeometry(geo.left(), geo.bottom() - self.height(), geo.width(), self.height())
        self._config.setdefault("window", {})["dock_side"] = side
        self._save_position()

        # Register as appbar using the correct negotiate-then-commit pattern
        if register_appbar:
            from ctypes import wintypes, byref, sizeof, windll

            class APPBARDATA(ctypes.Structure):
                _fields_ = [
                    ("cbSize", wintypes.DWORD),
                    ("hWnd", wintypes.HWND),
                    ("uCallbackMessage", wintypes.UINT),
                    ("uEdge", wintypes.UINT),
                    ("rc", wintypes.RECT),
                    ("lParam", wintypes.LPARAM),
                ]

            try:
                shell32 = windll.shell32
                user32 = windll.user32
                hwnd = wintypes.HWND(int(self.winId()))
                geom = self.frameGeometry()

                # Map side name to ABE constant
                edge_map = {"left": 0, "top": 1, "right": 2, "bottom": 3}
                edge = edge_map[side]

                # 1. ABM_NEW - register
                abd = APPBARDATA()
                abd.cbSize = sizeof(APPBARDATA)
                abd.hWnd = hwnd
                abd.uCallbackMessage = 0
                shell32.SHAppBarMessage(0, byref(abd))  # ABM_NEW

                # 2. Build RECT using absolute virtual screen coordinates
                abd.uEdge = edge
                thickness_w = geom.width() if edge in (0, 2) else 0
                thickness_h = geom.height() if edge in (1, 3) else 0
                if edge == 0:   # LEFT
                    abd.rc = wintypes.RECT(geo.left(), geo.top(), 
                        geo.left() + thickness_w, geo.bottom())
                elif edge == 2:  # RIGHT
                    abd.rc = wintypes.RECT(geo.right() - thickness_w, geo.top(), 
                        geo.right(), geo.bottom())
                elif edge == 1:  # TOP
                    abd.rc = wintypes.RECT(geo.left(), geo.top(), 
                        geo.right(), geo.top() + thickness_h)
                else:            # BOTTOM
                    abd.rc = wintypes.RECT(geo.left(), geo.bottom() - thickness_h, 
                        geo.right(), geo.bottom())

                # 3. ABM_QUERYPOS - negotiate with shell
                shell32.SHAppBarMessage(2, byref(abd))  # ABM_QUERYPOS

                # 4. Re-apply thickness (QUERYPOS only adjusts perpendicular axis)
                tw = geom.width() if edge in (0, 2) else 0
                th = geom.height() if edge in (1, 3) else 0
                if edge == 0:
                    abd.rc.right = abd.rc.left + tw
                elif edge == 2:
                    abd.rc.left = abd.rc.right - tw
                elif edge == 1:
                    abd.rc.bottom = abd.rc.top + th
                else:
                    abd.rc.top = abd.rc.bottom - th

                # 5. ABM_SETPOS - commit the rect
                shell32.SHAppBarMessage(3, byref(abd))  # ABM_SETPOS

                # 6. MoveWindow to the approved position
                user32.SetWindowPos(
                    hwnd, 0,
                    abd.rc.left, abd.rc.top,
                    abd.rc.right - abd.rc.left,
                    abd.rc.bottom - abd.rc.top,
                    0x0004,  # SWP_NOZORDER | SWP_NOACTIVATE
                )
            except Exception:
                pass

    def _on_card_dropped(self, dragged: str, target: str) -> None:
        """Handle a card drag-and-drop: move `dragged` before `target`."""
        ui = self._config.setdefault("ui", {})
        order = ui.get("card_order")
        if not order:
            order = [n for n, _, _ in _CARD_DEFS]
        if dragged not in order or target not in order:
            return
        order.remove(dragged)
        idx = order.index(target)
        order.insert(idx, dragged)
        ui["card_order"] = order

        outer = self.centralWidget().layout()
        if outer is None:
            return
        cards_in_layout = set()
        for i in range(outer.count() - 1, -1, -1):
            item = outer.itemAt(i)
            w = item.widget() if item is not None else None
            if w is not None and w is not self._header and not isinstance(w, QSizeGrip):
                outer.removeWidget(w)
                cards_in_layout.add(w)
        for n in order:
            card = getattr(self, _card_attr(n), None)
            if card is not None and card in cards_in_layout:
                outer.addWidget(card, 1)
        self._save_position()

    def _move_card(self, name: str, direction: int) -> None:
        """Move a card up (-1) or down (+1) in the layout order."""
        ui = self._config.setdefault("ui", {})
        order = ui.get("card_order")
        if not order:
            order = [n for n, _, _ in _CARD_DEFS]
        idx = order.index(name)
        new_idx = idx + direction
        if new_idx < 0 or new_idx >= len(order):
            return
        order.insert(new_idx, order.pop(idx))
        ui["card_order"] = order

        outer = self.centralWidget().layout()
        if outer is None:
            return
        # Collect cards currently in the layout
        cards_in_layout = set()
        for i in range(outer.count() - 1, -1, -1):
            item = outer.itemAt(i)
            w = item.widget() if item is not None else None
            if w is not None and w is not self._header and not isinstance(w, QSizeGrip):
                outer.removeWidget(w)
                cards_in_layout.add(w)
        # Re-add in new order
        for n in order:
            card = getattr(self, _card_attr(n), None)
            if card is not None and card in cards_in_layout:
                outer.addWidget(card, 1)
        self._config.setdefault("window", {})["needs_save"] = True

    def _open_settings_menu(self) -> None:
        """Show a menu to toggle each card's visibility and detach."""
        btn = self.sender()
        if btn is None:
            return
        from PySide6.QtCore import QPoint
        from PySide6.QtWidgets import QMenu

        menu = QMenu(self)

        for name, attr, cfg_key in _CARD_DEFS:
            card = getattr(self, attr, None)
            if card is None:
                continue
            sub = menu.addMenu(name)
            vis_a = sub.addAction("Visible")
            vis_a.setCheckable(True)
            vis_a.setChecked(card.isVisible())
            vis_a.triggered.connect(
                lambda checked, n=name, c=card: (
                    c.setVisible(checked),
                    c.setVisible(checked) or self._config.setdefault("ui", {}).__setitem__(
                        f"show_{n.lower().replace(' ', '_')}", checked
                    ),
                )
            )

            if name in self._detached_windows:
                detach_a = sub.addAction("Reattach")
                detach_a.triggered.connect(lambda: self._reattach_card(name))
            else:
                detach_a = sub.addAction("Detach")
                detach_a.triggered.connect(lambda: self._detach_card(name))

            # Reorder controls
            order = self._config.get("ui", {}).get("card_order") or [n for n, _, _ in _CARD_DEFS]
            idx = order.index(name) if name in order else -1
            if idx > 0:
                up_a = sub.addAction("Move up")
                up_a.triggered.connect(lambda n=name: self._move_card(n, -1))
            if idx >= 0 and idx < len(order) - 1:
                down_a = sub.addAction("Move down")
                down_a.triggered.connect(lambda n=name: self._move_card(n, 1))

            # Per-item toggles for GPU and Disk cards
            if name == "GPU" and hasattr(card, "visible_gpu_list"):
                sub.addSeparator()
                for gpu_name in card.visible_gpu_list:
                    ga = sub.addAction(gpu_name)
                    ga.setCheckable(True)
                    ga.setChecked(gpu_name not in card.hidden_gpus)
                    ga.triggered.connect(
                        lambda checked, cn=gpu_name: (
                            card.hidden_gpus.add(cn) if not checked else card.hidden_gpus.discard(cn)
                        )
                    )
            if name == "Disk" and hasattr(card, "visible_disk_list"):
                sub.addSeparator()
                for disk_label in card.visible_disk_list:
                    da = sub.addAction(f"Drive {disk_label}")
                    da.setCheckable(True)
                    da.setChecked(disk_label not in card.hidden_disks)
                    da.triggered.connect(
                        lambda checked, dl=disk_label: (
                            card.hidden_disks.add(dl) if not checked else card.hidden_disks.discard(dl)
                        )
                    )

        menu.addSeparator()
        swap_a = menu.addAction("Show swap")
        swap_a.setCheckable(True)
        swap_a.setChecked(bool(self._config.get("ui", {}).get("show_swap", True)))
        swap_a.triggered.connect(self._toggle_show_swap)
        menu.addSeparator()
        lock_a = menu.addAction("Lock position (L)")
        lock_a.setCheckable(True)
        lock_a.setChecked(bool(self._config.get("window", {}).get("locked", False)))
        lock_a.triggered.connect(self._toggle_lock)

        menu.addSeparator()
        aot_a = menu.addAction("Always on top")
        aot_a.setCheckable(True)
        aot_a.setChecked(bool(self._config.get("window", {}).get("always_on_top", True)))
        aot_a.triggered.connect(self._toggle_always_on_top)

        autostart_a = menu.addAction("Run at Windows startup")
        autostart_a.setCheckable(True)
        autostart_a.setChecked(self._config.get("window", {}).get("autostart", False))
        autostart_a.triggered.connect(self._toggle_autostart)

        menu.addSeparator()

        dock_menu = menu.addMenu("Dock to edge")
        for side, label in [("left", "Left"), ("right", "Right"), ("top", "Top"), ("bottom", "Bottom")]:
            da = dock_menu.addAction(label)
            da.setCheckable(True)
            da.setChecked(self._config.get("window", {}).get("dock_side", "") == side)
            da.triggered.connect(lambda checked, s=side: self._dock_to_side(s, register_appbar=True))

        screen_menu = menu.addMenu("Screen")
        from PySide6.QtGui import QGuiApplication
        for i, sc in enumerate(QGuiApplication.screens()):
            name = sc.name() or f"Display {i + 1}"
            geo = sc.geometry()
            label = f"{name}  ({geo.width()}x{geo.height()})"
            sa = screen_menu.addAction(label)
            sa.setCheckable(True)
            sa.setChecked(self._config.get("window", {}).get("dock_screen", "") == name)
            sa.triggered.connect(lambda checked, n=name: (
                self._config.setdefault("window", {}) .__setitem__("dock_screen", n),
                self._save_position(),
                self._dock_to_side(self._config.get("window", {}).get("dock_side", ""), register_appbar=True)
                if self._config.get("window", {}).get("dock_side") else None,
            ))

        global_pos = btn.mapToGlobal(QPoint(0, btn.height()))
        menu.exec(global_pos)

    def _toggle_show_gpu(self) -> None:
        cfg = self._config.setdefault("ui", {})
        cfg["show_gpu"] = not bool(cfg.get("show_gpu", True))
        self._gpu.setVisible(bool(cfg["show_gpu"]))

    def _toggle_show_network(self) -> None:
        cfg = self._config.setdefault("ui", {})
        cfg["show_network"] = not bool(cfg.get("show_network", True))
        self._net.setVisible(bool(cfg["show_network"]))

    def _toggle_show_swap(self) -> None:
        cfg = self._config.setdefault("ui", {})
        cfg["show_swap"] = not bool(cfg.get("show_swap", True))
        self._ram.set_show_swap(bool(cfg["show_swap"]))

    def _toggle_autostart(self) -> None:
        on = not self._config.get("window", {}).get("autostart", False)
        self._config.setdefault("window", {})["autostart"] = on
        startup = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        link = startup / "System Monitor.lnk"
        if on:
            target = Path(sys.executable).resolve()
            args = f'"{Path.cwd() / "run.py"}"'
            icon = target  # use pythonw.exe icon
            try:
                import pythoncom
                from win32com.client import Dispatch

                pythoncom.CoInitialize()
                shell = Dispatch("WScript.Shell")
                shortcut = shell.CreateShortCut(str(link))
                shortcut.TargetPath = str(target)
                shortcut.Arguments = args
                shortcut.WorkingDirectory = str(Path.cwd())
                shortcut.IconLocation = str(target)
                shortcut.Save()
            except Exception:
                pass
        else:
            try:
                link.unlink(missing_ok=True)
            except Exception:
                pass
        self._save_position()

