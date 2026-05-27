"""
AURA — Event Bus compatibility shim.

This module re-exports from the canonical location at aura.core.event_bus.
All new code should import from aura.core.event_bus directly.

.. deprecated::
    Import from ``aura.core.event_bus`` instead.
"""

from aura.core.event_bus import EventBus, EventPayload, EventType, bus  # noqa: F401

__all__ = ["EventBus", "EventPayload", "EventType", "bus"]
