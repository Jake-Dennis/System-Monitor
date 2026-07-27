"""Media playback detection and control via Windows API.

Sends media keys (play/pause, next, prev) via keybd_event — no extra
dependencies. Reads current track info from window titles of known
media players (Spotify, YouTube, VLC, Windows Media Player, etc.).
"""
from __future__ import annotations

import logging
import re
from typing import Any

log = logging.getLogger(__name__)

# Virtual-key codes for media transport
_VK_MEDIA_PLAY_PAUSE = 0xB3
_VK_MEDIA_STOP = 0xB2
_VK_MEDIA_PREV_TRACK = 0xB1
_VK_MEDIA_NEXT_TRACK = 0xB0

# Known media player exe patterns (lowercase substring match).
_MEDIA_PROCESSES = (
    "spotify",
    "chrome",
    "msedge",
    "firefox",
    "brave",
    "vlc",
    "wmplayer",
    "foobar2000",
    "audacity",
    "mpc-hc",
    "mpv",
)

# Patterns to extract artist/title from window titles.
_TITLE_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    # "Artist - Title" or "Artist – Title" (em dash)
    (re.compile(r"^(.+?)\s*[–—-]\s*(.+?)$"), "artist", "title"),
    # "Title · Artist" (middle dot)
    (re.compile(r"^(.+?)\s*·\s*(.+?)$"), "title", "artist"),
    # "Title | Artist"
    (re.compile(r"^(.+?)\s*\|\s*(.+?)$"), "title", "artist"),
]


def _press_key(vk: int) -> None:
    """Press and release a virtual key."""
    import ctypes

    user32 = ctypes.windll.user32
    user32.keybd_event(vk, 0, 0, 0)  # Key down
    user32.keybd_event(vk, 0, 2, 0)  # Key up


def play_pause() -> None:
    """Toggle play/pause."""
    _press_key(_VK_MEDIA_PLAY_PAUSE)


def next_track() -> None:
    """Skip to next track."""
    _press_key(_VK_MEDIA_NEXT_TRACK)


def prev_track() -> None:
    """Go to previous track."""
    _press_key(_VK_MEDIA_PREV_TRACK)


def now_playing() -> dict[str, Any]:
    """Detect currently playing media by scanning window titles.

    Returns a dict with keys:
      title     — song/video title (or empty string)
      artist    — artist/channel name (or empty string)
      app       — detected media application name
      is_active — True if a media window with playable content was found
    """
    try:
        import win32gui
        import win32process
    except ImportError:
        return {"title": "", "artist": "", "app": "", "is_active": False}

    from collections import namedtuple

    WindowInfo = namedtuple("WindowInfo", ["hwnd", "title", "exe"])

    windows: list[WindowInfo] = []
    seen_hwnds: set[int] = set()

    def _enum_callback(hwnd: int, _) -> None:
        if not win32gui.IsWindowVisible(hwnd):
            return
        if hwnd in seen_hwnds:
            return
        seen_hwnds.add(hwnd)
        length = win32gui.GetWindowTextLength(hwnd)
        if length == 0:
            return
        title = win32gui.GetWindowText(hwnd)
        if not title or not title.strip():
            return
        # Get the process exe for this window.
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            import psutil

            proc = psutil.Process(pid)
            exe = (proc.exe() or "").lower()
        except Exception:
            exe = ""
        # Only keep windows from known media processes, or any window with
        # a title that looks like media content.
        if any(p in exe for p in _MEDIA_PROCESSES) or _looks_like_media(title):
            windows.append(WindowInfo(hwnd, title, exe))

    try:
        win32gui.EnumWindows(_enum_callback, None)
    except Exception:
        pass

    if not windows:
        return {"title": "", "artist": "", "app": "", "is_active": False}

    # Pick the most informative window (longest title usually = most data).
    best = max(windows, key=lambda w: len(w.title))
    title = best.title.strip()
    app_name = _app_name(best.exe)
    parsed = _parse_media_title(title)

    result = {
        "title": parsed.get("title", title),
        "artist": parsed.get("artist", ""),
        "app": app_name,
        "is_active": True,
    }
    return result


def _looks_like_media(title: str) -> bool:
    """Heuristic: does this window title look like media content?"""
    t = title.lower().strip()
    # Too short.
    if len(t) < 5:
        return False
    # Skip known non-media window titles.
    skip_prefixes = (
        "settings", "program manager", "default", "task",
        "property", "control panel", "file explorer",
    )
    if any(t.startswith(p) for p in skip_prefixes):
        return False
    # Contains separator → likely artist-title format.
    for sep in (" – ", " –", " - ", " · ", " | "):
        if sep in t:
            return True
    return False


def _parse_media_title(title: str) -> dict[str, str]:
    """Attempt to extract artist and title from a window title."""
    for pattern, first_key, second_key in _TITLE_PATTERNS:
        m = pattern.search(title)
        if m:
            first = m.group(1).strip()
            second = m.group(2).strip()
            if first and second:
                return {first_key: first, second_key: second}
    return {"title": title, "artist": ""}


def _app_name(exe: str) -> str:
    """Derive a user-friendly app name from the exe path."""
    exe_lower = exe.lower()
    if "spotify" in exe_lower:
        return "Spotify"
    if "chrome" in exe_lower:
        return "Chrome"
    if "msedge" in exe_lower:
        return "Edge"
    if "firefox" in exe_lower:
        return "Firefox"
    if "brave" in exe_lower:
        return "Brave"
    if "vlc" in exe_lower:
        return "VLC"
    if "wmplayer" in exe_lower:
        return "Windows Media Player"
    if "foobar2000" in exe_lower:
        return "foobar2000"
    if "mpc" in exe_lower or "mpv" in exe_lower:
        return "Media Player"
    return "Media"
