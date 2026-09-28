"""Context and settings menu construction.

Menus were ~180 lines of MainWindow. The actions are thin, but they are
*data* (labels, check states, ordering), not behaviour, and keeping them here
means MainWindow only has to expose intent-level methods
(``_set_card_visible``, ``_set_interval``, ...) for the menus to call.

Every action here goes through a MainWindow method rather than poking config
directly. The previous version wrote ``config["ui"][key] = checked`` inside a
lambda and relied on a later ``_save_position()`` call in the same tuple —
which is how drive visibility ended up never being persisted at all.
"""
from __future__ import annotations

import logging
from typing import Any

from PySide6.QtGui import QAction

from . import cards

log = logging.getLogger(__name__)

# Preset accent colors offered in the settings menu.
ACCENT_PRESETS: list[tuple[str, str]] = [
    ("Cyan", "#00D4FF"),
    ("Green", "#4ADE80"),
    ("Amber", "#FFB454"),
    ("Pink", "#FF6B9D"),
    ("White", "#E6ECF5"),
]

# Preset sample intervals in seconds.
INTERVAL_PRESETS: list[tuple[str, float]] = [
    ("0.5s (smooth)", 0.5),
    ("1s (default)", 1.0),
    ("2s (low overhead)", 2.0),
    ("5s (minimal)", 5.0),
]


def _add_toggle(menu: Any, label: str, *, checked: bool, on_toggle) -> None:
    """Add a simple checkable action to the menu."""
    a = menu.addAction(label)
    a.setCheckable(True)
    a.setChecked(bool(checked))
    a.triggered.connect(on_toggle)


# ----- settings menu (gear button) -----


def build_settings_menu(win: Any, anchor: Any) -> None:
    """Build and exec the settings menu below `anchor`."""
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QMenu

    menu = QMenu(win)

    for name, attr, _cfg_key in cards.CARD_DEFS:
        _add_card_submenu(win, menu, name, attr)

    _add_drive_menu(win, menu)

    menu.addSeparator()
    _add_disk_io_toggle(win, menu)
    _add_toggle(
        menu,
        "Show swap",
        checked=win._config.get("ui", {}).get("show_swap", True),
        on_toggle=win._toggle_show_swap,
    )

    menu.addSeparator()
    _add_toggle(
        menu,
        "Lock position",
        checked=win._config.get("window", {}).get("locked", False),
        on_toggle=win._toggle_lock,
    )
    _add_toggle(
        menu,
        "Run at Windows startup",
        checked=win._config.get("window", {}).get("autostart", False),
        on_toggle=win._toggle_autostart,
    )
    _add_toggle(
        menu,
        "Light theme",
        checked=win._config.get("ui", {}).get("theme", "dark") == "light",
        on_toggle=win._toggle_theme,
    )
    _add_accent_menu(win, menu)

    menu.addSeparator()
    _add_interval_menu(win, menu)
    _add_dock_menu(win, menu)
    _add_screen_menu(win, menu)

    menu.addSeparator()
    history = menu.addAction("Open history folder")
    history.triggered.connect(win._open_history)
    menu.addAction("Reset position").triggered.connect(win._reset_position)

    menu.exec(anchor.mapToGlobal(QPoint(0, anchor.height())))


def _add_card_submenu(win: Any, menu: Any, name: str, attr: str) -> None:
    """Add a per-card submenu with visibility/detach/reorder."""
    card = getattr(win, attr, None)
    if card is None:
        return
    sub = menu.addMenu(name)

    vis_a = sub.addAction("Visible")
    vis_a.setCheckable(True)
    vis_a.setChecked(card.isVisible())
    vis_a.triggered.connect(lambda checked, n=name: win._set_card_visible(n, checked))

    if name in win._detached_windows:
        sub.addAction("Reattach").triggered.connect(lambda n=name: win._reattach_card(n))
    else:
        sub.addAction("Detach").triggered.connect(lambda n=name: win._detach_card(n))

    order = cards.resolve_order(win._config, list(win._disk_cards))
    idx = order.index(name) if name in order else -1
    if idx > 0:
        sub.addAction("Move up").triggered.connect(lambda n=name: win._move_card(n, -1))
    if idx >= 0 and idx < len(order) - 1:
        sub.addAction("Move down").triggered.connect(lambda n=name: win._move_card(n, 1))

    # GPU-specific per-adapter toggles
    if name == "GPU" and hasattr(card, "visible_gpu_list"):
        sub.addSeparator()
        for gpu_name in card.visible_gpu_list:
            ga = sub.addAction(gpu_name)
            ga.setCheckable(True)
            ga.setChecked(gpu_name not in card.hidden_gpus)
            ga.triggered.connect(
                lambda checked, cn=gpu_name: (
                    card.hidden_gpus.add(cn)
                    if not checked
                    else card.hidden_gpus.discard(cn)
                )
            )


