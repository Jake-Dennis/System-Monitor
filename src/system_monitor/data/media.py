"""Media playback detection and control via Windows SMTC (winrt).

Uses the Windows SystemMediaTransportControls pipeline — the same API the
taskbar media widget uses. Reliable metadata and playback control for any
app that integrates with SMTC (Spotify, Chrome, Edge, etc.).
"""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

log = logging.getLogger(__name__)

# Playback command ids. These are the shared vocabulary between the panel
# buttons, the tray menu and the Windows taskbar thumbnail toolbar — they used
# to live in ui/taskbar_media.py, which meant the window layer had to import a
# taskbar-integration module just to name a command.
CMD_PREV = 1001
CMD_PLAY = 1002
CMD_NEXT = 1003

# Sentinel for "winrt is not installed". Previously this was smuggled in by
# assigning False to the same variable that holds the session, which made the
# module's own type annotation a lie.
_UNAVAILABLE = object()

# Windows.Media.SystemMediaTransportControlsPlaybackStatus ordinals. The
# generated winrt enum exposes .name, but fall back to ordinals so a mapping
# change can't turn "playing" into "unknown".
_STATUS_BY_ORDINAL = {
    0: "closed",
    1: "changing",
    2: "opened",
    3: "stopped",
    4: "paused",
    5: "playing",
}

# Shape returned whenever no media session is available.
NO_MEDIA: dict[str, Any] = {
    "title": "",
    "artist": "",
    "album": "",
    "app": "",
    "app_name": "",
    "status": "unknown",
    "is_active": False,
    "can_next": False,
    "can_prev": False,
    "can_play_pause": False,
}


def _status_str(value: Any) -> str:
    """Normalize a playback status to a lowercase string."""
    if value is None:
        return "unknown"
    name = getattr(value, "name", None)
    if isinstance(name, str) and name:
        return name.lower()
    try:
        return _STATUS_BY_ORDINAL.get(int(value), "unknown")
    except (TypeError, ValueError):
        return "unknown"


# Display names for the app ids SMTC reports. Keyed by the lowercased,
# suffix-stripped id so the panel can show "Edge" rather than "MSEdge".
_APP_ALIASES = {
    "msedge": "Edge",
    "chrome": "Chrome",
    "iexplore": "Internet Explorer",
    "spotify": "Spotify",
    "brave": "Brave",
    "firefox": "Firefox",
    "vlc": "VLC",
    "wmplayer": "Media Player",
    "microsoft.windowsstore_8wekyb3d8bbwe": "Store",
}

# Browsers publish an SMTC session for any page with <video> or <audio>, so
# they show up in get_sessions() alongside real players. They are excluded:
# browser media has no skip support (is_next_enabled is False), so half the
# transport buttons would be permanently dead, and YouTube-in-a-tab is not a
# "media player". Dedicated players — Spotify, VLC, foobar, AIMP, MusicBee,
# local Jellyfin clients, … — are all included.
_BROWSER_APPS = {
    "chrome",
    "msedge",
    "msedgewebview2",
    "firefox",
    "librewolf",
    "waterfox",
    "brave",
    "opera",
    "opera_gx",
    "vivaldi",
    "chromium",
    "whale",
    "yandex",
    "thorium",
    "seamonkey",
    "epic",
}


def normalize_app(app_id: str) -> str:
    """Lowercase, path- and extension-stripped form used for comparisons."""
    name = (app_id or "").rsplit("\\", 1)[-1]
    if name.lower().endswith(".exe"):
        name = name[:-4]
    if name.lower().startswith("microsoft.ms"):
        name = name.split(".")[-1]
    return name.split("_", 1)[0].lower()


def is_media_player(app_id: str) -> bool:
    """True for dedicated players, False for web browsers."""
    if not app_id:
        return False
    return normalize_app(app_id) not in _BROWSER_APPS


def friendly_app(app_id: str) -> str:
    """Turn an SMTC app id into something worth showing in a 380px panel.

    'Spotify.exe' -> 'Spotify', 'chrome.exe' -> 'Chrome',
    'Microsoft.MSEdge_8wekyb3d8bbwe' -> 'Edge'.
    """
    if not app_id:
        return ""
    name = app_id.rsplit("\\", 1)[-1]
    if name.lower().endswith(".exe"):
        name = name[:-4]
    # Packaged apps carry a Microsoft.<Product>_<hash> id.
    if name.lower().startswith("microsoft.ms"):
        name = name.split(".")[-1]
    # Drop the per-install hash suffix ("MSEdge_8wekyb3d8bbwe" -> "MSEdge").
    name = name.split("_", 1)[0]
    return _APP_ALIASES.get(name.lower(), name) or app_id

