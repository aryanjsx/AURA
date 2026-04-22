"""
AURA — Event Bus (Phase 0 infrastructure).

Thread-safe publish/subscribe channel used for ALL inter-module
communication.  Plugins, executors, loggers, and the error handler
communicate through the bus rather than by direct imports.

Contract
--------
- :meth:`subscribe` returns an opaque token usable with
  :meth:`unsubscribe`; the same handler may be registered many times.
- :meth:`emit` never raises — a broken subscriber cannot take down the
  bus or the publisher.  Errors inside subscribers are re-emitted on
  the reserved ``"bus.subscriber_error"`` channel so the error handler
  can log them.
- A wildcard subscription on ``"*"`` receives every event.

An application-wide singleton is exposed through :func:`get_event_bus`.
"""

from __future__ import annotations

import threading
import uuid
from collections import defaultdict
from typing import Any, Callable

Handler = Callable[[dict[str, Any]], None]


class EventBus:
    """Synchronous, thread-safe publish/subscribe bus."""

    WILDCARD = "*"
    SUBSCRIBER_ERROR = "bus.subscriber_error"

    def __init__(self) -> None:
        self._subs: dict[str, dict[str, Handler]] = defaultdict(dict)
        self._lock = threading.RLock()

    def subscribe(self, event_type: str, handler: Handler) -> str:
        """Register *handler* for *event_type* and return an unsubscribe token."""
        if not isinstance(event_type, str) or not event_type:
            raise ValueError("event_type must be a non-empty string")
        if not callable(handler):
            raise TypeError("handler must be callable")
        token = uuid.uuid4().hex
        with self._lock:
            self._subs[event_type][token] = handler
        return token

    def unsubscribe(self, token: str) -> bool:
        """Remove the subscription identified by *token*. Returns ``True`` if found."""
        with self._lock:
            for event_type, subs in list(self._subs.items()):
                if token in subs:
                    del subs[token]
                    if not subs:
                        del self._subs[event_type]
                    return True
        return False

    def emit(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        """Publish *payload* to every subscriber of *event_type* (plus wildcards).

        Never raises.  Subscriber failures are re-emitted on
        :data:`SUBSCRIBER_ERROR`.
        """
        if not isinstance(event_type, str) or not event_type:
            return
        body: dict[str, Any] = dict(payload or {})
        envelope = {"event": event_type, "payload": body}

        with self._lock:
            direct = list(self._subs.get(event_type, {}).values())
            wildcards = list(self._subs.get(self.WILDCARD, {}).values())

        for handler in (*direct, *wildcards):
            try:
                handler(envelope)
            except Exception as exc:
                if event_type == self.SUBSCRIBER_ERROR:
                    continue
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
            return len(self._subs.get(event_type, {}))

    def clear(self) -> None:
        """Remove every subscription (primarily for tests)."""
        with self._lock:
            self._subs.clear()


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