def _add_drive_menu(win: Any, menu: Any) -> None:
    """Add per-disk-drive visibility submenu."""
    if not win._disk_cards:
        return
    disk_menu = menu.addMenu("Drives")
    for label in sorted(win._disk_cards):
        da = disk_menu.addAction(f"Drive {label}")
        da.setCheckable(True)
        da.setChecked(win._drive_visible(label))
        da.triggered.connect(
            lambda checked, lbl=label: win._set_drive_visible(lbl, checked)
        )


def _add_disk_io_toggle(win: Any, menu: Any) -> None:
    """Master switch for every per-disk card.

    This is the `ui.show_disk_io` key. It shipped in DEFAULTS from the start
    and nothing ever read it, so the setting was invisible to users.
    """
    _add_toggle(
        menu,
        "Show disk I/O",
        checked=win._config.get("ui", {}).get("show_disk_io", True),
        on_toggle=win._toggle_disk_io,
    )


def _add_accent_menu(win: Any, menu: Any) -> None:
    sub = menu.addMenu("Accent color")
    current = win._config.get("ui", {}).get("accent", "")
    for label, value in ACCENT_PRESETS:
        action = sub.addAction(label)
        action.setCheckable(True)
        action.setChecked(str(current).lower() == value.lower())
        action.triggered.connect(lambda _checked, v=value: win._set_accent(v))


def _add_interval_menu(win: Any, menu: Any) -> None:
    sub = menu.addMenu("Sample interval")
    current = float(win._config.get("collector", {}).get("interval_seconds", 1.0))
    for label, value in INTERVAL_PRESETS:
        action = sub.addAction(label)
        action.setCheckable(True)
        action.setChecked(abs(current - value) < 0.01)
        action.triggered.connect(lambda _checked, v=value: win._set_interval(v))


def _add_dock_menu(win: Any, menu: Any) -> None:
    dock_menu = menu.addMenu("Dock to edge")
    current = win._config.get("window", {}).get("dock_side", "")
    for side, label in [
        ("left", "Left"),
        ("right", "Right"),
        ("top", "Top"),
        ("bottom", "Bottom"),
    ]:
        da = dock_menu.addAction(label)
        da.setCheckable(True)
        da.setChecked(current == side)
        da.triggered.connect(
            lambda checked, s=side: (
                win._dock_to_side(s, register_appbar=True) if checked else None
            )
        )
    dock_menu.addSeparator()
    undock = dock_menu.addAction("Undock")
    undock.triggered.connect(win._toggle_appbar)


def _add_screen_menu(win: Any, menu: Any) -> None:
    from PySide6.QtGui import QGuiApplication

    screen_menu = menu.addMenu("Screen")
    current = win._config.get("window", {}).get("dock_screen", "")
    for i, sc in enumerate(QGuiApplication.screens()):
        name = sc.name() or f"Display {i + 1}"
        geo = sc.geometry()
        sa = screen_menu.addAction(f"{name}  ({geo.width()}x{geo.height()})")
        sa.setCheckable(True)
        sa.setChecked(current == name)
        sa.triggered.connect(lambda checked, n=name: win._set_screen(n) if checked else None)


# ----- context menu (right-click on the panel) -----


def build_context_menu(win: Any, global_pos: Any) -> None:
    from PySide6.QtWidgets import QMenu

    menu = QMenu(win)
    ui = win._config.get("ui", {})

    _add_toggle(
        menu, "Show GPU", checked=ui.get("show_gpu", True), on_toggle=win._toggle_show_gpu
    )
    _add_toggle(
        menu,
        "Show network",
        checked=ui.get("show_network", True),
        on_toggle=win._toggle_show_network,
    )
    _add_toggle(
        menu, "Show swap", checked=ui.get("show_swap", True), on_toggle=win._toggle_show_swap
    )
    _add_toggle(
        menu,
        "Show disk I/O",
        checked=ui.get("show_disk_io", True),
        on_toggle=win._toggle_disk_io,
    )

    menu.addSeparator()
    menu.addAction("Settings").triggered.connect(win._open_settings_menu_at_center)
    menu.addAction("Reset position").triggered.connect(win._reset_position)

    quit_act = QAction("Quit", menu)
    quit_act.triggered.connect(win.close)
    menu.addAction(quit_act)

    menu.exec(global_pos)
