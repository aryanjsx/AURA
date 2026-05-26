"""
AURA — Phase 2 Event Bus.

Central synchronous pub/sub bus for the voice pipeline.
All cross-module communication goes through this bus.
Modules never import each other directly.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable


logger = logging.getLogger("aura.event_bus")


class EventType(str, Enum):
    """Every event the Phase 2 pipeline can emit or subscribe to."""

    WAKE_WORD_DETECTED = "WAKE_WORD_DETECTED"
    RECORDING_STARTED = "RECORDING_STARTED"
    RECORDING_STOPPED = "RECORDING_STOPPED"
    TRANSCRIPTION_COMPLETE = "TRANSCRIPTION_COMPLETE"
    INTENT_CLASSIFIED = "INTENT_CLASSIFIED"
    LLM_REQUEST_SENT = "LLM_REQUEST_SENT"
    LLM_RESPONSE_RECEIVED = "LLM_RESPONSE_RECEIVED"
    COMMAND_PLAN_READY = "COMMAND_PLAN_READY"
    SAFETY_CONFIRMATION_REQ = "SAFETY_CONFIRMATION_REQ"
    SAFETY_CONFIRMED = "SAFETY_CONFIRMED"
    SAFETY_DENIED = "SAFETY_DENIED"
    EXECUTION_STARTED = "EXECUTION_STARTED"
    EXECUTION_COMPLETE = "EXECUTION_COMPLETE"
    TTS_SPEAK_REQUEST = "TTS_SPEAK_REQUEST"
    TTS_SPEAKING_STARTED = "TTS_SPEAKING_STARTED"
    TTS_SPEAKING_FINISHED = "TTS_SPEAKING_FINISHED"
    MODE_CHANGED = "MODE_CHANGED"
    SYSTEM_ERROR = "SYSTEM_ERROR"


@dataclass
class EventPayload:
    """Structured payload delivered to every subscriber."""

    event_type: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


class EventBus:
    """Synchronous, thread-safe publish/subscribe bus for the voice pipeline."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable[[EventPayload], None]]] = {}
        self._lock = threading.Lock()

    def subscribe(
        self, event_type: str, handler: Callable[[EventPayload], None]
    ) -> None:
        """Register *handler* to be called whenever *event_type* is emitted.

        Duplicate subscriptions of the same handler are silently ignored.
        """
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            if handler not in self._subscribers[event_type]:
                self._subscribers[event_type].append(handler)

    def emit(self, event_type: str, data: dict[str, Any] | None = None) -> None:
        """Publish an event. Creates EventPayload automatically.

        Never raises — broken handlers are logged but do not crash the emitter.
        """
        payload = EventPayload(
            event_type=event_type,
            data=data if data is not None else {},
        )

        with self._lock:
            handlers = list(self._subscribers.get(event_type, []))

        for handler in handlers:
            try:
                handler(payload)
            except Exception:
                logger.exception(
                    "Handler %r failed for event %s", handler, event_type
                )

    def unsubscribe(
        self, event_type: str, handler: Callable[[EventPayload], None]
    ) -> None:
        """Remove *handler* from *event_type* subscribers."""
        with self._lock:
            if event_type in self._subscribers:
                try:
                    self._subscribers[event_type].remove(handler)
                except ValueError:
                    pass


# Module-level singleton — all modules import this
bus = EventBus()
