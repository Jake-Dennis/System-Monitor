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

# ---------------------------------------------------------------------------
# SMTC session — async winsdk wrapper running in a daemon thread
# ---------------------------------------------------------------------------

class _SMTCSession:
    """Async wrapper around Windows SMTC API via winrt."""

    def __init__(self) -> None:
        self._manager: Any = None
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
        """Return current media snapshot, or None if unavailable."""
        future = asyncio.run_coroutine_threadsafe(
            self._get_snapshot(), self._loop
        )
        try:
            return future.result(timeout=3)
        except Exception:
            return None

    async def _get_snapshot(self) -> dict[str, Any] | None:
        try:
            mgr = await self._ensure_manager()
            session = mgr.get_current_session()
            if session is None:
                return None

            props = await session.try_get_media_properties_async()
            playback = session.get_playback_info()
            timeline = session.get_timeline_properties()

            status = "unknown"
            if playback and playback.playback_status is not None:
                status = str(playback.playback_status.name).lower()

            return {
                "title": (props.title or "").strip(),
                "artist": (props.artist or "").strip(),
                "album": (props.album_title or "").strip(),
                "source": (session.source_app_user_model_id or "").strip(),
                "status": status,
                "position_s": timeline.position.total_seconds() if timeline and timeline.position else 0.0,
                "duration_s": timeline.end_time.total_seconds() if timeline and timeline.end_time else 0.0,
            }
        except Exception:
            log.debug("SMTC snapshot error", exc_info=True)
            return None

    def send_command(self, command: str) -> bool:
        """Send a playback command. Returns True on success."""
        future = asyncio.run_coroutine_threadsafe(
            self._send_command(command), self._loop
        )
        try:
            return future.result(timeout=5)
        except Exception:
            return False

    async def _send_command(self, command: str) -> bool:
        try:
            mgr = await self._ensure_manager()
            session = mgr.get_current_session()
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
            log.debug("SMTC command error", exc_info=True)
            return False


# ---------------------------------------------------------------------------
# Module-level singleton + convenience functions
# ---------------------------------------------------------------------------

_smtc: _SMTCSession | None = None
_smtc_lock = threading.Lock()


def _ensure_smtc() -> bool:
    global _smtc
    if _smtc is None:
        with _smtc_lock:
            if _smtc is None:
                try:
                    import winrt.windows.media.control  # noqa: F401
                    _smtc = _SMTCSession()
                except ImportError:
                    log.info("winrt-Windows.Media.Control not installed — media controls disabled")
                    _smtc = False  # type: ignore[assignment]
    return _smtc is not False and _smtc is not None


def now_playing() -> dict[str, Any]:
    """Return current media info, or fallback dict when unavailable.

    Returns:
      title     — track title (or empty)
      artist    — artist name (or empty)
      status    — "playing", "paused", "stopped", or "unknown"
      is_active — True when a media session is active
    """
    if not _ensure_smtc():
        return {"title": "", "artist": "", "status": "unknown", "is_active": False}
    snap = _smtc.snapshot()
    if snap is None or not snap.get("title"):
        return {"title": "", "artist": "", "status": "unknown", "is_active": False}
    return {
        "title": snap["title"],
        "artist": snap.get("artist", ""),
        "status": snap.get("status", "unknown"),
        "is_active": True,
    }


def play_pause() -> None:
    if _ensure_smtc():
        _smtc.send_command("toggle")


def next_track() -> None:
    if _ensure_smtc():
        _smtc.send_command("next")


def prev_track() -> None:
    if _ensure_smtc():
        _smtc.send_command("prev")
