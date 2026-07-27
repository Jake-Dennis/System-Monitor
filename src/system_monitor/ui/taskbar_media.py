"""Windows taskbar thumbnail toolbar for media controls.

Adds play/pause/next/prev buttons to the app's taskbar preview
(like old Windows Media Player). Uses ITaskbarList3 COM interface.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QStyle

from ..data.media import next_track, play_pause, prev_track

log = logging.getLogger(__name__)

ID_PREV = 1001
ID_PLAY = 1002
ID_NEXT = 1003
THBN_CLICKED = 0x1800

# THUMBBUTTON structure
class THUMBBUTTON(ctypes.Structure):
    _fields_ = [
        ("dwMask", ctypes.wintypes.DWORD),
        ("iId", ctypes.c_int),
        ("iBitmap", ctypes.c_int),
        ("hIcon", ctypes.wintypes.HICON),
        ("szTip", ctypes.wintypes.WCHAR * 260),
        ("dwFlags", ctypes.wintypes.DWORD),
    ]


THB_ICON = 0x0001
THB_TOOLTIP = 0x0004
THB_FLAGS = 0x0008
THBF_ENABLED = 0x0000

# GUIDs as byte arrays
_CLSID = (ctypes.c_ubyte * 16)(0x44, 0xF3, 0xFD, 0x56, 0x6D, 0xFD, 0xD0, 0x11,
                                0x95, 0x8A, 0x00, 0x60, 0x97, 0xC9, 0xA0, 0x90)
_IID = (ctypes.c_ubyte * 16)(0x91, 0xFB, 0x1A, 0xEA, 0x28, 0x9E, 0x86, 0x4B,
                              0x90, 0xE9, 0x9E, 0x9F, 0x8A, 0x5E, 0xEF, 0xAF)


def _make_hicon(sp: QStyle.StandardPixmap) -> int:
    """Create a simple HICON for a media control button.

    Falls back to the application icon if custom drawing fails.
    """
    try:
        hicon = _make_icon_win32gui(sp)
        if hicon:
            return hicon
    except Exception as e:
        log.debug("Custom icon failed: %s", e)
    # Fallback: load the default application icon
    try:
        return ctypes.windll.user32.LoadIconW(0, 32512)
    except Exception:
        return 0


def _make_icon_win32gui(sp: QStyle.StandardPixmap) -> int:
    """Draw a simple play/prev/next shape and convert to HICON."""
    import win32gui
    import win32ui
    import win32con

    if sp == QStyle.StandardPixmap.SP_MediaSkipBackward:
        shape = "prev"
    elif sp == QStyle.StandardPixmap.SP_MediaPlay:
        shape = "play"
    elif sp == QStyle.StandardPixmap.SP_MediaSkipForward:
        shape = "next"
    else:
        return 0

    w, h = 32, 32

    # Get a compatible DC for the screen
    hdc = win32gui.GetDC(0)
    mem_dc = win32gui.CreateCompatibleDC(hdc)

    bmp = win32gui.CreateCompatibleBitmap(hdc, w, h)
    old_bmp = win32gui.SelectObject(mem_dc, bmp)

    # Transparent background
    win32gui.SetBkColor(mem_dc, win32gui.RGB(0, 0, 0))
    win32gui.ExtTextOut(mem_dc, 0, 0, win32con.ETO_OPAQUE, (0, 0, w, h), "", 0, None)

    # White drawing
    pen = win32gui.CreatePen(win32con.PS_SOLID, 2, win32gui.RGB(220, 220, 220))
    brush = win32gui.CreateSolidBrush(win32gui.RGB(220, 220, 220))
    win32gui.SelectObject(mem_dc, pen)
    win32gui.SelectObject(mem_dc, brush)

    if shape == "prev":
        win32gui.Polygon(mem_dc, [(2, 16), (22, 4), (22, 28)])
        win32gui.PatBlt(mem_dc, 24, 4, 4, 24, win32con.PATCOPY)
    elif shape == "play":
        win32gui.Polygon(mem_dc, [(6, 4), (28, 16), (6, 28)])
    elif shape == "next":
        win32gui.Polygon(mem_dc, [(30, 16), (10, 4), (10, 28)])
        win32gui.PatBlt(mem_dc, 4, 4, 4, 24, win32con.PATCOPY)

    win32gui.SelectObject(mem_dc, old_bmp)
    win32gui.DeleteDC(mem_dc)
    win32gui.ReleaseDC(0, hdc)

    # Create icon
    icon_info = win32gui.ICONINFO()
    icon_info.fIcon = True
    icon_info.hbmMask = bmp
    icon_info.hbmColor = bmp
    hicon = win32gui.CreateIconIndirect(icon_info)
    win32gui.DeleteObject(bmp)
    return hicon


class TaskbarMediaController:
    """Manages media control buttons on the Windows taskbar thumbnail."""

    def __init__(self, hwnd: int) -> None:
        self._hwnd = hwnd
        self._unk: int | None = None
        self._icons: list[int] = []
        self._init_com()

    def _init_com(self) -> None:
        try:
            ole32 = ctypes.windll.ole32
            ole32.CoInitialize(None)
            unk = ctypes.c_void_p()
            hr = ole32.CoCreateInstance(
                ctypes.cast(_CLSID, ctypes.c_void_p),
                None, 1,
                ctypes.cast(_IID, ctypes.c_void_p),
                ctypes.byref(unk),
            )
            if hr == 0:
                self._unk = unk.value
        except Exception:
            pass

    def setup(self) -> None:
        if self._unk is None:
            return
        try:
            vtable = ctypes.c_void_p.from_address(self._unk).value

            # HrInit at vtable index 3
            fn_hrinit = ctypes.CFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(
                ctypes.c_void_p.from_address(vtable + 3 * 8).value
            )
            fn_hrinit(self._unk)

            # AddTab at vtable index 4 — ensure the window has a taskbar entry.
            fn_addtab = ctypes.CFUNCTYPE(
                ctypes.c_ulong, ctypes.c_void_p, ctypes.c_void_p,
            )(
                ctypes.c_void_p.from_address(vtable + 4 * 8).value
            )
            fn_addtab(self._unk, ctypes.c_void_p(self._hwnd))

            # Create icons
            icons = [
                _make_hicon(QStyle.StandardPixmap.SP_MediaSkipBackward),
                _make_hicon(QStyle.StandardPixmap.SP_MediaPlay),
                _make_hicon(QStyle.StandardPixmap.SP_MediaSkipForward),
            ]
            self._icons = [h for h in icons if h]

            # Build 3 buttons
            buttons = (THUMBBUTTON * 3)()
            for i, (hicon, cmd_id, tip) in enumerate([
                (icons[0], ID_PREV, "Previous"),
                (icons[1], ID_PLAY, "Play/Pause"),
                (icons[2], ID_NEXT, "Next"),
            ]):
                btn = buttons[i]
                btn.dwMask = THB_ICON | THB_TOOLTIP | THB_FLAGS
                btn.iId = cmd_id
                btn.hIcon = hicon
                btn.szTip = tip
                btn.dwFlags = THBF_ENABLED

            # ThumbBarAddButtons at vtable index 8
            fn_add = ctypes.CFUNCTYPE(
                ctypes.c_ulong,
                ctypes.c_void_p,  # this
                ctypes.c_void_p,  # HWND
                ctypes.c_uint,    # cButtons
                ctypes.c_void_p,  # pButton
            )(
                ctypes.c_void_p.from_address(vtable + 8 * 8).value
            )
            hr = fn_add(
                self._unk,
                ctypes.c_void_p(self._hwnd),
                ctypes.c_uint(3),
                ctypes.byref(buttons),
            )
            if hr != 0:
                log.warning("ThumbBarAddButtons failed: %d", hr)
        except Exception as e:
            log.warning("Taskbar setup error: %s", e)

    def handle_click(self, cmd_id: int) -> None:
        if cmd_id == ID_PREV:
            prev_track()
        elif cmd_id == ID_PLAY:
            play_pause()
        elif cmd_id == ID_NEXT:
            next_track()

    def cleanup(self) -> None:
        for h in self._icons:
            if h:
                try:
                    ctypes.windll.user32.DestroyIcon(h)
                except Exception:
                    pass
        self._icons.clear()
        try:
            if self._unk is not None:
                vtable = ctypes.c_void_p.from_address(self._unk).value
                fn_release = ctypes.CFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(
                    ctypes.c_void_p.from_address(vtable + 2 * 8).value
                )
                fn_release(self._unk)
        except Exception:
            pass
        self._unk = None
