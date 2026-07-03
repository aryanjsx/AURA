# tests/test_session_controller.py
# Run with: pytest tests/test_session_controller.py -v

import time
import threading
import pytest
from unittest.mock import MagicMock, patch

from aura.core.event_bus import bus, EventType


# ── Fixture: reset the bus between tests ──────────────────────────────

@pytest.fixture(autouse=True)
def clear_bus():
    """Reset all event subscriptions before each test."""
    bus._handlers.clear()
    yield
    bus._handlers.clear()


# ── Helpers ───────────────────────────────────────────────────────────

def make_controller(inactivity_minutes: float = 10.0):
    from aura.core.session_controller import SessionController
    mock_wake = MagicMock()
    mock_wake.pause = MagicMock()
    mock_wake.resume = MagicMock()
    config = {"session": {"inactivity_timeout_minutes": inactivity_minutes}}
    return SessionController(config, mock_wake), mock_wake


# ── Tests ─────────────────────────────────────────────────────────────

class TestSessionActivation:

    def test_inactive_by_default(self):
        ctrl, _ = make_controller()
        assert ctrl.is_active is False

    def test_wake_word_starts_session(self):
        ctrl, mock_wake = make_controller()
        bus.emit(EventType.WAKE_WORD_DETECTED, {})
        assert ctrl.is_active is True

    def test_wake_pauses_listener_on_start(self):
        ctrl, mock_wake = make_controller()
        bus.emit(EventType.WAKE_WORD_DETECTED, {})
        mock_wake.pause.assert_called_once()

    def test_second_wake_word_ignored_during_session(self):
        ctrl, mock_wake = make_controller()
        bus.emit(EventType.WAKE_WORD_DETECTED, {})
        bus.emit(EventType.WAKE_WORD_DETECTED, {})
        assert mock_wake.pause.call_count == 1

    def test_session_started_event_emitted(self):
        ctrl, _ = make_controller()
        events = []
        bus.subscribe(EventType.SESSION_STARTED, lambda p: events.append(p))
        bus.emit(EventType.WAKE_WORD_DETECTED, {})
        assert len(events) == 1
        assert "timestamp" in events[0]


class TestSessionDeactivation:

    def test_session_ended_event_deactivates(self):
        ctrl, _ = make_controller()
        bus.emit(EventType.WAKE_WORD_DETECTED, {})
        assert ctrl.is_active is True
        bus.emit(EventType.SESSION_ENDED, {"reason": "test"})
        assert ctrl.is_active is False

    def test_speaking_finished_after_session_ends_rearms_wake(self):
        ctrl, mock_wake = make_controller()
        bus.emit(EventType.WAKE_WORD_DETECTED, {})
        bus.emit(EventType.SESSION_ENDED, {"reason": "manual"})
        bus.emit(EventType.TTS_SPEAKING_FINISHED, {})
        time.sleep(0.1 + 3.0 + 0.2)
        mock_wake.resume.assert_called_once()


class TestInactivityTimer:

    def test_inactivity_timeout_fires_after_configured_time(self):
        """Use a very short timeout so the test completes quickly."""
        ctrl, mock_wake = make_controller(inactivity_minutes=2 / 60)  # 2 seconds
        timeout_events = []
        bus.subscribe(EventType.INACTIVITY_TIMEOUT, lambda p: timeout_events.append(p))

        bus.emit(EventType.WAKE_WORD_DETECTED, {})
        assert ctrl.is_active is True

        time.sleep(2.5)
        assert ctrl.is_active is False
        assert len(timeout_events) == 1

    def test_transcription_resets_timer(self):
        """Timer resets on transcription — session stays alive."""
        ctrl, _ = make_controller(inactivity_minutes=2 / 60)  # 2 second timeout
        bus.emit(EventType.WAKE_WORD_DETECTED, {})

        for _ in range(3):
            time.sleep(1.5)
            bus.emit(EventType.TRANSCRIPTION_COMPLETE, {"text": "open chrome"})

        assert ctrl.is_active is True

    def test_empty_transcription_does_not_reset_timer(self):
        """Silence-only recordings do NOT reset the inactivity timer."""
        ctrl, _ = make_controller(inactivity_minutes=2 / 60)  # 2 seconds
        bus.emit(EventType.WAKE_WORD_DETECTED, {})
        bus.emit(EventType.TRANSCRIPTION_COMPLETE, {"text": ""})
        bus.emit(EventType.TRANSCRIPTION_COMPLETE, {"text": "   "})
        time.sleep(2.5)
        assert ctrl.is_active is False


class TestListenNowLoop:

    def test_silence_cycle_emits_listen_now(self):
        """After a silent recording, LISTEN_NOW is emitted to keep the loop going."""
        ctrl, _ = make_controller()
        bus.emit(EventType.WAKE_WORD_DETECTED, {})

        listen_events = []
        bus.subscribe(EventType.LISTEN_NOW, lambda p: listen_events.append(p))

        bus.emit(EventType.RECORDING_STOPPED, {"duration_ms": 500})
        time.sleep(0.3)
        assert any(e.get("source") == "silence_loop" for e in listen_events)

    def test_speaking_finished_emits_listen_now_during_session(self):
        """After TTS finishes a response, LISTEN_NOW re-arms the STT."""
        ctrl, _ = make_controller()
        bus.emit(EventType.WAKE_WORD_DETECTED, {})

        ctrl._pipeline_busy = True
        listen_events = []
        bus.subscribe(EventType.LISTEN_NOW, lambda p: listen_events.append(p))

        bus.emit(EventType.TTS_SPEAKING_FINISHED, {})
        time.sleep(0.1 + 0.5 + 0.2)
        assert any(e.get("source") == "session_loop" for e in listen_events)
