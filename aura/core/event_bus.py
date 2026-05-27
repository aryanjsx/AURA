"""
AURA — Event Bus (Canonical Implementation).

Thread-safe publish/subscribe channel used for ALL inter-module
communication.  Plugins, executors, loggers, and the error handler
communicate through the bus rather than by direct imports.

Contract
--------
- :meth:`subscribe` registers a handler and returns ``None``.
- :meth:`unsubscribe` removes a handler by event_type + handler reference.
- :meth:`emit` never raises — a broken subscriber cannot take down the
  bus or the publisher.  Errors inside subscribers are re-emitted on
  the reserved ``"bus.subscriber_error"`` channel so the error handler
  can log them.
- A wildcard subscription on ``"*"`` receives every event.

A process-wide singleton is exposed through :func:`get_event_bus`.
"""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable

logger = logging.getLogger("aura.event_bus")

Handler = Callable[[Any], None]


class EventType(str, Enum):
    """Every event the AURA pipeline can emit or subscribe to."""

    WAKE_WORD_DETECTED = "WAKE_WORD_DETECTED"
    WAKE_WORD_ERROR = "WAKE_WORD_ERROR"
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

    def __getitem__(self, key: str) -> Any:
        if key == "event":
            return self.event_type
        elif key == "payload":
            return self.data
        elif key == "timestamp":
            return self.timestamp
        raise KeyError(key)

    def __contains__(self, key: str) -> bool:
        return key in ("event", "payload", "timestamp")

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default


class EventBus:
    """Synchronous, thread-safe publish/subscribe bus.

    Supports both handler-reference-based and wildcard subscriptions.
    """

    WILDCARD = "*"
    SUBSCRIBER_ERROR = "bus.subscriber_error"

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Handler]] = {}
        self._token_to_handler: dict[str, tuple[str, Handler]] = {}
        self._lock = threading.RLock()

    def subscribe(self, event_type: str, handler: Handler) -> str:
        """Register *handler* for *event_type*.

        Returns a unique token string.
        Duplicate subscriptions of the same handler are silently ignored.
        """
        if not isinstance(event_type, str) or not event_type:
            raise ValueError("event_type must be a non-empty string")
        if not callable(handler):
            raise TypeError("handler must be callable")
        with self._lock:
            token = f"token_{id(handler)}_{event_type}"
            handlers = self._subscribers.setdefault(event_type, [])
            if handler not in handlers:
                handlers.append(handler)
                self._token_to_handler[token] = (event_type, handler)
            else:
                for tok, (et, h) in self._token_to_handler.items():
                    if et == event_type and h == handler:
                        token = tok
                        break
            return token

    def unsubscribe(self, event_type_or_token: str, handler: Handler | None = None) -> bool | None:
        """Remove subscriber.

        Can be called with:
            - unsubscribe(event_type, handler)  (Phase 2 style)
            - unsubscribe(token)               (Phase 1 style)
        """
        with self._lock:
            if handler is None:
                token = event_type_or_token
                if token in self._token_to_handler:
                    event_type, h = self._token_to_handler.pop(token)
                    handlers = self._subscribers.get(event_type, [])
                    try:
                        handlers.remove(h)
                    except ValueError:
                        pass
                    if not handlers and event_type in self._subscribers:
                        del self._subscribers[event_type]
                    return True
                return False
            else:
                event_type = event_type_or_token
                handlers = self._subscribers.get(event_type, [])
                try:
                    handlers.remove(handler)
                except ValueError:
                    pass
                if not handlers and event_type in self._subscribers:
                    del self._subscribers[event_type]
                tokens_to_remove = [
                    tok for tok, (et, h) in self._token_to_handler.items()
                    if et == event_type and h == handler
                ]
                for tok in tokens_to_remove:
                    self._token_to_handler.pop(tok, None)
                return None

    def emit(self, event_type: str, data: dict[str, Any] | None = None) -> None:
        """Publish an event. Creates EventPayload automatically.

        Never raises — broken handlers are logged but do not crash the emitter.
        """
        if not isinstance(event_type, str) or not event_type:
            return

        payload = EventPayload(
            event_type=event_type,
            data=data if data is not None else {},
        )

        with self._lock:
            direct = list(self._subscribers.get(event_type, []))
            wildcards = list(self._subscribers.get(self.WILDCARD, []))

        for handler in (*direct, *wildcards):
            try:
                handler(payload)
            except Exception as exc:
                if event_type == self.SUBSCRIBER_ERROR:
                    continue
                logger.exception(
                    "Handler %r failed for event %s", handler, event_type
                )
                try:
                    self.emit(
                        self.SUBSCRIBER_ERROR,
                        {
                            "origin_event": event_type,
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        },
                    )
                except Exception:
                    pass

    def subscribers(self, event_type: str) -> int:
        """Return the number of active subscribers for *event_type*."""
        with self._lock:
            return len(self._subscribers.get(event_type, []))

    def clear(self) -> None:
        """Remove every subscription (primarily for tests)."""
        with self._lock:
            self._subscribers.clear()
            self._token_to_handler.clear()


# ---------------------------------------------------------------------------
# Process-wide singleton
# ---------------------------------------------------------------------------

_bus: EventBus | None = None
_bus_lock = threading.Lock()


def get_event_bus() -> EventBus:
    """Return the process-wide :class:`EventBus` singleton."""
    global _bus
    if _bus is None:
        with _bus_lock:
            if _bus is None:
                _bus = EventBus()
    return _bus


def reset_event_bus() -> None:
    """Discard the singleton (tests only)."""
    global _bus
    with _bus_lock:
        _bus = None


# Module-level convenience — all modules can import this directly
bus = get_event_bus()
