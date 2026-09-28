"""Windows AppBar registration: reserve a screen edge so maximized windows
avoid the panel.

This was ~200 lines of MainWindow, including the same ``APPBARDATA`` ctypes
struct declared three separate times (once per method) and two independent
copies of the negotiate-then-commit dance. It is now one struct and one
implementation.

The shell contract is fiddly and worth stating once:

1. ``ABM_NEW``      — register, with a real callback message id
2. build the RECT in *absolute virtual screen* coordinates
3. ``ABM_QUERYPOS`` — ask the shell where it will actually put us
4. re-apply our thickness, because QUERYPOS only fixes the perpendicular axis
5. ``ABM_SETPOS``   — commit
6. ``SetWindowPos`` — put ourselves back at our original size, because
   ``ABM_SETPOS`` stretches the window to the full edge
"""
from __future__ import annotations

import ctypes
import logging
from typing import Any

log = logging.getLogger(__name__)

ABM_NEW = 0x00000000
ABM_REMOVE = 0x00000001
ABM_QUERYPOS = 0x00000002
ABM_SETPOS = 0x00000003

ABE_LEFT = 0
ABE_TOP = 1
ABE_RIGHT = 2
ABE_BOTTOM = 3

EDGE_BY_SIDE = {"left": ABE_LEFT, "top": ABE_TOP, "right": ABE_RIGHT, "bottom": ABE_BOTTOM}


