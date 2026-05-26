"""
AURA — Mode Monitor (Phase 2).

Polls internet connectivity every 30 seconds. Emits MODE_CHANGED on the
event bus whenever online/offline status changes. Used by TTSEngine and
BrainController to select the right tool automatically.
"""

from __future__ import annotations

import logging
import threading

import httpx

from aura.utils.event_bus import EventType, bus

logger = logging.getLogger("aura.mode_monitor")


class ModeMonitor:
    """Daemon-threaded connectivity monitor with event-bus integration."""

    _POLL_INTERVAL = 30  # seconds

    def __init__(self) -> None:
        self._current_mode: str = "OFFLINE"
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._poll_interval: int | float = self._POLL_INTERVAL

    @staticmethod
    def is_online() -> bool:
        """Check internet connectivity by reaching Cloudflare DNS."""
        try:
            httpx.get("https://1.1.1.1", timeout=2)
            return True
        except Exception:
            return False

    @property
    def current_mode(self) -> str:
        """Return 'ONLINE' or 'OFFLINE' based on last known state."""
        return self._current_mode

    def start(self) -> None:
        """Launch the polling daemon thread. Emits an immediate first reading."""
        if self._thread is not None and self._thread.is_alive():
            return

        self._stop_event.clear()

        # Immediate first reading so all subscribers know initial state
        online = self.is_online()
        self._current_mode = "ONLINE" if online else "OFFLINE"
        bus.emit(EventType.MODE_CHANGED, {"mode": self._current_mode})
        logger.info("ModeMonitor started — initial state: %s", self._current_mode)

        self._thread = threading.Thread(
            target=self._poll, name="ModeMonitor", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """Signal the daemon thread to stop gracefully."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("ModeMonitor stopped")

    def _poll(self) -> None:
        """Background loop — checks connectivity every _POLL_INTERVAL seconds."""
        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=self._poll_interval)
            if self._stop_event.is_set():
                break

            online = self.is_online()
            new_mode = "ONLINE" if online else "OFFLINE"

            if new_mode != self._current_mode:
                self._current_mode = new_mode
                bus.emit(EventType.MODE_CHANGED, {"mode": self._current_mode})
                logger.info("Mode changed → %s", self._current_mode)


# Module-level singleton
mode_monitor = ModeMonitor()