# ---------------------------------------------------------------------------
# SMTC session — async winsdk wrapper running in a daemon thread
# ---------------------------------------------------------------------------

class _SMTCSession:
    """Async wrapper around Windows SMTC API via winrt."""

    def __init__(self) -> None:
        self._manager: Any = None
        self._target: str | None = None
        # App id of the session the panel is currently showing. Commands fall
        # back to this so the buttons always steer what the card displays —
        # otherwise a browser session could be "current" while the card shows
        # Spotify, and the buttons would control the wrong app.
        self._active: str | None = None
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    # -- internals ----------------------------------------------------------

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    async def _ensure_manager(self) -> Any:
        if self._manager is None:
            from winrt.windows.media.control import (
                GlobalSystemMediaTransportControlsSessionManager as Mgr,
            )
            self._manager = await Mgr.request_async()
        return self._manager

    # -- public API (thread-safe, synchronous) -----------------------------

    def snapshot(self) -> dict[str, Any] | None:
        """Return the targeted session's state, or None if unavailable."""
        future = asyncio.run_coroutine_threadsafe(self._get_snapshot(), self._loop)
        try:
            return future.result(timeout=3)
        except Exception:
            log.debug("media snapshot failed", exc_info=True)
            return None

    def sessions(self) -> list[dict[str, Any]]:
        """Every media-player session Windows currently knows about.

        Browsers are excluded (see `_BROWSER_APPS`).
        """
        future = asyncio.run_coroutine_threadsafe(
            self._list_sessions(), self._loop
        )
        try:
            return future.result(timeout=3)
        except Exception:
            log.debug("media session list failed", exc_info=True)
            return []

    def send_command(self, command: str, app_id: str | None = None) -> bool:
        """Send a playback command. Returns True on success.

        `app_id` targets a specific app; without it the user's pinned choice
        is used, falling back to whichever session Windows considers current.
        """
        future = asyncio.run_coroutine_threadsafe(
            self._send_command(command, app_id), self._loop
        )
        try:
            return future.result(timeout=5)
        except Exception:
            log.debug("media command %s failed", command, exc_info=True)
            return False

    def set_target(self, app_id: str | None) -> None:
        """Pin control to one app, or pass None to follow Windows' choice."""
        self._target = app_id or None

    @property
    def target(self) -> str | None:
        return self._target

    # -- internals ----------------------------------------------------------

    @staticmethod
    def _describe(session: Any, props: Any, info: Any) -> dict[str, Any]:
        """Flatten one SMTC session into a plain dict.

        `playback_info` exposes `playback_status`; reading `.status` raised
        AttributeError, which the surrounding try/except turned into "no
        media" for every app.
        """
        controls = getattr(info, "controls", None) if info is not None else None
        app_id = session.source_app_user_model_id or ""
        return {
            "app": app_id,
            "app_name": friendly_app(app_id),
            "title": (getattr(props, "title", "") or "").strip(),
            "artist": (getattr(props, "artist", "") or "").strip(),
            "album": (getattr(props, "album_title", "") or "").strip(),
            "status": _status_str(getattr(info, "playback_status", None)),
            # Browsers (YouTube and friends) expose play/pause and seek but
            # not skip. Reporting this is the difference between a dead button
            # and an honestly disabled one.
            "can_next": bool(getattr(controls, "is_next_enabled", False)),
            "can_prev": bool(getattr(controls, "is_previous_enabled", False)),
            "can_play_pause": bool(
                getattr(controls, "is_play_pause_toggle_enabled", False)
            ),
        }

    async def _list_sessions(self) -> list[dict[str, Any]]:
        mgr = await self._ensure_manager()
        out: list[dict[str, Any]] = []
        for session in mgr.get_sessions() or []:
            app_id = session.source_app_user_model_id or ""
            if not is_media_player(app_id):
                continue  # web browser: no skip, not a media player
            try:
                props = await session.try_get_media_properties_async()
                info = session.get_playback_info()
            except Exception:
                log.debug("skipping unreadable SMTC session", exc_info=True)
                continue
            out.append(self._describe(session, props, info))
        # Playing first: that is what the user most likely wants to control.
        out.sort(key=lambda s: (s["status"] != "playing", not s["title"], s["app_name"]))
        return out

    def _find_session(self, mgr: Any, app_id: str | None) -> Any | None:
        sessions = mgr.get_sessions() or []
        if app_id:
            for session in sessions:
                if (session.source_app_user_model_id or "") == app_id:
                    return session
        return mgr.get_current_session()

    async def _get_snapshot(self) -> dict[str, Any] | None:
        try:
            sessions = await self._list_sessions()
        except Exception:
            log.debug("SMTC session enumeration failed", exc_info=True)
            self._active = None
            return None
        if not sessions:
            self._active = None
            return None

        # Honour a pinned target, but drop it if that app went away.
        if self._target:
            match = next((s for s in sessions if s["app"] == self._target), None)
            if match is not None:
                self._active = match["app"]
                return match
            self._target = None

        # Otherwise follow whichever *media player* Windows calls current, and
        # fall back to the highest-priority player (playing sorts first).
        mgr = await self._ensure_manager()
        current = self._find_session(mgr, None)
        current_id = getattr(current, "source_app_user_model_id", None) or ""
        chosen = next((s for s in sessions if s["app"] == current_id), sessions[0])
        self._active = chosen["app"]
        return chosen

    async def _send_command(self, command: str, app_id: str | None) -> bool:
        try:
            mgr = await self._ensure_manager()
            # Target order: explicit app → user pin → whatever the card is
            # showing. Only then Windows' "current" session, which may be a
            # browser we deliberately don't display.
            session = self._find_session(mgr, app_id or self._target or self._active)
            if session is None:
                return False
            commands = {
                "play": lambda: session.try_play_async(),
                "pause": lambda: session.try_pause_async(),
                "toggle": lambda: session.try_toggle_play_pause_async(),
                "next": lambda: session.try_skip_next_async(),
                "prev": lambda: session.try_skip_previous_async(),
                "previous": lambda: session.try_skip_previous_async(),
            }
            fn = commands.get(command)
            if fn is None:
                return False
            return bool(await fn())
        except Exception:
            log.debug("SMTC command %s error", command, exc_info=True)
            return False