class _Rect(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class _AppBarData(ctypes.Structure):
    # `rc` must be a RECT struct, not a bare array: we assign `_Rect`
    # instances to it, and ctypes rejects an array field getting a struct.
    # (It failed at runtime for every registration until this matched.)
    _fields_ = [
        ("cbSize", ctypes.c_uint32),
        ("hWnd", ctypes.c_void_p),
        ("uCallbackMessage", ctypes.c_uint),
        ("uEdge", ctypes.c_uint),
        ("rc", _Rect),
        ("lParam", ctypes.c_ssize_t),
    ]


class AppBarController:
    """Owns the AppBar registration state for one window."""

    def __init__(self, window: Any, config: dict[str, Any]) -> None:
        self._win = window
        self._config = config
        self.active = False

    # -- internals --

    def _abd(self, edge: int, rc: _Rect) -> tuple[_AppBarData, Any]:
        """Build an APPBARDATA for `edge`; also returns ctypes.byref."""
        from ctypes import byref, sizeof, windll

        abd = _AppBarData()
        abd.cbSize = sizeof(_AppBarData)
        abd.hWnd = int(self._win.winId())
        abd.uCallbackMessage = windll.user32.RegisterWindowMessageW("SM_AppBarNotify")
        abd.uEdge = edge
        abd.rc = rc
        return abd, byref

    def _screens(self) -> list:
        try:
            from PySide6.QtGui import QGuiApplication

            return list(QGuiApplication.screens())
        except Exception:
            log.debug("no screens available", exc_info=True)
            return []

    def _screen_under_window(self):
        from PySide6.QtCore import QPoint

        screens = self._screens()
        if not screens:
            return None
        center = self._win.mapToGlobal(
            QPoint(self._win.width() // 2, self._win.height() // 2)
        )
        for s in screens:
            if s.geometry().contains(center):
                return s
        return screens[0]

    def _target_screen(self):
        """The screen to dock to: the configured one, else the one we're on."""
        preferred = self._config.get("window", {}).get("dock_screen", "")
        if preferred:
            for s in self._screens():
                if s.name() == preferred:
                    return s
        return self._screen_under_window()

    # -- geometry --

    def dock_to_side(self, side: str, register_appbar: bool = False) -> bool:
        """Snap the window flush against a screen edge.

        Positioning uses the **work area** (availableGeometry), not the raw
        monitor rectangle: the taskbar lives in the difference, so a window
        sized against the monitor ends up overlapping it. Each side also pins
        the cross-axis to the work-area origin, so the panel sits flush at the
        top-left of the edge instead of wherever it was last dragged to.
        """
        if side not in EDGE_BY_SIDE:
            return False
        screen = self._target_screen()
        if screen is None:
            return False
        sg = screen.geometry()
        work = screen.availableGeometry()

        # Qt rects are inclusive on right()/bottom(); Win32 RECTs are too, but
        # SetWindowPos takes a width/height. Work in exclusive edges to avoid
        # an off-by-one that leaves the panel 1px off the screen edge.
        right = sg.left() + sg.width()
        bottom = sg.top() + sg.height()
        work_right = work.left() + work.width()
        work_bottom = work.top() + work.height()

        # Never let the panel grow past the usable area on the cross-axis.
        w = min(self._win.width(), work.width())
        h = min(self._win.height(), work.height())

        if side == "left":
            self._win.setGeometry(sg.left(), work.top(), w, h)
        elif side == "right":
            self._win.setGeometry(right - w, work.top(), w, h)
        elif side == "top":
            self._win.setGeometry(work.left(), sg.top(), w, h)
        else:
            self._win.setGeometry(work.left(), work_bottom - h, w, h)

        self._config.setdefault("window", {})["dock_side"] = side
        if register_appbar:
            self.register(edge=EDGE_BY_SIDE[side])
        return True

    # -- registration --

    def register(self, edge: int | None = None) -> bool:
        """Register as an appbar on `edge`, keeping the current window size.

        The window is restored to the exact geometry it had on entry.
        ABM_SETPOS stretches the window to the full edge, and ABM_QUERYPOS may
        move the *cross-axis* — for a left/right bar that is the vertical
        axis, so honouring it left a gap above the panel and pushed its
        bottom into the taskbar. So the negotiated rect is used only as the
        reservation; placement always comes from the window's own geometry.
        """
        try:
            from ctypes import windll

            screen = self._target_screen()
            if screen is None:
                return False
            sg = screen.geometry()
            work = screen.availableGeometry()
            right = sg.left() + sg.width()
            bottom = sg.top() + sg.height()
            work_right = work.left() + work.width()
            work_bottom = work.top() + work.height()

            # Geometry to restore after ABM_SETPOS stretches us.
            target = self._win.geometry()
            orig_w = target.width()
            orig_h = target.height()

            if edge is None:
                edge = self._config.get("window", {}).get("appbar_edge")
            if edge is None:
                cx = target.x() + orig_w // 2
                cy = target.y() + orig_h // 2
                candidates = sorted(
                    [
                        (abs(cx - sg.left()), ABE_LEFT),
                        (abs(cx - right), ABE_RIGHT),
                        (abs(cy - sg.top()), ABE_TOP),
                        (abs(cy - bottom), ABE_BOTTOM),
                    ]
                )
                edge = candidates[0][1]

            # The reserved rect is the window's own footprint, clipped to the
            # work area on the cross-axis so the taskbar is never covered.
            # RECT members are inclusive, hence the -1.
            if edge == ABE_LEFT:
                rc = _Rect(sg.left(), work.top(), sg.left() + orig_w - 1, work_bottom - 1)
            elif edge == ABE_RIGHT:
                rc = _Rect(right - orig_w, work.top(), right - 1, work_bottom - 1)
            elif edge == ABE_TOP:
                rc = _Rect(work.left(), sg.top(), work_right - 1, sg.top() + orig_h - 1)
            else:
                rc = _Rect(work.left(), work_bottom - orig_h, work_right - 1, work_bottom - 1)

            abd, byref = self._abd(edge, rc)
            windll.shell32.SHAppBarMessage(ABM_NEW, byref(abd))
            windll.shell32.SHAppBarMessage(ABM_QUERYPOS, byref(abd))

            # Re-assert our extent on BOTH axes. QUERYPOS only guarantees the
            # main axis, and letting it pick the cross-axis is what produced
            # the gap and the taskbar overlap.
            if edge == ABE_LEFT:
                abd.rc.right = abd.rc.left + orig_w - 1
                abd.rc.top, abd.rc.bottom = work.top(), work_bottom - 1
            elif edge == ABE_RIGHT:
                abd.rc.left = abd.rc.right - orig_w + 1
                abd.rc.top, abd.rc.bottom = work.top(), work_bottom - 1
            elif edge == ABE_TOP:
                abd.rc.bottom = abd.rc.top + orig_h - 1
                abd.rc.left, abd.rc.right = work.left(), work_right - 1
            else:
                abd.rc.top = abd.rc.bottom - orig_h + 1
                abd.rc.left, abd.rc.right = work.left(), work_right - 1

            windll.shell32.SHAppBarMessage(ABM_SETPOS, byref(abd))

            # ABM_SETPOS stretched us to the full edge; put the panel back.
            windll.user32.SetWindowPos(
                int(self._win.winId()),
                0,
                target.x(),
                target.y(),
                orig_w,
                orig_h,
                0x0004 | 0x0010,  # SWP_NOZORDER | SWP_NOACTIVATE
            )

            self._config.setdefault("window", {})["appbar_edge"] = edge
            self.active = True
            return True
        except Exception:
            log.warning("appbar registration failed", exc_info=True)
            self.active = False
            return False

    def unregister(self) -> None:
        try:
            from ctypes import byref, sizeof, windll

            abd = _AppBarData()
            abd.cbSize = sizeof(_AppBarData)
            abd.hWnd = int(self._win.winId())
            windll.shell32.SHAppBarMessage(ABM_REMOVE, byref(abd))
        except Exception:
            log.debug("appbar removal failed", exc_info=True)
        self.active = False

    def toggle(self) -> bool:
        """Flip appbar state. Returns the new active state."""
        from PySide6.QtCore import Qt

        if self.active:
            self.unregister()
            self._config.setdefault("window", {})["dock_side"] = ""
            saved = self._config.get("window", {}).get("_pre_appbar")
            if saved:
                self._win.setGeometry(saved["x"], saved["y"], saved["w"], saved["h"])
        else:
            # AppBar and always-on-top fight over the same edge; drop the latter.
            win_cfg = self._config.setdefault("window", {})
            if win_cfg.get("always_on_top", False):
                win_cfg["always_on_top"] = False
                win_cfg["always_on_back"] = False
                flags = self._win.windowFlags()
                flags &= ~Qt.WindowType.WindowStaysOnTopHint
                flags &= ~Qt.WindowType.WindowStaysOnBottomHint
                self._win.setWindowFlags(flags)
                self._win.show()
            geo = self._win.frameGeometry()
            win_cfg["_pre_appbar"] = {
                "x": geo.x(), "y": geo.y(), "w": geo.width(), "h": geo.height()
            }
            self.register()
        self._config.setdefault("window", {})["appbar"] = self.active
        return self.active