# ---------------------------------------------------------------------------
# Module-level singleton + convenience functions
# ---------------------------------------------------------------------------

_smtc: _SMTCSession | None = None
_smtc_lock = threading.Lock()
_smtc_checked = False


def _ensure_smtc() -> bool:
    """Create the SMTC session on first use. False if winrt is unavailable."""
    global _smtc, _smtc_checked
    if not _smtc_checked:
        with _smtc_lock:
            if not _smtc_checked:
                try:
                    import winrt.windows.media.control  # noqa: F401

                    _smtc = _SMTCSession()
                except ImportError:
                    log.info(
                        "winrt-Windows.Media.Control not installed — media controls disabled"
                    )
                _smtc_checked = True
    return _smtc is not None


def now_playing() -> dict[str, Any]:
    """Return current media info, or a no-media dict when unavailable.

    This blocks for up to 3s waiting on the SMTC async call, so it belongs on
    the collector thread (once per sample interval) — not on the 10 Hz repaint
    path that paints the panel.

    Returns title, artist, app (raw id) / app_name (friendly), status,
    is_active, and the can_next / can_prev / can_play_pause capabilities of
    the targeted session.
    """
    if not _ensure_smtc() or _smtc is None:
        return dict(NO_MEDIA)
    snap = _smtc.snapshot()
    if snap is None or not snap.get("title"):
        return dict(NO_MEDIA)
    out = dict(snap)
    out["is_active"] = True
    return out


def sessions() -> list[dict[str, Any]]:
    """All SMTC sessions (Spotify, browsers, etc.), playing ones first."""
    if not _ensure_smtc() or _smtc is None:
        return []
    return _smtc.sessions()


def set_target(app_id: str | None) -> None:
    """Control a specific app (e.g. 'Spotify.exe' or 'Brave').

    Pass None to go back to following whichever session Windows considers
    current. A pinned app that stops publishing a session is dropped
    automatically rather than leaving the panel stuck.
    """
    if _ensure_smtc() and _smtc is not None:
        _smtc.set_target(app_id)


def target() -> str | None:
    """The pinned app id, or None if following Windows' choice."""
    if not _ensure_smtc() or _smtc is None:
        return None
    return _smtc.target


def play_pause() -> None:
    if _ensure_smtc() and _smtc is not None:
        _smtc.send_command("toggle")


def next_track() -> None:
    if _ensure_smtc() and _smtc is not None:
        _smtc.send_command("next")


def prev_track() -> None:
    if _ensure_smtc() and _smtc is not None:
        _smtc.send_command("prev")


def dispatch(cmd_id: int) -> None:
    """Run a playback command by id. Used by the taskbar toolbar."""
    if cmd_id == CMD_PREV:
        prev_track()
    elif cmd_id == CMD_PLAY:
        play_pause()
    elif cmd_id == CMD_NEXT:
        next_track()
